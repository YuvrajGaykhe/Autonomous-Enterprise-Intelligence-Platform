"""
VS02-M2 against a real database: the dataset, the fixtures and the reads.

"Dataset" here is plan A25.1's: the committed dataset, ingested into the
harness database by the clean full-dataset path and read through
app/pipeline/facts.py, at as_of 2026-09-18 with the committed rate set. Every
figure asserted is Appendix 1's or Appendix 2's, restated from the plan as
text and never recomputed through the code under test.

Three kinds of test:

Reproduction: the four partitions equal Appendix 1 and Appendix 2 in full
(named test 1, coverage rows C-1 to C-4), and each reconciles exactly to the
pinned totals (C-5).

Fixtures: what the committed dataset cannot show, each through its fixture
of tests/fixtures/vs02/: unvalued deals, owners, customers, an undated deal,
a stage that disagrees with the activity, a second source system and a
currency with no rate (named tests 13 to 17, C-10, C-15, C-17).

The reads: deal_rows selects nine columns in code-point order and nothing
else, the facts reader makes exactly three SELECTs over three tables, and
nothing is written (plan A16.2, A21.1, A21.2).
"""

from __future__ import annotations

import dataclasses
import itertools
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import event, func, insert, select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.registry import build_connector
from app.core.database import Base
from app.fx import default_rate_set
from app.fx.errors import FxRateMissingError
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence import Scope, resolve_scope
from app.intelligence.signals import compute_all_signals
from app.normalization.config import default_config
from app.persistence.models import Deal
from app.persistence.repositories import pipeline_queries
from app.persistence.repositories.pipeline_queries import DealRow, deal_rows
from app.pipeline import (
    DealFact,
    DealNote,
    DealState,
    NoteCode,
    OwnerKind,
    Partitions,
    PeriodKind,
    build_partitions,
    deal_notes,
    deal_state,
    default_pipeline_rules,
    read_deal_facts,
)
from app.pipeline.errors import PipelineDataError
from app.pipeline.facts import OWNER_BASIS, OWNER_CARRIER_FIELD
from app.relationships import EdgeType, edges_of_type
from tests.fixtures.vs02 import OTHER_DEAL, OTHER_EMPLOYEE, OTHER_SOURCE, apply
from tests.unit.vs02_support import rate_set

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]

SOURCE_SYSTEM = "csv_demo"
AS_OF = date(2026, 9, 18)
PINNED = "1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00"
PARTITIONS = ("by_currency", "by_stage", "by_owner", "by_expected_close")

#: Appendix 1, the open pipeline by currency: deals, unweighted, weighted.
NATIVE_TOTALS = {
    "EUR": (1, "96633.33", "38653.33"),
    "INR": (21, "47342500.00", "20707975.00"),
    "USD": (8, "193373.46", "91796.37"),
}
#: Appendix 2, pinned at VS02-M0: the open pipeline in the base currency.
BASE_TOTAL = ("73442577.10", "32375999.45")
#: Appendix 2's three "from" rows.
BASE_FROM = {
    "EUR": ("9663333.00", "3865333.00"),
    "INR": ("47342500.00", "20707975.00"),
    "USD": ("16436744.10", "7802691.45"),
}
#: The approved rates (U-1): units of INR per one unit of the currency.
RATES = {"EUR": "100", "INR": "1", "USD": "85"}


@pytest.fixture
def demo(e1_sessions: sessionmaker[Session]) -> sessionmaker[Session]:
    """The clean full-dataset path: 233 rows, 7 entity types, 0 rejected."""
    counts = run_ingestion(build_connector(SOURCE_SYSTEM), e1_sessions, IngestionRequest()).counts
    assert (counts.inserted, counts.rejected) == (233, 0)
    return e1_sessions


def read(sessions: sessionmaker[Session], *, source_system: str = SOURCE_SYSTEM,
         as_of: date = AS_OF) -> tuple[Scope, tuple[DealFact, ...]]:
    """The scope a test resolves, and the facts the reader gives for it (plan A21.1)."""
    with sessions() as session:
        scope = resolve_scope(session, source_system=source_system, as_of=as_of)
        return scope, read_deal_facts(session, scope)


def stages() -> frozenset[str]:
    """The frozen D1 stage vocabulary, as service.py will supply it at M3."""
    return default_config().fields["deals"]["stage"].enum_values


def partition(facts, *, as_of: date = AS_OF, rate_set_=None) -> Partitions:
    return build_partitions(facts, rate_set_ or default_rate_set(), stages(), as_of)


def dataset(sessions: sessionmaker[Session], *, as_of: date = AS_OF) -> Partitions:
    return partition(read(sessions, as_of=as_of)[1], as_of=as_of)


def notes(facts) -> list[DealNote]:
    closed = default_pipeline_rules().closed_stages
    return [note for fact in facts for note in deal_notes(fact, closed)]


def by_key(buckets):
    return {bucket.key: bucket for bucket in buckets}


def native(bucket) -> dict[str, tuple[str, str]]:
    return {amount.currency: (str(amount.unweighted), str(amount.weighted))
            for amount in bucket.native}


def base(bucket) -> tuple[str, str, str]:
    return (bucket.base.currency, str(bucket.base.unweighted), str(bucket.base.weighted))


def plain(value: object) -> object:
    """A partition as nested plain values, every Decimal as its text."""
    if isinstance(value, Decimal):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: plain(getattr(value, field.name))
                for field in dataclasses.fields(value)}
    if isinstance(value, tuple):
        return [plain(item) for item in value]
    return value


