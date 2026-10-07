"""
VS02-M3 on constructed input: the stored bands, the arithmetic of
concentration, the two partitions M3 adds, deal_counts and the view.

"Constructed" is plan A25.2's: deal facts and band rows built in the test and
handed to the pure builders, with a rate set loaded through the path loader
and the stage vocabulary passed as an argument. Nothing here touches a
database. The dataset, the stored rows and the service are in
tests/integration/test_vs02_service.py.

Nothing is proved through the code it is about. An expected figure is either
a literal worked out by hand, compared as text so that a missing rounding
cannot hide behind numeric equality, or the output of the oracles of
tests/unit/vs02_support, which work plan A9 and A11 in fractions and integer
rounding and use no application code and no Decimal context.

The M2 partitions, and what the entry point did at M2, are in
tests/unit/test_vs02_pipeline.py and are unchanged by this file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import itertools
import json
from datetime import date
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_UP,
    Context,
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Rounded,
    localcontext,
)
from fractions import Fraction

import pytest

from app.fx.errors import FxRateMissingError
from app.intelligence import RiskBand
from app.intelligence.errors import ContractViolationError
from app.persistence.repositories.pipeline_queries import BandRow
from app.pipeline import aggregation, measures
from app.pipeline import facts as facts_module
from app.pipeline import view as view_module
from app.pipeline.aggregation import (
    NO_OPEN_EXPOSURE,
    OPEN_PIPELINE_KEY,
    RESERVED_KEYS,
    UNASSESSED,
    UNLINKED,
    BandBucket,
    Bucket,
    CustomerBucket,
    CustomerKind,
    build_partitions,
    valid_deals,
)
from app.pipeline.config import PipelineRules
from app.pipeline.errors import (
    RESERVED_KEY,
    STAGE_OUTSIDE_VOCABULARY,
    PipelineDataError,
)
from app.pipeline.facts import (
    BAND_OUTSIDE_VOCABULARY,
    CUSTOMERS,
    BandFact,
    CustomerBand,
    customer_bands,
    read_band_facts,
)
from app.pipeline.measures import cumulative_share, hhi, share
from app.pipeline.view import (
    LIMITATIONS,
    NO_ASSESSMENT_FOR_SCOPE,
    UNSTAGED,
    PipelineView,
    build_view,
    check_data,
    citations,
    deal_counts,
    limitation_texts,
    view_hash,
)
from tests.unit.vs02_support import (
    AS_OF,
    STAGES,
    band,
    deal,
    exact_concentration,
    exact_cumulative,
    exact_hhi,
    exact_share,
    exact_values,
    rate_set,
    view_scope,
)

pytestmark = pytest.mark.unit

RULES = PipelineRules(pipeline_version=1, closed_stages=frozenset({"won"}))
#: Rates that are not integers, so a figure converted per deal differs from
#: one converted per bucket (plan A25.2, "constructed").
RATES = {"USD": "83.2575", "EUR": "91.123456"}
#: Plan A14.1 item 7, restated.
RESERVED = ("UNASSIGNED", "UNRESOLVED", "UNLINKED", "OVERDUE", "LATER", "UNDATED", "ALL",
            "UNASSESSED")
#: Plan A12.3, restated: the four bands by descending rank, then the two coverage buckets.
BAND_ORDER = ["CRITICAL", "ELEVATED", "WATCH", "NONE", "UNASSESSED", "UNLINKED"]

#: Decimal contexts a caller could be in. The first is plan A25.2's hostile
#: one, row C-43: a precision of 1, a rounding mode other than half-even, and
#: Inexact and Rounded trapped. The others are M2's, from C-9.
HOSTILE = [
    lambda: Context(prec=1, rounding=ROUND_UP, traps=[Inexact, Rounded]),
    lambda: Context(prec=1, rounding=ROUND_UP),
    lambda: Context(prec=3, rounding=ROUND_DOWN),
    lambda: Context(prec=5, rounding=ROUND_CEILING, Emin=-3, Emax=3, traps=[]),
    lambda: Context(prec=6, rounding=ROUND_HALF_EVEN, traps=[Inexact, Rounded]),
]
HOSTILE_IDS = ["one digit, round up, inexact and rounded trapped", "one digit, round up",
               "three digits, round down", "narrow exponents, no trap",
               "six digits, inexact and rounded trapped"]


@pytest.fixture
def rates(tmp_path):
    return rate_set(tmp_path, RATES)


@pytest.fixture
def plain_rates(tmp_path):
    """INR only, and USD at 1.5: every figure of a test that uses it can be worked by hand."""
    return rate_set(tmp_path, {"USD": "1.5"}, version="by-hand")


def build(deals, rate_set_, *, bands=(), stages=STAGES, as_of=AS_OF):
    return build_partitions(deals, rate_set_, stages, as_of, bands)


def view_of(deals, rate_set_, *, bands=(), stages=STAGES, as_of=AS_OF,
            source_system="csv_demo"):
    return build_view(scope=view_scope(source_system, as_of), facts=deals, bands=bands,
                      rate_set=rate_set_, rules=RULES, rules_version=3, linker_version="L-2",
                      stage_vocabulary=stages)


def by_key(buckets):
    return {bucket.key: bucket for bucket in buckets}


def keyed(buckets):
    return {bucket["key"]: bucket for bucket in buckets}


def state_of(context: Context) -> tuple:
    return (context.prec, context.rounding, context.Emin, context.Emax, dict(context.traps),
            dict(context.flags))


def refused(call, *args, **kwargs) -> PipelineDataError:
    with pytest.raises(PipelineDataError) as raised:
        call(*args, **kwargs)
    return raised.value


# ---------------------------------------------------------------------------
# The data error's entity (OD-M3-2; plan A10.5 item 5)
# ---------------------------------------------------------------------------


def test_the_data_error_takes_its_entity_by_keyword_and_the_default_is_deals():
    """OD-M3-2: one keyword-only parameter, and nothing else of the class moved."""
    parameters = inspect.signature(PipelineDataError.__init__).parameters

    assert list(parameters) == ["self", "condition", "source_ids", "keys", "entity"]
    assert parameters["condition"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert {name: parameters[name].kind for name in ("source_ids", "keys", "entity")} == (
        dict.fromkeys(("source_ids", "keys", "entity"), inspect.Parameter.KEYWORD_ONLY))
    assert parameters["entity"].default == "deals"
    assert (parameters["source_ids"].default, parameters["keys"].default) == ((), ())
    with pytest.raises(TypeError):
        PipelineDataError("X", ["D-1"])  # type: ignore[misc]
    with pytest.raises(TypeError):
        PipelineDataError("X", (), (), "customers")  # type: ignore[misc]


def test_an_error_that_names_customers_identifies_them_ascending_and_once_each():
    """Plan A12.3 item 2: the entity `customers` and the source ids of customers, never deals."""
    error = PipelineDataError(BAND_OUTSIDE_VOCABULARY, entity=CUSTOMERS,
                              source_ids=["CUST-2", "CUST-10", "cust-1", "CUST-2", "CUST-1"])

    assert (error.condition, error.entity) == ("BAND_OUTSIDE_VOCABULARY", "customers")
    assert error.source_ids == ("CUST-1", "CUST-10", "CUST-2", "cust-1")
    assert error.keys == ()
    assert str(error) == "BAND_OUTSIDE_VOCABULARY; customers CUST-1, CUST-10, CUST-2, cust-1"
    assert "deals" not in str(error)


def test_every_error_m2_raised_reads_as_it_did_at_m2():
    """OD-M3-2: byte for byte, for a call site that does not pass an entity."""
    both = PipelineDataError(RESERVED_KEY, source_ids=["D-2", "D-10", "D-2", "D-1"],
                             keys={"UNDATED", "ALL"})

    assert (both.condition, both.entity) == ("RESERVED_KEY", "deals")
    assert (both.source_ids, both.keys) == (("D-1", "D-10", "D-2"), ("ALL", "UNDATED"))
    assert str(both) == "RESERVED_KEY; keys ALL, UNDATED; deals D-1, D-10, D-2"
    assert str(PipelineDataError(STAGE_OUTSIDE_VOCABULARY, source_ids=["D-1"])) == (
        "STAGE_OUTSIDE_VOCABULARY; deals D-1")
    assert str(PipelineDataError(RESERVED_KEY, keys=["ALL"])) == "RESERVED_KEY; keys ALL"
    assert str(PipelineDataError("ANY")) == "ANY"


def test_an_error_names_each_reserved_key_once_however_often_it_is_given():
    """Plan A10.5 item 1: every colliding key, ascending and once each, as the ids are."""
    error = PipelineDataError(RESERVED_KEY, source_ids=["D-2", "D-1", "D-2"],
                              keys=["UNLINKED", "ALL", "UNLINKED", "ALL"])

    assert error.keys == ("ALL", "UNLINKED")
    assert error.source_ids == ("D-1", "D-2")
    assert str(error) == "RESERVED_KEY; keys ALL, UNLINKED; deals D-1, D-2"


def test_the_unknown_band_condition_and_its_entity_are_named_once():
    assert (BAND_OUTSIDE_VOCABULARY, CUSTOMERS) == ("BAND_OUTSIDE_VOCABULARY", "customers")
    assert BAND_OUTSIDE_VOCABULARY not in {RESERVED_KEY, STAGE_OUTSIDE_VOCABULARY}


# ---------------------------------------------------------------------------
# The stored bands (plan A12.3 item 2; C-22, constructed)
# ---------------------------------------------------------------------------


def test_the_band_vocabulary_these_tests_use_is_the_frozen_one():
    assert [member.value for member in sorted(RiskBand, key=lambda one: one.rank,
                                              reverse=True)] == BAND_ORDER[:4]
    assert not {member.value for member in RiskBand} & {UNASSESSED, UNLINKED}
    assert {UNASSESSED, UNLINKED, OPEN_PIPELINE_KEY} <= RESERVED_KEYS


def test_a_band_fact_is_what_was_stored_and_decides_nothing():
    """Reading a band does not check it: an unknown one is a BandFact like any other."""
    stored = band("CUST-1", "SEVERE", True)

    assert [field.name for field in dataclasses.fields(BandFact)] == [
        "customer", "band", "executive_worthy"]
    assert (stored.customer, stored.band, stored.executive_worthy) == ("CUST-1", "SEVERE", True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        stored.band = "NONE"  # type: ignore[misc]


def test_the_band_reader_passes_the_identity_on_and_orders_its_facts_itself(monkeypatch):
    """
    Plan A12.2, A14.1 item 6: one read, at the scope's identity and the two
    versions the caller gives. The facts come back in code-point order by
    customer, which is not the order the rows arrived in and not a
    locale's. A band is handed on as stored and is not judged.
    """
    calls = []
    session, scope = object(), view_scope("some_system", date(2026, 1, 2))
    ids = ["cust-2", "CUST-10", "Cust-1", "CUST-2", "CUST-é", "CUST-z", "CUST-1"]

    def rows(given_session, **identity):
        calls.append((given_session, identity))
        return [BandRow(source_id, "SEVERE" if source_id == "CUST-z" else "WATCH",
                        source_id == "CUST-2") for source_id in ids]

    monkeypatch.setattr(facts_module, "band_rows", rows)

    read = read_band_facts(session, scope, rules_version=7, linker_version="L-3")

    assert calls == [(session, {"source_system": "some_system", "as_of": date(2026, 1, 2),
                                "layer1_fingerprint": scope.layer1_fingerprint,
                                "rules_version": 7, "linker_version": "L-3"})]
    assert type(read) is tuple and all(type(fact) is BandFact for fact in read)
    found = [fact.customer for fact in read]
    assert found == ["CUST-1", "CUST-10", "CUST-2", "CUST-z", "CUST-é", "Cust-1", "cust-2"]
    assert found == sorted(ids) and found != ids and found != sorted(ids, key=str.casefold)
    assert {fact.customer: (fact.band, fact.executive_worthy) for fact in read
            if fact.customer in {"CUST-2", "CUST-z"}} == {
        "CUST-2": ("WATCH", True), "CUST-z": ("SEVERE", False)}


def test_the_band_reader_returns_nothing_where_no_assessment_is_stored(monkeypatch):
    monkeypatch.setattr(facts_module, "band_rows", lambda session, **identity: [])

    assert read_band_facts(object(), view_scope(), rules_version=1, linker_version="1") == ()


def test_each_stored_band_becomes_a_band_of_the_frozen_vocabulary_with_its_verdict():
    assessed = customer_bands([band("C-2", "WATCH", True), band("C-1", "NONE"),
                               band("C-3", "CRITICAL", True), band("C-4", "ELEVATED")])

    assert assessed == {
        "C-1": CustomerBand(RiskBand.NONE, False), "C-2": CustomerBand(RiskBand.WATCH, True),
        "C-3": CustomerBand(RiskBand.CRITICAL, True),
        "C-4": CustomerBand(RiskBand.ELEVATED, False)}
    assert all(type(one.band) is RiskBand for one in assessed.values())
    assert customer_bands([]) == {} and customer_bands(iter(())) == {}


@pytest.mark.parametrize("stored", ["SEVERE", "", "none", "Critical", "WATCH ", "UNASSESSED",
                                    "UNLINKED", "HIGH"])
def test_a_band_outside_the_vocabulary_fails_closed_and_names_its_customer(stored):
    """
    C-22: not renamed, and compared exactly. It is given no bucket, neither
    NONE nor UNASSESSED: a stored UNASSESSED is itself outside the vocabulary.
    """
    error = refused(customer_bands, [band("C-1", "NONE"), band("C-9", stored)])

    assert (error.condition, error.entity) == ("BAND_OUTSIDE_VOCABULARY", "customers")
    assert error.source_ids == ("C-9",) and error.keys == ()
    assert str(error) == "BAND_OUTSIDE_VOCABULARY; customers C-9"


def test_several_unknown_bands_raise_once_and_name_every_customer_in_any_order():
    """C-22, C-39: ascending by code point and once each, whatever order the rows arrive in."""
    rows = [band("cust-2", "X"), band("CUST-10", "Y"), band("CUST-B", "NONE"),
            band("CUST-2", "X"), band("CUST-é", "?"), band("CUST-A", "WATCH"),
            band("CUST-10", "Z")]

    for arranged in (rows, list(reversed(rows)), rows[3:] + rows[:3], iter(rows)):
        error = refused(customer_bands, arranged)
        assert error.source_ids == ("CUST-10", "CUST-2", "CUST-é", "cust-2")
    assert error.entity == "customers" and "deals" not in str(error)


def test_an_unknown_band_fails_whoever_its_customer_is(rates):
    """
    C-22: the row of a customer holding an open valued deal, of one holding
    only closed or unvalued deals, and of one holding no deal at all. No
    partition is returned for any of them, and no deal is named.
    """
    deals = [deal("D-1", customer="C-OPEN"), deal("D-2", customer="C-SHUT", is_active=False),
             deal("D-3", customer="C-BARE", amount=None)]

    for customer in ("C-OPEN", "C-SHUT", "C-BARE", "C-NOBODY"):
        for call in (lambda rows: build(deals, rates, bands=rows),
                     lambda rows: view_of(deals, rates, bands=rows),
                     lambda rows: check_data(deals, rows, STAGES)):
            error = refused(call, [band("C-OPEN", "NONE"), band(customer, "SEVERE")]
                            if customer != "C-OPEN" else [band(customer, "SEVERE")])
            assert (error.entity, error.source_ids) == ("customers", (customer,))


def test_an_error_the_entry_point_raises_for_a_deal_still_names_deals(rates):
    """C-22, C-44: with bands supplied, a stage-1 error is what it was at M2."""
    stored = [band("CUST-900", "WATCH")]

    key = refused(build, [deal("D-2", currency="ALL"), deal("D-1", owner="LATER")], rates,
                  bands=stored)
    assert (key.condition, key.entity, key.source_ids, key.keys) == (
        "RESERVED_KEY", "deals", ("D-1", "D-2"), ("ALL", "LATER"))
    assert str(key) == "RESERVED_KEY; keys ALL, LATER; deals D-1, D-2"
    stage = refused(build, [deal("D-7", stage="prospect")], rates, bands=stored)
    assert str(stage) == "STAGE_OUTSIDE_VOCABULARY; deals D-7"


# ---------------------------------------------------------------------------
# The arithmetic of concentration (plan A11 item 5, OD-M3-6; C-27 to C-29)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("amount", "whole", "expected"), [
    ("500", "1000", "0.5000"),
    ("1", "3", "0.3333"),
    ("2", "3", "0.6667"),
    ("1000", "1000", "1.0000"),
    ("0", "7", "0.0000"),
    ("18769993.30", "73442577.10", "0.2556"),
    ("0.01", "99999999999999.99", "0.0000"),
])
def test_a_share_is_the_amount_over_the_whole_to_four_places(amount, whole, expected):
    """Plan A11 item 5, by hand. Always four decimal places: the rounding is a quantize."""
    found = share(Decimal(amount), Decimal(whole))

    assert type(found) is Decimal and str(found) == expected
    assert found == exact_share(amount, whole)


@pytest.mark.parametrize(("amount", "expected", "direction"), [
    ("1", "0.0000", "down to the even digit below"),
    ("3", "0.0002", "up to the even digit above"),
    ("5", "0.0002", "down to the even digit below"),
    ("7", "0.0004", "up to the even digit above"),
    ("9", "0.0004", "down to the even digit below"),
])
def test_a_share_that_is_an_exact_tie_rounds_to_the_even_digit(amount, expected, direction):
    """
    Half-even, in both directions: n/20000 is exactly n x 0.00005. Half-up
    would give 0.0001 for 1 and 0.0003 for 5; half-down 0.0001 for 3.
    """
    assert str(share(Decimal(amount), Decimal("20000"))) == expected, direction


def test_a_cumulative_share_is_taken_from_the_summed_amounts_and_rounded_once():
    """
    Plan A11 item 5: "It is not a sum of rounded shares." Three thirds are
    each 0.3333, which sum to 0.9999, and together they are 1.0000.
    """
    thirds = [Decimal("1"), Decimal("1"), Decimal("1")]

    assert [str(share(one, Decimal("3"))) for one in thirds] == ["0.3333"] * 3
    assert str(cumulative_share(thirds, Decimal("3"))) == "1.0000"
    assert str(cumulative_share(thirds[:2], Decimal("3"))) == "0.6667"
    assert str(cumulative_share(thirds[:1], Decimal("3"))) == "0.3333"
    assert str(cumulative_share([], Decimal("3"))) == "0.0000"
    assert str(cumulative_share(iter(thirds), Decimal("3"))) == "1.0000"


def test_the_index_is_the_sum_of_the_squared_parts_rounded_once():
    """Plan A11 item 5, by hand: 0.25 + 0.09 + 0.04, and a third, and one holder alone."""
    assert str(hhi([Decimal("500"), Decimal("300"), Decimal("200")], Decimal("1000"))) == "0.3800"
    assert str(hhi([Decimal("1")] * 3, Decimal("3"))) == "0.3333"
    assert str(hhi([Decimal("7.50")], Decimal("7.50"))) == "1.0000"
    assert str(hhi([], Decimal("5"))) == "0.0000"
    # Squaring the rounded parts instead would give 3 x 0.3333 squared, which is 0.3333 too,
    # so this pair tells the two apart: 0.33335 squared twice is 0.2222, and rounded first 0.2223.
    parts = [Decimal("33335"), Decimal("33335"), Decimal("33330")]
    assert str(hhi(parts, Decimal("100000"))) == "0.3333"
    assert str(hhi(parts[:2], Decimal("100000"))) == "0.2222"
    rounded_first = sum((share(one, Decimal("100000")) ** 2 for one in parts[:2]), Decimal(0))
    assert str(rounded_first.quantize(Decimal("0.0001"))) == "0.2223"


@pytest.mark.parametrize("amounts", [
    ["500", "300", "200"], ["1", "1", "1"], ["18769993.30", "12797000.00", "9663333.00"],
    ["0.01", "0.02", "99999999999999.99"], ["12.34", "0", "56.78", "0.00"], ["7"],
])
def test_the_three_helpers_agree_with_exact_arithmetic_that_uses_no_application_code(amounts):
    whole = str(sum((Decimal(one) for one in amounts), Decimal(0)))
    values = [Decimal(one) for one in amounts]

    assert [share(one, Decimal(whole)) for one in values] == [
        exact_share(one, whole) for one in amounts]
    for count in range(len(amounts) + 1):
        assert cumulative_share(values[:count], Decimal(whole)) == exact_cumulative(
            amounts[:count], whole)
    assert hhi(values, Decimal(whole)) == exact_hhi(amounts, whole)


def test_the_helpers_are_given_amounts_and_a_whole_and_nothing_else():
    """
    OD-M3-6, plan A12.4 item 4: no band, no customer and no holder's
    identity reaches the arithmetic, and each returns a Decimal and nothing
    that names what it is a share of.
    """
    assert list(inspect.signature(share).parameters) == ["amount", "whole"]
    assert list(inspect.signature(cumulative_share).parameters) == ["amounts", "whole"]
    assert list(inspect.signature(hhi).parameters) == ["amounts", "whole"]
    assert not [name for name in vars(measures) if "band" in name.lower()]
    assert measures.SHARE_QUANTUM == Decimal("0.0001") and str(measures.SHARE_QUANTUM) == "0.0001"


def test_what_measures_held_at_m2_is_as_it_was():
    """C-44, OD-M3-6: the module only gained. Its M2 functions keep their signatures."""
    assert list(inspect.signature(measures.weigh).parameters) == ["amount", "probability"]
    assert list(inspect.signature(measures.deal_values).parameters) == [
        "amount", "probability", "rate_set"]
    assert list(inspect.signature(measures.total).parameters) == ["currency", "values"]
    assert [field.name for field in dataclasses.fields(measures.DealValues)] == [
        "native_unweighted", "native_weighted", "base_unweighted", "base_weighted"]
    assert str(measures.WEIGHT_QUANTUM) == "0.01"


def test_a_whole_of_zero_has_no_parts_and_dividing_by_it_is_refused():
    """Plan A11 item 6: nothing is called with a zero whole. If it were, nothing is returned."""
    with pytest.raises(DivisionByZero):
        share(Decimal("1"), Decimal("0"))
    with pytest.raises(DivisionByZero):
        cumulative_share([Decimal("1")], Decimal("0"))
    with pytest.raises(DivisionByZero):
        hhi([Decimal("1")], Decimal("0"))
    with pytest.raises(InvalidOperation):
        share(Decimal("0"), Decimal("0"))


@pytest.mark.parametrize("hostile", HOSTILE, ids=HOSTILE_IDS)
def test_the_arithmetic_of_concentration_does_not_depend_on_the_callers_context(hostile):
    """
    C-43, plan A9.1 item 5: precision, rounding mode and traps are the
    caller's to set, and none of them changes a share, a cumulative share or
    an index, or whether one is returned. The caller's context is left as set.
    """
    amounts = [Decimal("18769993.30"), Decimal("12797000.00"), Decimal("9663333.00"),
               Decimal("0.07")]
    whole = Decimal("73442577.10")
    expected = ([share(one, whole) for one in amounts], cumulative_share(amounts, whole),
                hhi(amounts, whole))

    with localcontext(hostile()) as current:
        before = state_of(current)
        found = ([share(one, whole) for one in amounts], cumulative_share(amounts, whole),
                 hhi(amounts, whole))
        after = state_of(current)

    assert [str(one) for one in found[0]] == [str(one) for one in expected[0]] == [
        "0.2556", "0.1742", "0.1316", "0.0000"]
    assert (str(found[1]), str(found[2])) == (str(expected[1]), str(expected[2]))
    assert found[1] == exact_cumulative(amounts, whole) and found[2] == exact_hhi(amounts, whole)
    assert after == before


def test_the_narrow_contexts_would_change_a_share_without_a_context_of_its_own():
    """C-43's own control: the same division in the caller's context is another number."""
    with localcontext(Context(prec=1, rounding=ROUND_UP)):
        assert str(Decimal("1") / Decimal("3")) == "0.4"
    with localcontext(Context(prec=28, traps=[Inexact])), pytest.raises(Inexact):
        Decimal("1") / Decimal("3")


# ---------------------------------------------------------------------------
# The reserved customer key (plan A10.5 item 1, A14.1 item 7; C-25)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reserved", RESERVED)
def test_a_customer_who_would_head_a_bucket_under_a_reserved_key_fails_closed(rates, reserved):
    """
    C-25: from M3 a customer's source_id is a generated key. One namespace:
    UNLINKED would be merged into the pseudo-bucket of this partition, and
    the other seven are refused as well.
    """
    error = refused(build, [deal("D-52", customer=reserved), deal("D-51", customer=reserved),
                            deal("D-50", customer="CUST-OK")], rates)

    assert (error.condition, error.entity) == ("RESERVED_KEY", "deals")
    assert error.source_ids == ("D-51", "D-52")
    assert error.keys == (reserved,)
    assert str(error) == f"RESERVED_KEY; keys {reserved}; deals D-51, D-52"
    assert refused(valid_deals, [deal("D-9", customer=reserved)], STAGES).keys == (reserved,)


@pytest.mark.parametrize("changes", [
    {"is_active": False, "stage": "won"}, {"amount": None}, {"probability": None},
    {"amount": "-1.00"}], ids=["closed", "no amount", "no probability", "negative"])
def test_a_reserved_customer_id_on_a_closed_or_unvalued_deal_raises_nothing(rates, changes):
    """C-25: a source_id is a generated key only where it would be a bucket key."""
    others = [deal("D-1"), deal("D-2", customer="C-2", currency="USD")]

    for reserved in ("UNLINKED", "UNASSESSED", "ALL"):
        assert build([*others, deal("D-51", customer=reserved, **changes)], rates) == build(
            others, rates)


def test_a_customer_key_that_resolves_to_no_one_is_data_and_not_a_generated_key(rates):
    """Only a resolved customer heads a bucket. An unmatched key that spells UNLINKED is a key."""
    partitions = build([deal("D-1", customer=None, customer_key="UNLINKED")], rates)

    assert [(bucket.key, bucket.kind, bucket.deal_ids) for bucket in partitions.by_customer] == [
        ("UNLINKED", CustomerKind.UNLINKED, ("D-1",))]


def test_an_employees_key_and_a_customers_key_that_both_collide_are_reported_at_once(rates):
    """C-25: one error, every colliding key and every colliding deal, ascending and once each."""
    deals = [deal("D-4", owner="OVERDUE", customer="UNLINKED"), deal("D-1", customer="UNDATED"),
             deal("D-3", owner="LATER"), deal("D-2", currency="ALL", customer="C-OK"),
             deal("D-5")]

    for arranged in (deals, list(reversed(deals))):
        error = refused(build, arranged, rates, stages=[*STAGES, "UNASSESSED"])
        assert error.source_ids == ("D-1", "D-2", "D-3", "D-4")
        assert error.keys == ("ALL", "LATER", "OVERDUE", "UNASSESSED", "UNDATED", "UNLINKED")


def test_a_customer_key_that_only_resembles_a_reserved_one_is_an_ordinary_key(rates):
    partitions = build([deal("D-1", customer="unlinked"), deal("D-2", customer="UNLINKED "),
                        deal("D-3", customer="Unassessed")], rates)

    assert sorted(bucket.key for bucket in partitions.by_customer) == [
        "UNLINKED", "UNLINKED ", "Unassessed", "unlinked"]


def test_a_reserved_customer_key_wins_over_a_stage_outside_the_vocabulary_and_a_missing_rate(
        rates):
    """Plan A10.5 items 5 and 6: stage 1's own order, with the new key among its checks."""
    for deals in ([deal("D-1", customer="UNLINKED"), deal("D-2", stage="prospect"),
                   deal("D-3", currency="GBP")],
                  [deal("D-3", currency="GBP"), deal("D-2", stage="prospect"),
                   deal("D-1", customer="UNLINKED")]):
        error = refused(build, deals, rates)
        assert (error.condition, error.source_ids) == ("RESERVED_KEY", ("D-1",))


