"""
VS02-M2 on constructed input: deal facts, per-deal values and the four partitions.

The dataset cannot show most of what M2 computes. Its rates are integers, it
holds no unvalued, unowned, overdue or undated deal, and only one of its
figures tells rounding per deal from rounding per bucket. So everything here
is built in the test: DealFacts handed to the aggregation entry point, with a
rate set loaded through the path loader (plan A25.1, "constructed").

Nothing is proved through the code it is about. An expected figure is either
a literal worked out by hand, compared as text because Decimal("0.5") equals
Decimal("0.50") and equality would hide a missing quantize, or the output of
tests/unit/vs02_support.exact_values, which works plan A9.2 and A9.3 in
fractions and uses no application code and no Decimal context.

The dataset, the fixtures and the reads against a real database are in
tests/integration/test_vs02_dataset.py; the methodology digest and its pin
are in tests/unit/test_vs02_config.py.
"""

from __future__ import annotations

import dataclasses
import itertools
from datetime import date
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_UP,
    Context,
    Decimal,
    Inexact,
    InvalidOperation,
    Rounded,
    getcontext,
    localcontext,
)
from types import SimpleNamespace

import pytest

import app.pipeline
from app.fx import default_rate_set
from app.fx.errors import FxRateMissingError
from app.intelligence import EntityRef, Scope
from app.intelligence.errors import ContractViolationError, CurrencyMismatchError
from app.intelligence.money import MoneyValue
from app.intelligence.scope import AsOfSource
from app.normalization.config import default_config
from app.persistence.repositories.canonical import ENTITY_MODELS
from app.pipeline import aggregation, facts
from app.pipeline.aggregation import (
    CONCENTRATION_TOP_N,
    CUMULATIVE_POINTS,
    PERIOD_HORIZON,
    RESERVED_KEYS,
    Amount,
    Bucket,
    CurrencyBucket,
    OwnerBucket,
    Partitions,
    PeriodBucket,
    PeriodKind,
    build_partitions,
)
from app.pipeline.errors import (
    RESERVED_KEY,
    STAGE_OUTSIDE_VOCABULARY,
    PipelineConfigError,
    PipelineDataError,
    PipelineError,
)
from app.pipeline.facts import (
    OWNER_BASIS,
    OWNER_CARRIER_FIELD,
    DealFact,
    DealNote,
    DealState,
    NoteCode,
    OwnerKind,
    deal_notes,
    deal_state,
    owner_kind,
    read_deal_facts,
    valued_deal,
)
from app.pipeline.measures import (
    SHARE_QUANTUM,
    WEIGHT_QUANTUM,
    DealValues,
    deal_values,
    total,
    weigh,
)
from app.relationships import EDGE_SPECS, Edge, EdgeBasis, EdgeType
from tests.unit.vs02_support import AS_OF, STAGES, deal, exact_values, rate_set

pytestmark = pytest.mark.unit

CLOSED_STAGES = frozenset({"won"})
#: Plan A14.1 item 7, restated.
RESERVED = ("UNASSIGNED", "UNRESOLVED", "UNLINKED", "OVERDUE", "LATER", "UNDATED", "ALL",
            "UNASSESSED")
#: Plan A8.1, restated: the nine stored values and the two resolved references.
DEAL_FACT_FIELDS = ("source_id", "stage", "is_active", "amount", "currency", "probability",
                    "expected_close_date", "owner_source_id", "customer_source_id", "owner",
                    "customer")

#: Rates that are not integers, so a figure converted per deal differs from
#: one converted per bucket. The committed rates are integers and cannot show it.
RATES = {"USD": "83.2575", "EUR": "91.123456"}

#: Decimal contexts a caller could be in: too little precision for any figure
#: here, another rounding mode, narrow exponents, and every signal trapped.
AMBIENT = [
    Context(prec=1, rounding=ROUND_UP),
    Context(prec=3, rounding=ROUND_DOWN),
    Context(prec=5, rounding=ROUND_CEILING, Emin=-3, Emax=3, traps=[]),
    Context(prec=6, rounding=ROUND_HALF_EVEN, traps=[Inexact, Rounded]),
]
AMBIENT_IDS = ["one digit, round up", "three digits, round down", "narrow exponents, no trap",
               "inexact and rounded trapped"]


@pytest.fixture
def rates(tmp_path):
    return rate_set(tmp_path, RATES)


def plain(value: object) -> object:
    """A partition, bucket or amount as nested plain values, every Decimal as its text."""
    if isinstance(value, Decimal):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: plain(getattr(value, field.name))
                for field in dataclasses.fields(value)}
    if isinstance(value, tuple):
        return [plain(item) for item in value]
    return value


def by_key(buckets):
    return {bucket.key: bucket for bucket in buckets}


def native(bucket: Bucket) -> dict[str, tuple[str, str]]:
    return {amount.currency: (str(amount.unweighted), str(amount.weighted))
            for amount in bucket.native}


def base(bucket: Bucket) -> tuple[str, str, str]:
    return (bucket.base.currency, str(bucket.base.unweighted), str(bucket.base.weighted))


def build(deals, rate_set_, *, stages=STAGES, as_of=AS_OF) -> Partitions:
    return build_partitions(deals, rate_set_, stages, as_of)


def refused(deals, rate_set_, *, stages=STAGES) -> PipelineDataError:
    with pytest.raises(PipelineDataError) as raised:
        build(deals, rate_set_, stages=stages)
    return raised.value


# ---------------------------------------------------------------------------
# The package, its constants and its value types
# ---------------------------------------------------------------------------


def test_the_package_exports_exactly_its_public_api():
    assert sorted(app.pipeline.__all__) == app.pipeline.__all__ == [
        "Amount", "Bucket", "CurrencyBucket", "DealFact", "DealNote", "DealState", "NoteCode",
        "OwnerBucket", "OwnerKind", "Partitions", "PeriodBucket", "PeriodKind",
        "PipelineConfigError", "PipelineDataError", "PipelineError", "PipelineRules",
        "build_partitions", "deal_notes", "deal_state", "default_pipeline_rules",
        "load_pipeline_rules", "owner_kind", "read_deal_facts"]
    for name in app.pipeline.__all__:
        assert getattr(app.pipeline, name) is not None


def test_no_export_hides_a_module_of_the_package():
    """M1's trap: a function re-exported under its module's name shadows the module."""
    modules = {"aggregation", "config", "errors", "facts", "measures"}

    assert modules.isdisjoint(app.pipeline.__all__)
    for name in modules:
        assert type(getattr(app.pipeline, name)).__name__ == "module"


def test_the_five_constants_of_the_package_are_the_plans():
    """Plan A9.2, A10.4, A11 and A22.3 item 2: defined once, with their final values (OD-2)."""
    assert str(WEIGHT_QUANTUM) == "0.01" and type(WEIGHT_QUANTUM) is Decimal
    assert str(SHARE_QUANTUM) == "0.0001" and type(SHARE_QUANTUM) is Decimal
    assert PERIOD_HORIZON == 12 and type(PERIOD_HORIZON) is int
    assert CONCENTRATION_TOP_N == 5 and type(CONCENTRATION_TOP_N) is int
    assert CUMULATIVE_POINTS == (1, 3, 5) and type(CUMULATIVE_POINTS) is tuple


def test_a_deal_fact_holds_exactly_its_eleven_fields_and_cannot_be_changed():
    """Plan A8.1: nine stored values and two resolved references, and no convenience field."""
    assert tuple(field.name for field in dataclasses.fields(DealFact)) == DEAL_FACT_FIELDS
    assert len(DEAL_FACT_FIELDS) == 11

    one = deal()
    with pytest.raises(dataclasses.FrozenInstanceError):
        one.amount = Decimal("1")  # type: ignore[misc]
    assert one == deal() and hash(one) == hash(deal())


@pytest.mark.parametrize("value_type", [
    DealFact, facts.ValuedDeal, DealNote, DealValues, Amount, Bucket, CurrencyBucket, OwnerBucket,
    PeriodBucket, Partitions, aggregation._Measured], ids=lambda value_type: value_type.__name__)
def test_every_value_type_of_the_package_is_immutable(value_type):
    """Plan A19 item 1: a pure function of its inputs builds nothing that can be changed later."""
    assert dataclasses.is_dataclass(value_type)
    assert value_type.__dataclass_params__.frozen


def test_a_figure_cannot_be_changed_after_it_is_stated(rates):
    values = deal_values(MoneyValue(Decimal("1.00"), "USD"), Decimal("50"), rates)
    bucket = build([deal()], rates).by_currency[0]

    for stated, name in ((values, "base_weighted"), (bucket, "deal_count"),
                         (bucket.base, "unweighted"), (bucket.native[0], "weighted"),
                         (deal_notes(deal(expected=None), CLOSED_STAGES)[0], "key"),
                         (valued_deal(deal()), "amount")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(stated, name, None)


def test_the_reserved_keys_are_the_plans_eight_and_one_namespace():
    """Plan A14.1 item 7. Every pseudo-bucket M2 emits is named from it."""
    assert sorted(RESERVED) == sorted(RESERVED_KEYS) and len(RESERVED_KEYS) == 8
    assert type(RESERVED_KEYS) is frozenset

    assert {OwnerKind.UNASSIGNED.value, OwnerKind.UNRESOLVED.value, PeriodKind.OVERDUE.value,
            PeriodKind.LATER.value, PeriodKind.UNDATED.value} <= RESERVED_KEYS
    assert [kind.value for kind in OwnerKind] == ["EMPLOYEE", "UNASSIGNED", "UNRESOLVED"]
    assert [kind.value for kind in PeriodKind] == ["OVERDUE", "MONTH", "LATER", "UNDATED"]
    assert [state.value for state in DealState] == ["OPEN_VALUED", "OPEN_UNVALUED", "CLOSED"]


def test_the_stage_vocabulary_these_tests_use_is_layer_1s():
    assert set(STAGES) == default_config().fields["deals"]["stage"].enum_values
    assert list(STAGES) == sorted(STAGES)
    assert CLOSED_STAGES <= set(STAGES)


def test_an_owner_is_known_the_way_the_frozen_edge_is():
    """Plan A10.3 item 1: a source-key join over deals.owner_source_id, restated and pinned."""
    spec = EDGE_SPECS[EdgeType.DEAL_OWNED_BY]

    assert OWNER_BASIS is spec.basis is EdgeBasis.SOURCE_KEY_JOIN
    assert OWNER_CARRIER_FIELD == spec.carrier_field == "deals.owner_source_id"


def test_the_error_classes_keep_a_refused_file_apart_from_refused_data():
    assert issubclass(PipelineDataError, PipelineError)
    assert not issubclass(PipelineConfigError, PipelineError)
    assert not issubclass(PipelineError, PipelineConfigError)


def test_a_data_error_identifies_its_deals_and_keys_ascending_and_once_each():
    """Plan A10.5 item 5."""
    error = PipelineDataError(RESERVED_KEY, source_ids=["D-2", "D-10", "D-2", "D-1"],
                              keys={"UNDATED", "ALL"})

    assert error.condition == "RESERVED_KEY" and error.entity == "deals"
    assert error.source_ids == ("D-1", "D-10", "D-2")
    assert error.keys == ("ALL", "UNDATED")
    assert str(error) == "RESERVED_KEY; keys ALL, UNDATED; deals D-1, D-10, D-2"
    assert str(PipelineDataError(STAGE_OUTSIDE_VOCABULARY, source_ids=["D-1"])) == (
        "STAGE_OUTSIDE_VOCABULARY; deals D-1")
    assert str(PipelineDataError(RESERVED_KEY, keys=["ALL"])) == "RESERVED_KEY; keys ALL"


# ---------------------------------------------------------------------------
# Classification (plan A8.2, A8.3, A10.3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("stage", "is_active", "state"), [
    ("negotiation", True, DealState.OPEN_VALUED),
    ("won", True, DealState.OPEN_VALUED),
    ("negotiation", False, DealState.CLOSED),
    ("won", False, DealState.CLOSED),
    (None, False, DealState.CLOSED),
])
def test_a_deal_is_open_by_is_active_alone_and_never_by_its_stage(stage, is_active, state):
    """MD-1: an active deal in a closed stage is open, and an inactive one in an open stage is not."""
    assert deal_state(deal(stage=stage, is_active=is_active)) is state


