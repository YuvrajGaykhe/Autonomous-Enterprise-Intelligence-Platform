"""
M6 against a real database: the whole CUST-007 path, and the corpus around it.

The demo dataset is ingested by the clean full-dataset path and every link is
derived in an explicit arrange step, exactly as M5's tests do it: the
production call to derive_and_persist is the assessment run's, which is M7's
(§0.4.3), and M6 never invokes it. Nothing here calls M7, persists a result or
uses a production run -- the chain is

    AnalystContexts  ->  M5 positions  ->  conflict detection  ->  policy
    matching  ->  worthiness  ->  ordering  ->  winner  ->  dissent  ->
    resolved positions  ->  Reconciliation

and each arrow has an assertion below. The measured values -- one conflict,
one worthy customer, the order of all fifty -- are §0.5's expectations stated
before the tests were written; a different measurement is reported, not
pasted over (§0.3.8).

Four properties the unit suite cannot show on its own are shown here on real
rows: every citation, the resolution's and the dissent's included, names a
Layer 1 row in scope; multiplying every deal amount by a thousand changes no
Reconciliation and no rank; the §0.5.5 shape, created by promoting CUST-036's
qualification deal to negotiation, raises rather than resolving; and building
and reconciling every customer writes nothing.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.analysts import CommercialAnalyst, SupportRiskAnalyst, build_contexts
from app.connectors import CsvConnector, CsvConnectorConfig, SourceConnector
from app.core.database import Base
from app.decisions import (
    Reconciliation,
    UnresolvableConflictError,
    Worthiness,
    load_conflict_policy,
    order_reconciliations,
    reconcile,
)
from app.decisions.policy import DEFAULT_POLICY_PATH, default_action_catalogue
from app.evidence.linker import derive_and_persist
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence import Scope, resolve_scope
from app.intelligence.config import default_risk_rules
from app.intelligence.contract import (
    ActionId,
    EvidenceKind,
    Function,
    RecordCitation,
    RiskBand,
    canonical_json,
)
from app.intelligence.signals import customers_in_scope
from app.persistence.models import Customer, Deal, Document, SupportTicket

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
SOURCE_SYSTEM = "csv_demo"
ACCEPTANCE_AS_OF = date(2026, 9, 18)
MERIDIAN = "CUST-007"

PAUSE = ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED
ACCELERATE = ActionId.ACCELERATE_DEAL_CLOSE

#: §0.5.7's ordered_positions for CUST-007, as (function, action, object_ref).
MERIDIAN_ORDERED = (
    ("SALES", "ACCELERATE_DEAL_CLOSE", "DEAL-001"),
    ("SUPPORT", "ASSIGN_DEDICATED_SUPPORT_OWNER", "CUST-007"),
    ("SUPPORT", "ESCALATE_TO_ACCOUNT_OWNER_PER_SLA", "CUST-007"),
    ("SUPPORT", "SCHEDULE_EXECUTIVE_SPONSOR_CALL", "CUST-007"),
    ("SUPPORT", "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED", "DEAL-001"),
    ("SUPPORT", "REVIEW_INVOICE_DISPUTE", "TKT-079"),
)

#: §0.5.9's measured order at ACCEPTANCE_AS_OF: CRITICAL, then the two WATCH
#: customers split only by id, then NONE by S4 desc and id -- CUST-009 at
#: S4 = 2, thirteen at S4 = 1, thirty-three at S4 = 0.
MEASURED_ORDER = (
    ["CUST-007", "CUST-025", "CUST-036", "CUST-009"]
    + [f"CUST-{n:03d}" for n in (5, 8, 12, 14, 18, 24, 26, 33, 38, 40, 41, 47, 50)]
    + [f"CUST-{n:03d}" for n in (1, 2, 3, 4, 6, 10, 11, 13, 15, 16, 17, 19, 20, 21, 22, 23,
                                 27, 28, 29, 30, 31, 32, 34, 35, 37, 39, 42, 43, 44, 45, 46,
                                 48, 49)]
)

#: §0.4.8 criterion 8: the ticketless customers with a qualifying deal.
TICKETLESS_WITH_A_DEAL = ("CUST-019", "CUST-042", "CUST-043")


def _csv_connector() -> SourceConnector:
    config = CsvConnectorConfig.from_yaml(REPO / "config" / "connectors" / "csv_demo.yaml")
    config.data_directory = str(DEMO_DIR)
    return CsvConnector(config)


@pytest.fixture
def demo(e1_sessions: sessionmaker[Session]) -> sessionmaker[Session]:
    """The clean full-dataset path of plan A28: 233 rows, 7 entity types, 0 rejected."""
    counts = run_ingestion(_csv_connector(), e1_sessions, IngestionRequest()).counts
    assert counts.rejected == 0
    return e1_sessions


@pytest.fixture
def scope(demo: sessionmaker[Session]) -> Scope:
    with demo() as session:
        return resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=ACCEPTANCE_AS_OF)


@pytest.fixture
def linked(demo: sessionmaker[Session], scope: Scope) -> sessionmaker[Session]:
    """Every derived link persisted -- an explicit arrange step, never an M6 call."""
    with demo.begin() as session:
        derive_and_persist(session, scope)
    return demo


def reconcile_all(sessions, scope: Scope, **kwargs) -> dict[str, Reconciliation]:
    with sessions() as session:
        return {
            customer: reconcile(build_contexts(session, scope, customer), **kwargs)
            for customer in customers_in_scope(session, scope)
        }


def rows(positions) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (str(one.function), str(one.proposed_action), one.object_ref) for one in positions
    )


def _table_counts(sessions) -> dict[str, int]:
    with sessions() as session:
        return {
            table.name: session.scalar(select(func.count()).select_from(table)) or 0
            for table in Base.metadata.sorted_tables
        }


def _row_exists(session: Session, citation: RecordCitation) -> bool:
    """
    Whether a citation names a row in scope. A cited policy document must also
    have the text it is cited for; a cited ticket field may be NULL, because
    M5 cites an open ticket's empty `resolved_at` as the ground for "open".
    """
    model = {"customers": Customer, "deals": Deal, "support_tickets": SupportTicket,
             "documents": Document}[citation.entity_type]
    query = select(func.count()).select_from(model).where(
        model.source_system == SOURCE_SYSTEM,
        model.source_entity == citation.entity_type,
        model.source_id == citation.source_id,
    )
    if model is Document:
        query = query.where(getattr(Document, citation.field_name).is_not(None))
    return session.scalar(query) == 1


# ---------------------------------------------------------------------------
# The CUST-007 path, arrow by arrow
# ---------------------------------------------------------------------------


def test_the_cust_007_path_from_contexts_to_reconciliation(linked, scope):
    """§0.5.14 criteria 1, 3, 6 and 7, and §0.5.7's table, on real rows."""
    with linked() as session:
        contexts = build_contexts(session, scope, MERIDIAN)
    emitted = (SupportRiskAnalyst(context=contexts.support).positions()
               + CommercialAnalyst(context=contexts.commercial).positions())

    result = reconcile(contexts)

    # M5 positions: every one kept, unmodified, in §0.4.1's order.
    assert sorted(result.ordered_positions, key=repr) == sorted(emitted, key=repr)
    assert rows(result.ordered_positions) == MERIDIAN_ORDERED
    # Conflict detection: one, over DEAL-001, Sales against Support.
    (conflict,) = result.conflicts
    assert conflict.object_ref == "DEAL-001"
    assert [(one.function, one.proposed_action) for one in conflict.positions] == [
        (Function.SALES, ACCELERATE), (Function.SUPPORT, PAUSE)]
    # Policy matching and the winner: CONF-001, PAUSE.
    (resolution,) = result.resolutions
    assert resolution.policy_id == "CONF-001"
    assert result.policy_ids == ("CONF-001",)
    assert resolution.resolved_action is PAUSE
    # Dissent: Sales's own position, whole.
    assert result.dissent == tuple(one for one in emitted if one.function is Function.SALES)
    # Resolved positions: Support's five, §0.4.1 rows 1-5.
    assert rows(result.resolved_positions) == MERIDIAN_ORDERED[1:]
    # Worthiness and order.
    assert result.worthiness == Worthiness(RiskBand.CRITICAL, 1, 0)
    assert result.worthiness.executive_worthy
    assert result.ranking_key == (-3, -3, -5, MERIDIAN)
    assert result.policy_version == 1