# ---------------------------------------------------------------------------
# The customer partition (plan A12.6; C-24, constructed)
# ---------------------------------------------------------------------------

#: A book with a tie, a customer in two currencies, two unlinked deals, and two
#: customers who hold no open valued deal.
CUSTOMER_BOOK = [
    deal("D-1", customer="C-B", amount="300.00"),
    deal("D-2", customer="C-A", amount="300.00"),
    deal("D-3", customer="C-C", amount="900.00"),
    deal("D-4", customer="C-C", amount="1.00", currency="USD"),
    deal("D-5", customer=None, customer_key=None, amount="50.00"),
    deal("D-6", customer=None, customer_key="CUST-404", amount="60.00"),
    deal("D-7", customer="C-D", is_active=False, stage="won", amount="99999.00"),
    deal("D-8", customer="C-E", amount=None),
]
CUSTOMER_BANDS = [band("C-A", "WATCH", True), band("C-C", "NONE"), band("C-D", "CRITICAL", True)]


def test_by_customer_holds_one_bucket_per_customer_with_a_deal_then_unlinked(rates):
    """
    C-24: by base unweighted exposure descending, then key ascending, so the
    two customers at 300.00 are C-A and then C-B; UNLINKED is last. A
    customer with only a closed or an unvalued deal has no bucket.
    """
    buckets = build(CUSTOMER_BOOK, rates, bands=CUSTOMER_BANDS).by_customer

    assert all(type(bucket) is CustomerBucket for bucket in buckets)
    assert [(bucket.key, bucket.kind, bucket.deal_ids) for bucket in buckets] == [
        ("C-C", CustomerKind.CUSTOMER, ("D-3", "D-4")),
        ("C-A", CustomerKind.CUSTOMER, ("D-2",)),
        ("C-B", CustomerKind.CUSTOMER, ("D-1",)),
        ("UNLINKED", CustomerKind.UNLINKED, ("D-5", "D-6"))]
    assert [str(bucket.base.unweighted) for bucket in buckets] == [
        "983.26", "300.00", "300.00", "110.00"]
    assert [kind.value for kind in CustomerKind] == ["CUSTOMER", "UNLINKED"]


def test_each_customer_bucket_carries_its_stored_band_and_verdict_or_unassessed(rates):
    """
    C-24: the assessment's own band and verdict. A customer with no
    assessment is UNASSESSED with no verdict, never NONE and never false;
    the UNLINKED bucket has neither.
    """
    buckets = by_key(build(CUSTOMER_BOOK, rates, bands=CUSTOMER_BANDS).by_customer)

    assert {key: (bucket.band, bucket.executive_worthy) for key, bucket in buckets.items()} == {
        "C-C": ("NONE", False), "C-A": ("WATCH", True), "C-B": ("UNASSESSED", None),
        "UNLINKED": (None, None)}
    unassessed = by_key(build(CUSTOMER_BOOK, rates).by_customer)
    assert {key: (bucket.band, bucket.executive_worthy)
            for key, bucket in unassessed.items()} == {
        "C-C": ("UNASSESSED", None), "C-A": ("UNASSESSED", None), "C-B": ("UNASSESSED", None),
        "UNLINKED": (None, None)}


