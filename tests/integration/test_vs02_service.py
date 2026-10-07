"""
VS02-M3 against a real database: the band read, the service and the view of
the committed dataset.

"Dataset" here is plan A25.2's: the committed dataset, ingested into the
harness database by the clean full-dataset path, assessed by VS-01's own
assessment run at 2026-09-18, and viewed through pipeline_view at that date
with the committed rate set. "Stored" is rows a fixture of
tests/fixtures/vs02 puts in the harness database: one of the ten entries, or
a stored-row loader where the test needs a row neither Layer 1 nor VS-01's
frozen writer can produce.

Every figure asserted is Appendix 1's or Appendix 2's, restated from the
plan as text, or is worked here from data/demo/deals.csv with fractions and
integer rounding. No expected figure is taken from the code under test.

What is here:

    The band read      band_rows, its five identity filters, its order and
                       its join (C-20, C-21; named test 12).
    The dataset        the six partitions, coincidence, concentration,
                       deal_counts and the multi-currency customers, against
                       the appendices and against the CSV (C-23, C-24, C-26
                       to C-28, C-30, C-31, C-40; named tests 2, 4, 5, 19).
    The service        its contract, its event, its errors and their order,
                       and that it reads and never writes (C-22, C-25, C-34
                       to C-38; named tests 9, 20, 21, 27).
    What moves         DOC-004 removed, a changed rate, permuted bands,
                       partial coverage (named tests 3, 8, 10, 11).
    What does not      the empty view, the scope note, order, and the
                       caller's Decimal context (C-39, C-41 to C-43).
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import inspect
import json
import logging
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import ROUND_UP, Context, Decimal, Inexact, Rounded, localcontext
from fractions import Fraction
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import read_snapshot
from app.connectors.registry import build_connector
from app.core.database import Base
from app.decisions.assessment import run_assessment
from app.evidence import citable_text
from app.fx import default_rate_set
from app.fx.errors import FxConfigError, FxRateMissingError
from app.fx.rates import load_rate_set
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence import default_risk_rules, resolve_scope
from app.intelligence.errors import ContractViolationError
from app.intelligence.signals import compute_all_signals
from app.normalization.config import default_config
from app.persistence.models import Customer, Deal, Document, RiskAssessment
from app.persistence.repositories.pipeline_queries import BandRow, band_rows
from app.pipeline import build_partitions, default_pipeline_rules, read_deal_facts
from app.pipeline import service as service_module
from app.pipeline.errors import PipelineConfigError, PipelineDataError
from app.pipeline.facts import BandFact, read_band_facts
from app.pipeline.service import pipeline_view
from app.pipeline.view import PipelineView
from tests.fixtures.vs02 import apply, store_assessment, store_customer, store_deal
from tests.unit.vs02_support import (
    exact_concentration,
    exact_values,
    half_even_cents,
    rate_set,
)

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]

SOURCE_SYSTEM = "csv_demo"
AS_OF = date(2026, 9, 18)
PINNED = "1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00"
#: tests/unit/test_vs02_fx.py's pin for rate set "1", restated.
RATE_SET_DIGEST = "61313648d0ddfc69d8f5b0b40ea07fc90ecf35460c8a04a37e4f38e3d1588426"
EVENTS_LOGGER = "app.pipeline.service"
#: The approved rates (U-1): units of INR per one unit of the currency.
RATES = {"EUR": "100", "INR": "1", "USD": "85"}
BAND_ORDER = ["CRITICAL", "ELEVATED", "WATCH", "NONE", "UNASSESSED", "UNLINKED"]
SIX = ("by_currency", "by_stage", "by_owner", "by_expected_close", "by_risk_band", "by_customer")
#: Appendix 1: the bands VS-01 persists at 2026-09-18. Every other customer is NONE.
BANDED = {"CUST-007": "CRITICAL", "CUST-025": "WATCH", "CUST-036": "WATCH"}
#: A customer with a closed deal only, and one with no deal at all (data/demo).
CLOSED_ONLY, NO_DEAL = "CUST-021", "CUST-025"


# ---------------------------------------------------------------------------
# Building what is viewed
# ---------------------------------------------------------------------------


@pytest.fixture
def demo(e1_sessions: sessionmaker[Session]) -> sessionmaker[Session]:
    """The clean full-dataset path: 233 rows, 7 entity types, 0 rejected."""
    counts = run_ingestion(build_connector(SOURCE_SYSTEM), e1_sessions, IngestionRequest()).counts
    assert (counts.inserted, counts.rejected) == (233, 0)
    return e1_sessions


def assess(sessions: sessionmaker[Session], **kwargs) -> None:
    """VS-01's own assessment run, committed."""
    kwargs.setdefault("as_of", AS_OF)
    with sessions.begin() as session:
        run_assessment(session, **kwargs)


@pytest.fixture
def assessed(demo) -> sessionmaker[Session]:
    assess(demo)
    return demo


def built(sessions: sessionmaker[Session], *, as_of: date = AS_OF,
          source_system: str = SOURCE_SYSTEM) -> PipelineView:
    with sessions() as session:
        return pipeline_view(session, as_of=as_of, source_system=source_system)


def view(sessions: sessionmaker[Session], **kwargs) -> dict:
    return built(sessions, **kwargs).view


@contextmanager
def stored(sessions: sessionmaker[Session]) -> Iterator[Session]:
    """A session whose stored rows are gone when the block ends: a loader never commits."""
    with sessions() as session:
        try:
            yield session
        finally:
            session.rollback()


def identity(session: Session, source_system: str = SOURCE_SYSTEM,
             as_of: date = AS_OF) -> dict:
    """The identity of plan A12.2 for what the session holds now, as store_assessment takes it."""
    scope = resolve_scope(session, source_system=source_system, as_of=as_of)
    rules = default_risk_rules()
    return {"source_system": source_system, "as_of": as_of,
            "layer1_fingerprint": scope.layer1_fingerprint,
            "rules_version": rules.rules_version, "linker_version": rules.linker_version}


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


def events(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == EVENTS_LOGGER]


def keyed(buckets) -> dict[str, dict]:
    return {bucket["key"]: bucket for bucket in buckets}


def native(bucket: dict) -> dict[str, tuple[str, str]]:
    return {amount["currency"]: (amount["unweighted"], amount["weighted"])
            for amount in bucket["native"]}


def base(bucket: dict) -> tuple[str, str, str]:
    return (bucket["base"]["currency"], bucket["base"]["unweighted"], bucket["base"]["weighted"])


def dec(value: Decimal | str) -> str:
    """A number as the view states one: plain notation with no trailing zeros."""
    digits = format(Decimal(value), "f")
    stripped = digits.rstrip("0").rstrip(".") if "." in digits else digits
    return "0" if Decimal(value) == 0 else stripped


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def walk(value):
    yield value
    if isinstance(value, dict):
        for inner in value.values():
            yield from walk(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from walk(inner)


# ---------------------------------------------------------------------------
# The oracle: data/demo/deals.csv, worked here in fractions
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CsvDeal:
    source_id: str
    customer: str
    owner: str
    stage: str
    currency: str
    is_open: bool
    values: tuple[Decimal, Decimal, Decimal, Decimal]


def csv_deals() -> list[CsvDeal]:
    """Every committed deal, with its four values worked by the oracle at the approved rates."""
    with (REPO / "data" / "demo" / "deals.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [CsvDeal(source_id=row["deal_id"], customer=row["customer_id"],
                    owner=row["owner_id"], stage=row["stage"], currency=row["currency"],
                    is_open=row["is_active"] == "true",
                    values=exact_values(row["amount"], row["probability"],
                                        RATES[row["currency"]]))
            for row in rows]


def open_csv_deals() -> list[CsvDeal]:
    return [one for one in csv_deals() if one.is_open]


def oracle_bucket(deals: list[CsvDeal]) -> tuple[list[str], dict, tuple[str, str]]:
    """(ids, native per currency, base) of a bucket over these deals, as the view states them."""
    native_sums: dict[str, list[Decimal]] = {}
    base_sums = [Decimal(0), Decimal(0)]
    for one in deals:
        held = native_sums.setdefault(one.currency, [Decimal(0), Decimal(0)])
        held[0] += one.values[0]
        held[1] += one.values[1]
        base_sums[0] += one.values[2]
        base_sums[1] += one.values[3]
    return (sorted(one.source_id for one in deals),
            {currency: (dec(sums[0]), dec(sums[1]))
             for currency, sums in sorted(native_sums.items())},
            (dec(base_sums[0]), dec(base_sums[1])))


def oracle_by(deals: list[CsvDeal], attribute: str) -> dict[str, list[CsvDeal]]:
    grouped: dict[str, list[CsvDeal]] = {}
    for one in deals:
        grouped.setdefault(getattr(one, attribute), []).append(one)
    return grouped


def test_the_oracle_reads_the_committed_file_and_gives_the_pinned_totals():
    """The oracle itself, against Appendix 1 and 2, before anything is compared with it."""
    deals = csv_deals()
    ids, by_currency, total = oracle_bucket(open_csv_deals())

    assert (len(deals), len(ids)) == (44, 30)
    assert by_currency == {"EUR": ("96633.33", "38653.33"), "INR": ("47342500", "20707975"),
                           "USD": ("193373.46", "91796.37")}
    assert total == ("73442577.1", "32375999.45")
    assert len(oracle_by(open_csv_deals(), "customer")) == 23


# ---------------------------------------------------------------------------
# The band read (plan A16.2, A12.2; C-20)
# ---------------------------------------------------------------------------


def stored_bands(session: Session, **changes) -> list[BandRow]:
    return band_rows(session, **{**identity(session), **changes})


def test_band_rows_returns_no_row_before_the_assessment_run_and_appendix_1s_bands_after(demo):
    """
    C-20: plain rows of (customer_source_id, band, executive_worthy), one per
    assessment at the identity. CUST-007 CRITICAL; CUST-025 and CUST-036
    WATCH; no customer ELEVATED; every other customer NONE.
    """
    with demo() as session:
        assert stored_bands(session) == []
    assess(demo)
    with demo() as session:
        rows = stored_bands(session)

    assert BandRow._fields == ("customer_source_id", "band", "executive_worthy")
    assert type(rows) is list and all(type(row) is BandRow for row in rows)
    assert len(rows) == 50 and len({row.customer_source_id for row in rows}) == 50
    assert [row.customer_source_id for row in rows] == [f"CUST-{n:03d}" for n in range(1, 51)]
    assert {row.customer_source_id: row.band for row in rows if row.band != "NONE"} == BANDED
    assert not [row for row in rows if row.band == "ELEVATED"]
    assert {type(row.band) for row in rows} == {str}
    assert {type(row.executive_worthy) for row in rows} == {bool}
    assert [row.customer_source_id for row in rows if row.executive_worthy] == ["CUST-007"]


def test_band_rows_runs_one_select_of_three_columns_joined_to_the_customers(assessed):
    """
    Plan A16.2: three columns, an inner join to customers, the five columns
    of the identity, and the order inside the statement in the C collation.
    It reads no signal, no rule and no ranking key of an assessment.
    """
    with assessed() as session:
        scope = identity(session)
        with statements(assessed) as seen:
            band_rows(session, **scope)

    [statement] = seen
    columns = statement.removeprefix("SELECT ").split(" FROM ")[0].split(", ")
    assert columns == ["customers.source_id", "risk_assessments.band",
                       "risk_assessments.executive_worthy"]
    assert (" FROM risk_assessments JOIN customers ON customers.id = "
            "risk_assessments.customer_id WHERE ") in statement
    conditions = statement.split(" WHERE ")[1].split(" ORDER BY ")[0].split(" AND ")
    assert [condition.split(" = ")[0] for condition in conditions] == [
        "risk_assessments.source_system", "risk_assessments.as_of",
        "risk_assessments.layer1_fingerprint", "risk_assessments.rules_version",
        "risk_assessments.linker_version"]
    assert statement.endswith('ORDER BY customers.source_id COLLATE "C"')
    assert not re.search(r"\b(LEFT|OUTER|FOR UPDATE|LIMIT|signals|ranking_key|satisfied_rules)\b",
                         statement)


def test_band_rows_takes_its_identity_by_keyword_alone():
    parameters = inspect.signature(band_rows).parameters

    assert list(parameters) == ["session", "source_system", "as_of", "layer1_fingerprint",
                                "rules_version", "linker_version"]
    assert all(parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
               for name in list(parameters)[1:])