def test_the_resolution_cites_doc_003_and_doc_009_and_both_resolve(linked, scope):
    """§0.5.14 criterion 5: cited by id, as canonical facts, and each names a real row."""
    result = reconcile_all(linked, scope)[MERIDIAN]
    (resolution,) = result.resolutions

    assert [(item.kind, item.citation) for item in resolution.evidence] == [
        (EvidenceKind.CANONICAL_FACT, RecordCitation("documents", "DOC-003", "body_text")),
        (EvidenceKind.CANONICAL_FACT, RecordCitation("documents", "DOC-009", "body_text")),
    ]
    with linked() as session:
        for item in resolution.evidence:
            assert _row_exists(session, item.citation), item.citation


def test_every_citation_in_every_reconciliation_resolves(linked, scope):
    """Positions, dissent and resolution evidence alike, over all fifty customers."""
    resolved = 0
    results = reconcile_all(linked, scope)
    with linked() as session:
        for result in results.values():
            citations = [citation for one in result.ordered_positions
                         for citation in one.citations]
            citations += [item.citation for resolution in result.resolutions
                          for item in resolution.evidence]
            for citation in citations:
                assert _row_exists(session, citation), (result.customer.source_id, citation)
                resolved += 1

    assert resolved > 0, "the scan would pass vacuously with no citations at all"


# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------


def test_the_corpus_holds_exactly_one_conflict_and_no_customer_raises(linked, scope):
    """§0.5.14 criterion 2: reconcile_all would raise on an unresolvable conflict."""
    results = reconcile_all(linked, scope)

    assert len(results) == 50
    conflicted = {customer: result.conflicts for customer, result in results.items()
                  if result.conflicts}
    assert list(conflicted) == [MERIDIAN]
    assert [conflict.object_ref for conflict in conflicted[MERIDIAN]] == ["DEAL-001"]


def test_the_corpus_keeps_every_position_but_one(linked, scope):
    """Fifteen positions across ten customers; the one dissent is the only one not resolved."""
    results = reconcile_all(linked, scope).values()

    assert sum(len(result.ordered_positions) for result in results) == 15
    assert sum(1 for result in results if result.ordered_positions) == 10
    assert sum(len(result.resolved_positions) for result in results) == 14
    assert [rows(result.dissent) for result in results if result.dissent] == [
        (MERIDIAN_ORDERED[0],)]


def test_only_cust_007_is_executive_worthy(linked, scope):
    """§A27.2 and §0.5.8's measurement: 16 customers have a project, none is band >= ELEVATED."""
    results = reconcile_all(linked, scope)

    assert [customer for customer, result in results.items()
            if result.worthiness.executive_worthy] == [MERIDIAN]
    assert sum(1 for result in results.values()
               if result.worthiness.active_project_count > 0) == 16


@pytest.mark.parametrize("customer", TICKETLESS_WITH_A_DEAL + ("CUST-002",))
def test_a_customer_whose_functions_share_no_object_has_no_conflict(linked, scope, customer):
    """§0.5.14 criterion 8: the ticketless customers with a deal, and one with nothing at all."""
    result = reconcile_all(linked, scope)[customer]

    assert result.conflicts == () and result.dissent == () and result.resolutions == ()
    assert result.resolved_positions == result.ordered_positions
    expected = [Function.SALES] if customer in TICKETLESS_WITH_A_DEAL else []
    assert [one.function for one in result.ordered_positions] == expected


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------