def fact_of(facts, source_id: str) -> DealFact:
    [found] = [fact for fact in facts if fact.source_id == source_id]
    return found


def table_counts(sessions: sessionmaker[Session]) -> dict[str, int]:
    with sessions() as session:
        return {table.name: session.scalar(select(func.count()).select_from(table))
                for table in Base.metadata.sorted_tables}


@contextmanager
def statements(sessions: sessionmaker[Session]) -> Iterator[list[str]]:
    """Every SQL statement the engine is asked to run while the block is open."""
    seen: list[str] = []
    engine = sessions.kw["bind"]

    def record(connection, cursor, statement, parameters, context, executemany):
        seen.append(" ".join(statement.split()))

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


# ---------------------------------------------------------------------------
# The dataset, as the reader gives it
# ---------------------------------------------------------------------------


def test_the_dataset_is_the_pinned_snapshot_with_30_open_valued_and_14_closed_deals(demo):
    """Plan 0.11 and Appendix 1's counts: 44 deals, 30 open and all valued, 14 closed."""
    scope, facts = read(demo)

    assert scope.layer1_fingerprint == PINNED
    assert scope.entity_counts["deals"] == len(facts) == 44
    assert [fact.source_id for fact in facts] == [f"DEAL-{n:03d}" for n in range(1, 45)]
    states = [deal_state(fact) for fact in facts]
    assert (states.count(DealState.OPEN_VALUED), states.count(DealState.OPEN_UNVALUED),
            states.count(DealState.CLOSED)) == (30, 0, 14)
    assert {fact.stage for fact in facts if not fact.is_active} == {"won"}
    assert notes(facts) == []


def test_a_fact_carries_the_nine_stored_values_and_its_two_resolved_references(demo):
    """Plan A8.1, on DEAL-001 as data/demo/deals.csv states it."""
    _, facts = read(demo)

    assert facts[0] == DealFact(
        source_id="DEAL-001", stage="negotiation", is_active=True, amount=Decimal("5361.44"),
        currency="USD", probability=Decimal("90.00"), expected_close_date=date(2027, 3, 5),
        owner_source_id="EMP-007", customer_source_id="CUST-007", owner="EMP-007",
        customer="CUST-007")
    assert str(facts[0].amount) == "5361.44" and type(facts[0].amount) is Decimal
    assert type(facts[0].probability) is Decimal and type(facts[0].is_active) is bool


def test_every_deal_of_the_dataset_resolves_to_its_owner_and_its_customer(demo):
    _, facts = read(demo)

    assert all(fact.owner == fact.owner_source_id is not None for fact in facts)
    assert all(fact.customer == fact.customer_source_id is not None for fact in facts)
    assert {fact.owner for fact in facts if fact.is_active} == {
        "EMP-007", "EMP-008", "EMP-009", "EMP-010"}


def test_the_reader_is_deterministic_and_does_not_depend_on_as_of(demo):
    """Plan A6 item 4: as_of does not select deals."""
    assert read(demo)[1] == read(demo)[1] == read(demo, as_of=date(1900, 1, 1))[1]


# ---------------------------------------------------------------------------
# Reproduction (named test 1; C-1 to C-4, C-6)
# ---------------------------------------------------------------------------


def test_the_open_pipelines_native_figures_equal_appendix_1(demo):
    """Named test 1 [R]: per-currency reproduction, and DOC-004's own INR figure among them."""
    buckets = dataset(demo).by_currency

    assert {bucket.key: (bucket.deal_count, *native(bucket)[bucket.key]) for bucket in buckets} == (
        NATIVE_TOTALS)
    assert native(by_key(buckets)["INR"])["INR"][0] == "47342500.00"


def test_by_currency_equals_appendix_1_and_appendix_2_in_full(demo):
    """C-1: count, native unweighted and weighted, each bucket's base, and the rate applied."""
    buckets = dataset(demo).by_currency

    assert [bucket.key for bucket in buckets] == ["EUR", "INR", "USD"]
    for bucket in buckets:
        count, unweighted, weighted = NATIVE_TOTALS[bucket.key]
        assert bucket.deal_count == count == len(bucket.deal_ids)
        assert native(bucket) == {bucket.key: (unweighted, weighted)}
        assert base(bucket) == ("INR", *BASE_FROM[bucket.key])
        assert str(bucket.rate_to_base) == RATES[bucket.key]


def test_by_stage_equals_appendix_1_and_appendix_2_in_full(demo):
    """C-2: per currency, unweighted and weighted; the two base figures; won present and empty."""
    buckets = dataset(demo).by_stage

    assert [(bucket.key, bucket.deal_count) for bucket in buckets] == [
        ("negotiation", 14), ("qualification", 16), ("won", 0)]
    assert native(buckets[0]) == {
        "INR": ("23340000.00", "15675500.00"), "USD": ("92319.26", "70995.17")}
    assert base(buckets[0]) == ("INR", "31187137.10", "21710089.45")
    assert native(buckets[1]) == {
        "EUR": ("96633.33", "38653.33"), "INR": ("24002500.00", "5032475.00"),
        "USD": ("101054.20", "20801.20")}
    assert base(buckets[1]) == ("INR", "42255440.00", "10665910.00")
    assert plain(buckets[2]) == {
        "key": "won", "deal_count": 0, "deal_ids": [], "native": [],
        "base": {"currency": "INR", "unweighted": "0", "weighted": "0"}}