def test_a_band_does_not_order_the_customer_partition(rates):
    """Plan A12.4: the order is exposure and then id. A CRITICAL customer is not moved up."""
    stored = [band("C-B", "CRITICAL", True), band("C-A", "NONE"), band("C-C", "WATCH")]

    assert [bucket.key for bucket in build(CUSTOMER_BOOK, rates, bands=stored).by_customer] == [
        "C-C", "C-A", "C-B", "UNLINKED"]


def test_the_unlinked_bucket_is_always_present_and_empty_when_every_deal_is_linked(rates):
    buckets = build([deal("D-1")], rates).by_customer

    assert [(bucket.key, bucket.deal_count, bucket.deal_ids, bucket.native) for bucket
            in buckets[-1:]] == [("UNLINKED", 0, (), ())]
    assert (buckets[-1].base.currency, str(buckets[-1].base.unweighted),
            str(buckets[-1].base.weighted)) == ("INR", "0", "0")
    assert [bucket.key for bucket in build([], rates).by_customer] == ["UNLINKED"]


def test_a_customer_in_two_currencies_states_each_natively_and_one_base(rates):
    """
    C-40: one native Amount per currency, ascending and never summed, and
    one base Amount that is the sum of the deals' own converted values.
    """
    bucket = by_key(build(CUSTOMER_BOOK, rates).by_customer)["C-C"]

    assert [(amount.currency, str(amount.unweighted), str(amount.weighted))
            for amount in bucket.native] == [("INR", "900.00", "450.00"),
                                             ("USD", "1.00", "0.50")]
    usd = exact_values("1.00", "50.00", RATES["USD"])
    assert str(usd[2]) == "83.26" and str(usd[3]) == "41.63"
    assert (str(bucket.base.unweighted), str(bucket.base.weighted)) == ("983.26", "491.63")


def test_a_buckets_native_amounts_are_in_code_point_order_of_their_currencies(tmp_path):
    """
    C-39, plan A14.1 item 6: one customer in eight currencies. With eight, no
    arbitrary order of a set of them is the ascending one by chance.
    """
    codes = ["USD", "EUR", "GBP", "JPY", "AED", "SGD", "CHF", "AUD"]
    eight = rate_set(tmp_path, dict.fromkeys(codes, "2"), version="eight")
    deals = [deal(f"D-{index}", currency=code, customer="C-1", amount="10.00")
             for index, code in enumerate(codes)]
    partitions = build(deals, eight)
    ascending = ["AED", "AUD", "CHF", "EUR", "GBP", "JPY", "SGD", "USD"]

    assert sorted(codes) == ascending
    assert [bucket.key for bucket in partitions.by_currency] == ascending
    for bucket in (partitions.open_pipeline, partitions.by_customer[0],
                   by_key(partitions.by_risk_band)["UNASSESSED"],
                   by_key(partitions.by_stage)["negotiation"]):
        assert [amount.currency for amount in bucket.native] == ascending, bucket.key
        assert {str(amount.unweighted) for amount in bucket.native} == {"10.00"}
    assert str(partitions.open_pipeline.base.unweighted) == "160.00"
    found = view_of(deals, eight)
    assert [amount["currency"] for amount in found["open_pipeline"]["native"]] == ascending
    assert found["fx"]["used_currencies"] == ascending
    assert [rate["currency"] for rate in found["fx"]["rates"]] == sorted([*ascending, "INR"])


def test_a_customers_base_is_the_sum_of_converted_deals_and_not_its_total_converted(tmp_path):
    """
    C-40: two deals of USD 0.33 at 1.5 are 0.50 each, so the customer and its
    band state 1.00. The native total, 0.66, converted once is 0.99. The
    shares are taken from those base amounts.
    """
    one_and_a_half = rate_set(tmp_path, {"USD": "1.5"})
    deals = [deal("D-1", amount="0.33", currency="USD", probability="100", customer="C-1"),
             deal("D-2", amount="0.33", currency="USD", probability="100", customer="C-1"),
             deal("D-3", amount="3.00", currency="INR", probability="100", customer="C-2")]
    partitions = build(deals, one_and_a_half, bands=[band("C-1", "WATCH")])

    customer = by_key(partitions.by_customer)["C-1"]
    watch = by_key(partitions.by_risk_band)["WATCH"]
    assert (str(customer.base.unweighted), str(watch.base.unweighted)) == ("1.00", "1.00")
    assert str((Decimal("0.66") * Decimal("1.5")).quantize(Decimal("0.01"))) == "0.99"
    block = partitions.concentration.by_customer.unweighted
    assert [(holder.key, str(holder.amount), str(holder.share)) for holder in block.top] == [
        ("C-2", "3.00", "0.7500"), ("C-1", "1.00", "0.2500")]
    assert str(block.total) == "4.00"


# ---------------------------------------------------------------------------
# The band partition (plan A12.3; C-23, constructed)
# ---------------------------------------------------------------------------


def test_by_risk_band_is_always_six_buckets_in_rank_order_then_the_two_coverage_buckets(rates):
    for deals, stored in (([], []), (CUSTOMER_BOOK, CUSTOMER_BANDS), (CUSTOMER_BOOK, [])):
        buckets = build(deals, rates, bands=stored).by_risk_band

        assert [bucket.key for bucket in buckets] == BAND_ORDER
        assert all(type(bucket) is BandBucket for bucket in buckets)


def test_a_deal_sits_under_its_customers_band_or_unassessed_or_unlinked(rates):
    """
    C-23: a deal whose customer has no assessment is UNASSESSED, and a deal
    with no customer is UNLINKED. Neither is merged with NONE or with the
    other. C-D is CRITICAL and holds no open valued deal, so it is in no bucket.
    """
    buckets = by_key(build(CUSTOMER_BOOK, rates, bands=CUSTOMER_BANDS).by_risk_band)

    assert {key: (bucket.deal_ids, bucket.customer_count, bucket.customer_ids)
            for key, bucket in buckets.items()} == {
        "CRITICAL": ((), 0, ()),
        "ELEVATED": ((), 0, ()),
        "WATCH": (("D-2",), 1, ("C-A",)),
        "NONE": (("D-3", "D-4"), 1, ("C-C",)),
        "UNASSESSED": (("D-1",), 1, ("C-B",)),
        "UNLINKED": (("D-5", "D-6"), 0, ()),
    }
    assert "C-D" not in itertools.chain.from_iterable(
        bucket.customer_ids for bucket in buckets.values())
    assert str(buckets["UNLINKED"].base.unweighted) == "110.00"
    assert str(buckets["NONE"].base.unweighted) == "983.26"


def test_with_no_band_every_linked_deal_is_unassessed_and_the_totals_are_unchanged(rates):
    """Named test 11's first half, constructed: missing coverage is a bucket, not an error."""
    assessed = build(CUSTOMER_BOOK, rates, bands=CUSTOMER_BANDS)
    bare = build(CUSTOMER_BOOK, rates)
    buckets = by_key(bare.by_risk_band)

    assert {key: bucket.deal_ids for key, bucket in buckets.items() if bucket.deal_count} == {
        "UNASSESSED": ("D-1", "D-2", "D-3", "D-4"), "UNLINKED": ("D-5", "D-6")}
    assert buckets["UNASSESSED"].customer_ids == ("C-A", "C-B", "C-C")
    assert (bare.open_pipeline, bare.by_currency, bare.by_stage, bare.by_owner,
            bare.by_expected_close, bare.concentration, bare.per_deal) == (
        assessed.open_pipeline, assessed.by_currency, assessed.by_stage, assessed.by_owner,
        assessed.by_expected_close, assessed.concentration, assessed.per_deal)
    assert bare.risk_coincidence == ()


def test_the_customers_of_a_band_are_listed_by_code_point_and_once_each(rates):
    deals = [deal(f"D-{index}", customer=customer) for index, customer in enumerate(
        ["cust-2", "CUST-10", "Cust-1", "CUST-2", "CUST-é", "CUST-2", "CUST-1"])]
    stored = [band(customer, "WATCH") for customer in
              {"cust-2", "CUST-10", "Cust-1", "CUST-2", "CUST-é", "CUST-1"}]

    for arranged in (deals, list(reversed(deals))):
        watch = by_key(build(arranged, rates, bands=reversed(stored)).by_risk_band)["WATCH"]
        assert watch.customer_ids == ("CUST-1", "CUST-10", "CUST-2", "CUST-é", "Cust-1",
                                      "cust-2")
        assert watch.customer_count == 6 and watch.deal_count == 7


# ---------------------------------------------------------------------------
# Reconciliation of all six partitions (named test 4; plan A9.4)
# ---------------------------------------------------------------------------

#: Three currencies, rates that are not integers, and a deal in every kind of bucket.
_ROWS = [
    ("D-01", "negotiation", "1000.00", "INR", "50.00", date(2026, 9, 1), "EMP-A", "C-A"),
    ("D-02", "qualification", "333.33", "USD", "33.33", date(2026, 9, 18), "EMP-A", "C-B"),
    ("D-03", "qualification", "0.25", "USD", "50.00", date(2027, 8, 31), None, "C-B"),
    ("D-04", "negotiation", "777.77", "EUR", "12.50", date(2027, 9, 1), None, "C-C"),
    ("D-05", "won", "19.99", "EUR", "99.99", None, "EMP-B", None),
    ("D-06", "negotiation", "5000000.05", "INR", "0.01", date(2026, 12, 31), None, "C-D"),
    ("D-07", "qualification", "0.75", "USD", "50.00", date(2026, 9, 17), None, None),
]
PORTFOLIO = [
    *(deal(source_id, stage=stage, amount=amount, currency=currency, probability=probability,
           expected=expected, owner=owner, owner_key=owner, customer=customer,
           customer_key=customer)
      for source_id, stage, amount, currency, probability, expected, owner, customer in _ROWS),
    deal("D-08", stage="won", is_active=False, amount="900000.00", currency="USD",
         customer="C-A"),
    deal("D-09", amount=None, currency="EUR", customer="C-E"),
    deal("D-10", amount="-25.00", currency="USD", customer="C-A"),
]
PORTFOLIO_BANDS = [band("C-A", "CRITICAL", True), band("C-B", "WATCH"), band("C-D", "NONE"),
                   band("C-E", "ELEVATED", True), band("C-Z", "WATCH")]
VALUED_IDS = [row[0] for row in _ROWS]
EXACT = {row[0]: (row[3], exact_values(row[2], row[4], {"INR": "1", **RATES}[row[3]]))
         for row in _ROWS}
SIX = ("by_currency", "by_stage", "by_owner", "by_expected_close", "by_risk_band", "by_customer")


def exact_sums(ids) -> tuple[dict[str, tuple[str, str]], tuple[str, str]]:
    """What a bucket over these deals must state: per-deal values summed as integers of cents."""
    def text(cents: int) -> str:
        return f"{cents // 100}.{cents % 100:02d}"

    native: dict[str, list[int]] = {}
    base = [0, 0]
    for source_id in ids:
        currency, values = EXACT[source_id]
        cents = [int(value.scaleb(2)) for value in values]
        held = native.setdefault(currency, [0, 0])
        held[0] += cents[0]
        held[1] += cents[1]
        base[0] += cents[2]
        base[1] += cents[3]
    return ({currency: (text(one), text(two)) for currency, (one, two) in native.items()},
            (text(base[0]), text(base[1])))


@pytest.mark.parametrize("partition", SIX)
def test_every_one_of_the_six_partitions_reconciles_exactly_to_the_open_pipeline(
        rates, partition):
    """
    Named test 4 [R], plan A9.4 item 1: the buckets hold every open valued
    deal exactly once and no other, and sum with no tolerance to the total,
    by count, per currency natively, and in the base, weighted and unweighted.
    """
    partitions = build(PORTFOLIO, rates, bands=PORTFOLIO_BANDS)
    buckets = getattr(partitions, partition)
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
    assert (str(sum((bucket.base.unweighted for bucket in buckets), Decimal(0))),
            str(sum((bucket.base.weighted for bucket in buckets), Decimal(0)))) == expected_base
    total = partitions.open_pipeline
    assert (str(total.base.unweighted), str(total.base.weighted)) == expected_base == (
        "5101530.17", "20972.12")


def test_the_open_pipeline_is_one_bucket_over_every_open_valued_deal(rates):
    """Plan A14.2: its key is ALL, and its figures are the sums of the deals' own values."""
    total = build(PORTFOLIO, rates, bands=PORTFOLIO_BANDS).open_pipeline
    expected_native, expected_base = exact_sums(VALUED_IDS)

    assert type(total) is Bucket and total.key == OPEN_PIPELINE_KEY == "ALL"
    assert (total.deal_count, total.deal_ids) == (7, tuple(VALUED_IDS))
    assert {amount.currency: (str(amount.unweighted), str(amount.weighted))
            for amount in total.native} == expected_native
    assert [amount.currency for amount in total.native] == ["EUR", "INR", "USD"]
    assert (total.base.currency, str(total.base.unweighted), str(total.base.weighted)) == (
        "INR", *expected_base)
    empty = build([], rates).open_pipeline
    assert (empty.key, empty.deal_count, empty.deal_ids, empty.native,
            str(empty.base.unweighted), str(empty.base.weighted)) == ("ALL", 0, (), (), "0", "0")


def test_each_deals_own_values_come_back_with_the_partitions(rates):
    """What the view states of each open valued deal is what the buckets were summed from."""
    per_deal = dict(build(PORTFOLIO, rates, bands=PORTFOLIO_BANDS).per_deal)

    assert list(per_deal) == VALUED_IDS
    assert {source_id: (str(values.native_unweighted.amount), str(values.native_weighted.amount),
                        str(values.base_unweighted.amount), str(values.base_weighted.amount))
            for source_id, values in per_deal.items()} == {
        source_id: tuple(str(value) for value in values)
        for source_id, (_, values) in EXACT.items()}


# ---------------------------------------------------------------------------
# No blend (named test 10; plan A12.4)
# ---------------------------------------------------------------------------


def test_permuting_the_band_labels_moves_deals_between_buckets_and_changes_no_figure(rates):
    """
    Named test 10 [R]: a band only selects the bucket a deal's amounts are
    summed in. With the same customers given other bands, the deals move,
    and no amount, no total and no concentration figure changes.
    """
    first = build(PORTFOLIO, rates, bands=PORTFOLIO_BANDS)
    relabelled = [band("C-A", "NONE"), band("C-B", "CRITICAL", True), band("C-D", "ELEVATED"),
                  band("C-E", "WATCH"), band("C-Z", "CRITICAL")]
    second = build(PORTFOLIO, rates, bands=relabelled)

    assert {bucket.key: bucket.deal_ids for bucket in first.by_risk_band} == {
        "CRITICAL": ("D-01",), "ELEVATED": (), "WATCH": ("D-02", "D-03"), "NONE": ("D-06",),
        "UNASSESSED": ("D-04",), "UNLINKED": ("D-05", "D-07")}
    assert {bucket.key: bucket.deal_ids for bucket in second.by_risk_band} == {
        "CRITICAL": ("D-02", "D-03"), "ELEVATED": ("D-06",), "WATCH": (), "NONE": ("D-01",),
        "UNASSESSED": ("D-04",), "UNLINKED": ("D-05", "D-07")}

    assert (second.open_pipeline, second.by_currency, second.by_stage, second.by_owner,
            second.by_expected_close, second.concentration, second.per_deal) == (
        first.open_pipeline, first.by_currency, first.by_stage, first.by_owner,
        first.by_expected_close, first.concentration, first.per_deal)
    plain = [dataclasses.replace(bucket, band=None, executive_worthy=None)
             for bucket in first.by_customer]
    assert [dataclasses.replace(bucket, band=None, executive_worthy=None)
            for bucket in second.by_customer] == plain
    # A band's figures are exactly the figures of the deals it was handed.
    for partitions in (first, second):
        for bucket in partitions.by_risk_band:
            native, base = exact_sums(bucket.deal_ids)
            assert (str(bucket.base.unweighted), str(bucket.base.weighted)) == (
                base if bucket.deal_ids else ("0", "0"))
            assert {amount.currency: (str(amount.unweighted), str(amount.weighted))
                    for amount in bucket.native} == native