def test_an_assessment_whose_customer_is_gone_is_not_returned(demo):
    """C-20, plan A16.2: it has no customer to attach a deal to. The join is an inner one."""
    with stored(demo) as session:
        scope = identity(session)
        store_assessment(session, **scope, customer=None, band="CRITICAL")
        store_assessment(session, **scope, customer="CUST-036", band="WATCH",
                         executive_worthy=True)
        rows = band_rows(session, **scope)
        held = session.scalar(select(func.count()).select_from(RiskAssessment))

    assert held == 2
    assert rows == [BandRow("CUST-036", "WATCH", True)]


ORDER_SYSTEM = "order_demo"
#: Ids a case-insensitive or locale-aware order arranges differently from code-point order.
ORDER_IDS = ["CUST-b", "CUST-B", "CUST-a", "CUST-A", "cust-1", "CUST-é", "CUST-10", "CUST-9",
             "CUST-Z", "Cust-2", "CUST_1"]


def test_band_rows_orders_by_code_point_where_a_locale_would_order_otherwise(demo):
    """
    C-20, with stored rows. The control: the same customers under an ICU
    collation come back in another order, so these ids can tell the two apart.
    """
    with stored(demo) as session:
        for source_id in ORDER_IDS:
            store_customer(session, source_system=ORDER_SYSTEM, source_id=source_id)
        scope = identity(session, ORDER_SYSTEM)
        for source_id in reversed(ORDER_IDS):
            store_assessment(session, **scope, customer=source_id, band="WATCH")
        found = [row.customer_source_id for row in band_rows(session, **scope)]
        by_locale = session.scalars(
            select(Customer.source_id).where(Customer.source_system == ORDER_SYSTEM)
            .order_by(Customer.source_id.collate("en-x-icu"))).all()
        facts = read_band_facts(session, resolve_scope(session, source_system=ORDER_SYSTEM,
                                                       as_of=AS_OF),
                                rules_version=scope["rules_version"],
                                linker_version=scope["linker_version"])

    assert found == sorted(ORDER_IDS) == [
        "CUST-10", "CUST-9", "CUST-A", "CUST-B", "CUST-Z", "CUST-a", "CUST-b", "CUST-é",
        "CUST_1", "Cust-2", "cust-1"]
    assert sorted(by_locale) == found and by_locale != found
    assert [fact.customer for fact in facts] == found
    assert all(type(fact) is BandFact for fact in facts) and type(facts) is tuple


def test_the_facts_reader_hands_the_bands_on_as_stored(assessed):
    """Plan A22.2: the band read in facts.py judges nothing. It is band_rows, as BandFacts."""
    with assessed() as session:
        scope = resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=AS_OF)
        rules = default_risk_rules()
        with statements(assessed) as seen:
            facts = read_band_facts(session, scope, rules_version=rules.rules_version,
                                    linker_version=rules.linker_version)
        rows = stored_bands(session)

    assert len(seen) == 1 and seen[0].startswith("SELECT customers.source_id")
    assert [(fact.customer, fact.band, fact.executive_worthy) for fact in facts] == [
        tuple(row) for row in rows]
    assert list(inspect.signature(read_band_facts).parameters) == [
        "session", "scope", "rules_version", "linker_version"]


# ---------------------------------------------------------------------------
# The five filters of the identity (C-21; named test 12)
# ---------------------------------------------------------------------------

OFF_IDENTITY = {
    "source_system": lambda scope: {"source_system": "other_demo",
                                    "customer_system": SOURCE_SYSTEM},
    "as_of": lambda scope: {"as_of": date(2026, 9, 17)},
    "layer1_fingerprint": lambda scope: {"layer1_fingerprint": "f" * 64},
    "rules_version": lambda scope: {"rules_version": scope["rules_version"] + 1},
    "linker_version": lambda scope: {"linker_version": scope["linker_version"] + "-next"},
}


@pytest.mark.parametrize("differs", sorted(OFF_IDENTITY))
def test_an_assessment_that_differs_from_the_identity_in_one_column_is_not_joined(demo, differs):
    """
    C-21: for each of the five in turn. CUST-007 holds an open valued deal
    and its one stored assessment is CRITICAL, but it differs from the
    identity in exactly one column. It is not returned and not joined: every
    linked deal is UNASSESSED and the scope note is present.
    """
    with stored(demo) as session:
        scope = identity(session)
        store_assessment(session, **{**scope, **OFF_IDENTITY[differs](scope)},
                         customer="CUST-007", band="CRITICAL", executive_worthy=True)
        held = session.scalar(select(func.count()).select_from(RiskAssessment))
        rows = band_rows(session, **scope)
        found = pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM).view

    assert held == 1 and rows == []
    bands = keyed(found["by_risk_band"])
    assert {key: bucket["deal_count"] for key, bucket in bands.items()} == {
        "CRITICAL": 0, "ELEVATED": 0, "WATCH": 0, "NONE": 0, "UNASSESSED": 30, "UNLINKED": 0}
    assert bands["UNASSESSED"]["customer_count"] == 23
    assert keyed(found["by_customer"])["CUST-007"]["band"] == "UNASSESSED"
    assert found["risk_coincidence"] == []
    assert found["data_quality"] == [{"code": "NO_ASSESSMENT_FOR_SCOPE", "entity": None,
                                      "id": None, "fields": [], "key": None}]


def test_the_same_assessment_at_exactly_the_identity_is_joined(demo):
    """C-21's control: with no column changed, the row is returned and the deal is banded."""
    with stored(demo) as session:
        scope = identity(session)
        store_assessment(session, **scope, customer="CUST-007", band="CRITICAL",
                         executive_worthy=True)
        rows = band_rows(session, **scope)
        found = pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM).view

    assert rows == [BandRow("CUST-007", "CRITICAL", True)]
    assert keyed(found["by_risk_band"])["CRITICAL"]["deal_ids"] == ["DEAL-001"]
    assert found["risk_coincidence"] == ["CUST-007"] and found["data_quality"] == []


def test_stale_assessments_made_by_vs01_itself_are_not_joined(demo):
    """
    Named test 12, with VS-01's own writer: an assessment run at another
    as_of, one under another rules version, and one made before the snapshot
    moved. None is joined at the acceptance date.
    """
    assess(demo, as_of=date(2026, 9, 17))
    assess(demo, config=dataclasses.replace(default_risk_rules(), rules_version=99))
    with demo() as session:
        held = session.scalar(select(func.count()).select_from(RiskAssessment))
    stale = view(demo)

    assert held == 100
    assert keyed(stale["by_risk_band"])["UNASSESSED"]["deal_count"] == 30
    assert stale["data_quality"][0]["code"] == "NO_ASSESSMENT_FOR_SCOPE"

    assess(demo)
    assert keyed(view(demo)["by_risk_band"])["UNASSESSED"]["deal_count"] == 0
    assert view(demo, as_of=date(2026, 9, 17))["risk_coincidence"] == view(demo)[
        "risk_coincidence"], "the other date joins its own assessments"

    apply("undated_deal", demo)
    moved = view(demo)
    assert moved["scope"]["layer1_fingerprint"] != PINNED
    assert keyed(moved["by_risk_band"])["UNASSESSED"]["deal_count"] == 31
    assert moved["risk_coincidence"] == []
    assert {"code": "NO_ASSESSMENT_FOR_SCOPE", "entity": None, "id": None, "fields": [],
            "key": None} in moved["data_quality"]


# ---------------------------------------------------------------------------
# The service and its contract (C-36)
# ---------------------------------------------------------------------------


def test_pipeline_view_takes_a_session_a_date_and_a_source_system_and_nothing_else():
    """
    Plan A22.2, A22.5 seam 1: it obtains the default rate set and rules
    itself. No parameter selects either.
    """
    parameters = inspect.signature(pipeline_view).parameters

    assert list(parameters) == ["session", "as_of", "source_system"]
    assert parameters["session"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert {parameters[name].kind for name in ("as_of", "source_system")} == {
        inspect.Parameter.KEYWORD_ONLY}
    assert all(parameter.default is inspect.Parameter.empty for parameter in parameters.values())


def test_the_service_returns_the_view_its_hash_the_texts_and_the_citations(assessed):
    """
    C-36: every key of plan A14, the hash of the view it returned, the nine
    texts in order, and the citations. The scope is Scope.to_payload() with
    an explicit date; the versions are the committed rules file's and
    VS-01's current ones; fx states the committed rate set.
    """
    result = built(assessed)
    found = result.view
    with assessed() as session:
        scope = resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=AS_OF)

    assert type(result) is PipelineView
    assert list(found) == [
        "view_version", "scope", "versions", "fx", "deal_counts", "open_pipeline", "by_currency",
        "by_stage", "by_owner", "by_expected_close", "by_risk_band", "by_customer",
        "risk_coincidence", "concentration", "open_deals", "closed_deals", "data_quality",
        "limitations"]
    assert result.view_hash == hashlib.sha256(canonical(found).encode("utf-8")).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", result.view_hash)
    assert found["view_version"] == 1

    assert found["scope"] == scope.to_payload()
    assert found["scope"]["layer1_fingerprint"] == PINNED
    assert (found["scope"]["source_system"], found["scope"]["as_of"],
            found["scope"]["as_of_source"]) == ("csv_demo", "2026-09-18", "EXPLICIT")
    assert found["scope"]["entity_counts"] == {
        "customers": 50, "deals": 44, "documents": 12, "employees": 24, "organizations": 1,
        "projects": 22, "support_tickets": 80}
    rules = default_risk_rules()
    assert found["versions"] == {
        "pipeline_version": default_pipeline_rules().pipeline_version,
        "rules_version": rules.rules_version, "linker_version": rules.linker_version}
    assert found["versions"]["pipeline_version"] == 1

    assert found["fx"] == {
        "base_currency": "INR", "rate_set_version": "1", "rate_as_of_date": "2026-10-01",
        "rate_set_digest": RATE_SET_DIGEST, "standing": "STATED_ASSUMPTION",
        "source_note": ("Owner-authored illustrative rates for VS-02 deterministic demo "
                        "calculations and acceptance testing; not sourced from a live market "
                        "feed."),
        "rates": [{"currency": "EUR", "rate_to_base": "100"},
                  {"currency": "INR", "rate_to_base": "1"},
                  {"currency": "USD", "rate_to_base": "85"}],
        "used_currencies": ["EUR", "INR", "USD"]}
    assert [bucket["key"] for bucket in found["by_stage"]] == sorted(
        default_config().fields["deals"]["stage"].enum_values) == [
        "negotiation", "qualification", "won"]
    assert all(type(value) in {dict, list, str, int, bool, type(None)} for value in walk(found))


def test_the_nine_limitation_texts_are_the_plans_character_for_character(assessed):
    """C-36, named test 6 [R]: plan A13.1's texts, in order, with their placeholders filled."""
    result = built(assessed)

    assert result.view["limitations"] == [entry["code"] for entry in result.limitation_texts]
    assert result.limitation_texts == [
        {"code": "NO_LOST_STAGE",
         "text": "The deal-stage vocabulary is negotiation, qualification, won. It records no "
                 "lost outcome, so no win rate and no stage-conversion figure can be stated, "
                 "and none is."},
        {"code": "NO_ACTUAL_CLOSE_DATE",
         "text": "A closed deal carries an expected close date only. No actual close date "
                 "exists."},
        {"code": "NO_DEAL_HISTORY",
         "text": "Deals carry no creation or stage-change date. The pipeline is that of the "
                 "data snapshot; as_of does not rewind it."},
        {"code": "FX_STATED_ASSUMPTION",
         "text": "Base-currency figures use rate set 1, stated for 2026-10-01. The rates are an "
                 "assumption, not a market quotation, and are not matched to as_of."},
        {"code": "SHARES_FOLLOW_RATES",
         "text": "Concentration shares are computed in the base currency and change with the "
                 "rate set."},
        {"code": "SOURCE_STATED_PROBABILITY",
         "text": "Weighted exposure multiplies each amount by the probability the source system "
                 "states. It is not a forecast."},
        {"code": "SINGLE_SOURCE_SYSTEM",
         "text": "Only source system csv_demo is included. Nothing is aggregated across source "
                 "systems."},
        {"code": "PERIOD_HORIZON",
         "text": "Expected-close periods are the twelve calendar months from the month of "
                 "as_of. Later dates are grouped as LATER."},
        {"code": "BAND_IS_NOT_MONEY",
         "text": "A risk band groups exposure and is never applied to an amount."},
    ]
    assert "lost" not in default_config().fields["deals"]["stage"].enum_values