def test_by_owner_equals_appendix_1_in_full(demo):
    """
    C-3. EMP-010's USD weighted exposure, 43,129.52, is the one figure of the
    dataset that rounding once per bucket would change: it would be 43,129.51.
    """
    buckets = dataset(demo).by_owner

    assert [(bucket.key, bucket.kind, bucket.deal_count) for bucket in buckets] == [
        ("EMP-007", OwnerKind.EMPLOYEE, 10), ("EMP-008", OwnerKind.EMPLOYEE, 7),
        ("EMP-009", OwnerKind.EMPLOYEE, 1), ("EMP-010", OwnerKind.EMPLOYEE, 12),
        ("UNASSIGNED", OwnerKind.UNASSIGNED, 0), ("UNRESOLVED", OwnerKind.UNRESOLVED, 0)]
    assert [native(bucket) for bucket in buckets[:4]] == [
        {"INR": ("13159000.00", "3404000.00"), "USD": ("23156.61", "8974.69")},
        {"INR": ("8942500.00", "4999500.00"), "USD": ("56921.68", "39692.16")},
        {"INR": ("1109500.00", "221900.00")},
        {"EUR": ("96633.33", "38653.33"), "INR": ("24131500.00", "12082575.00"),
         "USD": ("113295.17", "43129.52")}]
    assert native(buckets[3])["USD"][1] == "43129.52"
    for bucket in buckets[:4]:
        assert (bucket.basis, bucket.carrier_field, bucket.unresolved_keys) == (
            "SOURCE_KEY_JOIN", "deals.owner_source_id", ())
    for bucket in buckets[4:]:
        assert plain(bucket) == {
            "key": bucket.key, "deal_count": 0, "deal_ids": [], "native": [],
            "base": {"currency": "INR", "unweighted": "0", "weighted": "0"},
            "kind": bucket.key, "basis": None, "carrier_field": None, "unresolved_keys": []}


def test_the_figure_that_tells_per_deal_from_per_bucket_rounding_is_what_the_plan_says(demo):
    """Plan A25.1, by hand from the facts: EMP-010's USD weights, each rounded, sum to 43,129.52."""
    _, facts = read(demo)
    weights = [fact.amount * fact.probability / 100 for fact in facts
               if fact.is_active and fact.owner == "EMP-010" and fact.currency == "USD"]

    cent = Decimal("0.01")
    assert str(sum(weight.quantize(cent) for weight in weights)) == "43129.52"
    assert str(sum(weights).quantize(cent)) == "43129.51"


def test_the_owner_edges_are_known_the_way_the_buckets_say(demo):
    """C-3: the basis and the carrier a bucket states are those of the edges that were read."""
    scope, _ = read(demo)
    with demo() as session:
        edges = edges_of_type(EdgeType.DEAL_OWNED_BY, session, scope)

    assert len(edges) == 44
    assert {(edge.basis, edge.carrier_field) for edge in edges} == {
        (OWNER_BASIS, OWNER_CARRIER_FIELD)}


#: Appendix 1, by expected close at 2026-09-18: deals and native unweighted per currency.
BY_MONTH = {
    "2026-09": (1, {"INR": "4200000.00"}),
    "2026-10": (3, {"INR": "2105500.00"}),
    "2026-11": (3, {"INR": "670000.00", "USD": "11451.80"}),
    "2026-12": (3, {"INR": "249000.00", "USD": "56921.68"}),
    "2027-01": (4, {"INR": "585000.00", "USD": "24487.95"}),
    "2027-02": (2, {"INR": "770500.00"}),
    "2027-03": (7, {"INR": "8270000.00", "USD": "100512.03"}),
    "2027-04": (7, {"EUR": "96633.33", "INR": "30492500.00"}),
}
FIFTEEN = ["OVERDUE", "2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03",
           "2027-04", "2027-05", "2027-06", "2027-07", "2027-08", "LATER", "UNDATED"]


def test_by_expected_close_equals_appendix_1_at_the_acceptance_date(demo):
    """C-4, named test 13: fifteen buckets in order, eight with deals and the other seven empty."""
    buckets = dataset(demo).by_expected_close

    assert [bucket.key for bucket in buckets] == FIFTEEN
    assert [bucket.kind for bucket in buckets] == [
        PeriodKind.OVERDUE, *[PeriodKind.MONTH] * 12, PeriodKind.LATER, PeriodKind.UNDATED]
    assert {bucket.key: (bucket.deal_count,
                         {currency: figures[0] for currency, figures in native(bucket).items()})
            for bucket in buckets if bucket.deal_count} == BY_MONTH
    empty = [bucket for bucket in buckets if bucket.key not in BY_MONTH]
    assert [bucket.key for bucket in empty] == [
        "OVERDUE", "2027-05", "2027-06", "2027-07", "2027-08", "LATER", "UNDATED"]
    for bucket in empty:
        assert (bucket.deal_count, bucket.deal_ids, bucket.native, base(bucket)) == (
            0, (), (), ("INR", "0", "0"))


@pytest.mark.parametrize(("as_of", "overdue", "in_window", "later"), [
    (date(2026, 9, 18), 0, 30, 0),
    (date(2027, 1, 15), 11, 19, 0),
    (date(2025, 1, 1), 0, 0, 30),
    (date(1900, 1, 1), 0, 0, 30),
])
def test_the_periods_move_with_as_of_and_there_are_always_fifteen(
        demo, as_of, overdue, in_window, later):
    """Named test 13: at 2027-01-15, 11 overdue and 19 in the window; long before, all LATER."""
    buckets = dataset(demo, as_of=as_of).by_expected_close

    assert len(buckets) == 15
    assert buckets[0].deal_count == overdue
    assert sum(bucket.deal_count for bucket in buckets[1:13]) == in_window
    assert (buckets[13].deal_count, buckets[14].deal_count) == (later, 0)
    assert sum(bucket.deal_count for bucket in buckets) == 30