@pytest.mark.parametrize("missing", ["stage", "amount", "currency", "probability"])
def test_an_open_deal_missing_any_of_its_four_values_is_unvalued(missing):
    """C-14: a null stage and a null currency as much as a null amount or probability."""
    one = deal(**{missing: None})

    assert deal_state(one) is DealState.OPEN_UNVALUED
    assert valued_deal(one) is None


@pytest.mark.parametrize(("amount", "state"), [
    ("-0.01", DealState.OPEN_UNVALUED),
    ("-5000000.00", DealState.OPEN_UNVALUED),
    ("0", DealState.OPEN_VALUED),
    ("0.00", DealState.OPEN_VALUED),
    ("-0.00", DealState.OPEN_VALUED),
    ("0.01", DealState.OPEN_VALUED),
])
def test_a_negative_amount_is_unvalued_and_zero_is_not_negative(amount, state):
    assert deal_state(deal(amount=amount)) is state


def test_what_is_not_among_the_four_values_does_not_decide_whether_a_deal_is_valued():
    bare = deal(expected=None, owner=None, owner_key=None, customer=None, customer_key=None,
                probability="0")

    assert deal_state(bare) is DealState.OPEN_VALUED
    assert valued_deal(bare) is not None


def test_a_valued_deal_carries_its_fact_and_its_four_values_unchanged():
    one = deal(stage="qualification", amount="12.5", currency="USD", probability="33.3")
    valued = valued_deal(one)

    assert valued is not None and valued.fact is one
    assert (valued.stage, str(valued.amount), valued.currency, str(valued.probability)) == (
        "qualification", "12.5", "USD", "33.3")
    assert valued_deal(deal(is_active=False)) is None


@pytest.mark.parametrize("amount", ["NaN", "-NaN", "sNaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("ambient", [Context(prec=28, traps=[InvalidOperation]),
                                     Context(prec=28, traps=[])],
                         ids=["invalid operation trapped", "nothing trapped"])
def test_an_amount_that_is_not_a_number_is_refused_by_the_frozen_type_in_any_context(
        rates, amount, ambient):
    """
    Comparing a NaN signals or not according to the context in force, so
    nothing compares one: it is classified without a context, reaches stage
    1, and the frozen MoneyValue refuses it (plan A10.5 item 3).
    """
    one = deal(amount=Decimal(amount))

    with localcontext(ambient):
        assert deal_state(one) is DealState.OPEN_VALUED
        with pytest.raises(ContractViolationError, match="must be finite"):
            build([one], rates)


@pytest.mark.parametrize(("owner", "owner_key", "kind"), [
    ("EMP-1", "EMP-1", OwnerKind.EMPLOYEE),
    (None, None, OwnerKind.UNASSIGNED),
    (None, "EMP-404", OwnerKind.UNRESOLVED),
    (None, "", OwnerKind.UNRESOLVED),
])
def test_an_owner_is_an_employee_or_unassigned_or_unresolved(owner, owner_key, kind):
    """MD-7: no key at all and a key that names no one are different states."""
    assert owner_kind(deal(owner=owner, owner_key=owner_key)) is kind


# ---------------------------------------------------------------------------
# Deal-level notes (plan A13.2; C-14, C-15)
# ---------------------------------------------------------------------------


def codes(one: DealFact) -> list[str]:
    return [note.code.value for note in deal_notes(one, CLOSED_STAGES)]


def note(one: DealFact, code: NoteCode) -> DealNote:
    [found] = [note for note in deal_notes(one, CLOSED_STAGES) if note.code is code]
    return found


def test_a_deal_with_nothing_wrong_draws_no_note():
    assert deal_notes(deal(), CLOSED_STAGES) == ()
    assert deal_notes(deal(stage="won", is_active=False), CLOSED_STAGES) == ()


def test_the_note_codes_are_the_eight_deal_level_codes_of_the_plan():
    """Plan A13.2. NO_ASSESSMENT_FOR_SCOPE is the scope's, and arrives with the view at M3."""
    assert sorted(code.value for code in NoteCode) == [code.value for code in NoteCode] == [
        "CUSTOMER_KEY_MISSING", "CUSTOMER_KEY_UNRESOLVED", "EXPECTED_CLOSE_MISSING",
        "INCOMPLETE_DEAL", "NEGATIVE_AMOUNT", "OWNER_KEY_MISSING", "OWNER_KEY_UNRESOLVED",
        "STAGE_ACTIVITY_MISMATCH"]


@pytest.mark.parametrize(("nulls", "fields"), [
    (("stage",), ("stage",)),
    (("amount",), ("amount",)),
    (("currency",), ("currency",)),
    (("probability",), ("probability",)),
    (("stage", "amount"), ("amount", "stage")),
    (("probability", "currency"), ("currency", "probability")),
    (("stage", "probability", "currency", "amount"), ("amount", "currency", "probability",
                                                      "stage")),
])
def test_an_incomplete_deal_draws_one_note_naming_exactly_its_null_fields_ascending(nulls, fields):
    """C-14: one note however many fields are null, never one per field."""
    one = deal("DEAL-7", **dict.fromkeys(nulls))

    assert codes(one) == ["INCOMPLETE_DEAL"]
    assert deal_notes(one, CLOSED_STAGES) == (
        DealNote(code=NoteCode.INCOMPLETE_DEAL, entity="deals", id="DEAL-7", fields=fields,
                 key=None),)


def test_a_negative_amount_draws_its_own_note_only_when_the_four_values_are_present():
    assert deal_notes(deal("DEAL-8", amount="-1.00"), CLOSED_STAGES) == (
        DealNote(code=NoteCode.NEGATIVE_AMOUNT, entity="deals", id="DEAL-8", fields=("amount",),
                 key=None),)
    assert codes(deal(amount="-1.00", probability=None)) == ["INCOMPLETE_DEAL"]
    assert codes(deal(amount="0.00")) == []


def test_a_closed_deal_draws_no_note_about_its_values():
    """Plan A13.2: both value notes are for an open deal."""
    closed = deal(stage="won", is_active=False, amount=None, currency=None, probability=None)

    assert codes(closed) == []
    assert codes(deal(stage="won", is_active=False, amount="-5.00")) == []


@pytest.mark.parametrize(("stage", "is_active", "mismatch"), [
    ("won", True, True),
    ("negotiation", False, True),
    ("qualification", False, True),
    ("won", False, False),
    ("negotiation", True, False),
    (None, True, False),
    (None, False, False),
])
def test_a_stage_and_an_activity_that_disagree_are_noted_in_both_directions(
        stage, is_active, mismatch):
    """Fixture 6's two rows, and the rule that a null stage draws no mismatch note."""
    one = deal("DEAL-9", stage=stage, is_active=is_active)

    assert ("STAGE_ACTIVITY_MISMATCH" in codes(one)) is mismatch
    if mismatch:
        assert note(one, NoteCode.STAGE_ACTIVITY_MISMATCH) == DealNote(
            code=NoteCode.STAGE_ACTIVITY_MISMATCH, entity="deals", id="DEAL-9",
            fields=("is_active", "stage"), key=None)


def test_the_mismatch_note_is_drawn_by_any_deal_valued_or_not():
    assert codes(deal(stage="won", amount=None)) == ["INCOMPLETE_DEAL", "STAGE_ACTIVITY_MISMATCH"]
    assert codes(deal(stage="won", amount="-1")) == ["NEGATIVE_AMOUNT", "STAGE_ACTIVITY_MISMATCH"]


def test_the_closed_stages_are_the_ones_supplied_and_no_others():
    one = deal(stage="negotiation", is_active=False)

    assert [n.code.value for n in deal_notes(one, {"negotiation"})] == []
    assert [n.code.value for n in deal_notes(one, {"won", "negotiation"})] == []
    assert [n.code.value for n in deal_notes(deal(stage="won"), frozenset())] == []


def test_an_unowned_and_an_unresolved_owner_draw_different_notes():
    assert deal_notes(deal("DEAL-3", owner=None, owner_key=None), CLOSED_STAGES) == (
        DealNote(code=NoteCode.OWNER_KEY_MISSING, entity="deals", id="DEAL-3",
                 fields=("owner_source_id",), key=None),)
    assert deal_notes(deal("DEAL-4", owner=None, owner_key="EMP-404"), CLOSED_STAGES) == (
        DealNote(code=NoteCode.OWNER_KEY_UNRESOLVED, entity="deals", id="DEAL-4",
                 fields=("owner_source_id",), key="EMP-404"),)


def test_an_unlinked_deal_draws_a_missing_or_an_unresolved_customer_note():
    assert deal_notes(deal("DEAL-5", customer=None, customer_key=None), CLOSED_STAGES) == (
        DealNote(code=NoteCode.CUSTOMER_KEY_MISSING, entity="deals", id="DEAL-5",
                 fields=("customer_source_id",), key=None),)
    assert deal_notes(deal("DEAL-6", customer=None, customer_key="CUST-404"), CLOSED_STAGES) == (
        DealNote(code=NoteCode.CUSTOMER_KEY_UNRESOLVED, entity="deals", id="DEAL-6",
                 fields=("customer_source_id",), key="CUST-404"),)


def test_a_deal_with_no_expected_close_date_is_noted():
    assert deal_notes(deal("DEAL-2", expected=None), CLOSED_STAGES) == (
        DealNote(code=NoteCode.EXPECTED_CLOSE_MISSING, entity="deals", id="DEAL-2",
                 fields=("expected_close_date",), key=None),)


@pytest.mark.parametrize("changes", [
    {"amount": None}, {"amount": "-1.00"}, {"is_active": False, "stage": "won"}],
    ids=["unvalued", "negative", "closed"])