def test_no_amount_is_computed_from_a_band(rates, monkeypatch):
    """
    Plan A12.4 items 1, 2 and 4: the arithmetic never sees a band. Every
    call into the measures is recorded, and no argument of any is a band, a
    band fact or a customer's assessment.
    """
    seen = []
    for name in ("deal_values", "total", "share", "cumulative_share", "hhi"):
        original = getattr(aggregation, name)

        def spy(*args, _original=original, **kwargs):
            seen.extend(args)
            seen.extend(kwargs.values())
            return _original(*args, **kwargs)

        monkeypatch.setattr(aggregation, name, spy)

    build(PORTFOLIO, rates, bands=PORTFOLIO_BANDS)

    flat = [item for argument in seen
            for item in (list(argument) if isinstance(argument, list | tuple) else [argument])]
    assert seen and len(flat) > 50
    assert not [item for item in flat
                if isinstance(item, RiskBand | BandFact | CustomerBand)]
    assert not [item for item in flat if isinstance(item, str)
                and item in {member.value for member in RiskBand}]


# ---------------------------------------------------------------------------
# Coincidence (plan A12.5; C-26, constructed)
# ---------------------------------------------------------------------------

COINCIDENCE_BOOK = [
    deal("D-0", customer="K0", amount="50.00"),
    deal("D-1", customer="K1", amount="100.00"),
    deal("D-2", customer="K2", amount="900.00"),
    deal("D-3", customer="K3", amount="500.00"),
    deal("D-4", customer="K4", amount="500.00"),
    deal("D-5", customer="K5", amount="700.00"),
    deal("D-6", customer="K6", amount="10000.00"),
    deal("D-7", customer="K7", amount="5000.00"),
    deal("D-8", customer="K8", amount="99999.00", is_active=False, stage="won"),
    deal("D-9", customer="K9", amount=None),
]
COINCIDENCE_BANDS = [
    band("K0", "CRITICAL"), band("K1", "CRITICAL"), band("K2", "ELEVATED"), band("K3", "WATCH"),
    band("K4", "WATCH"), band("K5", "WATCH"), band("K6", "NONE"), band("K8", "CRITICAL"),
    band("K9", "ELEVATED"),
]


def test_coincidence_is_band_rank_then_exposure_then_id(rates):
    """
    C-26, plan A12.4 item 3: CRITICAL, then ELEVATED, then WATCH. Inside a
    band the larger exposure is first, and K3 and K4 are tied at 500.00 and
    so are by id. K2 has the most exposure of all and is not first.
    """
    for deals, stored in ((COINCIDENCE_BOOK, COINCIDENCE_BANDS),
                          (list(reversed(COINCIDENCE_BOOK)), list(reversed(COINCIDENCE_BANDS)))):
        assert build(deals, rates, bands=stored).risk_coincidence == (
            "K1", "K0", "K2", "K5", "K3", "K4")


def test_only_a_banded_customer_who_holds_an_open_valued_deal_coincides(rates):
    """
    C-26: a NONE customer, an unassessed one, and a banded customer with only
    a closed or an unvalued deal are absent. Every id is a CUSTOMER bucket's
    key, and the list states no figure.
    """
    partitions = build(COINCIDENCE_BOOK, rates, bands=COINCIDENCE_BANDS)
    listed = partitions.risk_coincidence

    assert not {"K6", "K7", "K8", "K9"} & set(listed)
    assert set(listed) <= {bucket.key for bucket in partitions.by_customer
                           if bucket.kind is CustomerKind.CUSTOMER}
    assert all(type(customer) is str for customer in listed) and type(listed) is tuple


def test_with_no_banded_customer_coincidence_is_empty(rates):
    assert build(COINCIDENCE_BOOK, rates).risk_coincidence == ()
    assert build(COINCIDENCE_BOOK, rates, bands=[band("K6", "NONE"), band("K8", "CRITICAL")]
                 ).risk_coincidence == ()
    assert build([], rates, bands=COINCIDENCE_BANDS).risk_coincidence == ()
    assert build([deal("D-1", customer=None, customer_key=None)], rates,
                 bands=[band("UNLINKED", "CRITICAL")]).risk_coincidence == ()


# ---------------------------------------------------------------------------
# Concentration (plan A11, A14.7; C-27 to C-29 and named test 18, constructed)
# ---------------------------------------------------------------------------


def block_of(block) -> dict[str, object]:
    """A block as the oracle states one, every figure as its text."""
    def text(value: Decimal) -> str:
        digits = format(value, "f")
        stripped = digits.rstrip("0").rstrip(".") if "." in digits else digits
        return "0" if value == 0 else stripped

    return {
        "holder_count": block.holder_count,
        "top": [(holder.key, text(holder.share)) for holder in block.top],
        "cumulative": [(point.holders, text(point.share)) for point in block.cumulative],
        "hhi": None if block.hhi is None else text(block.hhi),
    }


def test_three_holders_by_hand(plain_rates):
    """
    Named test 18: 500, 300 and 200 of 1000. Shares 0.5, 0.3, 0.2; the
    largest one, three and "five" are 0.5, 1 and 1; the index is 0.38. Fewer
    than five holders: top holds all three, and cumulative still has three
    entries, at 1, 3 and 5.
    """
    deals = [deal("D-1", customer="C-A", owner="EMP-1", amount="500.00", probability="100"),
             deal("D-2", customer="C-B", owner="EMP-1", amount="300.00", probability="100"),
             deal("D-3", customer="C-C", owner="EMP-2", amount="200.00", probability="100")]
    blocks = build(deals, plain_rates).concentration

    customers = blocks.by_customer.unweighted
    assert (customers.currency, customers.rate_set_version, str(customers.total),
            customers.holder_count, customers.reason) == ("INR", "by-hand", "1000.00", 3, None)
    assert [(holder.key, holder.pseudo, str(holder.amount), str(holder.share))
            for holder in customers.top] == [
        ("C-A", False, "500.00", "0.5000"), ("C-B", False, "300.00", "0.3000"),
        ("C-C", False, "200.00", "0.2000")]
    assert [(point.holders, str(point.share)) for point in customers.cumulative] == [
        (1, "0.5000"), (3, "1.0000"), (5, "1.0000")]
    assert str(customers.hhi) == "0.3800"

    owners = blocks.by_owner.unweighted
    assert [(holder.key, str(holder.amount), str(holder.share)) for holder in owners.top] == [
        ("EMP-1", "800.00", "0.8000"), ("EMP-2", "200.00", "0.2000")]
    assert [(point.holders, str(point.share)) for point in owners.cumulative] == [
        (1, "0.8000"), (3, "1.0000"), (5, "1.0000")]
    assert str(owners.hhi) == "0.6800"
    assert blocks.by_customer.weighted == dataclasses.replace(customers), (
        "at 100% the two measures are the same amounts")


def test_more_than_five_holders_lists_five_and_counts_them_all(plain_rates):
    """C-29: top holds five, the index and the count cover all seven."""
    amounts = {"C-1": "700", "C-2": "600", "C-3": "500", "C-4": "400", "C-5": "300",
               "C-6": "200", "C-7": "100"}
    deals = [deal(f"D-{customer}", customer=customer, amount=amount, probability="100")
             for customer, amount in amounts.items()]
    block = build(list(reversed(deals)), plain_rates).concentration.by_customer.unweighted

    # A base amount is quantized to 0.01 by convert (plan A7.5 item 2), base currency included.
    assert block.holder_count == 7 and str(block.total) == "2800.00"
    assert [(holder.key, str(holder.share)) for holder in block.top] == [
        ("C-1", "0.2500"), ("C-2", "0.2143"), ("C-3", "0.1786"), ("C-4", "0.1429"),
        ("C-5", "0.1071")]
    assert [(point.holders, str(point.share)) for point in block.cumulative] == [
        (1, "0.2500"), (3, "0.6429"), (5, "0.8929")]
    # 1400000 / 7840000: every one of the seven is squared, not only the five listed.
    assert str(block.hhi) == "0.1786"
    assert block_of(block) == exact_concentration(list(amounts.items()))


def test_two_holders_with_equal_amounts_are_ordered_by_key(plain_rates):
    """C-29: amount descending, then key ascending by code point."""
    deals = [deal("D-1", customer="cust-b", amount="10"), deal("D-2", customer="CUST-b", amount="10"),
             deal("D-3", customer="CUST-A", amount="10"), deal("D-4", customer="CUST-10", amount="10"),
             deal("D-5", customer="CUST-9", amount="10"), deal("D-6", customer="CUST-é", amount="10"),
             deal("D-7", customer="ZZ", amount="11")]

    for arranged in (deals, list(reversed(deals))):
        block = build(arranged, plain_rates).concentration.by_customer.unweighted
        assert [holder.key for holder in block.top] == [
            "ZZ", "CUST-10", "CUST-9", "CUST-A", "CUST-b"]


def test_a_pseudo_bucket_above_zero_is_a_holder_flagged_pseudo_and_counted(plain_rates):
    """
    C-29, plan A11 item 4: UNLINKED, UNASSIGNED and UNRESOLVED are holders
    when their amount is above zero, so that the shares describe the whole
    total. They are flagged, and counted in holder_count and in the total.
    """
    deals = [deal("D-1", customer="C-A", owner="EMP-1", amount="400", probability="100"),
             deal("D-2", customer=None, customer_key=None, owner=None, owner_key=None,
                  amount="350", probability="100"),
             deal("D-3", customer=None, customer_key="C-404", owner=None, owner_key="EMP-404",
                  amount="250", probability="100")]
    blocks = build(deals, plain_rates).concentration

    assert [(holder.key, holder.pseudo, str(holder.amount), str(holder.share))
            for holder in blocks.by_customer.unweighted.top] == [
        ("UNLINKED", True, "600.00", "0.6000"), ("C-A", False, "400.00", "0.4000")]
    assert [(holder.key, holder.pseudo, str(holder.amount), str(holder.share))
            for holder in blocks.by_owner.unweighted.top] == [
        ("EMP-1", False, "400.00", "0.4000"), ("UNASSIGNED", True, "350.00", "0.3500"),
        ("UNRESOLVED", True, "250.00", "0.2500")]
    assert (blocks.by_customer.unweighted.holder_count,
            blocks.by_owner.unweighted.holder_count) == (2, 3)
    assert str(blocks.by_owner.unweighted.total) == str(
        blocks.by_customer.unweighted.total) == "1000.00"
    assert str(blocks.by_owner.unweighted.hhi) == "0.3450"


def test_a_pseudo_bucket_at_zero_is_not_a_holder(plain_rates):
    """C-29: the always-present empty pseudo-buckets hold nothing and are not listed."""
    blocks = build([deal("D-1", amount="5", probability="100")], plain_rates).concentration

    assert [(holder.key, holder.pseudo) for holder in blocks.by_customer.unweighted.top] == [
        ("CUST-900", False)]
    assert [(holder.key, holder.pseudo) for holder in blocks.by_owner.unweighted.top] == [
        ("EMP-900", False)]
    assert blocks.by_customer.unweighted.holder_count == 1
    assert [(point.holders, str(point.share))
            for point in blocks.by_owner.unweighted.cumulative] == [
        (1, "1.0000"), (3, "1.0000"), (5, "1.0000")]
    assert str(blocks.by_owner.unweighted.hhi) == "1.0000"


def test_the_weighted_blocks_are_computed_from_weighted_amounts_and_nothing_else(plain_rates):
    """
    C-28: C-ZERO holds 900 at probability 0, so it is the largest holder of
    the unweighted block and no holder of the weighted one. C-HALF leads the
    weighted block with 100 of 110.
    """
    deals = [deal("D-1", customer="C-ZERO", owner="EMP-1", amount="900", probability="0"),
             deal("D-2", customer="C-HALF", owner="EMP-2", amount="200", probability="50"),
             deal("D-3", customer="C-FULL", owner="EMP-2", amount="10", probability="100")]
    pair = build(deals, plain_rates).concentration.by_customer

    assert [(holder.key, str(holder.amount), str(holder.share))
            for holder in pair.unweighted.top] == [
        ("C-ZERO", "900.00", "0.8108"), ("C-HALF", "200.00", "0.1802"),
        ("C-FULL", "10.00", "0.0090")]
    assert [(holder.key, str(holder.amount), str(holder.share))
            for holder in pair.weighted.top] == [
        ("C-HALF", "100.00", "0.9091"), ("C-FULL", "10.00", "0.0909")]
    assert (pair.unweighted.holder_count, pair.weighted.holder_count) == (3, 2)
    assert (str(pair.unweighted.total), str(pair.weighted.total)) == ("1110.00", "110.00")
    assert str(pair.weighted.hhi) == "0.8347"
    owners = build(deals, plain_rates).concentration.by_owner
    assert [holder.key for holder in owners.unweighted.top] == ["EMP-1", "EMP-2"]
    assert [holder.key for holder in owners.weighted.top] == ["EMP-2"]


def test_a_zero_total_gives_the_zero_form(plain_rates):
    """
    C-29, plan A11 item 6: total 0, no holder, top and cumulative empty, no
    index, and the reason. With no deal, and with deals of which none is open
    and valued. A weighted total of zero beside an unweighted one above it.
    """
    for deals in ([], [deal("D-1", is_active=False, stage="won"), deal("D-2", amount=None)]):
        blocks = build(deals, plain_rates).concentration
        for block in (blocks.by_customer.unweighted, blocks.by_customer.weighted,
                      blocks.by_owner.unweighted, blocks.by_owner.weighted):
            assert (block.currency, block.rate_set_version, str(block.total),
                    block.holder_count, block.top, block.cumulative, block.hhi,
                    block.reason) == ("INR", "by-hand", "0", 0, (), (), None, NO_OPEN_EXPOSURE)
    assert NO_OPEN_EXPOSURE == "NO_OPEN_EXPOSURE"

    pair = build([deal("D-1", amount="80", probability="0")], plain_rates).concentration.by_owner
    assert (str(pair.unweighted.total), pair.unweighted.reason, str(pair.unweighted.hhi)) == (
        "80.00", None, "1.0000")
    assert (str(pair.weighted.total), pair.weighted.holder_count, pair.weighted.top,
            pair.weighted.cumulative, pair.weighted.hhi, pair.weighted.reason) == (
        "0.00", 0, (), (), None, "NO_OPEN_EXPOSURE")