def test_as_of_moves_only_the_period_partition(demo):
    """Plan A6 item 4: as_of places deals in periods and does nothing else to a figure."""
    then, now = dataset(demo, as_of=date(1900, 1, 1)), dataset(demo)

    assert (then.by_currency, then.by_stage, then.by_owner) == (
        now.by_currency, now.by_stage, now.by_owner)
    assert then.by_expected_close != now.by_expected_close


def test_a_bucket_holding_three_currencies_states_each_natively_and_one_base(demo):
    """C-6: qualification holds EUR, INR and USD. Never summed, and one base Amount."""
    bucket = by_key(dataset(demo).by_stage)["qualification"]

    assert [amount.currency for amount in bucket.native] == ["EUR", "INR", "USD"]
    assert base(bucket) == ("INR", "42255440.00", "10665910.00")
    # By hand: 96633.33 x 100 + 24002500.00 + 101054.20 x 85, the rates being integers.
    assert Decimal("9663333.00") + Decimal("24002500.00") + Decimal("8589607.00") == (
        bucket.base.unweighted)


# ---------------------------------------------------------------------------
# Reconciliation (C-5; plan A9.4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", PARTITIONS)
def test_each_partition_of_the_dataset_reconciles_exactly_to_the_pinned_totals(demo, name):
    """
    C-5: 30 deals, each in exactly one bucket; Appendix 1's totals per
    currency; INR 73,442,577.10 and INR 32,375,999.45. No tolerance.
    """
    _, facts = read(demo)
    buckets = getattr(partition(facts), name)
    open_valued = sorted(fact.source_id for fact in facts
                         if deal_state(fact) is DealState.OPEN_VALUED)

    assert sum(bucket.deal_count for bucket in buckets) == 30
    assert sorted(itertools.chain.from_iterable(bucket.deal_ids for bucket in buckets)) == (
        open_valued)
    for currency, (_, unweighted, weighted) in NATIVE_TOTALS.items():
        held = [amount for bucket in buckets for amount in bucket.native
                if amount.currency == currency]
        assert str(sum(amount.unweighted for amount in held)) == unweighted
        assert str(sum(amount.weighted for amount in held)) == weighted
    assert {amount.currency for bucket in buckets for amount in bucket.native} == set(
        NATIVE_TOTALS)
    assert {bucket.base.currency for bucket in buckets} == {"INR"}
    assert (str(sum(bucket.base.unweighted for bucket in buckets)),
            str(sum(bucket.base.weighted for bucket in buckets))) == BASE_TOTAL


def test_the_base_total_is_exactly_the_sum_of_the_per_currency_base_figures(demo):
    """Plan A9.4 item 2, and Appendix 2's hand check: 0.00 for both USD and EUR."""
    buckets = by_key(dataset(demo).by_currency)

    assert str(sum(Decimal(unweighted) for unweighted, _ in BASE_FROM.values())) == BASE_TOTAL[0]
    assert str(sum(Decimal(weighted) for _, weighted in BASE_FROM.values())) == BASE_TOTAL[1]
    for currency in ("EUR", "USD"):
        native_total = Decimal(NATIVE_TOTALS[currency][1])
        assert native_total * Decimal(RATES[currency]) - buckets[currency].base.unweighted == 0


# ---------------------------------------------------------------------------
# VS-01 equivalence (named test 17)
# ---------------------------------------------------------------------------


def vs02_exposure(facts) -> dict[str, dict[str, str]]:
    """Native unweighted open exposure per customer and currency, formed here from the facts."""
    held: dict[str, dict[str, Decimal]] = {}
    for fact in facts:
        if deal_state(fact) is DealState.OPEN_VALUED and fact.customer is not None:
            amounts = held.setdefault(fact.customer, {})
            amounts[fact.currency] = amounts.get(fact.currency, Decimal(0)) + fact.amount
    return {customer: {currency: str(amount) for currency, amount in sorted(amounts.items())}
            for customer, amounts in held.items()}


def vs01_exposure(sessions: sessionmaker[Session], scope: Scope) -> dict[str, dict[str, str]]:
    """VS-01's own exposure_by_currency, for every customer that has any."""
    with sessions() as session:
        computed = compute_all_signals(session, scope)
    return {one.customer.source_id: {currency: str(value.amount) for currency, value
                                     in sorted(one.signals.exposure_by_currency.items())}
            for one in computed if one.signals.exposure_by_currency}


def test_vs02_exposure_per_customer_equals_vs01s_on_the_committed_dataset(demo):
    """
    Named test 17: the committed dataset holds no negative-amount open deal,
    so the two agree for every customer. VS-02's figure is formed in this
    test from the open valued facts, grouped on DealFact.customer (OD-4).
    """
    scope, facts = read(demo)
    ours, theirs = vs02_exposure(facts), vs01_exposure(demo, scope)

    assert ours == theirs
    assert len(ours) == 23, "Appendix 1: 23 customers hold an open deal"
    assert sorted(customer for customer, held in ours.items() if len(held) == 2) == [
        "CUST-029", "CUST-042", "CUST-050"]
    assert ours["CUST-007"] == {"USD": "5361.44"}