def test_as_of_is_part_of_the_scope_and_places_deals_and_selects_assessments_and_no_more(
        assessed):
    """Plan A6 item 4: a date before all data, or in the future, is not an error."""
    now = view(assessed)
    for other in (date(1900, 1, 1), date(2099, 12, 31)):
        then = view(assessed, as_of=other)

        assert then["scope"]["as_of"] == other.isoformat()
        assert then["scope"]["layer1_fingerprint"] == PINNED
        for name in ("deal_counts", "open_pipeline", "by_currency", "by_stage", "by_owner",
                     "open_deals", "closed_deals", "concentration", "fx", "versions",
                     "limitations"):
            assert then[name] == now[name], name
        assert then["by_expected_close"] != now["by_expected_close"]
        assert len(then["by_expected_close"]) == 15
        assert keyed(then["by_risk_band"])["UNASSESSED"]["deal_count"] == 30


# ---------------------------------------------------------------------------
# The dataset: counts, partitions, bands, customers (C-23, C-24, C-30, C-31)
# ---------------------------------------------------------------------------


def test_deal_counts_equals_appendix_1_in_full(assessed):
    """C-30: 44 deals, 30 open and all valued, 14 closed; the four rows in order."""
    counts = view(assessed)["deal_counts"]

    assert counts == {
        "total": 44, "open": 30, "open_valued": 30, "open_unvalued": 0, "closed": 14,
        "unvalued_deal_ids": [],
        "by_stage": [{"stage": "negotiation", "total": 14, "open": 14, "closed": 0},
                     {"stage": "qualification", "total": 16, "open": 16, "closed": 0},
                     {"stage": "won", "total": 14, "open": 0, "closed": 14},
                     {"stage": "UNSTAGED", "total": 0, "open": 0, "closed": 0}]}
    stages = oracle_by(csv_deals(), "stage")
    assert {row["stage"]: (row["total"], row["open"], row["closed"])
            for row in counts["by_stage"][:-1]} == {
        stage: (len(deals), len([one for one in deals if one.is_open]),
                len([one for one in deals if not one.is_open]))
        for stage, deals in stages.items()}


def test_deal_counts_reconciles_on_the_dataset(assessed):
    """C-31: the four identities of plan A14.5, and no key beyond the four in any row."""
    counts = view(assessed)["deal_counts"]
    rows = counts["by_stage"]

    assert counts["open"] == counts["open_valued"] + counts["open_unvalued"]
    assert counts["total"] == counts["open"] + counts["closed"]
    assert all(row["total"] == row["open"] + row["closed"] for row in rows)
    assert sum(row["total"] for row in rows) == counts["total"] == 44
    assert sum(row["open"] for row in rows) == counts["open"]
    assert sum(row["closed"] for row in rows) == counts["closed"]
    assert all(list(row) == ["stage", "total", "open", "closed"] for row in rows)


def test_unvalued_deals_are_counted_listed_and_noted_in_the_view(demo):
    """
    C-30, named test 15 repeated over the view (OD-4): fixtures 1 and 2 are
    counted in open_unvalued, listed ascending in unvalued_deal_ids and in
    open_deals, noted, and in no monetary figure.
    """
    before = view(demo)
    apply("unvalued_deals", demo)
    apply("negative_amount", demo)
    after = view(demo)
    counts = after["deal_counts"]

    assert (counts["total"], counts["open"], counts["open_valued"], counts["open_unvalued"],
            counts["closed"]) == (47, 33, 30, 3, 14)
    assert counts["open_valued"] + counts["open_unvalued"] == counts["open"]
    assert counts["unvalued_deal_ids"] == ["DEAL-960", "DEAL-961", "DEAL-962"]
    assert {row["stage"]: (row["total"], row["open"], row["closed"])
            for row in counts["by_stage"]} == {
        "negotiation": (15, 15, 0), "qualification": (18, 18, 0), "won": (14, 0, 14),
        "UNSTAGED": (0, 0, 0)}
    unvalued = [entry for entry in after["open_deals"] if entry["state"] == "OPEN_UNVALUED"]
    assert [(entry["id"], entry["amount"], entry["probability"], entry["native_weighted"],
             entry["base_unweighted"], entry["base_weighted"]) for entry in unvalued] == [
        ("DEAL-960", None, "40", None, None, None), ("DEAL-961", "1250", None, None, None, None),
        ("DEAL-962", "-1500", "60", None, None, None)]
    assert len(after["open_deals"]) == 33
    assert [(note["code"], note["id"], note["fields"]) for note in after["data_quality"]
            if note["id"] is not None] == [
        ("INCOMPLETE_DEAL", "DEAL-960", ["amount"]),
        ("INCOMPLETE_DEAL", "DEAL-961", ["probability"]),
        ("NEGATIVE_AMOUNT", "DEAL-962", ["amount"])]
    for name in (*SIX, "open_pipeline", "concentration"):
        assert after[name] == before[name], name
    assert not {"DEAL-960", "DEAL-961", "DEAL-962"} & {
        source_id for name in SIX for bucket in after[name] for source_id in bucket["deal_ids"]}


def test_a_deal_is_counted_by_its_activity_in_the_row_of_its_stage(demo):
    """
    C-30 with fixture 6: an open deal in a closed stage is counted in that
    stage's open, and a closed deal in an open stage in that stage's closed.
    """
    apply("stage_activity_mismatch", demo)
    found = view(demo)
    rows = {row["stage"]: (row["total"], row["open"], row["closed"])
            for row in found["deal_counts"]["by_stage"]}

    assert rows == {"negotiation": (15, 14, 1), "qualification": (16, 16, 0),
                    "won": (15, 1, 14), "UNSTAGED": (0, 0, 0)}
    assert (found["deal_counts"]["open"], found["deal_counts"]["closed"]) == (31, 15)
    assert keyed(found["by_stage"])["won"]["deal_ids"] == ["DEAL-968"]
    assert {"id": "DEAL-969", "stage": "negotiation", "is_active": False} in found[
        "closed_deals"]
    assert [(note["code"], note["id"]) for note in found["data_quality"]
            if note["id"] is not None] == [("STAGE_ACTIVITY_MISMATCH", "DEAL-968"),
                                           ("STAGE_ACTIVITY_MISMATCH", "DEAL-969")]


def test_the_four_partitions_of_m2_are_what_the_entry_point_gave_at_m2(assessed):
    """
    C-44: Appendix 1's and Appendix 2's figures for the four M2 partitions,
    through the view. The entry point called as M2 called it gives the same.
    """
    found = view(assessed)

    assert {bucket["key"]: (bucket["deal_count"], *native(bucket)[bucket["key"]], *base(bucket),
                            bucket["rate_to_base"]) for bucket in found["by_currency"]} == {
        "EUR": (1, "96633.33", "38653.33", "INR", "9663333", "3865333", "100"),
        "INR": (21, "47342500", "20707975", "INR", "47342500", "20707975", "1"),
        "USD": (8, "193373.46", "91796.37", "INR", "16436744.1", "7802691.45", "85")}
    assert [(bucket["key"], bucket["deal_count"], *base(bucket)[1:])
            for bucket in found["by_stage"]] == [
        ("negotiation", 14, "31187137.1", "21710089.45"),
        ("qualification", 16, "42255440", "10665910"), ("won", 0, "0", "0")]
    assert [(bucket["key"], bucket["kind"], bucket["deal_count"])
            for bucket in found["by_owner"]] == [
        ("EMP-007", "EMPLOYEE", 10), ("EMP-008", "EMPLOYEE", 7), ("EMP-009", "EMPLOYEE", 1),
        ("EMP-010", "EMPLOYEE", 12), ("UNASSIGNED", "UNASSIGNED", 0),
        ("UNRESOLVED", "UNRESOLVED", 0)]
    assert native(keyed(found["by_owner"])["EMP-010"])["USD"] == ("113295.17", "43129.52")
    assert {bucket["key"]: bucket["deal_count"] for bucket in found["by_expected_close"]
            if bucket["deal_count"]} == {
        "2026-09": 1, "2026-10": 3, "2026-11": 3, "2026-12": 3, "2027-01": 4, "2027-02": 2,
        "2027-03": 7, "2027-04": 7}

    with assessed() as session:
        scope = resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=AS_OF)
        partitions = build_partitions(
            read_deal_facts(session, scope), default_rate_set(),
            default_config().fields["deals"]["stage"].enum_values, AS_OF)
    assert [(bucket.key, bucket.deal_count, dec(bucket.base.unweighted))
            for bucket in partitions.by_currency] == [
        (bucket["key"], bucket["deal_count"], bucket["base"]["unweighted"])
        for bucket in found["by_currency"]]
    assert [bucket.deal_ids for bucket in partitions.by_owner] == [
        tuple(bucket["deal_ids"]) for bucket in found["by_owner"]]


def test_by_risk_band_equals_appendix_1_and_appendix_2_in_full(assessed):
    """
    C-23: six buckets in order; each bucket's customers and deals, with the
    ids the table names; its native figures; and Appendix 2's base figures.
    CUST-025 is WATCH, holds no deal and is in no bucket.
    """
    buckets = view(assessed)["by_risk_band"]
    bands = keyed(buckets)

    assert [bucket["key"] for bucket in buckets] == BAND_ORDER
    assert {key: (bucket["customer_count"], bucket["deal_count"])
            for key, bucket in bands.items()} == {
        "CRITICAL": (1, 1), "ELEVATED": (0, 0), "WATCH": (1, 1), "NONE": (21, 28),
        "UNASSESSED": (0, 0), "UNLINKED": (0, 0)}
    assert (bands["CRITICAL"]["customer_ids"], bands["CRITICAL"]["deal_ids"]) == (
        ["CUST-007"], ["DEAL-001"])
    assert (bands["WATCH"]["customer_ids"], bands["WATCH"]["deal_ids"]) == (
        ["CUST-036"], ["DEAL-037"])
    assert native(bands["CRITICAL"]) == {"USD": ("5361.44", "4825.3")}
    assert native(bands["WATCH"]) == {"INR": ("499000", "149700")}
    assert {currency: figures[0] for currency, figures in native(bands["NONE"]).items()} == {
        "EUR": "96633.33", "INR": "46843500", "USD": "188012.02"}
    assert [amount["currency"] for amount in bands["NONE"]["native"]] == ["EUR", "INR", "USD"]
    assert base(bands["CRITICAL"]) == ("INR", "455722.4", "410150.5")
    assert base(bands["WATCH"]) == ("INR", "499000", "149700")
    assert base(bands["NONE"]) == ("INR", "72487854.7", "31816148.95")
    for key in ("ELEVATED", "UNASSESSED", "UNLINKED"):
        assert bands[key] == {
            "key": key, "deal_count": 0, "deal_ids": [], "native": [],
            "base": {"currency": "INR", "unweighted": "0", "weighted": "0"},
            "customer_count": 0, "customer_ids": []}
    assert "CUST-025" not in {customer for bucket in buckets
                              for customer in bucket["customer_ids"]}
    assert len(bands["NONE"]["customer_ids"]) == 21
    assert bands["NONE"]["customer_ids"] == sorted(bands["NONE"]["customer_ids"])


def test_every_band_bucket_equals_what_the_committed_file_gives(assessed):
    """C-23, worked here from the CSV: each band's deals, native figures and base figures."""
    bands = keyed(view(assessed)["by_risk_band"])
    by_band = oracle_by(open_csv_deals(), "customer")
    grouped: dict[str, list[CsvDeal]] = {key: [] for key in BAND_ORDER}
    for customer, deals in by_band.items():
        grouped[BANDED.get(customer, "NONE")] += deals

    for key, deals in grouped.items():
        ids, native_figures, base_figures = oracle_bucket(deals)
        assert bands[key]["deal_ids"] == ids, key
        assert native(bands[key]) == native_figures, key
        assert base(bands[key])[1:] == base_figures, key
        assert bands[key]["customer_ids"] == sorted({one.customer for one in deals}), key