def test_owner_customer_and_close_date_notes_are_for_valued_deals_only(changes):
    """Plan A13.2 item 3: only a valued deal sits in the partitions those notes explain."""
    one = deal(owner=None, owner_key="EMP-404", customer=None, customer_key=None, expected=None,
               **changes)

    assert not {"OWNER_KEY_MISSING", "OWNER_KEY_UNRESOLVED", "CUSTOMER_KEY_MISSING",
                "CUSTOMER_KEY_UNRESOLVED", "EXPECTED_CLOSE_MISSING"} & set(codes(one))


def test_a_deal_may_draw_several_notes_ascending_by_code():
    one = deal(stage="won", owner=None, owner_key="EMP-404", customer=None, customer_key=None,
               expected=None)

    assert codes(one) == ["CUSTOMER_KEY_MISSING", "EXPECTED_CLOSE_MISSING",
                          "OWNER_KEY_UNRESOLVED", "STAGE_ACTIVITY_MISMATCH"]
    assert codes(one) == sorted(codes(one))


# ---------------------------------------------------------------------------
# The facts reader (plan A5, A8.1), with its three reads replaced
# ---------------------------------------------------------------------------


def _row(source_id: str, **changes: object) -> SimpleNamespace:
    values = {"source_id": source_id, "stage": "negotiation", "is_active": True,
              "amount": Decimal("10.00"), "currency": "INR", "probability": Decimal("50.00"),
              "expected_close_date": date(2026, 10, 1), "owner_source_id": "EMP-1",
              "customer_source_id": "CUST-1"}
    return SimpleNamespace(**{**values, **changes})


def _scope(source_system: str = "csv_demo") -> Scope:
    return Scope(source_system=source_system, as_of=AS_OF, layer1_fingerprint="0" * 64,
                 as_of_source=AsOfSource.EXPLICIT, entity_counts=dict.fromkeys(ENTITY_MODELS, 0))


def _owned(deal_id: str, employee: str) -> Edge:
    return Edge(EdgeType.DEAL_OWNED_BY, EntityRef("deals", deal_id),
                EntityRef("employees", employee), EdgeBasis.SOURCE_KEY_JOIN,
                "deals.owner_source_id", "csv_demo")


def _has(customer: str, deal_id: str) -> Edge:
    return Edge(EdgeType.CUSTOMER_HAS_DEAL, EntityRef("customers", customer),
                EntityRef("deals", deal_id), EdgeBasis.CANONICAL_FK, "deals.customer_id",
                "csv_demo")


def test_the_reader_makes_three_reads_and_resolves_each_deal_through_its_own_edges(monkeypatch):
    """
    Plan A5, A21.1: deal_rows, and edges_of_type with two edge types. The
    owner is the target of the deal's own edge and the customer the source
    of its own: neither is taken from the key the row carries.
    """
    calls = []
    session, scope = object(), _scope("some_system")

    def rows(given_session, source_system):
        calls.append(("deal_rows", given_session, source_system))
        return [_row("DEAL-B", owner_source_id="EMP-9", customer_source_id="CUST-9",
                     stage=None, amount=None, currency=None, probability=None,
                     expected_close_date=None, is_active=False),
                _row("DEAL-a"), _row("DEAL-A", owner_source_id=None, customer_source_id=None)]

    def edges(edge_type, given_session, given_scope, **narrowing):
        calls.append((edge_type, given_session, given_scope, narrowing))
        if edge_type is EdgeType.DEAL_OWNED_BY:
            return (_owned("DEAL-a", "EMP-1"),)
        return (_has("CUST-2", "DEAL-a"), _has("CUST-7", "DEAL-A"))

    monkeypatch.setattr(facts, "deal_rows", rows)
    monkeypatch.setattr(facts, "edges_of_type", edges)

    read = read_deal_facts(session, scope)

    assert sorted(calls, key=str) == sorted([
        ("deal_rows", session, "some_system"),
        (EdgeType.DEAL_OWNED_BY, session, scope, {}),
        (EdgeType.CUSTOMER_HAS_DEAL, session, scope, {})], key=str)
    assert read == (
        DealFact("DEAL-A", "negotiation", True, Decimal("10.00"), "INR", Decimal("50.00"),
                 date(2026, 10, 1), None, None, None, "CUST-7"),
        DealFact("DEAL-B", None, False, None, None, None, None, "EMP-9", "CUST-9", None, None),
        DealFact("DEAL-a", "negotiation", True, Decimal("10.00"), "INR", Decimal("50.00"),
                 date(2026, 10, 1), "EMP-1", "CUST-1", "EMP-1", "CUST-2"),
    )
    assert type(read) is tuple


def test_the_reader_orders_its_facts_itself_by_code_point(monkeypatch):
    """Plan A14.1 item 6: not the order the rows arrived in, and not a locale's order."""
    ids = ["deal-2", "DEAL-10", "Deal-1", "DEAL-2", "DEAL-é", "DEAL-z", "DEAL-1"]
    monkeypatch.setattr(facts, "deal_rows", lambda session, source_system: [
        _row(source_id) for source_id in ids])
    monkeypatch.setattr(facts, "edges_of_type", lambda *args, **kwargs: ())

    read = [fact.source_id for fact in read_deal_facts(object(), _scope())]

    assert read == ["DEAL-1", "DEAL-10", "DEAL-2", "DEAL-z", "DEAL-é", "Deal-1", "deal-2"]
    assert read == sorted(ids) and read != sorted(ids, key=str.casefold)


def test_the_reader_returns_nothing_for_a_source_system_with_no_deal(monkeypatch):
    monkeypatch.setattr(facts, "deal_rows", lambda session, source_system: [])
    monkeypatch.setattr(facts, "edges_of_type", lambda *args, **kwargs: ())

    assert read_deal_facts(object(), _scope()) == ()


# ---------------------------------------------------------------------------
# Per-deal values (plan A9.2, A9.3; C-7, C-8; named test 22)
# ---------------------------------------------------------------------------


def values_text(values: DealValues) -> tuple[str, str, str, str]:
    return (str(values.native_unweighted), str(values.native_weighted),
            str(values.base_unweighted), str(values.base_weighted))


@pytest.mark.parametrize(("amount", "probability", "weighted"), [
    ("1000.00", "50.00", "500.00"),
    ("333.33", "33.33", "111.10"),
    ("5000000.05", "0.01", "500.00"),
    ("19.99", "99.99", "19.99"),
    ("100", "100", "100.00"),
    ("100", "0", "0.00"),
    ("0", "75.5", "0.00"),
    ("0.01", "49.99", "0.00"),
    ("0.01", "50.01", "0.01"),
])
def test_a_weighted_amount_is_amount_times_probability_over_100_to_the_cent(
        amount, probability, weighted):
    """Plan A9.2, against values worked out by hand. Always two decimal places."""
    result = weigh(MoneyValue(Decimal(amount), "USD"), Decimal(probability))

    assert type(result) is MoneyValue and result.currency == "USD"
    assert str(result.amount) == weighted
    assert result.amount == exact_values(amount, probability, "1")[1]


@pytest.mark.parametrize(("amount", "weighted", "direction"), [
    ("0.25", "0.12", "down to the even cent below"),
    ("0.75", "0.38", "up to the even cent above"),
    ("0.05", "0.02", "down to the even cent below"),
    ("0.07", "0.04", "up to the even cent above"),
    ("0.01", "0.00", "down to the even cent below"),
    ("0.03", "0.02", "up to the even cent above"),
])
def test_a_weight_that_is_an_exact_half_cent_rounds_to_the_even_cent(amount, weighted, direction):
    """C-7: half-even, shown in both directions. Half-up would give 0.13, and half-down 0.37."""
    assert str(weigh(MoneyValue(Decimal(amount), "INR"), Decimal("50")).amount) == weighted, (
        direction)


def test_the_four_values_of_a_deal_are_the_plans(rates):
    """Plan A9.2 and A9.3, by hand: 333.33 USD at 33.33% and 83.2575."""
    values = deal_values(MoneyValue(Decimal("333.33"), "USD"), Decimal("33.33"), rates)

    assert values_text(values) == ("USD 333.33", "USD 111.10", "INR 27752.22", "INR 9249.91")
    assert [type(getattr(values, field.name)) for field in dataclasses.fields(values)] == (
        [MoneyValue] * 4)


def test_the_unweighted_native_value_is_the_amount_as_stored(rates):
    """Plan A9.2: not re-quantized, so an amount Layer 1 stored is stated as it was stored."""
    amount = MoneyValue(Decimal("12.5"), "USD")
    values = deal_values(amount, Decimal("10"), rates)

    assert values.native_unweighted is amount and str(values.native_unweighted.amount) == "12.5"
    assert str(values.native_weighted.amount) == "1.25"


def test_the_weighted_base_value_converts_the_already_rounded_weight(tmp_path):
    """
    C-8, plan A9.3: 0.25 at 50% is 0.125, which rounds to 0.12. At a rate of
    1.5 the rounded weight converts to 0.18; the unrounded one would give
    0.1875, which is 0.19.
    """
    values = deal_values(MoneyValue(Decimal("0.25"), "USD"), Decimal("50"),
                         rate_set(tmp_path, {"USD": "1.5"}))

    assert values_text(values) == ("USD 0.25", "USD 0.12", "INR 0.38", "INR 0.18")


def test_a_base_currency_deal_converts_at_exactly_one(rates):
    values = deal_values(MoneyValue(Decimal("1000.5"), "INR"), Decimal("50"), rates)

    assert values_text(values) == ("INR 1000.5", "INR 500.25", "INR 1000.50", "INR 500.25")


@pytest.mark.parametrize(("amount", "probability", "currency"), [
    ("1000.00", "50.00", "INR"), ("333.33", "33.33", "USD"), ("0.25", "50.00", "USD"),
    ("777.77", "12.50", "EUR"), ("19.99", "99.99", "EUR"), ("5000000.05", "0.01", "INR"),
    ("0.75", "50.00", "USD"), ("9999999999999.99", "100.00", "EUR"), ("0.01", "0.01", "USD"),
])
def test_the_four_values_agree_with_exact_arithmetic_that_uses_no_application_code(
        rates, amount, probability, currency):
    rate = {"INR": "1", **RATES}[currency]
    values = deal_values(MoneyValue(Decimal(amount), currency), Decimal(probability), rates)

    assert (str(values.native_unweighted.amount), str(values.native_weighted.amount),
            str(values.base_unweighted.amount), str(values.base_weighted.amount)) == tuple(
        str(value) for value in exact_values(amount, probability, rate))


#: Named test 22. The largest amount Numeric(15, 2) holds, at 99.99%, and a
#: rate of 10 integer digits and 8 decimal places.
LARGEST_AMOUNT = "9999999999999.99"
SENSITIVE_RATE = "9999999979.49999999"
#: Worked by hand, in integers. 99.99% of the amount is 9998999999999.990001,
#: which is 9998999999999.99. The amount times the rate is
#: 99999999794999899900000.2050000001, which is ...00.21: a 28-digit context
#: keeps 99999999794999899900000.20500, a tie, and rounds it to ...00.20.
EXACT_BASE_UNWEIGHTED = "99999999794999899900000.21"
EXACT_BASE_WEIGHTED = "99989999795020399900010.21"