def test_a_negative_amount_is_the_whole_difference_between_vs02_and_vs01(demo):
    """
    Named test 17 with fixture 2: VS-01 describes DEAL-962 and VS-02 does not
    value it. For every other customer the two still agree, and for its
    customer the difference is exactly that deal.
    """
    apply("negative_amount", demo)
    scope, facts = read(demo)
    ours, theirs = vs02_exposure(facts), vs01_exposure(demo, scope)
    negative = fact_of(facts, "DEAL-962")

    assert (negative.customer, negative.currency, str(negative.amount)) == (
        "CUST-005", "USD", "-1500.00")
    assert {customer: held for customer, held in theirs.items() if customer != "CUST-005"} == {
        customer: held for customer, held in ours.items() if customer != "CUST-005"}
    assert "CUST-005" not in ours, "it holds no other open deal"
    assert theirs["CUST-005"] == {"USD": "-1500.00"}


# ---------------------------------------------------------------------------
# Unvalued deals (named test 15; fixtures 1 and 2)
# ---------------------------------------------------------------------------


def test_unvalued_deals_are_counted_excluded_from_money_listed_and_noted(demo):
    """
    Named test 15 [R], asserted at M2 over the classified facts, their notes
    and the four partitions (OD-4). Nothing is dropped: the three deals are
    read, classified and noted, and they sit in no bucket and no figure.
    """
    before = dataset(demo)
    apply("unvalued_deals", demo)
    apply("negative_amount", demo)
    _, facts = read(demo)

    states = {state: sorted(fact.source_id for fact in facts if deal_state(fact) is state)
              for state in DealState}
    assert states[DealState.OPEN_UNVALUED] == ["DEAL-960", "DEAL-961", "DEAL-962"]
    assert len(states[DealState.OPEN_VALUED]) == 30 and len(states[DealState.CLOSED]) == 14
    assert len(states[DealState.OPEN_VALUED]) + len(states[DealState.OPEN_UNVALUED]) == len(
        [fact for fact in facts if fact.is_active]) == 33
    assert len(facts) == 47

    after = partition(facts)
    assert after == before, "an unvalued deal contributes to no monetary figure"
    for name in PARTITIONS:
        assert not {"DEAL-960", "DEAL-961", "DEAL-962"} & set(itertools.chain.from_iterable(
            bucket.deal_ids for bucket in getattr(after, name)))

    assert notes(facts) == [
        DealNote(NoteCode.INCOMPLETE_DEAL, "deals", "DEAL-960", ("amount",), None),
        DealNote(NoteCode.INCOMPLETE_DEAL, "deals", "DEAL-961", ("probability",), None),
        DealNote(NoteCode.NEGATIVE_AMOUNT, "deals", "DEAL-962", ("amount",), None),
    ]


# ---------------------------------------------------------------------------
# Owners and the second source system (named tests 14 and 16; fixtures 3 and 7)
# ---------------------------------------------------------------------------


def test_unassigned_and_unresolved_owners_stay_distinct_with_their_notes(demo):
    """Named test 14 with fixture 3: no key at all, and a key that names no employee."""
    apply("owner_keys", demo)
    _, facts = read(demo)
    buckets = by_key(partition(facts).by_owner)

    assert (buckets["UNASSIGNED"].deal_ids, buckets["UNASSIGNED"].unresolved_keys) == (
        ("DEAL-963",), ())
    assert (buckets["UNRESOLVED"].deal_ids, buckets["UNRESOLVED"].unresolved_keys) == (
        ("DEAL-964",), ("EMP-960",))
    assert native(buckets["UNASSIGNED"]) == {"INR": ("2000.00", "500.00")}
    assert native(buckets["UNRESOLVED"]) == {"INR": ("3000.00", "1500.00")}
    assert list(buckets) == ["EMP-007", "EMP-008", "EMP-009", "EMP-010", "UNASSIGNED",
                             "UNRESOLVED"]
    assert notes(facts) == [
        DealNote(NoteCode.OWNER_KEY_MISSING, "deals", "DEAL-963", ("owner_source_id",), None),
        DealNote(NoteCode.OWNER_KEY_UNRESOLVED, "deals", "DEAL-964", ("owner_source_id",),
                 "EMP-960"),
    ]


def test_another_source_systems_employee_is_never_joined_as_an_owner(demo):
    """
    Named test 14 and C-17, not vacuously. The second source system holds an
    employee with exactly the id DEAL-964 names, and the join does resolve
    that id inside the second system. So DEAL-964 is UNRESOLVED only because
    the join is scoped.
    """
    apply("owner_keys", demo)
    apply("second_source_system", demo)
    _, facts = read(demo)
    _, others = read(demo, source_system=OTHER_SOURCE)

    assert fact_of(facts, "DEAL-964").owner_source_id == OTHER_EMPLOYEE == "EMP-960"
    assert [(fact.source_id, fact.owner_source_id, fact.owner) for fact in others] == [
        (OTHER_DEAL, OTHER_EMPLOYEE, OTHER_EMPLOYEE)], "the id does resolve where it exists"

    assert fact_of(facts, "DEAL-964").owner is None
    buckets = by_key(partition(facts).by_owner)
    assert buckets["UNRESOLVED"].deal_ids == ("DEAL-964",)
    assert OTHER_EMPLOYEE not in buckets
    assert NoteCode.OWNER_KEY_UNRESOLVED in {note.code for note in notes(facts)}