def test_by_customer_holds_23_customers_in_exposure_order_then_unlinked(assessed):
    """
    C-24: 23 CUSTOMER buckets and UNLINKED, present, empty and last; ordered
    by base unweighted exposure descending and then by key, which the CSV
    gives independently; and each bucket's figures.
    """
    buckets = view(assessed)["by_customer"]
    by_customer = oracle_by(open_csv_deals(), "customer")
    expected = {customer: oracle_bucket(deals) for customer, deals in by_customer.items()}
    order = sorted(expected, key=lambda customer: (-Decimal(expected[customer][2][0]), customer))

    assert len(buckets) == 24
    assert [bucket["key"] for bucket in buckets] == [*order, "UNLINKED"]
    assert [bucket["kind"] for bucket in buckets] == [*["CUSTOMER"] * 23, "UNLINKED"]
    assert buckets[-1] == {
        "key": "UNLINKED", "deal_count": 0, "deal_ids": [], "native": [],
        "base": {"currency": "INR", "unweighted": "0", "weighted": "0"},
        "kind": "UNLINKED", "band": None, "executive_worthy": None}
    for bucket in buckets[:-1]:
        ids, native_figures, base_figures = expected[bucket["key"]]
        assert (bucket["deal_ids"], native(bucket), base(bucket)[1:]) == (
            ids, native_figures, base_figures), bucket["key"]
    assert [bucket["key"] for bucket in buckets[:5]] == [
        "CUST-042", "CUST-015", "CUST-037", "CUST-010", "CUST-049"]
    amounts = [Decimal(bucket["base"]["unweighted"]) for bucket in buckets[:-1]]
    assert amounts == sorted(amounts, reverse=True)


def test_each_customer_bucket_carries_the_stored_assessments_band_and_verdict(assessed):
    """C-24: equal to what VS-01 persisted, read here from its own table."""
    buckets = view(assessed)["by_customer"][:-1]
    with assessed() as session:
        persisted = {source_id: (band, worthy) for source_id, band, worthy in session.execute(
            select(Customer.source_id, RiskAssessment.band, RiskAssessment.executive_worthy)
            .join(RiskAssessment, RiskAssessment.customer_id == Customer.id))}

    assert len(persisted) == 50
    assert {bucket["key"]: (bucket["band"], bucket["executive_worthy"])
            for bucket in buckets} == {bucket["key"]: persisted[bucket["key"]]
                                       for bucket in buckets}
    assert {bucket["key"]: bucket["band"] for bucket in buckets
            if bucket["band"] != "NONE"} == {"CUST-007": "CRITICAL", "CUST-036": "WATCH"}
    assert [bucket["key"] for bucket in buckets if bucket["executive_worthy"]] == ["CUST-007"]
    assert {type(bucket["executive_worthy"]) for bucket in buckets} == {bool}


def test_by_customer_equals_vs01s_exposure_by_currency_for_every_customer(assessed):
    """
    C-24, named test 17 taken over by_customer: VS-02's native unweighted
    open exposure per currency equals VS-01's own exposure_by_currency. The
    committed dataset holds no negative-amount open deal, so for every customer.
    """
    buckets = view(assessed)["by_customer"][:-1]
    with assessed() as session:
        scope = resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=AS_OF)
        theirs = {one.customer.source_id: {
            currency: dec(value.amount)
            for currency, value in sorted(one.signals.exposure_by_currency.items())}
            for one in compute_all_signals(session, scope)
            if one.signals.exposure_by_currency}

    ours = {bucket["key"]: {currency: figures[0]
                            for currency, figures in native(bucket).items()}
            for bucket in buckets}
    assert ours == theirs and len(ours) == 23
    assert ours["CUST-007"] == {"USD": "5361.44"}


def test_customers_in_two_currencies_state_each_natively_and_one_base(assessed):
    """
    C-40, named test 19: CUST-029, CUST-042 and CUST-050 each hold open deals
    in two currencies. CUST-042 shows INR and USD natively and one base
    amount: 9,611,500.00 and 107,746.98 x 85.
    """
    found = view(assessed)
    customers = keyed(found["by_customer"])
    two = sorted(key for key, bucket in customers.items() if len(bucket["native"]) == 2)

    assert two == ["CUST-029", "CUST-042", "CUST-050"]
    assert native(customers["CUST-042"]) == {"INR": ("9611500", "1801150"),
                                             "USD": ("107746.98", "38690.97")}
    assert [amount["currency"] for amount in customers["CUST-042"]["native"]] == ["INR", "USD"]
    assert base(customers["CUST-042"]) == ("INR", "18769993.3", "5089882.45")
    assert Decimal("9611500.00") + Decimal("107746.98") * 85 == Decimal("18769993.30")
    assert customers["CUST-042"]["deal_ids"] == ["DEAL-005", "DEAL-008", "DEAL-016", "DEAL-032"]
    for key in two:
        assert all(set(amount) == {"currency", "unweighted", "weighted"}
                   for amount in customers[key]["native"])
        assert set(customers[key]["base"]) == {"currency", "unweighted", "weighted"}
    assert len(keyed(found["by_risk_band"])["NONE"]["native"]) == 3
    blocks = [block for pair in found["concentration"].values() for block in pair.values()]
    assert {block["currency"] for block in blocks} == {"INR"}


# ---------------------------------------------------------------------------
# Reconciliation and base labelling (named tests 4 and 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("partition", SIX)
def test_each_of_the_six_partitions_reconciles_exactly_to_the_pinned_totals(assessed, partition):
    """
    Named test 4 [R]: 30 deals, each in exactly one bucket; Appendix 1's
    totals per currency; INR 73,442,577.10 and INR 32,375,999.45. No tolerance.
    """
    found = view(assessed)
    buckets = found[partition]
    ids, native_totals, base_totals = oracle_bucket(open_csv_deals())

    assert sum(bucket["deal_count"] for bucket in buckets) == 30
    assert sorted(source_id for bucket in buckets for source_id in bucket["deal_ids"]) == ids
    for currency, (unweighted, weighted) in native_totals.items():
        held = [amount for bucket in buckets for amount in bucket["native"]
                if amount["currency"] == currency]
        assert dec(sum((Decimal(amount["unweighted"]) for amount in held), Decimal(0))) == (
            unweighted)
        assert dec(sum((Decimal(amount["weighted"]) for amount in held), Decimal(0))) == weighted
    assert {amount["currency"] for bucket in buckets for amount in bucket["native"]} == set(
        native_totals)
    assert (dec(sum((Decimal(bucket["base"]["unweighted"]) for bucket in buckets), Decimal(0))),
            dec(sum((Decimal(bucket["base"]["weighted"]) for bucket in buckets), Decimal(0)))
            ) == base_totals == ("73442577.1", "32375999.45")
    assert base(found["open_pipeline"]) == ("INR", *base_totals)
    assert (found["open_pipeline"]["deal_ids"], native(found["open_pipeline"])) == (
        ids, native_totals)


def test_every_open_deal_states_its_own_values_and_they_sum_to_the_pipeline(assessed):
    """Plan A9.4 item 3: each aggregate is the sum of the per-deal values the view states."""
    found = view(assessed)
    expected = {one.source_id: one for one in open_csv_deals()}

    assert [entry["id"] for entry in found["open_deals"]] == sorted(expected)
    for entry in found["open_deals"]:
        values = expected[entry["id"]].values
        assert (entry["state"], entry["is_active"], entry["amount"], entry["native_weighted"],
                entry["base_unweighted"], entry["base_weighted"]) == (
            "OPEN_VALUED", True, *(dec(value) for value in values)), entry["id"]
    assert dec(sum((Decimal(entry["base_unweighted"]) for entry in found["open_deals"]),
                   Decimal(0))) == found["open_pipeline"]["base"]["unweighted"]
    closed = [one.source_id for one in csv_deals() if not one.is_open]
    assert found["closed_deals"] == [{"id": source_id, "stage": "won", "is_active": False}
                                     for source_id in sorted(closed)]


def test_every_base_aggregate_of_the_dataset_names_the_views_base_currency(assessed):
    """
    Named test 5 [R], by walking the whole view: every `base` Amount and
    every Concentration block names fx.base_currency; the version and the
    digest are named once, in fx; a deal's base values carry no currency.
    """
    found = view(assessed)
    fx = found["fx"]
    bases = [value["base"] for value in walk(found) if isinstance(value, dict) and "base" in value]
    blocks = [block for pair in found["concentration"].values() for block in pair.values()]

    assert len(bases) == 1 + sum(len(found[name]) for name in SIX)
    assert {amount["currency"] for amount in bases} == {fx["base_currency"]} == {"INR"}
    assert len(blocks) == 4
    assert {(block["currency"], block["rate_set_version"]) for block in blocks} == {
        (fx["base_currency"], fx["rate_set_version"])}
    assert len([value for value in walk(found)
                if isinstance(value, dict) and "rate_set_version" in value]) == 5
    assert len([value for value in walk(found)
                if isinstance(value, dict) and "rate_set_digest" in value]) == 1
    assert all("base_currency" not in entry and "rate_set_version" not in entry
               for entry in found["open_deals"])


# ---------------------------------------------------------------------------
# Coincidence and concentration (C-26, C-27, C-28; named test 18)
# ---------------------------------------------------------------------------


def test_coincidence_on_the_dataset_is_the_two_banded_customers_who_hold_a_deal(assessed):
    """C-26: [CUST-007, CUST-036]. CUST-025 is WATCH and holds no deal."""
    found = view(assessed)

    assert found["risk_coincidence"] == ["CUST-007", "CUST-036"]
    assert set(found["risk_coincidence"]) <= {bucket["key"] for bucket in found["by_customer"]
                                              if bucket["kind"] == "CUSTOMER"}
    assert all(type(customer) is str for customer in found["risk_coincidence"])
    assert view(assessed, as_of=date(2026, 9, 17))["risk_coincidence"] == []


def test_concentration_equals_appendix_2_in_full(assessed):
    """
    C-27: by customer, 23 holders, the five largest with their shares, the
    three cumulative shares and the index; by owner, 4 holders, the four
    shares, the cumulative share at 5 holders, which is 1, and the index.
    """
    blocks = view(assessed)["concentration"]
    customers = blocks["by_customer"]["unweighted"]
    owners = blocks["by_owner"]["unweighted"]

    assert (customers["currency"], customers["rate_set_version"], customers["total"],
            customers["holder_count"], customers["reason"]) == (
        "INR", "1", "73442577.1", 23, None)
    assert [(holder["key"], holder["share"]) for holder in customers["top"]] == [
        ("CUST-042", "0.2556"), ("CUST-015", "0.1742"), ("CUST-037", "0.1316"),
        ("CUST-010", "0.0911"), ("CUST-049", "0.0794")]
    assert [(point["holders"], point["share"]) for point in customers["cumulative"]] == [
        (1, "0.2556"), (3, "0.5614"), (5, "0.7319")]
    assert customers["hhi"] == "0.135"
    assert not [holder for holder in customers["top"] if holder["pseudo"]]

    assert (owners["total"], owners["holder_count"]) == ("73442577.1", 4)
    assert [(holder["key"], holder["pseudo"], holder["share"]) for holder in owners["top"]] == [
        ("EMP-010", False, "0.5913"), ("EMP-007", False, "0.206"), ("EMP-008", False, "0.1876"),
        ("EMP-009", False, "0.0151")]
    assert [(point["holders"], point["share"]) for point in owners["cumulative"]][-1] == (5, "1")
    assert owners["hhi"] == "0.4275"


def test_the_weighted_blocks_are_taken_from_the_weighted_amounts(assessed):
    """
    C-28: by customer CUST-015 leads the weighted block at 0.2767 and its
    index is 0.1369, while CUST-042 leads the unweighted one.
    """
    pair = view(assessed)["concentration"]["by_customer"]

    assert (pair["weighted"]["top"][0]["key"], pair["weighted"]["top"][0]["share"]) == (
        "CUST-015", "0.2767")
    assert pair["weighted"]["hhi"] == "0.1369"
    assert pair["unweighted"]["top"][0]["key"] == "CUST-042"
    assert (pair["weighted"]["total"], pair["weighted"]["holder_count"]) == ("32375999.45", 23)
    assert pair["weighted"]["top"][0]["amount"] == "8957900"


def test_every_figure_of_the_four_blocks_equals_what_the_committed_file_gives(assessed):
    """
    C-27, C-28: each share, cumulative share and index, of all four blocks,
    against a calculation that uses no VS-02 code: the holders' amounts are
    summed here from the CSV, and the ratios are worked in fractions.
    """
    found = view(assessed)
    totals = oracle_bucket(open_csv_deals())[2]

    for partition, attribute, pseudo in (("by_customer", "customer", "UNLINKED"),
                                         ("by_owner", "owner", "UNASSIGNED")):
        grouped = oracle_by(open_csv_deals(), attribute)
        for index, measure in enumerate(("unweighted", "weighted")):
            candidates = [(key, sum((one.values[2 + index] for one in deals), Decimal(0)))
                          for key, deals in grouped.items()]
            expected = exact_concentration([*candidates, (pseudo, Decimal(0))])
            block = found["concentration"][partition][measure]

            assert block["total"] == totals[index]
            assert block["holder_count"] == expected["holder_count"]
            assert [(holder["key"], holder["share"]) for holder in block["top"]] == (
                expected["top"]), (partition, measure)
            assert [(point["holders"], point["share"]) for point in block["cumulative"]] == (
                expected["cumulative"])
            assert block["hhi"] == expected["hhi"]
            amounts = dict(candidates)
            assert [holder["amount"] for holder in block["top"]] == [
                dec(amounts[holder["key"]]) for holder in block["top"]]
            assert (block["currency"], block["rate_set_version"], block["reason"]) == (
                "INR", "1", None)