def test_every_block_of_the_portfolio_equals_the_oracles(rates):
    """
    C-27, C-28, C-40: with rates that are not integers, each of the four
    blocks equals what exact arithmetic gives from the holders' own base
    amounts, and its total is the open pipeline's figure in its measure.
    """
    partitions = build(PORTFOLIO, rates, bands=PORTFOLIO_BANDS)
    total = partitions.open_pipeline.base

    for pair, buckets in ((partitions.concentration.by_customer, partitions.by_customer),
                          (partitions.concentration.by_owner, partitions.by_owner)):
        for block, measure in ((pair.unweighted, "unweighted"), (pair.weighted, "weighted")):
            candidates = [(bucket.key, getattr(bucket.base, measure)) for bucket in buckets]
            assert block_of(block) == exact_concentration(candidates), measure
            assert block.total == getattr(total, measure)
            assert (block.currency, block.rate_set_version) == ("INR", "constructed")
            assert block.holder_count == len([one for _, one in candidates if one > 0])
    owners = partitions.concentration.by_owner.unweighted
    # D-03, D-04, D-06 and D-07 name no owner at all, and D-06 alone is 5,000,000.05.
    assert [(holder.key, holder.pseudo) for holder in owners.top] == [
        ("UNASSIGNED", True), ("EMP-A", False), ("EMP-B", False)]


def test_the_holders_amounts_are_what_the_shares_are_taken_from(rates):
    """Plan A18.3: a share is grounded by the holder amounts in the same block."""
    block = build(PORTFOLIO, rates, bands=PORTFOLIO_BANDS).concentration.by_customer.unweighted

    for holder in block.top:
        assert holder.share == exact_share(holder.amount, block.total)
    assert block.cumulative[0].share == block.top[0].share


# ---------------------------------------------------------------------------
# deal_counts (plan A14.5, OD-4, OD-9; C-30 to C-33, constructed)
# ---------------------------------------------------------------------------

COUNT_BOOK = [
    deal("D-1", stage="negotiation"),
    deal("D-2", stage="negotiation", amount=None),
    deal("D-3", stage="negotiation", is_active=False),
    deal("D-4", stage=None),
    deal("D-5", stage=None, is_active=False),
    deal("D-6", stage="won", is_active=False),
    deal("D-7", stage="won"),
    deal("D-8", stage="qualification", amount="-5.00"),
]


def test_deal_counts_counts_every_deal_by_state_and_by_stage():
    """
    C-30, C-31: an open valued, an open unvalued and a closed deal in a
    vocabulary stage; an open and a closed deal with a null stage; an open
    deal in a closed stage, counted in that stage's open.
    """
    counts = deal_counts(COUNT_BOOK, STAGES)

    assert counts == {
        "total": 8, "open": 5, "open_valued": 2, "open_unvalued": 3, "closed": 3,
        "unvalued_deal_ids": ["D-2", "D-4", "D-8"],
        "by_stage": [
            {"stage": "negotiation", "total": 3, "open": 2, "closed": 1},
            {"stage": "qualification", "total": 1, "open": 1, "closed": 0},
            {"stage": "won", "total": 2, "open": 1, "closed": 1},
            {"stage": "UNSTAGED", "total": 2, "open": 1, "closed": 1},
        ],
    }
    assert list(counts) == ["total", "open", "open_valued", "open_unvalued", "closed",
                            "unvalued_deal_ids", "by_stage"]


def test_the_unvalued_ids_are_ascending_whatever_order_the_facts_arrive_in():
    """Plan A14.5, A14.1 item 6: deal_counts orders what it lists itself."""
    unvalued = [deal("D-3", amount=None), deal("D-1", probability=None),
                deal("D-2", amount="-1.00"), deal("D-10", currency=None)]
    valued = deal("D-0")

    for order in ([*unvalued, valued], [valued, *unvalued[::-1]],
                  [unvalued[2], unvalued[0], valued, unvalued[3], unvalued[1]]):
        counts = deal_counts(order, STAGES)
        assert counts["unvalued_deal_ids"] == ["D-1", "D-10", "D-2", "D-3"]
        assert (counts["open"], counts["open_valued"], counts["open_unvalued"]) == (5, 1, 4)


@pytest.mark.parametrize("deals", [COUNT_BOOK, [], COUNT_BOOK[:1], COUNT_BOOK[3:5],
                                   list(reversed(COUNT_BOOK)), PORTFOLIO],
                         ids=["the book", "no deal", "one deal", "unstaged only", "reversed",
                              "the portfolio"])
def test_deal_counts_reconciles(deals):
    """
    C-31, plan A14.5's four identities. Overall: open is valued plus
    unvalued, and total is open plus closed. In every row: total is open
    plus closed. Across the rows: the totals sum to the total, and the opens
    and the closeds to theirs. No row has a key beyond the four.
    """
    counts = deal_counts(deals, STAGES)
    rows = counts["by_stage"]

    assert counts["open"] == counts["open_valued"] + counts["open_unvalued"]
    assert counts["total"] == counts["open"] + counts["closed"] == len(deals)
    assert all(row["total"] == row["open"] + row["closed"] for row in rows)
    assert sum(row["total"] for row in rows) == counts["total"]
    assert sum(row["open"] for row in rows) == counts["open"]
    assert sum(row["closed"] for row in rows) == counts["closed"]
    assert all(list(row) == ["stage", "total", "open", "closed"] for row in rows)
    assert len(counts["unvalued_deal_ids"]) == counts["open_unvalued"]
    assert [row["stage"] for row in rows] == ["negotiation", "qualification", "won", "UNSTAGED"]
    assert all(type(value) is int for row in rows for value in list(row.values())[1:])


def test_a_null_stage_is_unstaged_and_nothing_else_is():
    """
    C-32: open or closed, a null stage is counted in UNSTAGED and raises
    nothing. The row is present when empty, and last. No deal with a
    non-null stage is ever counted in it.
    """
    assert UNSTAGED == "UNSTAGED"
    empty = deal_counts([deal("D-1"), deal("D-2", stage="won", is_active=False)], STAGES)
    assert empty["by_stage"][-1] == {"stage": "UNSTAGED", "total": 0, "open": 0, "closed": 0}
    assert deal_counts([], STAGES)["by_stage"][-1]["stage"] == "UNSTAGED"

    held = deal_counts([deal("D-1", stage=None), deal("D-2", stage=None, is_active=False),
                        deal("D-3", stage=None, amount=None), deal("D-4")], STAGES)
    assert held["by_stage"][-1] == {"stage": "UNSTAGED", "total": 3, "open": 2, "closed": 1}
    assert held["unvalued_deal_ids"] == ["D-1", "D-3"]
    assert [row["total"] for row in held["by_stage"][:-1]] == [1, 0, 0]
    assert deal_counts([deal("D-1", stage=None)], ())["by_stage"] == [
        {"stage": "UNSTAGED", "total": 1, "open": 1, "closed": 0}]


@pytest.mark.parametrize("changes", [
    {"is_active": False}, {"amount": None}, {"probability": None}, {"currency": None},
    {"amount": "-1.00"}, {}],
    ids=["closed", "no amount", "no probability", "no currency", "negative", "open valued"])
def test_a_non_null_stage_outside_the_vocabulary_leaves_no_count_to_state(changes):
    """
    C-33, OD-9: a closed deal, an open unvalued deal and any other deal
    deal_counts counts. Never UNSTAGED, never another stage, never dropped.
    """
    error = refused(deal_counts, [*COUNT_BOOK, deal("D-70", stage="prospect", **changes)], STAGES)

    assert (error.condition, error.entity) == ("STAGE_OUTSIDE_VOCABULARY", "deals")
    assert error.source_ids == ("D-70",) and error.keys == ()
    assert str(error) == "STAGE_OUTSIDE_VOCABULARY; deals D-70"


def test_several_such_deals_raise_once_and_name_every_one_in_any_order():
    """C-33, C-39: ascending and once each, whatever order the facts arrive in."""
    odd = [deal("D-72", stage="Won", is_active=False), deal("D-70", stage="prospect", amount=None),
           deal("D-71", stage="lost", is_active=False), deal("D-73", stage="", amount=None),
           deal("D-74", stage="UNSTAGED", is_active=False)]

    for arranged in ([*COUNT_BOOK, *odd], [*reversed(odd), *COUNT_BOOK], odd[2:] + odd[:2]):
        error = refused(deal_counts, arranged, STAGES)
        assert error.source_ids == ("D-70", "D-71", "D-72", "D-73", "D-74")
    assert str(error) == "STAGE_OUTSIDE_VOCABULARY; deals D-70, D-71, D-72, D-73, D-74"


@pytest.mark.parametrize("changes", [{"is_active": False}, {"amount": None}],
                         ids=["closed", "open unvalued"])
def test_given_the_same_deals_the_aggregation_entry_point_still_raises_nothing(rates, changes):
    """C-33, C-12: OD-9's check is deal_counts' and was not added to stage 1."""
    odd = deal("D-70", stage="prospect", **changes)

    assert build([*PORTFOLIO, odd], rates) == build(PORTFOLIO, rates)
    assert valid_deals([*PORTFOLIO, odd], STAGES) == valid_deals(PORTFOLIO, STAGES)
    with pytest.raises(PipelineDataError):
        deal_counts([*PORTFOLIO, odd], STAGES)
    with pytest.raises(PipelineDataError):
        view_of([*PORTFOLIO, odd], rates)


def test_the_stage_rows_are_those_of_the_vocabulary_supplied():
    """Plan A22.5 seam 2: the builder is handed the vocabulary and reads none for itself."""
    counts = deal_counts([deal("D-1", stage="lost"), deal("D-2", stage="alpha", is_active=False)],
                         {"won", "lost", "alpha", "Lost"})

    assert [(row["stage"], row["total"]) for row in counts["by_stage"]] == [
        ("Lost", 0), ("alpha", 1), ("lost", 1), ("won", 0), ("UNSTAGED", 0)]
    assert [row["stage"] for row in deal_counts([], ["b", "a", "b"])["by_stage"]] == [
        "a", "b", "UNSTAGED"]
    assert refused(deal_counts, [deal("D-1", stage="negotiation")], ["won"]).source_ids == (
        "D-1",)


# ---------------------------------------------------------------------------
# The order of the data-validity conditions (plan A17.1, OD-M3-1), on the
# pure builders
# ---------------------------------------------------------------------------

STAGE_ONE = {
    "a reserved owner key": deal("D-82", owner="UNLINKED"),
    "a reserved customer key": deal("D-82", customer="UNASSESSED"),
    "the currency ALL": deal("D-82", currency="ALL"),
    "a stage outside the vocabulary on an open valued deal": deal("D-82", stage="prospect"),
}
OD9 = deal("D-90", stage="prospect", is_active=False)
UNKNOWN_BAND = band("CUST-900", "SEVERE")
UNPRICED = deal("D-80", currency="GBP")
OUTSIDE_D1 = deal("D-81", currency="XXX")


@pytest.mark.parametrize("condition", sorted(STAGE_ONE))
def test_a_stage_one_condition_wins_over_od9s_and_over_an_unknown_band(rates, condition):
    """
    OD-M3-1: stage 1, then the stage of every deal counted, then the bands.
    In either order of the facts, with every later condition present too.
    """
    first = STAGE_ONE[condition]

    for deals in ([first, OD9, UNPRICED], [UNPRICED, OD9, first]):
        for call in (lambda deals=deals: check_data(deals, [UNKNOWN_BAND], STAGES),
                     lambda deals=deals: view_of(deals, rates, bands=[UNKNOWN_BAND])):
            error = refused(call)
            assert (error.entity, error.source_ids) == ("deals", ("D-82",))
            assert error.condition in {RESERVED_KEY, STAGE_OUTSIDE_VOCABULARY}


def test_a_stage_outside_the_vocabulary_names_the_open_valued_deal_and_not_the_closed_one(rates):
    """OD-M3-1: both carry the same condition, and stage 1's own deals are the ones named."""
    error = refused(view_of, [OD9, STAGE_ONE["a stage outside the vocabulary on an open valued "
                                             "deal"]], rates)

    assert (error.condition, error.source_ids) == ("STAGE_OUTSIDE_VOCABULARY", ("D-82",))
    assert refused(view_of, [OD9], rates).source_ids == ("D-90",)


def test_the_frozen_types_refusal_keeps_its_place_before_od9s_check(rates):
    """
    OD-M3-1, "how stage 1 is read": a refusal by the frozen MoneyValue is the
    last thing stage 1 raises, and it comes before OD-9's check and before
    the bands. It is neither caught nor translated.
    """
    for deals in ([OUTSIDE_D1, OD9, UNPRICED], [UNPRICED, OD9, OUTSIDE_D1]):
        for call in (lambda deals=deals: check_data(deals, [UNKNOWN_BAND], STAGES),
                     lambda deals=deals: view_of(deals, rates, bands=[UNKNOWN_BAND])):
            with pytest.raises(ContractViolationError, match="'XXX' is not a configured"):
                call()


def test_od9s_condition_wins_over_an_unknown_band_and_names_deals(rates):
    for deals in ([deal("D-1"), OD9, UNPRICED], [UNPRICED, OD9, deal("D-1")]):
        for call in (lambda deals=deals: check_data(deals, [UNKNOWN_BAND], STAGES),
                     lambda deals=deals: view_of(deals, rates, bands=[UNKNOWN_BAND])):
            error = refused(call)
            assert (error.condition, error.entity, error.source_ids) == (
                "STAGE_OUTSIDE_VOCABULARY", "deals", ("D-90",))


def test_an_unknown_band_wins_over_a_missing_rate_on_the_builders(rates):
    """
    Plan 0.14 leaves this one to the implementation on a pure builder. Here
    every data-validity condition comes before any conversion, as it does
    through the service.
    """
    for call in (lambda: check_data([UNPRICED], [UNKNOWN_BAND], STAGES),
                 lambda: view_of([UNPRICED], rates, bands=[UNKNOWN_BAND]),
                 lambda: build([UNPRICED], rates, bands=[UNKNOWN_BAND])):
        assert refused(call).entity == "customers"


def test_check_data_needs_no_rate_and_passes_what_only_lacks_one(rates):
    """Plan A14.5: the three checks need the facts, the vocabulary and the bands, and no rate."""
    assert check_data([UNPRICED, deal("D-1")], [band("CUST-900", "WATCH")], STAGES) is None
    assert list(inspect.signature(check_data).parameters) == [
        "facts", "bands", "stage_vocabulary"]
    with pytest.raises(FxRateMissingError) as raised:
        view_of([UNPRICED, deal("D-1")], rates)
    assert raised.value.currencies == ("GBP",)
    assert check_data(iter([deal("D-1")]), iter([]), STAGES) is None


def test_nothing_is_converted_until_every_condition_has_passed(rates, monkeypatch):
    """Each condition is examined over everything before a figure exists."""
    measured = []
    monkeypatch.setattr(aggregation, "deal_values", lambda *args: measured.append(args))

    for deals, stored in (([deal("D-1"), OD9], []), ([deal("D-1")], [UNKNOWN_BAND])):
        with pytest.raises(PipelineDataError):
            view_of(deals, rates, bands=stored)
    assert measured == []


# ---------------------------------------------------------------------------
# The view (plan A14), in full, on a book small enough to work by hand
# ---------------------------------------------------------------------------