def test_a_second_source_systems_deals_appear_in_no_figure(demo):
    """
    Named test 16 [R] and C-17. The second system's deal carries the id of
    csv_demo's DEAL-001 and a much larger amount, so a read that lost its
    scope would count it twice or replace it. Every figure is unchanged.
    """
    before_facts = read(demo)[1]
    before = partition(before_facts)
    apply("second_source_system", demo)
    scope, facts = read(demo)
    other_scope, others = read(demo, source_system=OTHER_SOURCE)

    assert facts == before_facts and partition(facts) == before
    assert scope.layer1_fingerprint == PINNED
    assert fact_of(facts, "DEAL-001").amount == Decimal("5361.44")

    assert [(fact.source_id, str(fact.amount), fact.currency, fact.customer_source_id,
             fact.customer) for fact in others] == [
        ("DEAL-001", "999999.99", "USD", "CUST-001", None)]
    assert other_scope.entity_counts["deals"] == 1 and other_scope.entity_counts["employees"] == 1
    theirs = partition(others)
    assert [(bucket.key, bucket.deal_ids, native(bucket)) for bucket in theirs.by_currency] == [
        ("USD", ("DEAL-001",), {"USD": ("999999.99", "500000.00")})]
    assert [bucket.key for bucket in theirs.by_owner] == ["EMP-960", "UNASSIGNED", "UNRESOLVED"]


def test_a_source_system_with_no_deal_gives_the_empty_partitions(demo):
    """Plan A17.2: an empty source system is not an error."""
    scope, facts = read(demo, source_system="no_such_system")
    partitions = partition(facts)

    assert facts == () and scope.entity_counts["deals"] == 0
    assert partitions.by_currency == ()
    assert [len(part) for part in (partitions.by_stage, partitions.by_owner,
                                   partitions.by_expected_close)] == [3, 2, 15]
    assert {bucket.deal_count for name in PARTITIONS
            for bucket in getattr(partitions, name)} <= {0}


# ---------------------------------------------------------------------------
# Customers, the undated deal and the disagreeing stage (C-15; fixtures 4 to 6)
# ---------------------------------------------------------------------------


def test_a_deal_with_no_customer_draws_a_missing_or_an_unresolved_note(demo):
    """C-15 with fixture 4. Both deals are still open, valued and in every partition."""
    apply("customer_keys", demo)
    _, facts = read(demo)

    assert [(fact.source_id, fact.customer_source_id, fact.customer)
            for fact in facts if fact.source_id in ("DEAL-965", "DEAL-966")] == [
        ("DEAL-965", None, None), ("DEAL-966", "CUST-960", None)]
    assert notes(facts) == [
        DealNote(NoteCode.CUSTOMER_KEY_MISSING, "deals", "DEAL-965", ("customer_source_id",),
                 None),
        DealNote(NoteCode.CUSTOMER_KEY_UNRESOLVED, "deals", "DEAL-966", ("customer_source_id",),
                 "CUST-960"),
    ]
    buckets = by_key(partition(facts).by_owner)
    assert {"DEAL-965", "DEAL-966"} <= set(buckets["EMP-007"].deal_ids)
    assert buckets["EMP-007"].deal_count == 12


def test_an_undated_deal_is_in_the_undated_bucket_and_noted(demo):
    """C-15 and named test 13 with fixture 5: a null date is UNDATED."""
    apply("undated_deal", demo)
    _, facts = read(demo)
    buckets = by_key(partition(facts).by_expected_close)

    assert buckets["UNDATED"].deal_ids == ("DEAL-967",)
    assert native(buckets["UNDATED"]) == {"USD": ("6000.00", "4500.00")}
    assert base(buckets["UNDATED"]) == ("INR", "510000.00", "382500.00")
    assert notes(facts) == [DealNote(NoteCode.EXPECTED_CLOSE_MISSING, "deals", "DEAL-967",
                                     ("expected_close_date",), None)]
    assert sum(bucket.deal_count for bucket in buckets.values()) == 31


def test_a_deal_is_classified_by_its_activity_and_its_disagreeing_stage_is_noted(demo):
    """
    C-15 with fixture 6, MD-1: the active deal in `won` is open, valued and
    counted under `won`; the inactive deal in `negotiation` is closed and in
    no bucket. Neither is reclassified, and both draw the mismatch note.
    """
    apply("stage_activity_mismatch", demo)
    _, facts = read(demo)
    buckets = by_key(partition(facts).by_stage)

    assert deal_state(fact_of(facts, "DEAL-968")) is DealState.OPEN_VALUED
    assert deal_state(fact_of(facts, "DEAL-969")) is DealState.CLOSED
    assert buckets["won"].deal_ids == ("DEAL-968",)
    assert native(buckets["won"]) == {"INR": ("7000.00", "7000.00")}
    assert buckets["negotiation"].deal_count == 14
    assert "DEAL-969" not in buckets["negotiation"].deal_ids
    assert notes(facts) == [
        DealNote(NoteCode.STAGE_ACTIVITY_MISMATCH, "deals", "DEAL-968", ("is_active", "stage"),
                 None),
        DealNote(NoteCode.STAGE_ACTIVITY_MISMATCH, "deals", "DEAL-969", ("is_active", "stage"),
                 None),
    ]


# ---------------------------------------------------------------------------
# A currency with no rate (C-10; fixture 8)
# ---------------------------------------------------------------------------