# ---------------------------------------------------------------------------
# DOC-004 (named tests 2 and 3; plan A18.4)
# ---------------------------------------------------------------------------


def test_doc004s_stated_inr_figure_is_reproduced_from_the_records(assessed):
    """
    Named test 2 [R]: the INR native unweighted total of the open pipeline,
    rendered with two decimal places and comma grouping, equals the text of
    DOC-004's citable span [170, 187). The document is read here, by the
    test, and never by the code that built the view.
    """
    found = view(assessed)
    with assessed() as session:
        title, body = session.execute(
            select(Document.title, Document.body_text)
            .where(Document.source_system == SOURCE_SYSTEM,
                   Document.source_id == "DOC-004")).one()

    total = Decimal(native(found["open_pipeline"])["INR"][0])
    rendered = f"INR {total:,.2f}"
    assert rendered == "INR 47,342,500.00"
    assert citable_text(title, body)[170:187] == rendered
    assert native(keyed(found["by_currency"])["INR"])["INR"][0] == "47342500"


def test_with_doc004_removed_every_key_but_the_scope_is_identical(demo):
    """
    Named test 3, both halves. Each arm is assessed by VS-01's own run after
    its corpus is fixed, at the same as_of. Every top-level key but `scope`
    is identical as canonical JSON; the fingerprint, the document count and
    the hash differ. So the only difference is the snapshot's identity.
    """
    assess(demo)
    with_document = built(demo)

    apply("no_doc004", demo)
    unassessed = view(demo)
    assert keyed(unassessed["by_risk_band"])["UNASSESSED"]["deal_count"] == 30, (
        "the assessments made before the removal no longer join")
    assess(demo)
    without = built(demo)

    assert set(with_document.view) == set(without.view)
    for key in with_document.view:
        if key != "scope":
            assert canonical(without.view[key]) == canonical(with_document.view[key]), key
    assert (with_document.view["scope"]["layer1_fingerprint"],
            with_document.view["scope"]["entity_counts"]["documents"]) == (PINNED, 12)
    assert without.view["scope"]["layer1_fingerprint"] != PINNED
    assert without.view["scope"]["entity_counts"]["documents"] == 11
    assert {key: value for key, value in without.view["scope"]["entity_counts"].items()
            if key != "documents"} == {
        key: value for key, value in with_document.view["scope"]["entity_counts"].items()
        if key != "documents"}
    assert without.view_hash != with_document.view_hash
    assert without.limitation_texts == with_document.limitation_texts
    assert without.citations == with_document.citations
    assert without.view["risk_coincidence"] == ["CUST-007", "CUST-036"]


# ---------------------------------------------------------------------------
# What moves with the bands and the rates (named tests 8, 10 and 11)
# ---------------------------------------------------------------------------


def test_before_any_assessment_every_linked_deal_is_unassessed_and_the_totals_are_identical(demo):
    """
    Named test 11, first half; criterion 9. With no assessment every linked
    deal is UNASSESSED, the scope note is present, and no total moves when
    VS-01's assessment is then run.
    """
    before = view(demo)
    assess(demo)
    after = view(demo)

    bands = keyed(before["by_risk_band"])
    assert {key: bucket["deal_count"] for key, bucket in bands.items() if bucket["deal_count"]} == {
        "UNASSESSED": 30}
    assert bands["UNASSESSED"]["customer_count"] == 23
    assert base(bands["UNASSESSED"]) == ("INR", "73442577.1", "32375999.45")
    assert {bucket["band"] for bucket in before["by_customer"][:-1]} == {"UNASSESSED"}
    assert {bucket["executive_worthy"] for bucket in before["by_customer"]} == {None}
    assert before["risk_coincidence"] == []
    assert before["data_quality"] == [{"code": "NO_ASSESSMENT_FOR_SCOPE", "entity": None,
                                       "id": None, "fields": [], "key": None}]
    for name in ("deal_counts", "open_pipeline", "by_currency", "by_stage", "by_owner",
                 "by_expected_close", "concentration", "open_deals", "closed_deals", "fx",
                 "scope", "versions", "limitations"):
        assert after[name] == before[name], name
    assert after["data_quality"] == []


def test_with_one_customer_assessed_that_customer_is_banded_and_the_rest_are_unassessed(demo):
    """Named test 11, second half: VS-01's own run, for CUST-007 alone."""
    assess(demo, customer_source_id="CUST-007")
    found = view(demo)
    bands = keyed(found["by_risk_band"])

    assert {key: (bucket["customer_count"], bucket["deal_count"])
            for key, bucket in bands.items()} == {
        "CRITICAL": (1, 1), "ELEVATED": (0, 0), "WATCH": (0, 0), "NONE": (0, 0),
        "UNASSESSED": (22, 29), "UNLINKED": (0, 0)}
    assert bands["CRITICAL"]["customer_ids"] == ["CUST-007"]
    customers = keyed(found["by_customer"])
    assert (customers["CUST-007"]["band"], customers["CUST-007"]["executive_worthy"]) == (
        "CRITICAL", True)
    assert {bucket["band"] for key, bucket in customers.items()
            if key not in {"CUST-007", "UNLINKED"}} == {"UNASSESSED"}
    assert found["risk_coincidence"] == ["CUST-007"]
    assert found["data_quality"] == [], "one row was read, so the scope note is not stated"
    assert base(found["open_pipeline"]) == ("INR", "73442577.1", "32375999.45")


def test_permuting_the_stored_band_labels_moves_deals_and_changes_no_figure(demo):
    """
    Named test 10 [R], with stored assessments: the same customers given
    other bands. Deals move between the band buckets. No amount, no total
    and no concentration figure changes.
    """
    first_labels = {"CUST-042": "NONE", "CUST-015": "WATCH", "CUST-007": "CRITICAL",
                    "CUST-036": "ELEVATED", NO_DEAL: "CRITICAL"}
    second_labels = {"CUST-042": "CRITICAL", "CUST-015": "NONE", "CUST-007": "ELEVATED",
                     "CUST-036": "WATCH", NO_DEAL: "NONE"}
    views = []
    for labels in (first_labels, second_labels):
        with stored(demo) as session:
            scope = identity(session)
            for customer, label in labels.items():
                store_assessment(session, **scope, customer=customer, band=label,
                                 executive_worthy=label == "CRITICAL")
            views.append(pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM).view)
    first, second = views

    assert {key: bucket["customer_ids"] for key, bucket in keyed(first["by_risk_band"]).items()
            if bucket["deal_count"] and key != "UNASSESSED"} == {
        "CRITICAL": ["CUST-007"], "ELEVATED": ["CUST-036"], "WATCH": ["CUST-015"],
        "NONE": ["CUST-042"]}
    assert {key: bucket["customer_ids"] for key, bucket in keyed(second["by_risk_band"]).items()
            if bucket["deal_count"] and key != "UNASSESSED"} == {
        "CRITICAL": ["CUST-042"], "ELEVATED": ["CUST-007"], "WATCH": ["CUST-036"],
        "NONE": ["CUST-015"]}
    assert first["risk_coincidence"] == ["CUST-007", "CUST-036", "CUST-015"]
    assert second["risk_coincidence"] == ["CUST-042", "CUST-007", "CUST-036"]

    for name in ("deal_counts", "open_pipeline", "by_currency", "by_stage", "by_owner",
                 "by_expected_close", "concentration", "open_deals", "closed_deals", "fx",
                 "scope", "versions", "limitations", "data_quality"):
        assert second[name] == first[name], name

    def without_bands(buckets):
        return [{key: value for key, value in bucket.items()
                 if key not in {"band", "executive_worthy"}} for bucket in buckets]

    assert without_bands(second["by_customer"]) == without_bands(first["by_customer"])
    by_customer = keyed(first["by_customer"])
    for found in (first, second):
        for bucket in found["by_risk_band"]:
            held = [by_customer[customer] for customer in bucket["customer_ids"]]
            assert dec(sum((Decimal(one["base"]["unweighted"]) for one in held), Decimal(0))) == (
                bucket["base"]["unweighted"]), bucket["key"]
            assert dec(sum((Decimal(one["base"]["weighted"]) for one in held), Decimal(0))) == (
                bucket["base"]["weighted"]), bucket["key"]
        assert dec(sum((Decimal(bucket["base"]["unweighted"])
                        for bucket in found["by_risk_band"]), Decimal(0))) == "73442577.1"


def test_a_changed_usd_rate_changes_every_base_figure_with_a_usd_deal_and_no_native_one(
        assessed, tmp_path, monkeypatch):
    """
    Named test 8, through the service: the test authors a rate set of its
    own, loads it through the path loader, and substitutes what the default
    returns (plan A22.5 seam 1). The digest and the hash change with it.
    """
    before = built(assessed)
    other = rate_set(tmp_path, {"USD": "90.25", "EUR": "100"}, version="other")
    monkeypatch.setattr(service_module, "default_rate_set", lambda: other)
    after = built(assessed)
    usd = {one.source_id for one in open_csv_deals() if one.currency == "USD"}

    assert len(usd) == 8
    changed = 0
    for name in (*SIX, "open_pipeline"):
        old_buckets = keyed([before.view[name]] if name == "open_pipeline" else before.view[name])
        new_buckets = keyed([after.view[name]] if name == "open_pipeline" else after.view[name])
        assert sorted(old_buckets) == sorted(new_buckets), name
        for key, old in old_buckets.items():
            new = new_buckets[key]
            assert (old["deal_ids"], old["native"]) == (new["deal_ids"], new["native"]), name
            assert (old["base"] != new["base"]) is bool(usd & set(old["deal_ids"])), (name, key)
            changed += old["base"] != new["base"]
    assert changed > 10, "the control: buckets with a USD deal exist in every partition"
    assert after.view["deal_counts"] == before.view["deal_counts"]
    assert (after.view["fx"]["rate_set_version"], after.view["fx"]["rate_set_digest"]) == (
        "other", other.digest)
    assert after.view["fx"]["rate_set_digest"] != RATE_SET_DIGEST
    assert after.view_hash != before.view_hash
    assert keyed(after.view["by_currency"])["USD"]["base"]["unweighted"] == dec(
        sum((half_even_cents(Fraction(str(one.values[0])) * Fraction("90.25"))
             for one in open_csv_deals() if one.currency == "USD"), Decimal(0)))
    assert "rate set other, stated for 2026-10-01" in after.limitation_texts[3]["text"]


# ---------------------------------------------------------------------------
# Citations (named test 21; plan A18.2 item 3)
# ---------------------------------------------------------------------------


def stated(value: object) -> object:
    """A stored value rendered by plan A14.1's rule for its type."""
    if isinstance(value, Decimal):
        return dec(value)
    return value.isoformat() if isinstance(value, date) else value


def test_every_citation_resolves_to_the_stored_record_and_field(assessed):
    """
    Named test 21 [R], plan A18.2 item 3. The record exists in the scope.
    For every field but customer_id the stored value, rendered by the view's
    rule for its type, equals what the deal's entry states. For customer_id
    the stored key is not null and its customer has the id the entry states.
    """
    result = built(assessed)
    entries = {entry["id"]: entry
               for entry in (*result.view["open_deals"], *result.view["closed_deals"])}
    with assessed() as session:
        deals = {row.source_id: row for row in session.scalars(
            select(Deal).where(Deal.source_system == SOURCE_SYSTEM)).all()}
        customers = dict(session.execute(select(Customer.id, Customer.source_id)).all())

    assert len(result.citations) == 298 and len(deals) == 44
    assert [(one["id"], one["field"]) for one in result.citations] == sorted(
        (one["id"], one["field"]) for one in result.citations)
    assert {(one["kind"], one["entity"]) for one in result.citations} == {("record", "deals")}
    for citation in result.citations:
        row, entry = deals[citation["id"]], entries[citation["id"]]
        if citation["field"] == "customer_id":
            assert row.customer_id is not None
            assert customers[row.customer_id] == entry["customer"]
        else:
            assert stated(getattr(row, citation["field"])) == entry[citation["field"]], citation

    cited = {}
    for citation in result.citations:
        cited.setdefault(citation["id"], set()).add(citation["field"])
    assert cited["DEAL-001"] == {"is_active", "stage", "amount", "currency", "probability",
                                 "expected_close_date", "owner_source_id", "customer_source_id",
                                 "customer_id"}
    assert cited["DEAL-004"] == {"is_active", "stage"}
    assert len(cited) == 44 and 30 * 9 + 14 * 2 == 298