def test_the_measured_order_of_all_fifty_customers(linked, scope):
    ordered = order_reconciliations(reconcile_all(linked, scope).values())

    assert [result.customer.source_id for result in ordered] == MEASURED_ORDER


def test_the_order_does_not_depend_on_arrival_order(linked, scope):
    results = list(reconcile_all(linked, scope).values())
    arrivals = [results, results[::-1], results[1::2] + results[::2],
                sorted(results, key=lambda result: result.customer.source_id[::-1])]

    for arrival in arrivals:
        assert [result.customer.source_id
                for result in order_reconciliations(arrival)] == MEASURED_ORDER


def test_multiplying_every_amount_by_a_thousand_changes_nothing(linked, scope):
    """§A25 test 5, at M6's grain: every Reconciliation equal, the order unchanged."""
    before = reconcile_all(linked, scope)
    with linked.begin() as session:
        session.execute(text("UPDATE deals SET amount = amount * 1000"))
    after = reconcile_all(linked, scope)

    assert after == before
    assert [result.customer.source_id for result in order_reconciliations(after.values())] == \
        MEASURED_ORDER


# ---------------------------------------------------------------------------
# The policy is load-bearing, and it fails closed
# ---------------------------------------------------------------------------


def test_flipping_resolve_to_flips_the_outcome_on_the_real_data(linked, scope, tmp_path):
    """§A25 test 3."""
    flipped_path = tmp_path / "conflict_policy.yaml"
    flipped_path.write_text(
        DEFAULT_POLICY_PATH.read_text(encoding="utf-8").replace(
            "resolve_to: PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED",
            "resolve_to: ACCELERATE_DEAL_CLOSE"),
        encoding="utf-8")
    flipped = load_conflict_policy(flipped_path, catalogue=default_action_catalogue())

    result = reconcile_all(linked, scope, policy=flipped)[MERIDIAN]

    assert result.resolutions[0].resolved_action is ACCELERATE
    assert [one.proposed_action for one in result.dissent] == [PAUSE]
    assert result.policy_ids == ("CONF-001",)


def test_a_real_conflict_conf_001_does_not_apply_to_raises(linked, scope):
    """
    §0.5.5 on real rows. CUST-036 is WATCH with S8 = 1 and no S5; promoting its
    qualification deal DEAL-037 to negotiation at 90% makes Support pause and
    Sales accelerate one deal, and CONF-001's band condition fails.
    """
    with linked.begin() as session:
        session.execute(text(
            "UPDATE deals SET stage = 'negotiation', probability = 90 "
            "WHERE source_id = 'DEAL-037'"))

    with linked() as session:
        contexts = build_contexts(session, scope, "CUST-036")
        with pytest.raises(UnresolvableConflictError) as raised:
            reconcile(contexts)
        assert reconcile(build_contexts(session, scope, MERIDIAN)).policy_ids == ("CONF-001",)

    assert raised.value.object_ref == "DEAL-037"
    assert raised.value.rule_id == "CONF-001"
    assert "the band is WATCH" in str(raised.value)


# ---------------------------------------------------------------------------
# Pure, deterministic, and the snapshot untouched
# ---------------------------------------------------------------------------


def test_reconciling_every_customer_writes_nothing(linked, scope):
    before = _table_counts(linked)
    reconcile_all(linked, scope)

    assert _table_counts(linked) == before


def test_two_runs_serialise_identically(linked, scope):
    first, second = reconcile_all(linked, scope), reconcile_all(linked, scope)

    assert first == second
    assert [canonical_json(result.to_payload()) for result in first.values()] == [
        canonical_json(result.to_payload()) for result in second.values()]


def test_the_layer_1_snapshot_is_still_the_pinned_one(scope):
    """§0.5.14 criterion 20: M6 changes no Layer 1 row and no fingerprint input."""
    assert scope.layer1_fingerprint == default_risk_rules().pinned_fingerprint(SOURCE_SYSTEM)