def test_an_open_valued_deal_in_a_currency_without_a_rate_fails_the_whole_aggregation(
        demo, tmp_path):
    """
    C-10 with fixture 8: convert's own error names GBP, and no partition is
    returned. With a rate set that holds GBP, the same facts aggregate.
    """
    apply("gbp_deal", demo)
    _, facts = read(demo)

    assert (fact_of(facts, "DEAL-970").currency, deal_state(fact_of(facts, "DEAL-970"))) == (
        "GBP", DealState.OPEN_VALUED)
    with pytest.raises(FxRateMissingError) as raised:
        partition(facts)
    assert raised.value.currencies == ("GBP",)
    assert raised.value.rate_set_version == default_rate_set().rate_set_version == "1"

    with_gbp = rate_set(tmp_path, {"USD": "85", "EUR": "100", "GBP": "105.5"})
    pounds = by_key(partition(facts, rate_set_=with_gbp).by_currency)["GBP"]
    assert (pounds.deal_ids, native(pounds), base(pounds), str(pounds.rate_to_base)) == (
        ("DEAL-970",), {"GBP": ("9000.00", "2700.00")}, ("INR", "949500.00", "284850.00"),
        "105.5")


# ---------------------------------------------------------------------------
# Fixtures 9 and 10 at the aggregation: no document is read, and from M3 a
# customer's id is a generated key
# ---------------------------------------------------------------------------


def test_removing_doc004_changes_no_fact_and_no_figure(demo):
    """
    Plan A18.4 item 2 at M2: no document reaches a fact or a figure. The
    snapshot's identity does move, which is the scope's business and M3's test.
    """
    before_scope, before_facts = read(demo)
    before = partition(before_facts)
    apply("no_doc004", demo)
    scope, facts = read(demo)

    assert (facts, partition(facts)) == (before_facts, before)
    assert scope.layer1_fingerprint != before_scope.layer1_fingerprint
    assert (before_scope.entity_counts["documents"], scope.entity_counts["documents"]) == (12, 11)


def test_a_customer_whose_id_is_a_reserved_key_fails_the_aggregation_in_stage_one(demo):
    """
    Plan A10.5 item 1 and A14.1 item 7, coverage row C-25: from M3 the
    customer's source_id is a generated key, with by_customer. Fixture 10's
    deal is resolved to the customer UNLINKED, which would head a bucket
    under a reserved key, so the entry point raises in stage 1 and returns
    no partition. At M2 the same facts were ordinary data; this is the one
    input whose outcome the frozen M3 contract changes (OD-M3-4).
    """
    before = partition(read(demo)[1])
    apply("reserved_customer", demo)
    _, facts = read(demo)
    reserved = fact_of(facts, "DEAL-971")

    assert (reserved.customer_source_id, reserved.customer) == ("UNLINKED", "UNLINKED")
    assert deal_state(reserved) is DealState.OPEN_VALUED
    assert notes(facts) == []
    with pytest.raises(PipelineDataError) as raised:
        partition(facts)
    assert (raised.value.condition, raised.value.entity) == ("RESERVED_KEY", "deals")
    assert raised.value.keys == ("UNLINKED",)
    assert raised.value.source_ids == ("DEAL-971",)
    assert str(raised.value) == "RESERVED_KEY; keys UNLINKED; deals DEAL-971"

    # The deal itself is what is refused: without it the same database aggregates as before.
    assert partition([fact for fact in facts if fact is not reserved]) == before


# ---------------------------------------------------------------------------
# deal_rows (plan A16.2; C-16)
# ---------------------------------------------------------------------------

#: The nine columns of plan A16.2, in its order.
NINE = ("source_id", "stage", "is_active", "amount", "currency", "probability",
        "expected_close_date", "owner_source_id", "customer_source_id")
ORDER_SYSTEM = "order_demo"
#: Ids a case-insensitive or locale-aware order arranges differently from code-point order.
ORDER_IDS = ["DEAL-b", "DEAL-B", "DEAL-a", "DEAL-A", "deal-1", "DEAL-é", "DEAL-10", "DEAL-9",
             "DEAL-Z", "Deal-2", "DEAL_1"]


def _loader_row(source_system: str, source_id: str, *, source_entity: str = "deals") -> dict:
    return {"source_system": source_system, "source_entity": source_entity,
            "source_id": source_id, "ingestion_run_id": uuid.UUID(int=960),
            "record_hash": "0" * 64, "ingested_at": datetime(2026, 1, 1, tzinfo=UTC),
            "name": f"Order {source_id}", "is_active": True}


def test_deal_rows_returns_the_nine_columns_of_the_plan_as_plain_rows(demo):
    with demo() as session:
        rows = deal_rows(session, SOURCE_SYSTEM)

    assert DealRow._fields == NINE and len(NINE) == 9
    assert type(rows) is list and len(rows) == 44
    assert all(type(row) is DealRow for row in rows)
    assert rows[0] == ("DEAL-001", "negotiation", True, Decimal("5361.44"), "USD",
                       Decimal("90.00"), date(2027, 3, 5), "EMP-007", "CUST-007")
    assert rows[3] == ("DEAL-004", "won", False, Decimal("4019500.00"), "INR",
                       Decimal("100.00"), date(2025, 12, 30), "EMP-007", "CUST-021")
    assert [row.source_id for row in rows] == [f"DEAL-{n:03d}" for n in range(1, 45)]