def test_a_deal_with_no_customer_cites_no_customer_key(demo):
    """Plan A18.2 item 2: customer_id is cited only where the customer is resolved."""
    apply("customer_keys", demo)
    result = built(demo)
    cited = {(one["id"], one["field"]) for one in result.citations}

    assert ("DEAL-965", "customer_id") not in cited
    assert ("DEAL-965", "customer_source_id") not in cited
    assert ("DEAL-966", "customer_source_id") in cited and ("DEAL-966", "customer_id") not in cited
    unlinked = keyed(result.view["by_customer"])["UNLINKED"]
    assert unlinked["deal_ids"] == ["DEAL-965", "DEAL-966"]
    assert (unlinked["band"], unlinked["executive_worthy"]) == (None, None)
    assert keyed(result.view["by_risk_band"])["UNLINKED"]["deal_ids"] == ["DEAL-965", "DEAL-966"]
    assert keyed(result.view["by_risk_band"])["UNLINKED"]["customer_count"] == 0
    top = result.view["concentration"]["by_customer"]["unweighted"]
    assert top["holder_count"] == 24, "UNLINKED holds exposure, so it is a holder"
    assert [(note["code"], note["id"], note["key"]) for note in result.view["data_quality"]
            if note["id"] is not None] == [
        ("CUSTOMER_KEY_MISSING", "DEAL-965", None),
        ("CUSTOMER_KEY_UNRESOLVED", "DEAL-966", "CUST-960")]


# ---------------------------------------------------------------------------
# Errors: the unknown band, the reserved customer, the missing rate
# (C-22, C-25, C-34; named tests 9 and 27)
# ---------------------------------------------------------------------------


def refused(session: Session) -> PipelineDataError:
    with pytest.raises(PipelineDataError) as raised:
        pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM)
    return raised.value


@pytest.mark.parametrize("customer", ["CUST-007", CLOSED_ONLY, NO_DEAL],
                         ids=["holds an open valued deal", "holds a closed deal only",
                              "holds no deal"])
def test_a_stored_band_outside_the_vocabulary_yields_no_view_whoever_its_customer_is(
        demo, customer):
    """
    Named test 27, C-22: every row band_rows returns is checked. The error
    names the entity `customers` and the customer, and no deal. The band is
    given no bucket and its row is not skipped.
    """
    with stored(demo) as session:
        scope = identity(session)
        store_assessment(session, **scope, customer="CUST-036", band="WATCH")
        store_assessment(session, **scope, customer=customer, band="SEVERE")
        error = refused(session)

    assert (error.condition, error.entity) == ("BAND_OUTSIDE_VOCABULARY", "customers")
    assert error.source_ids == (customer,) and error.keys == ()
    assert str(error) == f"BAND_OUTSIDE_VOCABULARY; customers {customer}"
    assert "DEAL-" not in str(error)


def test_several_unknown_bands_raise_once_and_name_every_customer_ascending(demo):
    """C-22: several such rows, one error, the customers by code point and once each."""
    with stored(demo) as session:
        scope = identity(session)
        for customer, label in (("CUST-050", "?"), ("CUST-007", "SEVERE"), (NO_DEAL, "none"),
                                (CLOSED_ONLY, "UNASSESSED"), ("CUST-036", "WATCH")):
            store_assessment(session, **scope, customer=customer, band=label)
        error = refused(session)

    assert error.entity == "customers"
    assert error.source_ids == ("CUST-007", "CUST-021", "CUST-025", "CUST-050")
    assert str(error) == ("BAND_OUTSIDE_VOCABULARY; customers CUST-007, CUST-021, CUST-025, "
                          "CUST-050")


def test_fixture_10s_customer_under_a_reserved_key_yields_no_view(demo):
    """
    C-25, at the M3 gate what named test 24 shows over HTTP at M4: a customer
    whose source_id is UNLINKED, holding an open valued deal, fails stage 1.
    """
    apply("reserved_customer", demo)
    with demo() as session:
        error = refused(session)

    assert (error.condition, error.entity) == ("RESERVED_KEY", "deals")
    assert (error.keys, error.source_ids) == (("UNLINKED",), ("DEAL-971",))
    assert str(error) == "RESERVED_KEY; keys UNLINKED; deals DEAL-971"


def test_a_currency_without_a_rate_raises_once_naming_it_and_the_rate_set(demo):
    """
    Named test 9, C-34, with fixture 8: the service raises FxRateMissingError
    once, carrying GBP and the rate-set version. No view is returned. It is
    the existing class, raised by the service and not caught by it.
    """
    apply("gbp_deal", demo)

    with demo() as session, pytest.raises(FxRateMissingError) as raised:
        pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM)

    assert type(raised.value) is FxRateMissingError
    assert raised.value.currencies == ("GBP",)
    assert raised.value.rate_set_version == "1"
    assert str(raised.value) == "rate set '1' holds no rate for GBP"


def test_two_currencies_without_a_rate_are_both_named_ascending(demo, tmp_path, monkeypatch):
    """
    Named test 9, C-34: with a second such currency the one error names both,
    ascending. M2's entry point would name one, and which is not its contract.
    """
    apply("gbp_deal", demo)
    dollars_only = rate_set(tmp_path, {"USD": "85"}, version="no-eur")
    monkeypatch.setattr(service_module, "default_rate_set", lambda: dollars_only)

    with demo() as session, pytest.raises(FxRateMissingError) as raised:
        pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM)

    assert raised.value.currencies == ("EUR", "GBP")
    assert raised.value.rate_set_version == "no-eur"

    base_only = rate_set(tmp_path, version="base-only")
    monkeypatch.setattr(service_module, "default_rate_set", lambda: base_only)
    with demo() as session, pytest.raises(FxRateMissingError) as raised:
        pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM)
    assert raised.value.currencies == ("EUR", "GBP", "USD")


def test_a_closed_or_an_unvalued_deal_in_a_currency_without_a_rate_raises_nothing(demo):
    """C-34, plan A7.5 item 4: a rate is required only for the currency of an open valued deal."""
    expected = view(demo)

    with stored(demo) as session:
        store_deal(session, source_system=SOURCE_SYSTEM, source_id="DEAL-980", stage="won",
                   is_active=False, amount=Decimal("500.00"), currency="GBP",
                   probability=Decimal("100.00"))
        store_deal(session, source_system=SOURCE_SYSTEM, source_id="DEAL-981",
                   stage="negotiation", amount=None, currency="JPY",
                   probability=Decimal("10.00"))
        found = pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM).view

    assert found["fx"]["used_currencies"] == ["EUR", "INR", "USD"]
    for name in (*SIX, "open_pipeline", "concentration"):
        assert found[name] == expected[name], name
    assert (found["deal_counts"]["total"], found["deal_counts"]["open_unvalued"],
            found["deal_counts"]["closed"]) == (46, 1, 15)
    assert found["open_deals"][-1]["currency"] == "JPY"


# ---------------------------------------------------------------------------
# The order of the errors (plan A17.1, OD-M3-1; C-35)
# ---------------------------------------------------------------------------


def _open_valued(session: Session, source_id: str, **changes) -> None:
    values = {"stage": "negotiation", "amount": Decimal("10.00"), "currency": "INR",
              "probability": Decimal("50.00"), **changes}
    store_deal(session, source_system=SOURCE_SYSTEM, source_id=source_id, **values)


#: Each condition as a stored row. A stage-1 condition is on an open valued deal.
CONDITIONS = {
    "a reserved key": lambda session, source_id: _open_valued(session, source_id, currency="ALL"),
    "a stage outside the vocabulary on an open valued deal":
        lambda session, source_id: _open_valued(session, source_id, stage="prospect"),
    "a refusal by the frozen MoneyValue":
        lambda session, source_id: _open_valued(session, source_id, currency="XXX"),
    "OD-9": lambda session, source_id: store_deal(
        session, source_system=SOURCE_SYSTEM, source_id=source_id, stage="prospect",
        is_active=False),
    "a currency with no rate":
        lambda session, source_id: _open_valued(session, source_id, currency="GBP"),
}
STAGE_ONE = ("a reserved key", "a stage outside the vocabulary on an open valued deal",
             "a refusal by the frozen MoneyValue")
IDS = (("DEAL-981", "DEAL-982"), ("DEAL-982", "DEAL-981"))


def outcome(sessions, first: str, second: str | None, ids, *, unknown_band: bool = False):
    """What pipeline_view raises with the two conditions stored on the two ids."""
    with stored(sessions) as session:
        CONDITIONS[first](session, ids[0])
        if second is not None:
            CONDITIONS[second](session, ids[1])
        if unknown_band:
            store_assessment(session, **identity(session), customer=NO_DEAL, band="SEVERE")
        with pytest.raises(Exception) as raised:  # noqa: B017, PT011 - the class is asserted
            pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM)
    return raised.value


@pytest.mark.parametrize("ids", IDS, ids=["stage 1 on the earlier row", "stage 1 on the later row"])
@pytest.mark.parametrize("condition", STAGE_ONE)
def test_a_stage_one_condition_wins_over_od9s_and_over_an_unknown_band(demo, condition, ids):
    """
    C-35: with OD-9's condition on another row, and with an unknown band,
    stage 1's own error is raised, with its own condition and ids. The
    frozen type's refusal is raised as ContractViolationError.
    """
    for second, band in (("OD-9", False), (None, True), ("OD-9", True)):
        error = outcome(demo, condition, second, ids, unknown_band=band)

        if condition == "a refusal by the frozen MoneyValue":
            assert type(error) is ContractViolationError
            assert "'XXX' is not a configured ISO 4217 code" in str(error)
        else:
            assert type(error) is PipelineDataError and error.entity == "deals"
            assert error.source_ids == (ids[0],), "the open valued deal, and not the closed one"
            assert error.condition == ("RESERVED_KEY" if condition == "a reserved key"
                                       else "STAGE_OUTSIDE_VOCABULARY")
            assert error.keys == (("ALL",) if condition == "a reserved key" else ())


@pytest.mark.parametrize("ids", IDS, ids=["earlier row", "later row"])
def test_od9s_condition_wins_over_an_unknown_band_and_names_deals(demo, ids):
    """C-35: OD-9's error, naming the entity deals and the closed deal."""
    error = outcome(demo, "OD-9", None, ids, unknown_band=True)

    assert type(error) is PipelineDataError
    assert (error.condition, error.entity, error.source_ids) == (
        "STAGE_OUTSIDE_VOCABULARY", "deals", (ids[0],))


@pytest.mark.parametrize("ids", IDS, ids=["earlier row", "later row"])
@pytest.mark.parametrize("condition", [*STAGE_ONE, "OD-9"])
def test_a_data_validity_condition_wins_over_a_currency_with_no_rate(demo, condition, ids):
    """
    C-35, plan B6: each in turn with a currency that has no rate, in both
    orders of the rows. That error, and never FxRateMissingError: a request
    that would fail both answers 500 and not 409.
    """
    error = outcome(demo, condition, "a currency with no rate", ids)

    assert not isinstance(error, FxRateMissingError)
    assert type(error) is (ContractViolationError if "MoneyValue" in condition
                           else PipelineDataError)
    if isinstance(error, PipelineDataError):
        assert (error.entity, error.source_ids) == ("deals", (ids[0],))


def test_an_unknown_band_wins_over_a_currency_with_no_rate(demo):
    """C-35: step 5 comes before step 6, so the unknown band is never a missing rate."""
    error = outcome(demo, "a currency with no rate", None, IDS[0], unknown_band=True)

    assert type(error) is PipelineDataError
    assert (error.condition, error.entity, error.source_ids) == (
        "BAND_OUTSIDE_VOCABULARY", "customers", (NO_DEAL,))
    alone = outcome(demo, "a currency with no rate", None, IDS[0])
    assert type(alone) is FxRateMissingError and alone.currencies == ("GBP",)