def test_the_largest_amount_weights_and_converts_to_the_exact_value(tmp_path):
    """Named test 22: every digit is kept, at the bound of what Layer 1 and a rate can hold."""
    values = deal_values(MoneyValue(Decimal(LARGEST_AMOUNT), "USD"), Decimal("99.99"),
                         rate_set(tmp_path, {"USD": SENSITIVE_RATE}))

    assert values_text(values) == (
        f"USD {LARGEST_AMOUNT}", "USD 9998999999999.99",
        f"INR {EXACT_BASE_UNWEIGHTED}", f"INR {EXACT_BASE_WEIGHTED}")


def test_the_exact_values_of_test_22_are_derived_without_any_vs02_code():
    """In integers: cents times a rate in hundred-millionths, rounded half-even by hand."""
    cents, rate, scale = 999999999999999, 999999997949999999, 10 ** 8

    weighted_cents, remainder = divmod(cents * 9999, 10000)
    assert remainder * 2 < 10000, "below half, so the weight rounds down"
    assert weighted_cents == 999899999999999

    for native_cents, expected in ((cents, EXACT_BASE_UNWEIGHTED),
                                   (weighted_cents, EXACT_BASE_WEIGHTED)):
        base_cents, remainder = divmod(native_cents * rate, scale)
        assert remainder * 2 > scale, "above half, so the base figure rounds up"
        assert f"{(base_cents + 1) // 100}.{(base_cents + 1) % 100:02d}" == expected

    assert exact_values(LARGEST_AMOUNT, "99.99", SENSITIVE_RATE) == (
        Decimal(LARGEST_AMOUNT), Decimal("9998999999999.99"), Decimal(EXACT_BASE_UNWEIGHTED),
        Decimal(EXACT_BASE_WEIGHTED))


def _in_28_digits(amount: str, probability: str, rate: str) -> tuple[str, str]:
    """The same weighting and conversion with the standard library alone, in 28 digits."""
    cent = Decimal("0.01")
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        weighted = (Decimal(amount) * Decimal(probability) / Decimal(100)).quantize(
            cent, rounding=ROUND_HALF_EVEN)
        return (str((Decimal(amount) * Decimal(rate)).quantize(cent, rounding=ROUND_HALF_EVEN)),
                str((weighted * Decimal(rate)).quantize(cent, rounding=ROUND_HALF_EVEN)))


def test_the_fixture_of_test_22_is_precision_sensitive_and_the_largest_rate_is_not():
    """
    Named test 22's own control. In a 28-digit context the same arithmetic
    is off by 0.01 on both base figures, so this fixture can detect a lost
    context. The largest rate there is cannot: it gives the exact value at
    28 digits too, and a test built on it would pass with no context at all.
    """
    lost = _in_28_digits(LARGEST_AMOUNT, "99.99", SENSITIVE_RATE)

    assert lost == ("99999999794999899900000.20", "99989999795020399900010.20")
    assert Decimal(EXACT_BASE_UNWEIGHTED) - Decimal(lost[0]) == Decimal("0.01")
    assert Decimal(EXACT_BASE_WEIGHTED) - Decimal(lost[1]) == Decimal("0.01")

    largest = "9999999999.99999999"
    assert _in_28_digits(LARGEST_AMOUNT, "99.99", largest) == tuple(
        str(value) for value in exact_values(LARGEST_AMOUNT, "99.99", largest)[2:])


@pytest.mark.parametrize("ambient", AMBIENT, ids=AMBIENT_IDS)
def test_the_callers_decimal_context_cannot_change_a_value_or_be_changed(tmp_path, ambient):
    """Plan A9.1: the explicit context governs multiplication, division and rounding."""
    rate_set_ = rate_set(tmp_path, {"USD": SENSITIVE_RATE})
    before = (ambient.prec, ambient.rounding, dict(ambient.flags))

    with localcontext(ambient) as current:
        values = deal_values(MoneyValue(Decimal(LARGEST_AMOUNT), "USD"), Decimal("99.99"),
                             rate_set_)
        after = (current.prec, current.rounding, dict(current.flags))

    assert values_text(values)[1:] == ("USD 9998999999999.99", f"INR {EXACT_BASE_UNWEIGHTED}",
                                       f"INR {EXACT_BASE_WEIGHTED}")
    assert after == before


def test_the_measures_leave_the_default_context_as_they_found_it(rates):
    before = (getcontext().prec, getcontext().rounding)

    deal_values(MoneyValue(Decimal("1.00"), "USD"), Decimal("50"), rates)
    total("INR", [MoneyValue(Decimal("1.00"), "INR")])

    assert (getcontext().prec, getcontext().rounding) == before


def test_a_currency_without_a_rate_raises_converts_own_error_from_the_measures(rates):
    """Plan A7.5 item 3: no default rate. The error is not caught and not translated."""
    with pytest.raises(FxRateMissingError) as raised:
        deal_values(MoneyValue(Decimal("1.00"), "GBP"), Decimal("50"), rates)

    assert raised.value.currencies == ("GBP",)
    assert raised.value.rate_set_version == "constructed"


def test_the_measures_use_the_rate_set_they_are_given_and_load_none(tmp_path, monkeypatch):
    """Plan A22.5 seam 1: the pure modules receive the rate set and never load it."""
    def refuse():
        raise AssertionError("a pure module loaded the default rate set")

    monkeypatch.setattr("app.fx.rates.default_rate_set", refuse)
    monkeypatch.setattr("app.fx.default_rate_set", refuse)
    doubled = rate_set(tmp_path, {"USD": "2"}, version="doubled")

    assert str(deal_values(MoneyValue(Decimal("3.00"), "USD"), Decimal("100"),
                           doubled).base_unweighted) == "INR 6.00"
    assert base(build([deal(currency="USD", amount="3.00")], doubled).by_currency[0]) == (
        "INR", "6.00", "3.00")


# ---------------------------------------------------------------------------
# Sums (plan A7.5 item 5, A9.1 item 4; named test 7)
# ---------------------------------------------------------------------------


def test_a_total_is_the_sum_of_its_values_in_the_named_currency():
    summed = total("USD", [MoneyValue(Decimal("0.10"), "USD"), MoneyValue(Decimal("0.20"), "USD"),
                           MoneyValue(Decimal("1000000.05"), "USD")])

    assert type(summed) is MoneyValue and str(summed) == "USD 1000000.35"
    assert str(total("USD", [])) == "USD 0"
    assert str(total("USD", iter([MoneyValue(Decimal("2.50"), "USD")]))) == "USD 2.50"


def test_money_value_still_raises_across_currencies_and_so_does_a_total():
    """Named test 7: MoneyValue is unchanged, and nothing here catches its refusal."""
    rupees, dollars = MoneyValue(Decimal("1.00"), "INR"), MoneyValue(Decimal("1.00"), "USD")

    with pytest.raises(CurrencyMismatchError):
        rupees + dollars
    with pytest.raises(CurrencyMismatchError):
        total("INR", [rupees, dollars])
    with pytest.raises(CurrencyMismatchError):
        total("EUR", [rupees])
    with pytest.raises(TypeError):
        sum([rupees, rupees])


@pytest.mark.parametrize("ambient", AMBIENT, ids=AMBIENT_IDS)
def test_a_total_is_exact_whatever_decimal_context_the_caller_is_in(ambient):
    """Plan A9.1 item 4: addition is inside the explicit context too."""
    values = [MoneyValue(Decimal("99999999794999899900000.21"), "INR"),
              MoneyValue(Decimal("0.07"), "INR"), MoneyValue(Decimal("1234567.89"), "INR")]

    with localcontext(ambient):
        summed = total("INR", values)

    assert str(summed.amount) == "99999999794999901134568.17"


def test_no_path_sums_two_currencies(rates, monkeypatch):
    """
    Named test 7: every sum VS-02 takes names one currency and is handed
    amounts in that currency alone. Each native figure is summed in its own
    currency, and each base figure only after conversion.
    """
    summed = []
    frozen_total = MoneyValue.total.__func__

    def spy(cls, currency, values):
        values = list(values)
        summed.append((currency, {value.currency for value in values}))
        return frozen_total(cls, currency, values)

    monkeypatch.setattr(MoneyValue, "total", classmethod(spy))

    build(PORTFOLIO, rates)

    assert summed, "the spy saw no sum"
    assert all(held <= {currency} for currency, held in summed)
    assert {currency for currency, _ in summed} == {"EUR", "INR", "USD"}


# ---------------------------------------------------------------------------
# A constructed portfolio: three currencies, rates that are not integers, and
# a deal in every kind of bucket (C-5)
# ---------------------------------------------------------------------------

#: (id, stage, amount, currency, probability, expected close, owner, owner key).
_ROWS = [
    ("D-01", "negotiation", "1000.00", "INR", "50.00", date(2026, 9, 1), "EMP-A", "EMP-A"),
    ("D-02", "qualification", "333.33", "USD", "33.33", date(2026, 9, 18), "EMP-A", "EMP-A"),
    ("D-03", "qualification", "0.25", "USD", "50.00", date(2027, 8, 31), None, None),
    ("D-04", "negotiation", "777.77", "EUR", "12.50", date(2027, 9, 1), None, "EMP-GONE"),
    ("D-05", "won", "19.99", "EUR", "99.99", None, "EMP-B", "EMP-B"),
    ("D-06", "negotiation", "5000000.05", "INR", "0.01", date(2026, 12, 31), None, "EMP-AWAY"),
    ("D-07", "qualification", "0.75", "USD", "50.00", date(2026, 9, 17), None, "EMP-GONE"),
]
PORTFOLIO = [
    *(deal(source_id, stage=stage, amount=amount, currency=currency, probability=probability,
           expected=expected, owner=owner, owner_key=owner_key)
      for source_id, stage, amount, currency, probability, expected, owner, owner_key in _ROWS),
    # Neither sits in any bucket: a closed deal, and an open one that cannot be valued.
    deal("D-08", stage="won", is_active=False, amount="900000.00", currency="USD"),
    deal("D-09", amount=None, currency="EUR"),
    deal("D-10", amount="-25.00", currency="USD"),
]
VALUED_IDS = [row[0] for row in _ROWS]
#: The four per-deal values of every valued deal, from the oracle.
EXACT = {row[0]: (row[3], exact_values(row[2], row[4], {"INR": "1", **RATES}[row[3]]))
         for row in _ROWS}


def exact_sums(ids) -> tuple[dict[str, tuple[str, str]], tuple[str, str]]:
    """What a bucket over these deals must state: the per-deal values, summed as integers of cents."""
    def text(cents: int) -> str:
        return f"{cents // 100}.{cents % 100:02d}"

    def cents(value: Decimal) -> int:
        return int(value.scaleb(2))

    native_cents: dict[str, list[int]] = {}
    base_cents = [0, 0]
    for source_id in ids:
        currency, (unweighted, weighted, base_unweighted, base_weighted) = EXACT[source_id]
        held = native_cents.setdefault(currency, [0, 0])
        held[0] += cents(unweighted)
        held[1] += cents(weighted)
        base_cents[0] += cents(base_unweighted)
        base_cents[1] += cents(base_weighted)
    return ({currency: (text(one), text(two)) for currency, (one, two) in native_cents.items()},
            (text(base_cents[0]), text(base_cents[1])))