def test_deal_rows_runs_one_select_of_nine_columns_ordered_in_the_c_collation(demo):
    """
    Plan A16.2: it reads no other column of deals, the deal's name included,
    filters on source_system and source_entity, and orders inside the
    statement, so the order never depends on the database's default collation.
    """
    with demo() as session, statements(demo) as seen:
        deal_rows(session, SOURCE_SYSTEM)

    [statement] = [one for one in seen if "deals" in one]
    columns = statement.removeprefix("SELECT ").split(" FROM ")[0].split(", ")
    assert columns == [f"deals.{name}" for name in NINE]
    assert " FROM deals WHERE deals.source_system = " in statement
    assert " AND deals.source_entity = " in statement
    assert statement.endswith('ORDER BY deals.source_id COLLATE "C"')
    assert "deals.name" not in statement and "JOIN" not in statement
    assert "FOR UPDATE" not in statement


def test_deal_rows_orders_by_code_point_where_a_locale_would_order_otherwise(demo):
    """
    C-16, with loader rows. The control: the same rows under an ICU collation
    come back in another order, so these ids can tell the two apart.
    """
    with demo() as session:
        session.execute(insert(Deal), [_loader_row(ORDER_SYSTEM, source_id)
                                       for source_id in ORDER_IDS])
        found = [row.source_id for row in deal_rows(session, ORDER_SYSTEM)]
        by_locale = session.scalars(
            select(Deal.source_id).where(Deal.source_system == ORDER_SYSTEM)
            .order_by(Deal.source_id.collate("en-x-icu"))).all()
        facts = read_deal_facts(session, resolve_scope(session, source_system=ORDER_SYSTEM,
                                                       as_of=AS_OF))
        session.rollback()

    assert found == sorted(ORDER_IDS) == [
        "DEAL-10", "DEAL-9", "DEAL-A", "DEAL-B", "DEAL-Z", "DEAL-a", "DEAL-b", "DEAL-é",
        "DEAL_1", "Deal-2", "deal-1"]
    assert sorted(by_locale) == found and by_locale != found
    assert [fact.source_id for fact in facts] == found


def test_deal_rows_is_confined_to_one_source_system_and_to_the_deals_entity(demo):
    """Plan A16.2: the two filters, each shown by a row that only it excludes."""
    with demo() as session:
        session.execute(insert(Deal), [
            _loader_row(ORDER_SYSTEM, "DEAL-A"),
            _loader_row(ORDER_SYSTEM, "DEAL-B", source_entity="opportunities"),
            _loader_row(SOURCE_SYSTEM, "DEAL-999", source_entity="opportunities"),
        ])
        ours = [row.source_id for row in deal_rows(session, SOURCE_SYSTEM)]
        theirs = [row.source_id for row in deal_rows(session, ORDER_SYSTEM)]
        nobody = deal_rows(session, "no_such_system")
        session.rollback()

    assert len(ours) == 44 and "DEAL-999" not in ours and "DEAL-A" not in ours
    assert theirs == ["DEAL-A"]
    assert nobody == []


def test_deal_rows_returns_a_row_with_every_nullable_value_null(demo):
    with demo() as session:
        session.execute(insert(Deal), [_loader_row(ORDER_SYSTEM, "DEAL-A")])
        rows = deal_rows(session, ORDER_SYSTEM)
        session.rollback()

    assert rows == [("DEAL-A", None, True, None, None, None, None, None, None)]


def test_the_repository_names_three_models_and_nothing_of_layer_2():
    """
    Plan A16.2: Deal from M2, and RiskAssessment and Customer with band_rows
    from M3. No other model, no domain type and no third read.
    """
    assert sorted(name for name in vars(pipeline_queries) if not name.startswith("_")) == [
        "BandRow", "Customer", "DEALS", "Deal", "DealRow", "Decimal", "NamedTuple",
        "RiskAssessment", "Session", "annotations", "band_rows", "date", "deal_rows", "select"]
    assert sorted(name for name, value in vars(pipeline_queries).items()
                  if callable(value) and getattr(value, "__module__", None) == (
                      pipeline_queries.__name__) and not isinstance(value, type)) == [
        "band_rows", "deal_rows"]


# ---------------------------------------------------------------------------
# What is read, and that nothing is written (plan A21.1, A21.2)
# ---------------------------------------------------------------------------


def test_the_facts_reader_runs_exactly_three_selects_over_three_tables(demo):
    """
    Plan A21.1 item 1: nine columns of deals, and the two edge reads, which
    touch source_id columns of deals, employees and customers and no other
    table. No document, no ticket, and no write of any kind.
    """
    with demo() as session:
        scope = resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=AS_OF)
        with statements(demo) as seen:
            read_deal_facts(session, scope)

    assert len(seen) == 3 and all(statement.startswith("SELECT ") for statement in seen)
    tables = {table.name for table in Base.metadata.sorted_tables}
    touched = {table for statement in seen for table in tables
               if f" {table} " in f"{statement} " or f" {table}." in statement}
    assert touched == {"deals", "employees", "customers"}
    assert not [statement for statement in seen if re.search(
        r"\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|CREATE|ALTER|DROP|LOCK|COMMIT|ROLLBACK|SAVEPOINT"
        r"|BEGIN|SET|FOR UPDATE|FOR SHARE)\b", statement.upper())]


def test_reading_and_aggregating_leaves_every_table_as_it_was(demo):
    """Plan A21.2 item 4, observed at M2 ahead of named test 20: nothing is changed."""
    before = table_counts(demo)
    with demo() as session:
        scope = resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=AS_OF)
        facts = read_deal_facts(session, scope)
        partition(facts)
        notes(facts)

        assert not session.new and not session.dirty and not session.deleted

    assert table_counts(demo) == before
    assert before["deals"] == 44 and before["risk_assessments"] == 0