def refused_rate_file(tmp_path, monkeypatch) -> None:
    """Substitute a default that loads a refused file through the real path loader."""
    broken = tmp_path / "fx_rates.yaml"
    broken.write_text("version: 1\nrate_set_version: '1'\nbase_currency: INR\n"
                      "as_of_date: 2026-10-01\nsource_note: n\nrates: {INR: '1', USD: 85.5}\n",
                      encoding="utf-8")
    monkeypatch.setattr(service_module, "default_rate_set", lambda: load_rate_set(broken))


@pytest.mark.parametrize("condition", [*STAGE_ONE, "OD-9", "a currency with no rate"])
def test_a_refused_configuration_file_wins_over_every_other_condition(
        demo, tmp_path, monkeypatch, condition):
    """C-35, plan A17.1 step 2: the configuration error, before any data is read."""
    refused_rate_file(tmp_path, monkeypatch)

    with statements(demo) as seen:
        error = outcome(demo, condition, None, IDS[0], unknown_band=True)

    assert type(error) is FxConfigError
    assert "rates.USD" in str(error)
    assert not [statement for statement in seen if statement.startswith("SELECT deals.")
                and "stage" in statement], "step 2 fails before the facts are read"


def test_a_refused_rules_file_fails_the_view_the_same_way(demo, tmp_path, monkeypatch):
    broken = tmp_path / "pipeline_rules.yaml"
    broken.write_text("version: 1\npipeline_version: 1\nclosed_stages: [lost]\n",
                      encoding="utf-8")
    from app.pipeline.config import load_pipeline_rules

    monkeypatch.setattr(service_module, "default_pipeline_rules",
                        lambda: load_pipeline_rules(broken))

    with demo() as session, pytest.raises(PipelineConfigError, match="closed_stages"):
        pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM)


# ---------------------------------------------------------------------------
# The event (plan A20; C-37)
# ---------------------------------------------------------------------------


def test_a_view_that_is_built_emits_its_one_event_with_eight_fields_in_order(assessed, caplog):
    """
    C-37: vs02.pipeline_view_built, exactly once, at INFO, through log_event,
    with exactly the eight fields of plan A20 item 2 in that order, each
    equal to the view's own value.
    """
    caplog.set_level(logging.INFO, logger=EVENTS_LOGGER)
    result = built(assessed)
    found = result.view

    [record] = events(caplog)
    assert (record.levelno, record.name, record.event) == (
        logging.INFO, "app.pipeline.service", "vs02.pipeline_view_built")
    assert list(record.event_fields) == [
        "source_system", "as_of", "layer1_fingerprint", "pipeline_version", "rate_set_version",
        "open_deal_count", "unvalued_deal_count", "view_hash"]
    assert record.event_fields == {
        "source_system": "csv_demo", "as_of": "2026-09-18", "layer1_fingerprint": PINNED,
        "pipeline_version": 1, "rate_set_version": "1", "open_deal_count": 30,
        "unvalued_deal_count": 0, "view_hash": result.view_hash}
    assert record.event_fields["open_deal_count"] == found["deal_counts"]["open"]
    assert record.event_fields["unvalued_deal_count"] == found["deal_counts"]["open_unvalued"]
    assert record.getMessage() == (
        "vs02.pipeline_view_built source_system=csv_demo as_of=2026-09-18 "
        f"layer1_fingerprint={PINNED} pipeline_version=1 rate_set_version=1 open_deal_count=30 "
        f"unvalued_deal_count=0 view_hash={result.view_hash}")


def test_the_event_counts_open_and_unvalued_deals_as_the_view_does(demo, caplog):
    """C-37: the numbers of open and of unvalued deals, as plan A8.2 and A8.3 define them."""
    apply("unvalued_deals", demo)
    apply("negative_amount", demo)
    apply("stage_activity_mismatch", demo)
    caplog.set_level(logging.INFO, logger=EVENTS_LOGGER)
    found = view(demo)

    [record] = events(caplog)
    assert (record.event_fields["open_deal_count"], record.event_fields["unvalued_deal_count"]) == (
        found["deal_counts"]["open"], found["deal_counts"]["open_unvalued"]) == (34, 3)


def test_the_event_holds_no_amount_and_no_customer(assessed, caplog):
    """Plan A20 item 1: no monetary value, no customer identifier and no document text."""
    caplog.set_level(logging.INFO, logger=EVENTS_LOGGER)
    result = built(assessed)
    [record] = events(caplog)
    line = record.getMessage()
    amounts = {value for value in walk(result.view)
               if isinstance(value, str) and re.fullmatch(r"\d+\.\d+|\d{5,}", value)}

    assert len(amounts) > 100
    assert not [amount for amount in amounts if amount in line]
    assert "CUST-" not in line and "DEAL-" not in line and "EMP-" not in line
    assert not [value for value in record.event_fields.values() if isinstance(value, Decimal)]


def test_every_view_emits_one_event_and_a_failed_one_emits_none(
        demo, tmp_path, monkeypatch, caplog):
    """
    C-37, plan A20 item 3: a request that fails at step 2, 5 or 6 emits
    nothing. An empty view is a view, and emits its event.
    """
    caplog.set_level(logging.INFO, logger=EVENTS_LOGGER)

    view(demo, source_system="no_such_system")
    assert [record.event_fields["open_deal_count"] for record in events(caplog)] == [0]
    caplog.clear()

    apply("gbp_deal", demo)
    with demo() as session, pytest.raises(FxRateMissingError):
        pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM)
    apply("reserved_customer", demo)
    with demo() as session, pytest.raises(PipelineDataError):
        pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM)
    refused_rate_file(tmp_path, monkeypatch)
    with demo() as session, pytest.raises(FxConfigError):
        pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM)

    assert events(caplog) == []
    assert not [record for record in caplog.records if "vs02" in record.getMessage()]


# ---------------------------------------------------------------------------
# Read-only, the session, and determinism (C-38, C-39; named test 20)
# ---------------------------------------------------------------------------

#: Plan A21.1 item 1: the seven entity tables the scope's fingerprint reads,
#: and the persisted assessments. Nothing else is read.
READ = {"organizations", "employees", "customers", "deals", "projects", "support_tickets",
        "documents", "risk_assessments"}


def test_building_a_view_changes_no_row_count_in_any_table(assessed, tmp_path, monkeypatch):
    """
    Named test 20 [R], C-38: on the dataset, on an empty source system, and
    for a request that fails.
    """
    before = table_counts(assessed)

    built(assessed)
    built(assessed, source_system="no_such_system")
    built(assessed, as_of=date(1900, 1, 1))
    assert table_counts(assessed) == before

    apply("gbp_deal", assessed)
    after_fixture = table_counts(assessed)
    with assessed() as session, pytest.raises(FxRateMissingError):
        pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM)
    assert table_counts(assessed) == after_fixture
    assert before["risk_assessments"] == 50 and after_fixture["deals"] == 45


def test_every_statement_a_view_executes_is_a_select_over_the_tables_the_plan_names(assessed):
    """
    C-38, plan A21.1 item 1 and A21.2: only SELECTs, over the seven entity
    tables and the assessments. No ticket attribute and no document text is
    selected: of those two tables only source_id and record_hash, for the
    fingerprint. No brief, position or link is touched.
    """
    with assessed() as session, statements(assessed) as seen:
        pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM)

    assert len(seen) == 11, "seven for the fingerprint, the deals, two edges, the bands"
    assert len([statement for statement in seen if statement.startswith("SELECT deals.")
                and "stage" in statement]) == 1, "the facts read, which a refused file never reaches"
    assert all(statement.startswith("SELECT ") for statement in seen)
    assert not [statement for statement in seen if re.search(
        r"\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|CREATE|ALTER|DROP|LOCK|COMMIT|ROLLBACK|SAVEPOINT"
        r"|BEGIN|SET|FOR UPDATE|FOR SHARE)\b", statement.upper())]
    tables = {table.name for table in Base.metadata.sorted_tables}
    touched = {table for statement in seen for table in tables
               if f" {table} " in f"{statement} " or f" {table}." in statement}
    assert touched == READ
    for table in ("documents", "support_tickets"):
        reads = [statement for statement in seen if f" FROM {table} " in statement]
        assert [statement.split(" FROM ")[0] for statement in reads] == [
            f"SELECT {table}.source_id, {table}.record_hash"], table
    assert not [statement for statement in seen
                if "body_text" in statement or "title" in statement or "priority" in statement]


def test_the_service_runs_on_the_session_it_is_given_and_leaves_its_transaction_alone(assessed):
    """
    C-38, plan A19 item 5: it neither commits, rolls back, flushes, begins
    nor closes. The caller's transaction is the same one, still open, after
    the view is built, and nothing is pending in the session.
    """
    ended = []
    with assessed() as session:
        transaction = session.begin()
        connection = session.connection()
        for name in ("after_commit", "after_rollback", "after_soft_rollback", "before_flush"):
            event.listen(session, name, lambda *args, _name=name: ended.append(_name))
        seen_on = []

        def record(conn, *args):
            seen_on.append(conn)

        event.listen(assessed.kw["bind"], "before_cursor_execute", record)
        try:
            pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM)
        finally:
            event.remove(assessed.kw["bind"], "before_cursor_execute", record)

        assert ended == []
        assert session.get_transaction() is transaction and transaction.is_active
        assert session.in_transaction() and session.connection() is connection
        assert not session.new and not session.dirty and not session.deleted
        assert seen_on and {id(conn) for conn in seen_on} == {id(connection)}
        session.rollback()


def test_a_view_is_built_inside_a_read_only_repeatable_read_snapshot(assessed):
    """
    C-38, plan A19 item 6: the frozen read_snapshot gives a transaction that
    cannot write. The view built inside it is the view, so nothing wrote.
    """
    expected = built(assessed)

    with read_snapshot(assessed) as session:
        found = pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM)
        with pytest.raises(Exception, match="read-only"):
            session.execute(Deal.__table__.delete())

    assert found.view == expected.view and found.view_hash == expected.view_hash


def test_two_requests_over_one_snapshot_return_one_view_and_one_hash(assessed):
    """Plan A19 item 4, in one process: the same value, list for list."""
    first, second = built(assessed), built(assessed)

    assert first.view == second.view and first.view_hash == second.view_hash
    assert json.dumps(first.view) == json.dumps(second.view)
    assert first.citations == second.citations
    assert first.limitation_texts == second.limitation_texts


def test_the_hash_is_identical_in_another_process(assessed, e1_engine):
    """Named test 20 [R]: a different interpreter and hash seed, the same view_hash."""
    first = built(assessed)
    script = (
        "import sys, datetime;"
        "from sqlalchemy import create_engine;"
        "from sqlalchemy.orm import Session;"
        "from app.pipeline.service import pipeline_view;"
        "session = Session(create_engine(sys.argv[1]));"
        "built = pipeline_view(session, as_of=datetime.date(2026, 9, 18), "
        "source_system='csv_demo');"
        "print(built.view_hash, len(built.citations), built.view['risk_coincidence']);"
        "session.rollback()"
    )
    url = e1_engine.url.render_as_string(hide_password=False)
    for seed in ("1", "4242"):
        completed = subprocess.run(
            [sys.executable, "-c", script, url], cwd=REPO, capture_output=True, text=True,
            check=True, env={**os.environ, "PYTHONHASHSEED": seed,
                             "PYTHONDONTWRITEBYTECODE": "1"},
        )
        assert completed.stdout.strip().split(maxsplit=2) == [
            first.view_hash, "298", "['CUST-007', 'CUST-036']"]