def assert_bucket(bucket: Bucket, ids) -> None:
    """A bucket holds exactly these deals and states the exact sums of their own values."""
    ids = sorted(ids)
    expected_native, expected_base = exact_sums(ids)

    assert bucket.deal_ids == tuple(ids) and bucket.deal_count == len(ids)
    if ids:
        assert native(bucket) == expected_native
        assert base(bucket) == ("INR", *expected_base)
    else:
        assert bucket.native == ()
        assert base(bucket) == ("INR", "0", "0")
    assert [amount.currency for amount in bucket.native] == sorted(expected_native)


def test_the_oracle_gives_the_hand_worked_values_of_the_portfolio():
    """The per-deal values, by hand, so the oracle is itself checked against something."""
    assert {source_id: tuple(str(value) for value in values)
            for source_id, (_, values) in EXACT.items()} == {
        "D-01": ("1000.00", "500.00", "1000.00", "500.00"),
        "D-02": ("333.33", "111.10", "27752.22", "9249.91"),
        "D-03": ("0.25", "0.12", "20.81", "9.99"),
        "D-04": ("777.77", "97.22", "70873.09", "8859.02"),
        "D-05": ("19.99", "19.99", "1821.56", "1821.56"),
        "D-06": ("5000000.05", "500.00", "5000000.05", "500.00"),
        "D-07": ("0.75", "0.38", "62.44", "31.64"),
    }
    assert exact_sums(VALUED_IDS) == (
        {"INR": ("5001000.05", "1000.00"), "USD": ("334.33", "111.60"),
         "EUR": ("797.76", "117.21")},
        ("5101530.17", "20972.12"))


def test_the_portfolio_by_currency(rates):
    """C-5, C-1's shape: one bucket per currency held, ascending, each with the rate applied."""
    buckets = build(PORTFOLIO, rates).by_currency

    assert [bucket.key for bucket in buckets] == ["EUR", "INR", "USD"]
    assert all(type(bucket) is CurrencyBucket for bucket in buckets)
    assert [str(bucket.rate_to_base) for bucket in buckets] == ["91.123456", "1", "83.2575"]
    assert_bucket(buckets[0], ["D-04", "D-05"])
    assert_bucket(buckets[1], ["D-01", "D-06"])
    assert_bucket(buckets[2], ["D-02", "D-03", "D-07"])
    assert [list(native(bucket)) for bucket in buckets] == [["EUR"], ["INR"], ["USD"]]
    assert plain(buckets[2]) == {
        "key": "USD", "deal_count": 3, "deal_ids": ["D-02", "D-03", "D-07"],
        "native": [{"currency": "USD", "unweighted": "334.33", "weighted": "111.60"}],
        "base": {"currency": "INR", "unweighted": "27835.47", "weighted": "9291.54"},
        "rate_to_base": "83.2575"}


def test_the_portfolio_by_stage(rates):
    """C-5: one plain bucket per stage of the vocabulary. An active deal in `won` is counted there."""
    buckets = build(PORTFOLIO, rates).by_stage

    assert [bucket.key for bucket in buckets] == ["negotiation", "qualification", "won"]
    assert all(type(bucket) is Bucket for bucket in buckets)
    assert_bucket(buckets[0], ["D-01", "D-04", "D-06"])
    assert_bucket(buckets[1], ["D-02", "D-03", "D-07"])
    assert_bucket(buckets[2], ["D-05"])


def test_the_portfolio_by_owner(rates):
    """C-5, MD-7: employees ascending, then UNASSIGNED, then UNRESOLVED, which never collapse."""
    buckets = build(PORTFOLIO, rates).by_owner

    assert [(bucket.key, bucket.kind) for bucket in buckets] == [
        ("EMP-A", OwnerKind.EMPLOYEE), ("EMP-B", OwnerKind.EMPLOYEE),
        ("UNASSIGNED", OwnerKind.UNASSIGNED), ("UNRESOLVED", OwnerKind.UNRESOLVED)]
    assert all(type(bucket) is OwnerBucket for bucket in buckets)
    assert_bucket(buckets[0], ["D-01", "D-02"])
    assert_bucket(buckets[1], ["D-05"])
    assert_bucket(buckets[2], ["D-03"])
    assert_bucket(buckets[3], ["D-04", "D-06", "D-07"])
    assert [(bucket.basis, bucket.carrier_field) for bucket in buckets] == [
        (EdgeBasis.SOURCE_KEY_JOIN, "deals.owner_source_id"),
        (EdgeBasis.SOURCE_KEY_JOIN, "deals.owner_source_id"), (None, None), (None, None)]
    assert [bucket.unresolved_keys for bucket in buckets] == [
        (), (), (), ("EMP-AWAY", "EMP-GONE")]


def test_the_portfolio_by_expected_close(rates):
    """C-5, MD-6: a deal in each kind of period, and the as_of month split at as_of itself."""
    buckets = build(PORTFOLIO, rates).by_expected_close
    held = {bucket.key: list(bucket.deal_ids) for bucket in buckets if bucket.deal_count}

    assert held == {"OVERDUE": ["D-01", "D-07"], "2026-09": ["D-02"], "2026-12": ["D-06"],
                    "2027-08": ["D-03"], "LATER": ["D-04"], "UNDATED": ["D-05"]}
    assert all(type(bucket) is PeriodBucket for bucket in buckets)
    for bucket in buckets:
        assert_bucket(bucket, held.get(bucket.key, []))


@pytest.mark.parametrize("partition", ["by_currency", "by_stage", "by_owner", "by_expected_close"])
def test_every_partition_of_the_portfolio_reconciles_exactly_to_the_open_pipeline(
        rates, partition):
    """
    C-5, plan A9.4: for each partition separately, the buckets hold every
    open valued deal exactly once and no other, and sum with no tolerance to
    the sums of the per-deal values, per currency natively and in the base.
    """
    buckets = getattr(build(PORTFOLIO, rates), partition)
    expected_native, expected_base = exact_sums(VALUED_IDS)

    assert sum(bucket.deal_count for bucket in buckets) == len(VALUED_IDS) == 7
    assert sorted(itertools.chain.from_iterable(bucket.deal_ids for bucket in buckets)) == (
        VALUED_IDS)
    for currency, (unweighted, weighted) in expected_native.items():
        held = [amount for bucket in buckets for amount in bucket.native
                if amount.currency == currency]
        assert str(sum((amount.unweighted for amount in held), Decimal(0))) == unweighted
        assert str(sum((amount.weighted for amount in held), Decimal(0))) == weighted
    assert {amount.currency for bucket in buckets for amount in bucket.native} == set(
        expected_native)
    assert {bucket.base.currency for bucket in buckets} == {"INR"}
    assert str(sum((bucket.base.unweighted for bucket in buckets), Decimal(0))) == expected_base[0]
    assert str(sum((bucket.base.weighted for bucket in buckets), Decimal(0))) == expected_base[1]


def test_the_base_total_is_the_sum_of_the_per_currency_base_figures(rates):
    """Plan A9.4 item 2, exactly: 70873.09 + 1821.56, 5001000.05 and 27835.47."""
    buckets = build(PORTFOLIO, rates).by_currency

    assert [base(bucket)[1:] for bucket in buckets] == [
        ("72694.65", "10680.58"), ("5001000.05", "1000.00"), ("27835.47", "9291.54")]
    assert str(sum((bucket.base.unweighted for bucket in buckets), Decimal(0))) == "5101530.17"
    assert str(sum((bucket.base.weighted for bucket in buckets), Decimal(0))) == "20972.12"


def test_a_closed_deal_and_an_unvalued_deal_sit_in_no_bucket_and_change_no_figure(rates):
    """Plan A8.3 item 1: counted elsewhere, and in no partition and no monetary figure."""
    only_valued = [one for one in PORTFOLIO if one.source_id in VALUED_IDS]

    assert build(PORTFOLIO, rates) == build(only_valued, rates)
    assert [deal_state(one) for one in PORTFOLIO[7:]] == [
        DealState.CLOSED, DealState.OPEN_UNVALUED, DealState.OPEN_UNVALUED]


# ---------------------------------------------------------------------------
# Buckets (plan A14.4; C-6, C-7, C-8, C-13)
# ---------------------------------------------------------------------------


def test_a_bucket_with_several_currencies_states_each_natively_and_one_base(rates):
    """C-6: one native Amount per currency, ascending and never summed, and one base Amount."""
    bucket = by_key(build(PORTFOLIO, rates).by_stage)["negotiation"]

    assert plain(bucket) == {
        "key": "negotiation", "deal_count": 3, "deal_ids": ["D-01", "D-04", "D-06"],
        "native": [{"currency": "EUR", "unweighted": "777.77", "weighted": "97.22"},
                   {"currency": "INR", "unweighted": "5001000.05", "weighted": "1000.00"}],
        "base": {"currency": "INR", "unweighted": "5071873.14", "weighted": "9859.02"}}
    assert all(type(amount) is Amount for amount in (*bucket.native, bucket.base))


def test_a_bucket_states_the_sum_of_the_weights_each_rounded_and_not_the_sum_rounded_once(rates):
    """
    C-7: two deals of 0.25 at 50%. Each weight is 0.125 and rounds to 0.12,
    so the bucket states 0.24. Summing first and rounding once gives 0.25.
    """
    bucket = build([deal("D-1", amount="0.25"), deal("D-2", amount="0.25")], rates).by_currency[0]

    assert native(bucket) == {"INR": ("0.50", "0.24")}
    assert base(bucket) == ("INR", "0.50", "0.24")


def test_a_bucket_states_the_sum_of_its_converted_deals_and_not_its_total_converted(tmp_path):
    """
    C-8: two deals of USD 0.33 at a rate of 1.5. Each converts to 0.495,
    which is 0.50, so the bucket states 1.00. The native total, 0.66,
    converted once is 0.99.
    """
    one_and_a_half = rate_set(tmp_path, {"USD": "1.5"})
    bucket = build([deal("D-1", amount="0.33", currency="USD", probability="100"),
                    deal("D-2", amount="0.33", currency="USD", probability="100")],
                   one_and_a_half).by_currency[0]

    assert native(bucket) == {"USD": ("0.66", "0.66")}
    assert base(bucket) == ("INR", "1.00", "1.00")
    assert str((Decimal("0.66") * Decimal("1.5")).quantize(Decimal("0.01"))) == "0.99"