HAND_BOOK = [
    deal("D-1", stage="negotiation", amount="1000.00", currency="INR", probability="50.00",
         expected=date(2026, 10, 15), owner="EMP-1", customer="CUST-1"),
    deal("D-2", stage="qualification", amount="10.00", currency="USD", probability="25.00",
         expected=None, owner=None, owner_key="EMP-404", customer=None, customer_key=None),
    deal("D-3", stage="won", is_active=False, amount="99.00", currency="INR",
         probability="100.00", expected=date(2026, 1, 5), owner="EMP-1", customer="CUST-1"),
    deal("D-4", stage="negotiation", amount=None, currency="EUR", probability="10.00",
         expected=date(2026, 11, 1), owner="EMP-1", customer="CUST-1"),
]
HAND_BANDS = [band("CUST-1", "WATCH", True)]
MONTHS = ["2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "2027-04",
          "2027-05", "2027-06", "2027-07", "2027-08"]


def empty_bucket(key: str, **added) -> dict:
    return {"key": key, "deal_count": 0, "deal_ids": [], "native": [],
            "base": {"currency": "INR", "unweighted": "0", "weighted": "0"}, **added}


def one_deal_bucket(key: str, source_id: str, **added) -> dict:
    figures = {
        "D-1": ([{"currency": "INR", "unweighted": "1000", "weighted": "500"}],
                {"currency": "INR", "unweighted": "1000", "weighted": "500"}),
        "D-2": ([{"currency": "USD", "unweighted": "10", "weighted": "2.5"}],
                {"currency": "INR", "unweighted": "15", "weighted": "3.75"}),
    }[source_id]
    return {"key": key, "deal_count": 1, "deal_ids": [source_id], "native": figures[0],
            "base": figures[1], **added}


def hand_concentration(first: str, second: str, measure: str) -> dict:
    """By hand: 1000 and 15 of 1015, and 500 and 3.75 of 503.75."""
    figures = {
        "unweighted": ("1015", "1000", "0.9852", "15", "0.0148", "0.9709"),
        "weighted": ("503.75", "500", "0.9926", "3.75", "0.0074", "0.9852"),
    }[measure]
    return {
        "currency": "INR", "rate_set_version": "by-hand", "total": figures[0], "holder_count": 2,
        "top": [{"key": first, "pseudo": False, "amount": figures[1], "share": figures[2]},
                {"key": second, "pseudo": True, "amount": figures[3], "share": figures[4]}],
        "cumulative": [{"holders": 1, "share": figures[2]}, {"holders": 3, "share": "1"},
                       {"holders": 5, "share": "1"}],
        "hhi": figures[5], "reason": None,
    }


def test_the_view_of_a_small_book_is_exactly_this(plain_rates):
    """
    Plan A14 in full, C-36: every object, key, type, order and text, with
    each figure worked by hand. 10.00 USD at 25% is 2.50, and at 1.5 the two
    convert to 15.00 and 3.75. A dec has no trailing zeros.
    """
    view = view_of(HAND_BOOK, plain_rates, bands=HAND_BANDS)

    assert view == {
        "view_version": 1,
        "scope": {
            "source_system": "csv_demo", "as_of": "2026-09-18", "layer1_fingerprint": "0" * 64,
            "as_of_source": "EXPLICIT",
            "entity_counts": {"customers": 0, "deals": 0, "documents": 0, "employees": 0,
                              "organizations": 0, "projects": 0, "support_tickets": 0},
        },
        "versions": {"pipeline_version": 1, "rules_version": 3, "linker_version": "L-2"},
        "fx": {
            "base_currency": "INR", "rate_set_version": "by-hand",
            "rate_as_of_date": "2026-10-01", "rate_set_digest": plain_rates.digest,
            "standing": "STATED_ASSUMPTION", "source_note": "a rate set constructed for a test",
            "rates": [{"currency": "INR", "rate_to_base": "1"},
                      {"currency": "USD", "rate_to_base": "1.5"}],
            "used_currencies": ["INR", "USD"],
        },
        "deal_counts": {
            "total": 4, "open": 3, "open_valued": 2, "open_unvalued": 1, "closed": 1,
            "unvalued_deal_ids": ["D-4"],
            "by_stage": [{"stage": "negotiation", "total": 2, "open": 2, "closed": 0},
                         {"stage": "qualification", "total": 1, "open": 1, "closed": 0},
                         {"stage": "won", "total": 1, "open": 0, "closed": 1},
                         {"stage": "UNSTAGED", "total": 0, "open": 0, "closed": 0}],
        },
        "open_pipeline": {
            "key": "ALL", "deal_count": 2, "deal_ids": ["D-1", "D-2"],
            "native": [{"currency": "INR", "unweighted": "1000", "weighted": "500"},
                       {"currency": "USD", "unweighted": "10", "weighted": "2.5"}],
            "base": {"currency": "INR", "unweighted": "1015", "weighted": "503.75"},
        },
        "by_currency": [one_deal_bucket("INR", "D-1", rate_to_base="1"),
                        one_deal_bucket("USD", "D-2", rate_to_base="1.5")],
        "by_stage": [one_deal_bucket("negotiation", "D-1"),
                     one_deal_bucket("qualification", "D-2"), empty_bucket("won")],
        "by_owner": [
            one_deal_bucket("EMP-1", "D-1", kind="EMPLOYEE", basis="SOURCE_KEY_JOIN",
                            carrier_field="deals.owner_source_id", unresolved_keys=[]),
            empty_bucket("UNASSIGNED", kind="UNASSIGNED", basis=None, carrier_field=None,
                         unresolved_keys=[]),
            one_deal_bucket("UNRESOLVED", "D-2", kind="UNRESOLVED", basis=None,
                            carrier_field=None, unresolved_keys=["EMP-404"]),
        ],
        "by_expected_close": [
            empty_bucket("OVERDUE", kind="OVERDUE"),
            empty_bucket("2026-09", kind="MONTH"),
            one_deal_bucket("2026-10", "D-1", kind="MONTH"),
            *(empty_bucket(month, kind="MONTH") for month in MONTHS[2:]),
            empty_bucket("LATER", kind="LATER"),
            one_deal_bucket("UNDATED", "D-2", kind="UNDATED"),
        ],
        "by_risk_band": [
            empty_bucket("CRITICAL", customer_count=0, customer_ids=[]),
            empty_bucket("ELEVATED", customer_count=0, customer_ids=[]),
            one_deal_bucket("WATCH", "D-1", customer_count=1, customer_ids=["CUST-1"]),
            empty_bucket("NONE", customer_count=0, customer_ids=[]),
            empty_bucket("UNASSESSED", customer_count=0, customer_ids=[]),
            one_deal_bucket("UNLINKED", "D-2", customer_count=0, customer_ids=[]),
        ],
        "by_customer": [
            one_deal_bucket("CUST-1", "D-1", kind="CUSTOMER", band="WATCH",
                            executive_worthy=True),
            one_deal_bucket("UNLINKED", "D-2", kind="UNLINKED", band=None,
                            executive_worthy=None),
        ],
        "risk_coincidence": ["CUST-1"],
        "concentration": {
            "by_customer": {"unweighted": hand_concentration("CUST-1", "UNLINKED", "unweighted"),
                            "weighted": hand_concentration("CUST-1", "UNLINKED", "weighted")},
            "by_owner": {"unweighted": hand_concentration("EMP-1", "UNRESOLVED", "unweighted"),
                         "weighted": hand_concentration("EMP-1", "UNRESOLVED", "weighted")},
        },
        "open_deals": [
            {"id": "D-1", "state": "OPEN_VALUED", "stage": "negotiation", "is_active": True,
             "amount": "1000", "currency": "INR", "probability": "50",
             "expected_close_date": "2026-10-15", "owner_source_id": "EMP-1", "owner": "EMP-1",
             "customer_source_id": "CUST-1", "customer": "CUST-1", "native_weighted": "500",
             "base_unweighted": "1000", "base_weighted": "500"},
            {"id": "D-2", "state": "OPEN_VALUED", "stage": "qualification", "is_active": True,
             "amount": "10", "currency": "USD", "probability": "25",
             "expected_close_date": None, "owner_source_id": "EMP-404", "owner": None,
             "customer_source_id": None, "customer": None, "native_weighted": "2.5",
             "base_unweighted": "15", "base_weighted": "3.75"},
            {"id": "D-4", "state": "OPEN_UNVALUED", "stage": "negotiation", "is_active": True,
             "amount": None, "currency": "EUR", "probability": "10",
             "expected_close_date": "2026-11-01", "owner_source_id": "EMP-1", "owner": "EMP-1",
             "customer_source_id": "CUST-1", "customer": "CUST-1", "native_weighted": None,
             "base_unweighted": None, "base_weighted": None},
        ],
        "closed_deals": [{"id": "D-3", "stage": "won", "is_active": False}],
        "data_quality": [
            {"code": "CUSTOMER_KEY_MISSING", "entity": "deals", "id": "D-2",
             "fields": ["customer_source_id"], "key": None},
            {"code": "EXPECTED_CLOSE_MISSING", "entity": "deals", "id": "D-2",
             "fields": ["expected_close_date"], "key": None},
            {"code": "INCOMPLETE_DEAL", "entity": "deals", "id": "D-4", "fields": ["amount"],
             "key": None},
            {"code": "OWNER_KEY_UNRESOLVED", "entity": "deals", "id": "D-2",
             "fields": ["owner_source_id"], "key": "EMP-404"},
        ],
        "limitations": ["NO_LOST_STAGE", "NO_ACTUAL_CLOSE_DATE", "NO_DEAL_HISTORY",
                        "FX_STATED_ASSUMPTION", "SHARES_FOLLOW_RATES",
                        "SOURCE_STATED_PROBABILITY", "SINGLE_SOURCE_SYSTEM", "PERIOD_HORIZON",
                        "BAND_IS_NOT_MONEY"],
    }


def test_the_hand_worked_shares_of_the_small_book_are_the_oracles():
    """The literals above, against exact arithmetic that uses no application code."""
    assert exact_concentration([("CUST-1", "1000.00"), ("UNLINKED", "15.00")]) == {
        "holder_count": 2, "top": [("CUST-1", "0.9852"), ("UNLINKED", "0.0148")],
        "cumulative": [(1, "0.9852"), (3, "1"), (5, "1")], "hhi": "0.9709"}
    assert exact_concentration([("CUST-1", "500.00"), ("UNLINKED", "3.75")]) == {
        "holder_count": 2, "top": [("CUST-1", "0.9926"), ("UNLINKED", "0.0074")],
        "cumulative": [(1, "0.9926"), (3, "1"), (5, "1")], "hhi": "0.9852"}
    assert tuple(str(value) for value in exact_values("10.00", "25.00", "1.5")) == (
        "10.00", "2.50", "15.00", "3.75")
    assert Fraction(1000225, 1030225) > Fraction(97085, 100000)


#: Plan A14, restated: the keys of every object of the view, in the plan's order.
TOP_KEYS = ["view_version", "scope", "versions", "fx", "deal_counts", "open_pipeline",
            "by_currency", "by_stage", "by_owner", "by_expected_close", "by_risk_band",
            "by_customer", "risk_coincidence", "concentration", "open_deals", "closed_deals",
            "data_quality", "limitations"]
BUCKET_KEYS = ["key", "deal_count", "deal_ids", "native", "base"]
ADDED_KEYS = {
    "open_pipeline": [], "by_currency": ["rate_to_base"], "by_stage": [],
    "by_owner": ["kind", "basis", "carrier_field", "unresolved_keys"],
    "by_expected_close": ["kind"], "by_risk_band": ["customer_count", "customer_ids"],
    "by_customer": ["kind", "band", "executive_worthy"],
}
OPEN_DEAL_KEYS = ["id", "state", "stage", "is_active", "amount", "currency", "probability",
                  "expected_close_date", "owner_source_id", "owner", "customer_source_id",
                  "customer", "native_weighted", "base_unweighted", "base_weighted"]
CONCENTRATION_KEYS = ["currency", "rate_set_version", "total", "holder_count", "top",
                      "cumulative", "hhi", "reason"]