def test_every_list_of_the_dataset_view_is_in_its_stated_order(assessed):
    """C-39, on the dataset and with fixtures that fill the lists the dataset leaves empty."""
    for name in ("unvalued_deals", "negative_amount", "owner_keys", "customer_keys",
                 "undated_deal", "stage_activity_mismatch"):
        apply(name, assessed)
    result = built(assessed)
    found = result.view

    assert [bucket["key"] for bucket in found["by_risk_band"]] == BAND_ORDER
    for bucket in found["by_risk_band"]:
        assert bucket["customer_ids"] == sorted(bucket["customer_ids"])
        assert bucket["deal_ids"] == sorted(bucket["deal_ids"])
    customers = found["by_customer"]
    assert customers[-1]["key"] == "UNLINKED"
    assert [(-Decimal(bucket["base"]["unweighted"]), bucket["key"])
            for bucket in customers[:-1]] == sorted(
        (-Decimal(bucket["base"]["unweighted"]), bucket["key"]) for bucket in customers[:-1])
    for pair in found["concentration"].values():
        for block in pair.values():
            assert [(-Decimal(holder["amount"]), holder["key"]) for holder in block["top"]] == (
                sorted((-Decimal(holder["amount"]), holder["key"]) for holder in block["top"]))
            assert [point["holders"] for point in block["cumulative"]] == [1, 3, 5]
            assert len(block["top"]) == 5 or block["holder_count"] < 5
    assert [row["stage"] for row in found["deal_counts"]["by_stage"]] == [
        "negotiation", "qualification", "won", "UNSTAGED"]
    assert found["deal_counts"]["unvalued_deal_ids"] == ["DEAL-960", "DEAL-961", "DEAL-962"]
    for name in ("open_deals", "closed_deals"):
        assert [entry["id"] for entry in found[name]] == sorted(
            entry["id"] for entry in found[name])
    notes = [(note["code"], note["id"] is not None, note["id"] or "")
             for note in found["data_quality"]]
    assert notes == sorted(notes)
    assert [(code, source_id) for code, _, source_id in notes] == [
        ("CUSTOMER_KEY_MISSING", "DEAL-965"), ("CUSTOMER_KEY_UNRESOLVED", "DEAL-966"),
        ("EXPECTED_CLOSE_MISSING", "DEAL-967"), ("INCOMPLETE_DEAL", "DEAL-960"),
        ("INCOMPLETE_DEAL", "DEAL-961"), ("NEGATIVE_AMOUNT", "DEAL-962"),
        ("NO_ASSESSMENT_FOR_SCOPE", ""), ("OWNER_KEY_MISSING", "DEAL-963"),
        ("OWNER_KEY_UNRESOLVED", "DEAL-964"), ("STAGE_ACTIVITY_MISMATCH", "DEAL-968"),
        ("STAGE_ACTIVITY_MISMATCH", "DEAL-969")], (
        "one note per fixture deal, and the scope note: the fixtures moved the snapshot")
    assert [entry["code"] for entry in result.limitation_texts] == found["limitations"]
    pairs = [(one["id"], one["field"]) for one in result.citations]
    assert pairs == sorted(pairs)
    assert [rate["currency"] for rate in found["fx"]["rates"]] == ["EUR", "INR", "USD"]
    assert found["fx"]["used_currencies"] == sorted(found["fx"]["used_currencies"])
    owners = keyed(found["by_owner"])
    assert owners["UNRESOLVED"]["unresolved_keys"] == ["EMP-960"]
    pseudo = [holder for holder in found["concentration"]["by_owner"]["unweighted"]["top"]
              if holder["pseudo"]]
    assert pseudo == [] or {holder["key"] for holder in pseudo} <= {"UNASSIGNED", "UNRESOLVED"}


# ---------------------------------------------------------------------------
# The empty view and the scope note (C-41, C-42)
# ---------------------------------------------------------------------------

SCOPE_NOTE = {"code": "NO_ASSESSMENT_FOR_SCOPE", "entity": None, "id": None, "fields": [],
              "key": None}


def empty_bucket(key: str, **added) -> dict:
    return {"key": key, "deal_count": 0, "deal_ids": [], "native": [],
            "base": {"currency": "INR", "unweighted": "0", "weighted": "0"}, **added}


def test_a_source_system_with_no_row_gives_the_empty_view_of_plan_a14_11(assessed):
    """
    C-41, through pipeline_view, with every key present. It still names its
    base currency and its rate set, because step 2 has loaded them. With no
    row there is no assessment either, so the scope note is its only note.
    """
    result = built(assessed, source_system="no_such_system")
    found = result.view
    zero = {"currency": "INR", "rate_set_version": "1", "total": "0", "holder_count": 0,
            "top": [], "cumulative": [], "hhi": None, "reason": "NO_OPEN_EXPOSURE"}
    months = ["2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03",
              "2027-04", "2027-05", "2027-06", "2027-07", "2027-08"]

    assert len(found) == 18
    assert found["deal_counts"] == {
        "total": 0, "open": 0, "open_valued": 0, "open_unvalued": 0, "closed": 0,
        "unvalued_deal_ids": [],
        "by_stage": [{"stage": stage, "total": 0, "open": 0, "closed": 0}
                     for stage in ("negotiation", "qualification", "won", "UNSTAGED")]}
    assert found["open_pipeline"] == empty_bucket("ALL")
    assert found["by_currency"] == []
    assert found["by_stage"] == [empty_bucket(stage)
                                 for stage in ("negotiation", "qualification", "won")]
    assert found["by_owner"] == [
        empty_bucket(kind, kind=kind, basis=None, carrier_field=None, unresolved_keys=[])
        for kind in ("UNASSIGNED", "UNRESOLVED")]
    assert found["by_expected_close"] == [
        empty_bucket("OVERDUE", kind="OVERDUE"),
        *(empty_bucket(month, kind="MONTH") for month in months),
        empty_bucket("LATER", kind="LATER"), empty_bucket("UNDATED", kind="UNDATED")]
    assert found["by_risk_band"] == [empty_bucket(key, customer_count=0, customer_ids=[])
                                     for key in BAND_ORDER]
    assert found["by_customer"] == [
        empty_bucket("UNLINKED", kind="UNLINKED", band=None, executive_worthy=None)]
    assert found["risk_coincidence"] == []
    assert found["concentration"] == {"by_customer": {"unweighted": zero, "weighted": zero},
                                      "by_owner": {"unweighted": zero, "weighted": zero}}
    assert (found["open_deals"], found["closed_deals"]) == ([], [])
    assert found["data_quality"] == [SCOPE_NOTE]
    assert found["scope"]["source_system"] == "no_such_system"
    assert set(found["scope"]["entity_counts"].values()) == {0}
    assert found["scope"]["layer1_fingerprint"] != PINNED
    assert (found["fx"]["base_currency"], found["fx"]["rate_set_version"],
            found["fx"]["rate_set_digest"], found["fx"]["used_currencies"]) == (
        "INR", "1", RATE_SET_DIGEST, [])
    assert len(found["limitations"]) == 9 and result.citations == []
    assert "Only source system no_such_system is included." in result.limitation_texts[6]["text"]
    assert result.view_hash == hashlib.sha256(canonical(found).encode("utf-8")).hexdigest()


QUIET_SYSTEM = "quiet_demo"


def test_a_source_system_whose_deals_are_none_of_them_open_and_valued(demo):
    """
    C-41, plan A17.2: the partitions and the four blocks are in the same
    empty form, while deal_counts, open_deals and closed_deals state those
    deals. A closed deal in a currency with no rate raises nothing.
    """
    empty = view(demo, source_system="no_such_system")
    with stored(demo) as session:
        store_deal(session, source_system=QUIET_SYSTEM, source_id="DEAL-A", stage="won",
                   is_active=False, amount=Decimal("700.00"), currency="GBP",
                   probability=Decimal("100.00"))
        store_deal(session, source_system=QUIET_SYSTEM, source_id="DEAL-B",
                   stage="negotiation", amount=None, currency="INR",
                   probability=Decimal("20.00"))
        store_deal(session, source_system=QUIET_SYSTEM, source_id="DEAL-C", stage=None,
                   is_active=False)
        result = pipeline_view(session, as_of=AS_OF, source_system=QUIET_SYSTEM)
    found = result.view

    for name in ("open_pipeline", "by_currency", "by_stage", "by_owner", "by_expected_close",
                 "by_risk_band", "by_customer", "risk_coincidence", "concentration"):
        assert found[name] == empty[name], name
    assert found["deal_counts"] == {
        "total": 3, "open": 1, "open_valued": 0, "open_unvalued": 1, "closed": 2,
        "unvalued_deal_ids": ["DEAL-B"],
        "by_stage": [{"stage": "negotiation", "total": 1, "open": 1, "closed": 0},
                     {"stage": "qualification", "total": 0, "open": 0, "closed": 0},
                     {"stage": "won", "total": 1, "open": 0, "closed": 1},
                     {"stage": "UNSTAGED", "total": 1, "open": 0, "closed": 1}]}
    assert [entry["id"] for entry in found["open_deals"]] == ["DEAL-B"]
    assert found["closed_deals"] == [{"id": "DEAL-A", "stage": "won", "is_active": False},
                                     {"id": "DEAL-C", "stage": None, "is_active": False}]
    assert [(note["code"], note["id"]) for note in found["data_quality"]] == [
        ("INCOMPLETE_DEAL", "DEAL-B"), ("NO_ASSESSMENT_FOR_SCOPE", None)]
    assert [(one["id"], one["field"]) for one in result.citations] == [
        ("DEAL-A", "is_active"), ("DEAL-A", "stage"), ("DEAL-B", "currency"),
        ("DEAL-B", "is_active"), ("DEAL-B", "probability"), ("DEAL-B", "stage"),
        ("DEAL-C", "is_active")]
    assert found["fx"]["used_currencies"] == []


BARE_SYSTEM = "bare_demo"


def test_a_source_system_that_holds_assessments_and_no_deal_states_no_scope_note(demo):
    """
    C-42, OD-M3-3, plan A14.11: the empty view, and its data_quality is [],
    because band_rows returned a row. No second state of the note exists.
    """
    with stored(demo) as session:
        store_customer(session, source_system=BARE_SYSTEM, source_id="CUST-980")
        store_assessment(session, **identity(session, BARE_SYSTEM), customer="CUST-980",
                         band="CRITICAL", executive_worthy=True)
        found = pipeline_view(session, as_of=AS_OF, source_system=BARE_SYSTEM).view

    assert found["data_quality"] == []
    assert found["deal_counts"]["total"] == 0 and found["open_deals"] == []
    assert found["by_risk_band"] == [empty_bucket(key, customer_count=0, customer_ids=[])
                                     for key in BAND_ORDER]
    assert found["risk_coincidence"] == []
    assert found["scope"]["entity_counts"]["customers"] == 1


def test_the_scope_note_follows_the_band_read_and_nothing_else(demo):
    """
    C-42: present before any assessment, on the dataset and on the empty
    source system. Absent after the assessment run, and absent when every
    returned row belongs to a customer holding no open valued deal.
    """
    assert view(demo)["data_quality"] == [SCOPE_NOTE]
    assert view(demo, source_system="no_such_system")["data_quality"] == [SCOPE_NOTE]

    with stored(demo) as session:
        scope = identity(session)
        for customer in (NO_DEAL, CLOSED_ONLY):
            store_assessment(session, **scope, customer=customer, band="WATCH")
        only_bystanders = pipeline_view(session, as_of=AS_OF, source_system=SOURCE_SYSTEM).view
    assert only_bystanders["data_quality"] == []
    assert keyed(only_bystanders["by_risk_band"])["UNASSESSED"]["deal_count"] == 30
    assert only_bystanders["risk_coincidence"] == []

    assess(demo)
    assert view(demo)["data_quality"] == []
    assert view(demo, source_system="no_such_system")["data_quality"] == [SCOPE_NOTE], (
        "another source system reads no assessment of this one")


# ---------------------------------------------------------------------------
# The caller's Decimal context (plan A9.1 item 5, A19 item 8; C-43)
# ---------------------------------------------------------------------------


def test_the_view_of_the_dataset_is_the_same_in_a_hostile_decimal_context(assessed):
    """
    C-43: a precision of 1, a rounding mode other than half-even, and
    Inexact and Rounded trapped, set before the call. pipeline_view returns
    the same view and the same hash, and the context is left as it was set.
    The two digests are unchanged under it too.
    """
    expected = built(assessed)
    rules_digest = default_pipeline_rules().methodology_digest

    with localcontext(Context(prec=1, rounding=ROUND_UP, traps=[Inexact, Rounded])) as current:
        before = (current.prec, current.rounding, dict(current.traps), dict(current.flags))
        found = built(assessed)
        digests = (default_rate_set().digest, default_pipeline_rules().methodology_digest)
        after = (current.prec, current.rounding, dict(current.traps), dict(current.flags))

    assert found.view == expected.view and found.view_hash == expected.view_hash
    assert found.citations == expected.citations
    assert found.limitation_texts == expected.limitation_texts
    assert after == before and before[0] == 1
    assert digests == (RATE_SET_DIGEST, rules_digest)
    block = found.view["concentration"]["by_customer"]["unweighted"]
    assert (block["total"], block["top"][0]["amount"], block["top"][0]["share"],
            block["cumulative"][2]["share"], block["hhi"]) == (
        "73442577.1", "18769993.3", "0.2556", "0.7319", "0.135")
    assert found.view["open_pipeline"]["base"] == {"currency": "INR",
                                                   "unweighted": "73442577.1",
                                                   "weighted": "32375999.45"}