def test_a_bucket_converts_each_rounded_weight_and_not_the_unrounded_one(tmp_path):
    """C-8: 0.25 at 50% and 1.5 is 0.18 per deal, as the measures give it. Twice is 0.36, not 0.38."""
    one_and_a_half = rate_set(tmp_path, {"USD": "1.5"})
    bucket = build([deal("D-1", amount="0.25", currency="USD"),
                    deal("D-2", amount="0.25", currency="USD")], one_and_a_half).by_currency[0]

    assert native(bucket) == {"USD": ("0.50", "0.24")}
    assert base(bucket) == ("INR", "0.76", "0.36")


def test_a_bucket_orders_its_own_lists_whatever_order_its_deals_arrive_in(rates):
    """
    Plan A14.1 item 6: an order is compared in the builder that produces the
    list. The builder is handed deals out of order here, which the entry
    point never does, and still states ids and currencies ascending.
    """
    members = [
        aggregation._Measured(valued, deal_values(
            MoneyValue(valued.amount, valued.currency), valued.probability, rates))
        for valued in map(valued_deal, [deal("D-3", currency="USD"), deal("D-1"),
                                        deal("D-2", currency="EUR")])]

    bucket = aggregation._bucket(Bucket, "any", members, "INR")

    assert bucket.deal_ids == ("D-1", "D-2", "D-3")
    assert [amount.currency for amount in bucket.native] == ["EUR", "INR", "USD"]
    assert bucket.deal_count == 3


EMPTY = {"deal_count": 0, "deal_ids": [], "native": [],
         "base": {"currency": "INR", "unweighted": "0", "weighted": "0"}}
MONTHS_FROM_AS_OF = ["2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03",
                     "2027-04", "2027-05", "2027-06", "2027-07", "2027-08"]


@pytest.mark.parametrize("deals", [
    [],
    [deal("D-1", is_active=False, stage="won"), deal("D-2", amount=None),
     deal("D-3", amount="-1.00"), deal("D-4", is_active=False, currency="GBP")],
], ids=["no deal", "no open valued deal"])
def test_an_empty_pipeline_states_every_always_present_bucket_empty(rates, deals):
    """C-13, plan A14.4: zeros and empty lists, never a missing bucket."""
    partitions = build(deals, rates)

    assert partitions.by_currency == ()
    assert plain(partitions.by_stage) == [
        {"key": stage, **EMPTY} for stage in ("negotiation", "qualification", "won")]
    assert plain(partitions.by_owner) == [
        {"key": "UNASSIGNED", **EMPTY, "kind": "UNASSIGNED", "basis": None,
         "carrier_field": None, "unresolved_keys": []},
        {"key": "UNRESOLVED", **EMPTY, "kind": "UNRESOLVED", "basis": None,
         "carrier_field": None, "unresolved_keys": []}]
    assert plain(partitions.by_expected_close) == [
        {"key": "OVERDUE", **EMPTY, "kind": "OVERDUE"},
        *({"key": month, **EMPTY, "kind": "MONTH"} for month in MONTHS_FROM_AS_OF),
        {"key": "LATER", **EMPTY, "kind": "LATER"},
        {"key": "UNDATED", **EMPTY, "kind": "UNDATED"}]


def test_an_empty_bucket_names_the_rate_sets_base_currency(tmp_path):
    """SD-1: the base currency is data. Another base needs no code change."""
    in_dollars = rate_set(tmp_path, {"INR": "0.012"}, base="USD", version="dollars")
    partitions = build([deal(amount="1000.00", currency="INR", probability="50")], in_dollars)

    assert {bucket.base.currency for bucket in (*partitions.by_stage, *partitions.by_owner,
                                                *partitions.by_expected_close)} == {"USD"}
    assert base(partitions.by_currency[0]) == ("USD", "12.00", "6.00")
    assert str(partitions.by_currency[0].rate_to_base) == "0.012"


def test_the_stage_buckets_are_those_of_the_vocabulary_supplied(rates):
    """Plan A22.5 seam 2: the builder is handed the vocabulary and reads none for itself."""
    partitions = build([deal(stage="lost"), deal("D-2", stage="alpha")], rates,
                       stages={"won", "lost", "alpha", "Lost"})

    assert [(bucket.key, bucket.deal_count) for bucket in partitions.by_stage] == [
        ("Lost", 0), ("alpha", 1), ("lost", 1), ("won", 0)]
    assert build([], rates, stages=()).by_stage == ()
    assert [bucket.key for bucket in build([], rates, stages=["b", "a", "b"]).by_stage] == [
        "a", "b"]


# ---------------------------------------------------------------------------
# Owners (plan A10.3; named test 14's rule)
# ---------------------------------------------------------------------------


def test_unassigned_and_unresolved_never_collapse_and_list_the_keys_that_named_no_one(rates):
    partitions = build([
        deal("D-1", owner=None, owner_key=None),
        deal("D-2", owner=None, owner_key="EMP-z"),
        deal("D-3", owner=None, owner_key="EMP-B"),
        deal("D-4", owner=None, owner_key="EMP-z"),
        deal("D-5", owner=None, owner_key="EMP-10"),
        deal("D-6", owner="EMP-B"),
    ], rates)

    assert [(bucket.key, list(bucket.deal_ids), list(bucket.unresolved_keys))
            for bucket in partitions.by_owner] == [
        ("EMP-B", ["D-6"], []),
        ("UNASSIGNED", ["D-1"], []),
        ("UNRESOLVED", ["D-2", "D-3", "D-4", "D-5"], ["EMP-10", "EMP-B", "EMP-z"])]


def test_ownership_is_not_composed_from_anything_but_the_deals_own_owner(rates):
    """Plan A10.3 item 4: a deal is grouped under its resolved owner and under nothing else."""
    partitions = build([deal("D-1", owner="EMP-2", owner_key="EMP-1", customer="EMP-9"),
                        deal("D-2", owner="EMP-2", owner_key="EMP-2")], rates)

    assert [(bucket.key, bucket.deal_ids) for bucket in partitions.by_owner[:1]] == [
        ("EMP-2", ("D-1", "D-2"))]


# ---------------------------------------------------------------------------
# Periods (plan A10.4; named test 13's rules)
# ---------------------------------------------------------------------------


def period_of(expected: date | None, as_of: date, rate_set_) -> str:
    buckets = build([deal(expected=expected)], rate_set_, as_of=as_of).by_expected_close
    [key] = [bucket.key for bucket in buckets if bucket.deal_count]
    return key


@pytest.mark.parametrize("as_of", [date(2026, 9, 18), date(2027, 1, 15), date(2025, 1, 1),
                                   date(1900, 1, 1), date(1, 1, 1), date(9999, 12, 31),
                                   date(2024, 2, 29)])
def test_there_are_always_fifteen_period_buckets_in_one_order(rates, as_of):
    """Named test 13: the size of the result does not depend on as_of or on the data."""
    for deals in ([], PORTFOLIO):
        buckets = build(deals, rates, as_of=as_of).by_expected_close

        assert len(buckets) == 15
        assert [bucket.kind for bucket in buckets] == [
            PeriodKind.OVERDUE, *[PeriodKind.MONTH] * 12, PeriodKind.LATER, PeriodKind.UNDATED]
        assert [buckets[0].key, buckets[13].key, buckets[14].key] == [
            "OVERDUE", "LATER", "UNDATED"]
        assert len({bucket.key for bucket in buckets}) == 15


@pytest.mark.parametrize(("expected", "key"), [
    (date(2026, 9, 18), "2026-09"),
    (date(2026, 9, 17), "OVERDUE"),
    (date(2026, 9, 1), "OVERDUE"),
    (date(2026, 8, 31), "OVERDUE"),
    (date(1900, 1, 1), "OVERDUE"),
    (date(2026, 9, 19), "2026-09"),
    (date(2026, 9, 30), "2026-09"),
    (date(2026, 10, 1), "2026-10"),
    (date(2026, 12, 31), "2026-12"),
    (date(2027, 1, 1), "2027-01"),
    (date(2027, 8, 1), "2027-08"),
    (date(2027, 8, 31), "2027-08"),
    (date(2027, 9, 1), "LATER"),
    (date(2027, 9, 18), "LATER"),
    (date(9999, 12, 31), "LATER"),
    (None, "UNDATED"),
])
def test_a_deal_sits_in_the_one_period_its_expected_close_date_gives_it(rates, expected, key):
    """
    Named test 13, MD-6: a deal expected on as_of itself is in its month, one
    earlier in as_of's own month is OVERDUE, the twelfth month is the last
    in the window, and a null date is UNDATED.
    """
    assert period_of(expected, date(2026, 9, 18), rates) == key


@pytest.mark.parametrize(("as_of", "months"), [
    (date(2026, 9, 18), MONTHS_FROM_AS_OF),
    (date(2026, 1, 1), [f"2026-{month:02d}" for month in range(1, 13)]),
    (date(2026, 12, 31), ["2026-12", *(f"2027-{month:02d}" for month in range(1, 12))]),
    (date(999, 11, 5), ["0999-11", "0999-12", *(f"1000-{month:02d}" for month in range(1, 11))]),
    (date(1, 1, 1), [f"0001-{month:02d}" for month in range(1, 13)]),
])
def test_the_twelve_months_start_at_as_ofs_month_and_run_chronologically(rates, as_of, months):
    """PERIOD_HORIZON is 12: as_of's month and the eleven that follow, in that order."""
    buckets = build([], rates, as_of=as_of).by_expected_close

    assert [bucket.key for bucket in buckets[1:13]] == months


def test_the_months_stay_chronological_where_that_is_not_their_keys_code_point_order(rates):
    """
    Plan A10.4 item 3: late in year 9999 the window runs into year 10000,
    written with five digits. Nothing fails, and the order is chronological:
    "10000-01" sorts before "9999-12" by code point, and comes after it here.
    """
    as_of = date(9999, 12, 31)
    buckets = build([deal(expected=as_of)], rates, as_of=as_of).by_expected_close
    months = [bucket.key for bucket in buckets[1:13]]

    assert months == ["9999-12", *(f"10000-{month:02d}" for month in range(1, 12))]
    assert months != sorted(months)
    assert [bucket.key for bucket in buckets if bucket.deal_count] == ["9999-12"]


def test_a_deal_before_the_window_is_overdue_and_one_far_after_is_later(rates):
    """The window is twelve calendar months, counted from as_of's month and not from its day."""
    assert period_of(date(2026, 9, 18), date(9999, 12, 31), rates) == "OVERDUE"
    assert period_of(date(2026, 9, 18), date(1900, 1, 1), rates) == "LATER"
    assert period_of(date(2026, 9, 18), date(2025, 9, 30), rates) == "LATER"
    assert period_of(date(2026, 9, 18), date(2025, 9, 1), rates) == "LATER"
    assert period_of(date(2026, 9, 18), date(2025, 10, 1), rates) == "2026-09"
    assert period_of(date(2026, 9, 18), date(2025, 10, 31), rates) == "2026-09"