def walk(value):
    """Every value of a JSON structure, depth first, with the object keys as they come."""
    yield value
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from walk(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from walk(inner)


@pytest.mark.parametrize("deals, stored", [
    ([], []), (HAND_BOOK, HAND_BANDS), (PORTFOLIO, PORTFOLIO_BANDS), (COUNT_BOOK, []),
    (CUSTOMER_BOOK, CUSTOMER_BANDS)],
    ids=["empty", "by hand", "portfolio", "counts", "customers"])
def test_every_key_of_the_view_is_always_present_and_every_value_is_json(rates, deals, stored):
    """
    Plan A14.1 items 1 and 5: objects, lists, strings, integers, booleans
    and null, and no float anywhere; every key of every object always
    present, on any input.
    """
    view = view_of(deals, rates, bands=stored)

    assert list(view) == TOP_KEYS and len(TOP_KEYS) == 18
    assert all(type(value) in {dict, list, str, int, bool, type(None)} for value in walk(view))
    assert not [value for value in walk(view) if isinstance(value, float | Decimal | tuple)]
    assert list(view["scope"]) == ["source_system", "as_of", "layer1_fingerprint",
                                   "as_of_source", "entity_counts"]
    assert list(view["versions"]) == ["pipeline_version", "rules_version", "linker_version"]
    assert list(view["fx"]) == ["base_currency", "rate_set_version", "rate_as_of_date",
                                "rate_set_digest", "standing", "source_note", "rates",
                                "used_currencies"]
    assert list(view["deal_counts"]) == ["total", "open", "open_valued", "open_unvalued",
                                         "closed", "unvalued_deal_ids", "by_stage"]
    for name, added in ADDED_KEYS.items():
        buckets = [view[name]] if name == "open_pipeline" else view[name]
        for bucket in buckets:
            assert list(bucket) == [*BUCKET_KEYS, *added], name
            assert list(bucket["base"]) == ["currency", "unweighted", "weighted"]
            assert all(list(amount) == ["currency", "unweighted", "weighted"]
                       for amount in bucket["native"])
    assert list(view["concentration"]) == ["by_customer", "by_owner"]
    for pair in view["concentration"].values():
        assert list(pair) == ["unweighted", "weighted"]
        for block in pair.values():
            assert list(block) == CONCENTRATION_KEYS
            assert all(list(holder) == ["key", "pseudo", "amount", "share"]
                       for holder in block["top"])
            assert all(list(point) == ["holders", "share"] for point in block["cumulative"])
    assert all(list(entry) == OPEN_DEAL_KEYS for entry in view["open_deals"])
    assert all(list(entry) == ["id", "stage", "is_active"] for entry in view["closed_deals"])
    assert all(list(note) == ["code", "entity", "id", "fields", "key"]
               for note in view["data_quality"])
    json.dumps(view, allow_nan=False)


def test_the_empty_view_is_exactly_plan_a14_11(plain_rates):
    """
    C-41, constructed: with no deal every count is zero with its stage rows
    present, every always-present bucket is empty, the four concentration
    blocks are in their zero form, and fx, scope, versions and limitations
    are as always. With no band the scope note is the only note.
    """
    view = view_of([], plain_rates)
    zero = {"currency": "INR", "rate_set_version": "by-hand", "total": "0", "holder_count": 0,
            "top": [], "cumulative": [], "hhi": None, "reason": "NO_OPEN_EXPOSURE"}

    assert view["deal_counts"] == {
        "total": 0, "open": 0, "open_valued": 0, "open_unvalued": 0, "closed": 0,
        "unvalued_deal_ids": [],
        "by_stage": [{"stage": stage, "total": 0, "open": 0, "closed": 0}
                     for stage in ("negotiation", "qualification", "won", "UNSTAGED")]}
    assert view["open_pipeline"] == empty_bucket("ALL")
    assert view["by_currency"] == []
    assert view["by_stage"] == [empty_bucket(stage) for stage in STAGES]
    assert view["by_owner"] == [
        empty_bucket(kind, kind=kind, basis=None, carrier_field=None, unresolved_keys=[])
        for kind in ("UNASSIGNED", "UNRESOLVED")]
    assert view["by_expected_close"] == [
        empty_bucket("OVERDUE", kind="OVERDUE"),
        *(empty_bucket(month, kind="MONTH") for month in MONTHS),
        empty_bucket("LATER", kind="LATER"), empty_bucket("UNDATED", kind="UNDATED")]
    assert view["by_risk_band"] == [empty_bucket(key, customer_count=0, customer_ids=[])
                                    for key in BAND_ORDER]
    assert view["by_customer"] == [
        empty_bucket("UNLINKED", kind="UNLINKED", band=None, executive_worthy=None)]
    assert view["risk_coincidence"] == []
    assert view["concentration"] == {"by_customer": {"unweighted": zero, "weighted": zero},
                                     "by_owner": {"unweighted": zero, "weighted": zero}}
    assert (view["open_deals"], view["closed_deals"]) == ([], [])
    assert view["data_quality"] == [
        {"code": "NO_ASSESSMENT_FOR_SCOPE", "entity": None, "id": None, "fields": [],
         "key": None}]
    assert view["fx"]["used_currencies"] == [] and len(view["fx"]["rates"]) == 2
    assert (view["fx"]["base_currency"], view["fx"]["rate_set_version"]) == ("INR", "by-hand")
    assert len(view["limitations"]) == 9 and view["view_version"] == 1
    assert view["versions"] == {"pipeline_version": 1, "rules_version": 3,
                                "linker_version": "L-2"}


def test_a_scope_whose_deals_are_none_of_them_open_and_valued_has_the_same_empty_partitions(
        plain_rates):
    """
    C-41, plan A17.2: the partitions and the four blocks are in the empty
    form, while deal_counts, open_deals and closed_deals state those deals.
    """
    deals = [deal("D-1", is_active=False, stage="won"), deal("D-2", amount=None),
             deal("D-3", amount="-4.00"), deal("D-4", stage=None, is_active=False)]
    view = view_of(deals, plain_rates)
    empty = view_of([], plain_rates)

    for name in ("open_pipeline", "by_currency", "by_stage", "by_owner", "by_expected_close",
                 "by_risk_band", "by_customer", "risk_coincidence", "concentration"):
        assert view[name] == empty[name], name
    assert view["deal_counts"]["total"] == 4 and view["deal_counts"]["open_unvalued"] == 2
    assert [entry["id"] for entry in view["open_deals"]] == ["D-2", "D-3"]
    assert [entry["state"] for entry in view["open_deals"]] == ["OPEN_UNVALUED"] * 2
    assert view["open_deals"][1]["amount"] == "-4"
    assert view["closed_deals"] == [{"id": "D-1", "stage": "won", "is_active": False},
                                    {"id": "D-4", "stage": None, "is_active": False}]


# ---------------------------------------------------------------------------
# The scope note (plan A13.2 item 4, OD-M3-3; C-42, constructed)
# ---------------------------------------------------------------------------

SCOPE_NOTE = {"code": "NO_ASSESSMENT_FOR_SCOPE", "entity": None, "id": None, "fields": [],
              "key": None}


def test_the_scope_note_is_stated_when_no_band_was_read_and_only_then(plain_rates):
    """
    C-42: its one rule. Present with no band, whatever deals the scope
    holds. Absent with one band or more, whoever the rows belong to and
    whether or not any of those customers holds an open valued deal.
    """
    assert NO_ASSESSMENT_FOR_SCOPE == "NO_ASSESSMENT_FOR_SCOPE"
    for deals in ([], HAND_BOOK, COUNT_BOOK):
        assert SCOPE_NOTE in view_of(deals, plain_rates)["data_quality"]
        for stored in ([band("CUST-NOBODY", "NONE")], [band("CUST-1", "WATCH")],
                       [band("CUST-900", "CRITICAL"), band("CUST-NOBODY", "NONE")]):
            notes = view_of(deals, plain_rates, bands=stored)["data_quality"]
            assert SCOPE_NOTE not in notes
            assert not [note for note in notes if note["id"] is None]
    assert view_of([], plain_rates, bands=[band("CUST-NOBODY")])["data_quality"] == []


def test_a_linked_deal_whose_customer_has_no_returned_row_is_still_unassessed(plain_rates):
    """Plan A12.3 item 4: the note is the scope's. Coverage is per customer."""
    view = view_of(HAND_BOOK, plain_rates, bands=[band("CUST-NOBODY", "CRITICAL")])

    assert keyed(view["by_risk_band"])["UNASSESSED"]["deal_ids"] == ["D-1"]
    assert keyed(view["by_customer"])["CUST-1"]["band"] == "UNASSESSED"
    assert keyed(view["by_customer"])["CUST-1"]["executive_worthy"] is None
    assert view["risk_coincidence"] == []


def test_the_notes_are_ordered_by_code_and_then_by_id_with_the_scope_note_first_in_its_code(
        plain_rates):
    """Plan A13.2 item 2: code ascending, then id ascending, a null id first."""
    deals = [deal("D-b", expected=None), deal("D-A", expected=None), deal("D-10", amount=None),
             deal("D-9", amount=None), deal("D-a", stage="won"),
             deal("D-é", owner=None, owner_key=None, expected=None)]

    for arranged in (deals, list(reversed(deals))):
        notes = view_of(arranged, plain_rates)["data_quality"]
        assert [(note["code"], note["id"]) for note in notes] == [
            ("EXPECTED_CLOSE_MISSING", "D-A"), ("EXPECTED_CLOSE_MISSING", "D-b"),
            ("EXPECTED_CLOSE_MISSING", "D-é"), ("INCOMPLETE_DEAL", "D-10"),
            ("INCOMPLETE_DEAL", "D-9"), ("NO_ASSESSMENT_FOR_SCOPE", None),
            ("OWNER_KEY_MISSING", "D-é"), ("STAGE_ACTIVITY_MISMATCH", "D-a")]
    assert view_module._by_code_and_id({"code": "X", "id": None}) < (
        view_module._by_code_and_id({"code": "X", "id": ""}))


def test_every_deal_level_note_is_stated_in_the_shape_of_the_plan(plain_rates):
    """Plan A14.9: code, entity deals, id, fields as a list, and the unresolved key."""
    notes = view_of(HAND_BOOK, plain_rates)["data_quality"]

    assert {note["entity"] for note in notes if note["id"] is not None} == {"deals"}
    assert all(type(note["fields"]) is list for note in notes)
    assert [note["key"] for note in notes if note["code"] == "OWNER_KEY_UNRESOLVED"] == [
        "EMP-404"]


# ---------------------------------------------------------------------------
# Limitations (plan A13.1; named test 6)
# ---------------------------------------------------------------------------

#: Plan A13.1's nine texts, restated character for character, placeholders filled.
TEXTS = [
    ("NO_LOST_STAGE",
     "The deal-stage vocabulary is negotiation, qualification, won. It records no lost outcome, "
     "so no win rate and no stage-conversion figure can be stated, and none is."),
    ("NO_ACTUAL_CLOSE_DATE",
     "A closed deal carries an expected close date only. No actual close date exists."),
    ("NO_DEAL_HISTORY",
     "Deals carry no creation or stage-change date. The pipeline is that of the data snapshot; "
     "as_of does not rewind it."),
    ("FX_STATED_ASSUMPTION",
     "Base-currency figures use rate set by-hand, stated for 2026-10-01. The rates are an "
     "assumption, not a market quotation, and are not matched to as_of."),
    ("SHARES_FOLLOW_RATES",
     "Concentration shares are computed in the base currency and change with the rate set."),
    ("SOURCE_STATED_PROBABILITY",
     "Weighted exposure multiplies each amount by the probability the source system states. It "
     "is not a forecast."),
    ("SINGLE_SOURCE_SYSTEM",
     "Only source system csv_demo is included. Nothing is aggregated across source systems."),
    ("PERIOD_HORIZON",
     "Expected-close periods are the twelve calendar months from the month of as_of. Later dates "
     "are grouped as LATER."),
    ("BAND_IS_NOT_MONEY", "A risk band groups exposure and is never applied to an amount."),
]


def test_the_nine_limitations_are_stated_in_order_with_their_exact_texts(plain_rates):
    """Named test 6 [R], plan A13.1: the codes in the view, the texts beside it."""
    view = view_of(HAND_BOOK, plain_rates, bands=HAND_BANDS)

    assert view["limitations"] == [code for code, _ in TEXTS]
    assert limitation_texts(view) == [{"code": code, "text": text} for code, text in TEXTS]
    assert [code for code, _ in LIMITATIONS] == [code for code, _ in TEXTS]
    assert type(LIMITATIONS) is tuple and len(LIMITATIONS) == 9


def test_no_lost_stage_is_absent_when_the_vocabulary_holds_lost(plain_rates):
    """
    Named test 6: with a vocabulary containing `lost` passed to the builder
    the code is absent, from the view and from the texts, and the other
    eight are as they were. A stage that only resembles it does not count.
    """
    with_lost = view_of([], plain_rates, stages=[*STAGES, "lost"])

    assert with_lost["limitations"] == [code for code, _ in TEXTS[1:]]
    assert limitation_texts(with_lost) == [{"code": code, "text": text}
                                           for code, text in TEXTS[1:]]
    for stages in ([*STAGES, "Lost"], [*STAGES, "lost "], ["closed_lost"], []):
        assert view_of([], plain_rates, stages=stages)["limitations"][0] == "NO_LOST_STAGE"


def test_the_stages_of_the_first_text_are_the_vocabularys_ascending(plain_rates):
    view = view_of([], plain_rates, stages=["won", "Zeta", "alpha", "é"])

    assert limitation_texts(view)[0]["text"].startswith(
        "The deal-stage vocabulary is Zeta, alpha, won, é. It records")


def test_a_placeholder_is_filled_with_the_views_own_value_and_never_read_as_one(plain_rates):
    """
    Plan A21, reflected input: the source system is the request's own value.
    Braces in it are stated as they are and are not a placeholder.
    """
    view = view_of([], plain_rates, source_system="{rate_set_version} {0} {stages!r}")
    texts = {entry["code"]: entry["text"] for entry in limitation_texts(view)}

    assert texts["SINGLE_SOURCE_SYSTEM"] == (
        "Only source system {rate_set_version} {0} {stages!r} is included. Nothing is "
        "aggregated across source systems.")
    assert view["scope"]["source_system"] == "{rate_set_version} {0} {stages!r}"


def test_no_key_of_the_view_names_a_win_rate_a_conversion_or_a_forecast(rates):
    """Named test 6, plan A30: nothing out of scope has a key."""
    view = view_of(PORTFOLIO, rates, bands=PORTFOLIO_BANDS)
    keys = {value for value in walk(view) if isinstance(value, str)} & {
        key for value in walk(view) if isinstance(value, dict) for key in value}

    assert len(keys) > 60
    for word in ("win", "conversion", "forecast", "quota", "territory", "predict", "score",
                 "adjusted", "expected_value"):
        assert not [key for key in keys if word in key.lower()], word


# ---------------------------------------------------------------------------
# Base labelling (named test 5)
# ---------------------------------------------------------------------------


def test_every_base_aggregate_names_the_views_base_currency(tmp_path):
    """
    Named test 5 [R]: every `base` Amount and every Concentration block
    names a currency equal to fx.base_currency. The rate-set version and
    digest are named once, in fx, and again only in each concentration
    block. An open deal's base values carry no currency of their own.
    """
    in_dollars = rate_set(tmp_path, {"INR": "0.012", "EUR": "1.1"}, base="USD", version="usd")
    view = view_of(PORTFOLIO, in_dollars, bands=PORTFOLIO_BANDS)
    base = view["fx"]["base_currency"]

    assert base == "USD"
    bases = [value["base"] for value in walk(view) if isinstance(value, dict) and "base" in value]
    assert len(bases) == 1 + sum(len(view[name]) for name in ADDED_KEYS if name != "open_pipeline")
    assert {amount["currency"] for amount in bases} == {base}
    blocks = [block for pair in view["concentration"].values() for block in pair.values()]
    assert {block["currency"] for block in blocks} == {base}
    assert {block["rate_set_version"] for block in blocks} == {view["fx"]["rate_set_version"]}

    owners = [value for value in walk(view)
              if isinstance(value, dict) and "rate_set_version" in value]
    assert len(owners) == 1 + len(blocks), "fx, and the four blocks, and nothing else"
    assert len([value for value in walk(view)
                if isinstance(value, dict) and "rate_set_digest" in value]) == 1
    assert view["fx"]["rate_set_digest"] == in_dollars.digest
    for entry in view["open_deals"]:
        assert not [key for key in entry if "currency" in key and key != "currency"]
        assert entry["currency"] != base or entry["id"] in {"D-02", "D-03", "D-07", "D-10"}


# ---------------------------------------------------------------------------
# FX liveness (named test 8), on the builders
# ---------------------------------------------------------------------------


def test_a_changed_usd_rate_changes_every_base_figure_with_a_usd_deal_and_no_native_one(tmp_path):
    """
    Named test 8: the rate is live. Every base figure that includes a USD
    deal moves, every native figure and every figure with no USD deal
    stays, and the digest and the hash move with it.
    """
    before = view_of(PORTFOLIO, rate_set(tmp_path, RATES, version="one"), bands=PORTFOLIO_BANDS)
    after = view_of(PORTFOLIO, rate_set(tmp_path, {**RATES, "USD": "90.5"}, version="one"),
                    bands=PORTFOLIO_BANDS)
    usd = {entry["id"] for entry in before["open_deals"] if entry["currency"] == "USD"
           and entry["state"] == "OPEN_VALUED"}

    assert usd == {"D-02", "D-03", "D-07"}
    for name in ADDED_KEYS:
        pairs = ([(before[name], after[name])] if name == "open_pipeline"
                 else list(zip(before[name], after[name], strict=True)))
        for old, new in pairs:
            assert (old["key"], old["deal_ids"], old["native"]) == (
                new["key"], new["deal_ids"], new["native"]), name
            assert (old["base"] != new["base"]) is bool(usd & set(old["deal_ids"])), (
                name, old["key"])
    for old, new in zip(before["open_deals"], after["open_deals"], strict=True):
        moved = old["id"] in usd
        assert (old["base_unweighted"] != new["base_unweighted"]) is moved
        assert (old["base_weighted"] != new["base_weighted"]) is moved
        assert (old["amount"], old["native_weighted"]) == (new["amount"], new["native_weighted"])
    assert before["deal_counts"] == after["deal_counts"]
    assert before["fx"]["rate_set_digest"] != after["fx"]["rate_set_digest"]
    assert view_hash(before) != view_hash(after)
    assert keyed(after["by_currency"])["USD"]["rate_to_base"] == "90.5"


# ---------------------------------------------------------------------------
# The hash, and what is rendered outside it (plan A14.10)
# ---------------------------------------------------------------------------


def test_the_hash_is_the_sha256_of_the_views_canonical_json(rates):
    """Plan A14.10 items 2 and 3, computed here with the standard library alone."""
    view = view_of(PORTFOLIO, rates, bands=PORTFOLIO_BANDS)
    canonical = json.dumps(view, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                           allow_nan=False)

    assert view_hash(view) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert len(view_hash(view)) == 64 and view_hash(view) == view_hash(json.loads(canonical))
    assert view_hash(view) == view_hash(dict(reversed(list(view.items())))), (
        "key order is not significant: the canonical form sorts")


def test_the_hash_covers_every_part_of_the_view_and_nothing_outside_it(rates):
    """Plan A14.10: any stated value moves it. The texts and the citations are not in it."""
    view = view_of(PORTFOLIO, rates, bands=PORTFOLIO_BANDS)
    original = view_hash(view)

    for key in TOP_KEYS:
        changed = json.loads(json.dumps(view))
        changed[key] = None
        assert view_hash(changed) != original, key
    assert not {"limitation_texts", "citations", "view_hash"} & set(view)
    non_ascii = view_of([deal("DEAL-é")], rates)
    assert view_hash(non_ascii) == hashlib.sha256(json.dumps(
        non_ascii, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8")).hexdigest()


def test_what_the_service_returns_cannot_be_reassigned():
    built = PipelineView(view={}, view_hash="0" * 64, limitation_texts=[], citations=[])

    assert [field.name for field in dataclasses.fields(PipelineView)] == [
        "view", "view_hash", "limitation_texts", "citations"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        built.view_hash = "1" * 64  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Citations (plan A18.2; named test 21, on the builders)
# ---------------------------------------------------------------------------


def test_every_deal_value_the_view_states_is_cited_and_nothing_else_is(plain_rates):
    """
    Plan A18.2 item 2. An open deal: is_active always, each stored value its
    entry states, and customer_id where the customer is resolved. A closed
    deal: is_active, and its stage. Ordered by id and then by field.
    """
    view = view_of(HAND_BOOK, plain_rates, bands=HAND_BANDS)
    cited = citations(view)

    assert [(entry["id"], entry["field"]) for entry in cited] == [
        ("D-1", "amount"), ("D-1", "currency"), ("D-1", "customer_id"),
        ("D-1", "customer_source_id"), ("D-1", "expected_close_date"), ("D-1", "is_active"),
        ("D-1", "owner_source_id"), ("D-1", "probability"), ("D-1", "stage"),
        ("D-2", "amount"), ("D-2", "currency"), ("D-2", "is_active"),
        ("D-2", "owner_source_id"), ("D-2", "probability"), ("D-2", "stage"),
        ("D-3", "is_active"), ("D-3", "stage"),
        ("D-4", "currency"), ("D-4", "customer_id"), ("D-4", "customer_source_id"),
        ("D-4", "expected_close_date"), ("D-4", "is_active"), ("D-4", "owner_source_id"),
        ("D-4", "probability"), ("D-4", "stage")]
    assert all(entry == {"kind": "record", "entity": "deals", "id": entry["id"],
                         "field": entry["field"]} for entry in cited)
    assert all(list(entry) == ["kind", "entity", "id", "field"] for entry in cited)


def test_a_closed_deal_with_no_stage_cites_its_activity_alone(plain_rates):
    view = view_of([deal("D-1", stage=None, is_active=False),
                    deal("D-2", stage=None, amount=None, currency=None, probability=None,
                         expected=None, owner=None, owner_key=None, customer=None,
                         customer_key=None)], plain_rates)

    assert [(entry["id"], entry["field"]) for entry in citations(view)] == [
        ("D-1", "is_active"), ("D-2", "is_active")]
    assert citations(view_of([], plain_rates)) == []


def test_a_citation_is_built_through_the_frozen_type(plain_rates, monkeypatch):
    """Plan A18.2 item 1: only a citable field of `deals` can be named."""
    built = []
    frozen = view_module.RecordCitation

    def spy(*args):
        built.append(args)
        return frozen(*args)

    monkeypatch.setattr(view_module, "RecordCitation", spy)
    view = view_of(HAND_BOOK, plain_rates)

    assert len(citations(view)) == len(built) == 25
    assert {entity for entity, _, _ in built} == {"deals"}
    with pytest.raises(ContractViolationError):
        frozen("deals", "D-1", "ingested_at")


def test_the_citations_are_ordered_by_code_point_whatever_order_the_deals_arrive_in(plain_rates):
    deals = [deal("deal-2"), deal("DEAL-10"), deal("Deal-1"), deal("DEAL-2", is_active=False),
             deal("DEAL-é"), deal("DEAL-1")]

    for arranged in (deals, list(reversed(deals))):
        cited = citations(view_of(arranged, plain_rates))
        pairs = [(entry["id"], entry["field"]) for entry in cited]
        assert pairs == sorted(pairs)
        assert list(dict.fromkeys(entry["id"] for entry in cited)) == [
            "DEAL-1", "DEAL-10", "DEAL-2", "DEAL-é", "Deal-1", "deal-2"]


# ---------------------------------------------------------------------------
# Order (plan A14.1 item 6; C-39, constructed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arrange", [
    lambda rows: list(reversed(rows)),
    lambda rows: rows[3:] + rows[:3],
    lambda rows: rows[1::2] + rows[0::2],
    lambda rows: iter(rows),
    lambda rows: tuple(rows),
], ids=["reversed", "rotated", "odd then even", "an iterator", "a tuple"])
def test_the_facts_and_the_bands_in_any_order_give_one_view_and_one_hash(rates, arrange):
    """C-39: no order is taken from the order the facts or the band rows arrive in."""
    expected = view_of(PORTFOLIO, rates, bands=PORTFOLIO_BANDS)

    found = view_of(arrange(list(PORTFOLIO)), rates, bands=arrange(list(PORTFOLIO_BANDS)))

    assert found == expected
    assert view_hash(found) == view_hash(expected)
    assert json.dumps(found) == json.dumps(expected), "and each list in the same order"


def test_every_list_m3_adds_is_in_its_stated_order(rates):
    """
    C-39: ids, customers and keys that a case-insensitive or locale-aware
    order would arrange differently, in every list M3 adds.
    """
    names = ["cust-2", "CUST-10", "Cust-1", "CUST-2", "CUST-é", "CUST-1"]
    deals = [
        *(deal(f"deal-{index}" if index % 2 else f"DEAL-{index}", customer=customer,
               amount="10.00") for index, customer in enumerate(names)),
        deal("DEAL-z", is_active=False, stage="won"), deal("DEAL-Z", amount=None),
        deal("DEAL-é", is_active=False, stage=None), deal("Deal-9", amount="-1"),
    ]
    stored = [band(customer, "WATCH") for customer in names]

    for arranged, bands_ in ((deals, stored), (list(reversed(deals)), list(reversed(stored)))):
        view = view_of(arranged, rates, bands=bands_)
        ordered = ["CUST-1", "CUST-10", "CUST-2", "CUST-é", "Cust-1", "cust-2"]

        assert [bucket["key"] for bucket in view["by_risk_band"]] == BAND_ORDER
        assert keyed(view["by_risk_band"])["WATCH"]["customer_ids"] == ordered
        assert [bucket["key"] for bucket in view["by_customer"]] == [*ordered, "UNLINKED"]
        assert view["risk_coincidence"] == ordered
        top = view["concentration"]["by_customer"]["unweighted"]["top"]
        assert [holder["key"] for holder in top] == ordered[:5]
        assert [point["holders"] for point
                in view["concentration"]["by_owner"]["weighted"]["cumulative"]] == [1, 3, 5]
        assert [row["stage"] for row in view["deal_counts"]["by_stage"]] == [
            "negotiation", "qualification", "won", "UNSTAGED"]
        assert view["deal_counts"]["unvalued_deal_ids"] == ["DEAL-Z", "Deal-9"]
        assert [entry["id"] for entry in view["open_deals"]] == sorted(
            entry["id"] for entry in view["open_deals"])
        assert [entry["id"] for entry in view["closed_deals"]] == ["DEAL-z", "DEAL-é"]
        assert view["open_pipeline"]["deal_ids"] == sorted(view["open_pipeline"]["deal_ids"])
        assert [rate["currency"] for rate in view["fx"]["rates"]] == ["EUR", "INR", "USD"]


def test_the_used_currencies_are_those_of_the_open_valued_deals_ascending(rates):
    view = view_of([deal("D-1", currency="USD"), deal("D-2", currency="EUR"),
                    deal("D-3", currency="USD"), deal("D-4", currency="GBP", is_active=False),
                    deal("D-5", currency="JPY", amount=None)], rates)

    assert view["fx"]["used_currencies"] == ["EUR", "USD"]
    assert [rate["rate_to_base"] for rate in view["fx"]["rates"]] == ["91.123456", "1", "83.2575"]


# ---------------------------------------------------------------------------
# The text of a number (plan A14.1 item 2, A9.1 items 5 and 6; C-43)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("number", "text"), [
    ("0", "0"), ("0.00", "0"), ("-0.00", "0"), ("1000.00", "1000"), ("73442577.10", "73442577.1"),
    ("0.2060", "0.206"), ("1.0000", "1"), ("0.0001", "0.0001"), ("-1500.00", "-1500"),
    ("9999999999999.99", "9999999999999.99"), ("99999999794999899900000.21",
                                               "99999999794999899900000.21"),
    ("1E+3", "1000"), ("1E-8", "0.00000001"), ("90.00", "90"), ("100", "100"),
])
def test_a_dec_is_plain_notation_with_no_exponent_and_no_trailing_zeros(number, text):
    assert view_module._dec(Decimal(number)) == text