# ---------------------------------------------------------------------------
# The explicit context governs every figure (C-9)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ambient", AMBIENT, ids=AMBIENT_IDS)
def test_every_figure_of_the_four_partitions_is_unchanged_in_any_callers_context(
        tmp_path, ambient):
    """
    C-9: a precision below what the figures need and another rounding mode,
    set before the call, change nothing. The largest amount is among the
    deals, so addition as well as multiplication would be cut short.
    """
    rate_set_ = rate_set(tmp_path, {"USD": SENSITIVE_RATE, "EUR": "91.123456"})
    deals = [*PORTFOLIO, deal("D-99", amount=LARGEST_AMOUNT, currency="USD", probability="99.99",
                              stage="qualification", owner="EMP-A")]
    expected = build(deals, rate_set_)

    with localcontext(ambient):
        found = build(deals, rate_set_)

    assert plain(found) == plain(expected)
    usd = by_key(found.by_currency)["USD"]
    assert native(usd) == {"USD": ("10000000000334.32", "9999000000111.59")}
    assert base(usd) == ("INR", "99999999798343199893146.43", "99989999796136399897722.41")
    assert str(sum((bucket.base.unweighted for bucket in found.by_owner), Decimal(0))) == (
        "99999999798343204966841.13")


def test_the_figures_of_the_context_test_are_the_oracles():
    """
    The literals above. By hand, the largest amount converts to
    99999999794999899900000.21 and the other three USD deals to
    3333299993166.73, 2499999994.87 and 7499999984.62; the portfolio's INR
    and EUR deals add 5001000.05 and 72694.65 to the base total.
    """
    largest = exact_values(LARGEST_AMOUNT, "99.99", SENSITIVE_RATE)
    others = [exact_values(amount, probability, SENSITIVE_RATE)
              for amount, probability in (("333.33", "33.33"), ("0.25", "50.00"),
                                          ("0.75", "50.00"))]

    assert [str(sum((values[index] for values in (largest, *others)), Decimal(0)))
            for index in range(4)] == [
        "10000000000334.32", "9999000000111.59", "99999999798343199893146.43",
        "99989999796136399897722.41"]


# ---------------------------------------------------------------------------
# Order (plan A14.1 item 6; C-16)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arrange", [
    lambda deals: list(reversed(deals)),
    lambda deals: deals[3:] + deals[:3],
    lambda deals: deals[1::2] + deals[0::2],
    lambda deals: iter(deals),
    lambda deals: tuple(deals),
], ids=["reversed", "rotated", "odd then even", "an iterator", "a tuple"])
def test_the_facts_in_any_order_give_an_identical_result(rates, arrange):
    """C-16, plan A10.5 item 7: no order is taken from the order the facts arrive in."""
    assert plain(build(arrange(list(PORTFOLIO)), rates)) == plain(build(PORTFOLIO, rates))


def test_every_list_is_in_code_point_order_whatever_a_locale_would_say(rates):
    """
    C-16: ids, currencies, stage keys, owner keys and unresolved keys that a
    case-insensitive or locale-aware order would arrange differently.
    """
    deals = [
        deal("deal-2", owner="emp-1", currency="USD"),
        deal("DEAL-10", owner="EMP-10", currency="EUR"),
        deal("Deal-1", owner="EMP-2", currency="INR"),
        deal("DEAL-2", owner="EMP-é"),
        deal("DEAL-é", owner=None, owner_key="é"),
        deal("DEAL-1", owner=None, owner_key="Z"),
        deal("DEAL-z", owner=None, owner_key="a"),
    ]
    for supplied in (deals, list(reversed(deals))):
        partitions = build(supplied, rates, stages=["won", "Negotiation", "negotiation", "é"])
        everything = by_key(partitions.by_stage)["negotiation"]

        assert everything.deal_ids == ("DEAL-1", "DEAL-10", "DEAL-2", "DEAL-z", "DEAL-é",
                                       "Deal-1", "deal-2")
        assert [amount.currency for amount in everything.native] == ["EUR", "INR", "USD"]
        assert [bucket.key for bucket in partitions.by_currency] == ["EUR", "INR", "USD"]
        assert [bucket.key for bucket in partitions.by_stage] == [
            "Negotiation", "negotiation", "won", "é"]
        assert [bucket.key for bucket in partitions.by_owner] == [
            "EMP-10", "EMP-2", "EMP-é", "emp-1", "UNASSIGNED", "UNRESOLVED"]
        assert partitions.by_owner[-1].unresolved_keys == ("Z", "a", "é")
        assert partitions.by_owner[-1].deal_ids == ("DEAL-1", "DEAL-z", "DEAL-é")


# ---------------------------------------------------------------------------
# A missing rate (plan A7.5; C-10)
# ---------------------------------------------------------------------------


def test_an_open_valued_deal_in_a_currency_without_a_rate_raises_and_returns_nothing(rates):
    """C-10: convert's own error, naming the currency. No default rate, and the deal is not skipped."""
    with pytest.raises(FxRateMissingError) as raised:
        build([*PORTFOLIO, deal("D-50", currency="GBP")], rates)

    assert raised.value.currencies == ("GBP",)
    assert raised.value.rate_set_version == "constructed"


@pytest.mark.parametrize("unpriced", [
    deal("D-50", currency="GBP", is_active=False, stage="won"),
    deal("D-50", currency="GBP", amount=None),
    deal("D-50", currency="GBP", probability=None),
    deal("D-50", currency="GBP", stage=None),
    deal("D-50", currency="GBP", amount="-1.00"),
], ids=["closed", "no amount", "no probability", "no stage", "negative"])
def test_a_rate_is_needed_only_for_the_currency_of_an_open_valued_deal(rates, unpriced):
    """C-10, plan A7.5 item 4: a closed or an unvalued deal in such a currency raises nothing."""
    assert build([*PORTFOLIO, unpriced], rates) == build(PORTFOLIO, rates)


def test_a_rate_set_of_the_base_alone_prices_the_base_and_nothing_else(tmp_path):
    base_only = rate_set(tmp_path, version="base-only")

    assert base(build([deal(currency="INR")], base_only).by_currency[0]) == (
        "INR", "1000.00", "500.00")
    with pytest.raises(FxRateMissingError) as raised:
        build([deal(currency="INR"), deal("D-2", currency="USD")], base_only)
    assert raised.value.currencies == ("USD",)


# ---------------------------------------------------------------------------
# Reserved keys (plan A14.1 item 7, A10.5 item 1; C-11)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reserved", RESERVED)
def test_an_employee_who_would_head_a_bucket_under_a_reserved_key_fails_closed(rates, reserved):
    """
    C-11: one namespace. UNASSIGNED and UNRESOLVED would be merged into a
    pseudo-bucket of this partition; the other six are refused as well,
    because a reserved key is reserved everywhere.
    """
    error = refused([*PORTFOLIO, deal("D-51", owner=reserved), deal("D-52", owner=reserved),
                     deal("D-50", owner="EMP-A")], rates)

    assert (error.condition, error.entity) == ("RESERVED_KEY", "deals")
    assert error.source_ids == ("D-51", "D-52")
    assert error.keys == (reserved,)


@pytest.mark.parametrize("reserved", ["UNASSIGNED", "UNRESOLVED", "ALL"])
@pytest.mark.parametrize("changes", [
    {"is_active": False, "stage": "won"}, {"amount": None}, {"amount": "-1.00"}],
    ids=["closed", "unvalued", "negative"])
def test_a_reserved_owner_id_on_a_closed_or_unvalued_deal_raises_nothing(rates, reserved, changes):
    """C-11: a source_id is a generated key only where it would be a bucket key."""
    assert build([*PORTFOLIO, deal("D-51", owner=reserved, **changes)], rates) == (
        build(PORTFOLIO, rates))


def test_an_owner_key_that_merely_spells_a_reserved_key_and_resolves_to_no_one_is_unresolved(rates):
    """Only a resolved employee heads a bucket. An unmatched key is data in unresolved_keys."""
    partitions = build([deal("D-1", owner=None, owner_key="UNASSIGNED")], rates)

    assert [(bucket.key, bucket.deal_count, bucket.unresolved_keys)
            for bucket in partitions.by_owner] == [
        ("UNASSIGNED", 0, ()), ("UNRESOLVED", 1, ("UNASSIGNED",))]


def test_all_is_a_currency_layer_1_admits():
    """OD-8: the collision is real. ALL is an ISO 4217 code of the frozen D1 vocabulary."""
    assert "ALL" in default_config().currency_codes
    assert "ALL" in RESERVED_KEYS
    assert str(MoneyValue(Decimal("1.00"), "ALL")) == "ALL 1.00"


@pytest.mark.parametrize("all_rate", [{"ALL": "0.9"}, {}], ids=["a rate for ALL", "no rate for ALL"])
def test_an_open_valued_deal_in_the_currency_all_fails_closed_whatever_the_rate_set_holds(
        tmp_path, all_rate):
    """
    C-11, OD-8, plan A10.1 item 3: the same outcome with and without an ALL
    rate, because the check comes before any conversion. Every such deal is
    identified, and no partition is returned.
    """
    rate_set_ = rate_set(tmp_path, {**RATES, **all_rate})
    error = refused([*PORTFOLIO, deal("D-61", currency="ALL"), deal("D-60", currency="ALL"),
                     deal("D-62", currency="USD")], rate_set_)

    assert (error.condition, error.entity) == ("RESERVED_KEY", "deals")
    assert error.source_ids == ("D-60", "D-61")
    assert error.keys == ("ALL",)
    assert str(error) == "RESERVED_KEY; keys ALL; deals D-60, D-61"


@pytest.mark.parametrize("all_rate", [{"ALL": "0.9"}, {}], ids=["a rate for ALL", "no rate for ALL"])
@pytest.mark.parametrize("changes", [
    {"is_active": False, "stage": "won"}, {"amount": None}, {"probability": None},
    {"amount": "-1.00"}], ids=["closed", "no amount", "no probability", "negative"])
def test_a_closed_or_unvalued_deal_in_the_currency_all_fails_nothing(tmp_path, all_rate, changes):
    """OD-8: it sits in no partition and generates no key. It is valid Layer 1 data and stays so."""
    rate_set_ = rate_set(tmp_path, {**RATES, **all_rate})

    assert build([*PORTFOLIO, deal("D-60", currency="ALL", **changes)], rate_set_) == (
        build(PORTFOLIO, rate_set_))


@pytest.mark.parametrize("reserved", RESERVED)
def test_a_stage_vocabulary_that_holds_a_reserved_key_fails_closed_and_names_the_key(
        rates, reserved):
    """C-11, plan A10.5 item 5: no deal triggers it, so it identifies the key and no deal."""
    for deals in ([], PORTFOLIO, [deal(stage=reserved)]):
        error = refused(deals, rates, stages=[*STAGES, reserved])

        assert (error.condition, error.entity) == ("RESERVED_KEY", "deals")
        assert error.keys == (reserved,)
        assert error.source_ids == ()


def test_every_reserved_key_collision_is_reported_at_once(rates):
    """Plan A10.5 item 5: every deal that triggers it, and every key, ascending and once each."""
    error = refused([deal("D-3", currency="ALL", owner="UNDATED"), deal("D-1", owner="LATER"),
                     deal("D-2", currency="ALL"), deal("D-4")],
                    rates, stages=[*STAGES, "UNLINKED"])

    assert error.source_ids == ("D-1", "D-2", "D-3")
    assert error.keys == ("ALL", "LATER", "UNDATED", "UNLINKED")