@pytest.mark.parametrize("hostile", HOSTILE, ids=HOSTILE_IDS)
def test_the_text_of_a_number_is_the_same_in_any_callers_context(hostile):
    """
    C-43: VS-01's decimal_text normalises in the context in force, so each
    text is taken in a context of its own with as many digits as the number
    holds. Nothing is rounded there, and the caller's context is left as set.
    """
    numbers = ["73442577.10", "99999999794999899900000.21", "0.2556", "1E+3", "0.00", "-25.00",
               "1234567890123456789012345678901234567890.12345678"]

    with localcontext(hostile()) as current:
        before = state_of(current)
        found = [view_module._dec(Decimal(number)) for number in numbers]
        after = state_of(current)

    assert found == ["73442577.1", "99999999794999899900000.21", "0.2556", "1000", "0", "-25",
                     "1234567890123456789012345678901234567890.12345678"]
    assert after == before


def test_without_a_context_of_its_own_the_frozen_text_would_change_or_be_refused():
    """C-43's control: called bare in a hostile context, decimal_text is another text."""
    from app.intelligence.contract import decimal_text

    with localcontext(Context(prec=1, rounding=ROUND_UP)):
        assert decimal_text(Decimal("73442577.10")) == "80000000"
    with localcontext(Context(prec=1, traps=[Inexact])), pytest.raises(Inexact):
        decimal_text(Decimal("73442577.10"))


def test_a_number_that_is_not_finite_is_refused_and_never_stated(plain_rates):
    """An open deal that cannot be valued still states its amount, and a NaN has no text."""
    with pytest.raises(ContractViolationError, match="non-finite"):
        view_of([deal("D-1", stage=None, amount=Decimal("NaN"))], plain_rates)


@pytest.mark.parametrize("hostile", HOSTILE, ids=HOSTILE_IDS)
def test_the_whole_view_is_the_same_in_any_callers_context(tmp_path, hostile):
    """
    C-43, plan A19 item 8, constructed with a rate that is not an integer:
    the same view and the same hash, in particular every dec text, share,
    cumulative share, index, total and amount; and the caller's context is
    as it was set. The largest amount Layer 1 can hold is among the deals.
    """
    rate_set_ = rate_set(tmp_path, {"USD": "9999999979.49999999", "EUR": "91.123456"})
    deals = [*PORTFOLIO, deal("D-99", amount="9999999999999.99", currency="USD",
                              probability="99.99", stage="qualification", customer="C-B")]
    expected = view_of(deals, rate_set_, bands=PORTFOLIO_BANDS)

    with localcontext(hostile()) as current:
        before = state_of(current)
        found = view_of(deals, rate_set_, bands=PORTFOLIO_BANDS)
        texts = limitation_texts(found)
        cited = citations(found)
        digest = view_hash(found)
        after = state_of(current)

    assert found == expected and digest == view_hash(expected)
    assert texts == limitation_texts(expected) and cited == citations(expected)
    assert after == before
    assert found["open_pipeline"]["base"]["unweighted"] == "99999999798343204966841.13"
    block = found["concentration"]["by_customer"]["unweighted"]
    # C-B holds D-02, D-03 and D-99: its amount is the sum of their own converted values.
    held = sum((exact_values(amount, probability, "9999999979.49999999")[2]
                for amount, probability in (("333.33", "33.33"), ("0.25", "50.00"),
                                            ("9999999999999.99", "99.99"))), Decimal(0))
    assert str(held) == "99999999798335699893161.81"
    assert block["top"][0] == {"key": "C-B", "pseudo": False, "amount": str(held), "share": "1"}
    assert (block["currency"], block["rate_set_version"], block["total"]) == (
        "INR", "constructed", "99999999798343204966841.13")
    oracle = exact_concentration([(bucket["key"], bucket["base"]["unweighted"])
                                  for bucket in found["by_customer"]])
    assert [(holder["key"], holder["share"]) for holder in block["top"]] == oracle["top"]
    assert [(point["holders"], point["share"]) for point in block["cumulative"]] == (
        oracle["cumulative"])
    assert block["hhi"] == oracle["hhi"]


# ---------------------------------------------------------------------------
# M2 regression (C-44): the entry point is called as it was, and gives what it gave
# ---------------------------------------------------------------------------


def test_the_entry_point_is_still_called_with_four_arguments_and_bands_are_optional(rates):
    """Plan A22.5 item 3: it stays callable as M2 called it. The bands are one more, last."""
    parameters = inspect.signature(build_partitions).parameters

    assert list(parameters) == ["facts", "rate_set", "stage_vocabulary", "as_of", "bands"]
    assert parameters["bands"].default == ()
    assert all(parameters[name].default is inspect.Parameter.empty
               for name in ("facts", "rate_set", "stage_vocabulary", "as_of"))
    four = build_partitions(PORTFOLIO, rates, STAGES, AS_OF)
    assert four == build_partitions(PORTFOLIO, rates, STAGES, AS_OF, ())


def test_the_four_partitions_of_m2_do_not_depend_on_the_bands(rates):
    """C-44: figure for figure, whatever bands are supplied."""
    bare = build(PORTFOLIO, rates)
    banded = build(PORTFOLIO, rates, bands=PORTFOLIO_BANDS)

    assert (bare.by_currency, bare.by_stage, bare.by_owner, bare.by_expected_close) == (
        banded.by_currency, banded.by_stage, banded.by_owner, banded.by_expected_close)
    assert [str(bucket.base.unweighted) for bucket in bare.by_currency] == [
        "72694.65", "5001000.05", "27835.47"]


def test_stage_one_by_itself_is_what_the_entry_point_runs(rates, monkeypatch):
    """
    OD-M3-1: "stage 1 of plan A10.5, exactly as the M2 entry point executes
    it". valid_deals is that stage, and build_partitions calls it and
    nothing else for it.
    """
    calls = []
    original = aggregation.valid_deals

    def spy(facts, stage_vocabulary):
        calls.append(sorted(stage_vocabulary))
        return original(facts, stage_vocabulary)

    monkeypatch.setattr(aggregation, "valid_deals", spy)
    build(PORTFOLIO, rates)

    assert calls == [sorted(STAGES)]
    valid = original(reversed(PORTFOLIO), STAGES)
    assert [valued.fact.source_id for valued, _ in valid] == VALUED_IDS
    assert [(amount.currency, str(amount.amount)) for _, amount in valid][:2] == [
        ("INR", "1000.00"), ("USD", "333.33")]
    assert type(valid) is tuple