def test_a_key_that_only_resembles_a_reserved_one_is_an_ordinary_key(rates):
    """Compared exactly: no case folding and no trimming."""
    partitions = build([deal("D-1", owner="unassigned"), deal("D-2", owner="ALL "),
                        deal("D-3", owner="Unresolved")], rates, stages=[*STAGES, "later"])

    assert [bucket.key for bucket in partitions.by_owner] == [
        "ALL ", "Unresolved", "unassigned", "UNASSIGNED", "UNRESOLVED"]


def test_nothing_is_renamed_merged_or_dropped_to_avoid_a_collision(rates):
    """
    Plan A10.5 item 4: the whole calculation stops. Not even the partitions
    the offending value does not touch are returned, and nothing is computed.
    """
    with pytest.raises(PipelineDataError):
        build([deal("D-1", owner="UNASSIGNED"), deal("D-2", owner=None, owner_key=None)], rates)
    with pytest.raises(PipelineDataError):
        build([deal("D-1", currency="ALL")], rates)


# ---------------------------------------------------------------------------
# A stage outside the vocabulary (plan A10.2 item 4; C-12)
# ---------------------------------------------------------------------------


def test_an_open_valued_deal_whose_stage_is_outside_the_vocabulary_fails_closed(rates):
    """C-12, OD-3: every such deal is identified, ascending, and no partition is returned."""
    error = refused([*PORTFOLIO, deal("D-71", stage="lost"), deal("D-70", stage="prospect"),
                     deal("D-72", stage="Won"), deal("D-73", stage="")], rates)

    assert (error.condition, error.entity) == ("STAGE_OUTSIDE_VOCABULARY", "deals")
    assert error.source_ids == ("D-70", "D-71", "D-72", "D-73")
    assert error.keys == ()
    assert str(error) == "STAGE_OUTSIDE_VOCABULARY; deals D-70, D-71, D-72, D-73"


@pytest.mark.parametrize("changes", [
    {"is_active": False}, {"amount": None}, {"currency": None}, {"probability": None},
    {"amount": "-1.00"}],
    ids=["closed", "no amount", "no currency", "no probability", "negative"])
def test_a_closed_or_unvalued_deal_with_such_a_stage_is_not_checked_and_makes_no_bucket(
        rates, changes):
    """
    C-12: nothing is raised, no by_stage bucket is made for it, the
    partitions are those of the other deals, and its notes are what they
    would be for any stage.
    """
    odd = deal("D-70", stage="prospect", **changes)
    partitions = build([*PORTFOLIO, odd], rates)

    assert partitions == build(PORTFOLIO, rates)
    assert [bucket.key for bucket in partitions.by_stage] == ["negotiation", "qualification", "won"]
    assert deal_notes(odd, CLOSED_STAGES) == tuple(
        dataclasses.replace(note_, id="D-70")
        for note_ in deal_notes(deal("D-70", stage="negotiation", **changes), CLOSED_STAGES))


def test_the_vocabulary_is_the_one_supplied_and_is_never_widened_from_the_data(rates):
    """A stage is in the vocabulary only because the caller supplied it."""
    assert build([deal(stage="lost")], rates, stages=[*STAGES, "lost"]).by_stage[0].key == "lost"
    assert refused([deal(stage="lost")], rates).source_ids == ("DEAL-900",)
    assert refused([deal(stage="negotiation")], rates, stages=["won"]).condition == (
        STAGE_OUTSIDE_VOCABULARY)
    assert refused([deal()], rates, stages=()).source_ids == ("DEAL-900",)


def test_a_reserved_key_collision_is_reported_in_preference_to_a_stage_outside_the_vocabulary(
        rates):
    """Plan A10.5 item 5: when both conditions hold, on one deal or on two."""
    for deals in ([deal("D-1", stage="prospect", currency="ALL")],
                  [deal("D-1", stage="prospect"), deal("D-2", owner="UNLINKED")],
                  [deal("D-2", owner="UNLINKED"), deal("D-1", stage="prospect")]):
        assert refused(deals, rates).condition == RESERVED_KEY

    error = refused([deal("D-1", stage="prospect"), deal("D-2", owner="UNLINKED")], rates)
    assert error.source_ids == ("D-2",), "only the deals that trigger the condition reported"


# ---------------------------------------------------------------------------
# Error precedence: three stages (plan A10.5 items 3 and 6; C-19)
# ---------------------------------------------------------------------------

#: A deal whose currency has no rate in `rates`, and a deal Layer 1 could not have stored.
UNPRICED = deal("D-80", currency="GBP")
OUTSIDE_D1 = deal("D-81", currency="XXX")
INVALID = {
    "a reserved owner key": deal("D-82", owner="UNLINKED"),
    "the currency ALL": deal("D-82", currency="ALL"),
    "a stage outside the vocabulary": deal("D-82", stage="prospect"),
}


def both_orders(*deals: DealFact):
    return [list(deals), list(reversed(deals))]


@pytest.mark.parametrize("condition", sorted(INVALID))
def test_a_failed_check_wins_over_a_missing_rate_in_either_order(rates, condition):
    """
    C-19, OD-7: a data-validity condition on one deal and a currency with no
    rate on another raise the data-validity error, never FxRateMissingError,
    whichever comes first.
    """
    for deals in both_orders(INVALID[condition], UNPRICED):
        error = refused([*PORTFOLIO, *deals], rates)

        assert error.source_ids == ("D-82",)


def test_a_reserved_vocabulary_key_wins_over_a_missing_rate(rates):
    error = refused([UNPRICED], rates, stages=[*STAGES, "ALL"])

    assert (error.keys, error.source_ids) == (("ALL",), ())


def test_a_currency_outside_the_d1_vocabulary_is_refused_by_the_frozen_type_before_any_rate(rates):
    """
    C-19, plan A10.1 item 4: neither caught nor translated, and raised in
    stage 1, so it is never reported as a missing rate, in either order.
    """
    assert "XXX" not in default_config().currency_codes

    for deals in both_orders(OUTSIDE_D1, UNPRICED):
        with pytest.raises(ContractViolationError, match="'XXX' is not a configured ISO 4217 code"):
            build([*PORTFOLIO, *deals], rates)
    assert not issubclass(ContractViolationError, PipelineError)
    assert not issubclass(ContractViolationError, FxRateMissingError)


@pytest.mark.parametrize("condition", sorted(INVALID))
def test_a_failed_check_is_raised_in_preference_to_a_refusal_by_the_frozen_type(rates, condition):
    """C-19, plan A10.5 item 6: within stage 1, with the two on different deals and in either order."""
    for deals in both_orders(INVALID[condition], OUTSIDE_D1, UNPRICED):
        assert refused(deals, rates).source_ids == ("D-82",)


def test_a_missing_rate_alone_is_still_a_missing_rate(rates):
    """The precedence reorders nothing when only one condition holds."""
    with pytest.raises(FxRateMissingError):
        build([*PORTFOLIO, UNPRICED], rates)


@pytest.mark.parametrize("invalid", [*INVALID.values(), OUTSIDE_D1],
                         ids=[*INVALID, "a currency outside D1"])
def test_nothing_is_weighted_or_converted_until_every_fact_has_passed_stage_one(
        rates, monkeypatch, invalid):
    """
    Plan A10.5 item 3: a stage begins only when the one before it has
    finished for every fact. The invalid deal is the last in id order, and
    not one deal before it is measured.
    """
    measured = []
    monkeypatch.setattr(aggregation, "deal_values", lambda *args: measured.append(args))

    with pytest.raises((PipelineDataError, ContractViolationError)):
        build([*PORTFOLIO, dataclasses.replace(invalid, source_id="Z-99")], rates)

    assert measured == []


def test_every_deal_is_measured_before_any_bucket_is_summed(rates, monkeypatch):
    """Stage 2 before stage 3: a missing rate on the last deal leaves nothing summed."""
    summed = []
    monkeypatch.setattr(aggregation, "total", lambda *args: summed.append(args))

    with pytest.raises(FxRateMissingError):
        build([*PORTFOLIO, dataclasses.replace(UNPRICED, source_id="Z-99")], rates)

    assert summed == []


def test_no_error_class_was_added_for_the_precedence():
    """OD-7: PipelineDataError, ContractViolationError and FxRateMissingError are the existing ones."""
    from app.pipeline import errors

    assert sorted(name for name, value in vars(errors).items()
                  if isinstance(value, type) and issubclass(value, Exception)) == [
        "PipelineConfigError", "PipelineDataError", "PipelineError"]


# ---------------------------------------------------------------------------
# What the entry point does not do at M2
# ---------------------------------------------------------------------------


def test_the_entry_point_returns_the_four_partitions_and_nothing_more(rates):
    """OD-4 and plan B6: no count, no band, no customer partition, no concentration."""
    partitions = build(PORTFOLIO, rates)

    assert [field.name for field in dataclasses.fields(partitions)] == [
        "by_currency", "by_stage", "by_owner", "by_expected_close"]
    assert [field.name for field in dataclasses.fields(Bucket)] == [
        "key", "deal_count", "deal_ids", "native", "base"]
    assert [field.name for field in dataclasses.fields(CurrencyBucket)][5:] == ["rate_to_base"]
    assert [field.name for field in dataclasses.fields(OwnerBucket)][5:] == [
        "kind", "basis", "carrier_field", "unresolved_keys"]
    assert [field.name for field in dataclasses.fields(PeriodBucket)][5:] == ["kind"]
    assert [field.name for field in dataclasses.fields(Amount)] == [
        "currency", "unweighted", "weighted"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        partitions.by_stage = ()  # type: ignore[misc]


def test_the_entry_point_checks_one_currency_at_a_time_and_names_only_that_one(tmp_path):
    """
    OD-7, plan A10.5 item 6: M2 does not perform M3's check of every
    currency. With two currencies lacking a rate, convert's own error names
    one; which one is not part of the M2 contract, and nothing here pins it.
    """
    base_only = rate_set(tmp_path, version="base-only")

    with pytest.raises(FxRateMissingError) as raised:
        build([deal("D-1", currency="GBP"), deal("D-2", currency="USD")], base_only)

    assert len(raised.value.currencies) == 1
    assert set(raised.value.currencies) < {"GBP", "USD"}


def test_the_committed_rate_set_prices_a_constructed_deal_as_the_plan_states(rates):
    """The committed rates, USD 85 and EUR 100, through the same entry point."""
    partitions = build([deal("D-1", amount="5361.44", currency="USD", probability="90.00"),
                        deal("D-2", amount="96633.33", currency="EUR", probability="40.00")],
                       default_rate_set())

    assert [(bucket.key, str(bucket.rate_to_base), *base(bucket)[1:])
            for bucket in partitions.by_currency] == [
        ("EUR", "100", "9663333.00", "3865333.00"), ("USD", "85", "455722.40", "410150.50")]
