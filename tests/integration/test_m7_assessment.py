"""
The assessment run against a real database: §0.6.15's criteria, one by one.

The demo dataset is ingested by the clean full-dataset path, and every run is
unpinned at ACCEPTANCE_AS_OF unless a test says otherwise (§0.6.3), because a
pinned run would refuse the very snapshot changes §A25 tests 4 and 13 make.
The measured counts are §0.5's and §0.6's expectations, stated before these
tests were written; a different measurement is reported, not pasted over.

Every test owns the transaction, as a caller must: `run()` opens one with
`sessions.begin()`, so a run that raises is rolled back by the context
manager, and "nothing is durable" is asserted as equal table counts before
and after.
"""

from __future__ import annotations

import inspect
import logging
import os
import re
import subprocess
import sys
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.connectors import CsvConnector, CsvConnectorConfig, SourceConnector
from app.core.database import Base
from app.core.logging import FIELDS_ATTRIBUTE
from app.decisions import UnresolvableConflictError, reconcile
from app.decisions import assessment as assessments
from app.decisions import brief as briefs
from app.decisions.assessment import AssessmentResult, run_assessment
from app.decisions.payload import SPAN_TARGETS, payload_hash
from app.evidence import CitationResolutionError, citable_text
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence import FingerprintMismatchError, ScopeResolutionError, resolve_scope
from app.intelligence.config import default_risk_rules
from app.intelligence.contract import RecordCitation, canonical_json
from app.intelligence.errors import ContractViolationError
from app.persistence.models import (
    Customer,
    Deal,
    Document,
    DocumentCustomerLink,
    RiskAssessment,
    RiskBrief,
    RiskPosition,
    SupportTicket,
)
from app.relationships import UnknownCustomerError
from tests.unit.m6_support import load_policy, policy_data

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
SOURCE_SYSTEM = "csv_demo"
ACCEPTANCE_AS_OF = date(2026, 9, 18)
MERIDIAN = "CUST-007"
PINNED = "1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00"
BRIEFED = ["CUST-007", "CUST-025", "CUST-036"]
EVENTS_LOGGER = "app.decisions.assessment"

#: §0.5.7's ordered positions for CUST-007, as (function, action, object_ref, stance).
MERIDIAN_POSITIONS = [
    ("SALES", "ACCELERATE_DEAL_CLOSE", "DEAL-001", "ADVANCE"),
    ("SUPPORT", "ASSIGN_DEDICATED_SUPPORT_OWNER", "CUST-007", "NEUTRAL"),
    ("SUPPORT", "ESCALATE_TO_ACCOUNT_OWNER_PER_SLA", "CUST-007", "NEUTRAL"),
    ("SUPPORT", "SCHEDULE_EXECUTIVE_SPONSOR_CALL", "CUST-007", "NEUTRAL"),
    ("SUPPORT", "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED", "DEAL-001", "RESTRAIN"),
    ("SUPPORT", "REVIEW_INVOICE_DISPUTE", "TKT-079", "NEUTRAL"),
]

#: §0.6.13.6's fields, in order, per event.
EVENT_FIELDS = {
    "vs01.scope_resolved": ["source_system", "as_of", "layer1_fingerprint", "as_of_source"],
    "vs01.links_derived": ["source_system", "layer1_fingerprint", "linker_version", "inserted"],
    "vs01.conflict_detected": ["customer", "object_ref", "policy_id", "policy_version"],
    "vs01.conflict_resolved": ["customer", "object_ref", "policy_id", "policy_version",
                               "resolved_action"],
    "vs01.brief_generated": ["customer", "payload_hash", "citation_count", "created"],
}


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
def assessed(demo) -> tuple[sessionmaker[Session], tuple[AssessmentResult, ...]]:
    return demo, run(demo)


def run(sessions, **kwargs) -> tuple[AssessmentResult, ...]:
    kwargs.setdefault("as_of", ACCEPTANCE_AS_OF)
    with sessions.begin() as session:
        return run_assessment(session, **kwargs)


def counts(sessions) -> dict[str, int]:
    with sessions() as session:
        return {
            table.name: session.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.sorted_tables
        }


def assessments_by_customer(sessions) -> dict[str, RiskAssessment]:
    """Each customer's assessment; call it only while one assessment per customer exists."""
    with sessions() as session:
        return dict(session.execute(
            select(Customer.source_id, RiskAssessment)
            .join(Customer, RiskAssessment.customer_id == Customer.id)
        ).tuples().all())


def briefs_by_customer(sessions) -> dict[str, list[RiskBrief]]:
    found: dict[str, list[RiskBrief]] = {}
    with sessions() as session:
        rows = session.execute(
            select(Customer.source_id, RiskBrief)
            .join(RiskAssessment, RiskBrief.assessment_id == RiskAssessment.id)
            .join(Customer, RiskAssessment.customer_id == Customer.id)
            .order_by(Customer.source_id, RiskBrief.policy_version)
        ).all()
    for source_id, row in rows:
        found.setdefault(source_id, []).append(row)
    return found


def meridian_brief(sessions) -> RiskBrief:
    (brief,) = briefs_by_customer(sessions)[MERIDIAN]
    return brief


def events(caplog) -> list[tuple[str, dict]]:
    return [
        (record.getMessage().split(" ", 1)[0], getattr(record, FIELDS_ATTRIBUTE))
        for record in caplog.records if record.name == EVENTS_LOGGER
    ]


def citation_values(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "citation":
                yield value
            else:
                yield from citation_values(value)
    elif isinstance(node, list):
        for item in node:
            yield from citation_values(item)


def resolves_independently(session: Session, citation: dict) -> bool:
    """§0.6.9's rule, restated from the plan rather than read from the module under test."""
    if citation["kind"] == "document":
        row = session.execute(select(Document.title, Document.body_text).where(
            Document.source_system == SOURCE_SYSTEM, Document.source_id == citation["document_id"],
        )).one_or_none()
        return row is not None and citation["end"] <= len(citable_text(*row))
    model = {"customers": Customer, "deals": Deal, "support_tickets": SupportTicket,
             "documents": Document}[citation["entity"]]
    row = session.execute(select(getattr(model, citation["field"])).where(
        model.source_system == SOURCE_SYSTEM, model.source_entity == citation["entity"],
        model.source_id == citation["id"],
    )).one_or_none()
    if row is None:
        return False
    must_hold = {("documents", "body_text"), ("support_tickets", "created_at"),
                 ("deals", "amount"), ("deals", "currency")}
    return row[0] is not None or (citation["entity"], citation["field"]) not in must_hold


def add_synthetic_ticket(sessions) -> None:
    """§A25 test 13: one extra ticket, for a customer with none, changes the snapshot."""
    with sessions.begin() as session:
        customer_id = session.scalar(select(Customer.id).where(Customer.source_id == "CUST-001"))
        session.add(SupportTicket(
            source_system=SOURCE_SYSTEM, source_entity="support_tickets", source_id="TKT-900",
            record_hash="9" * 64, ingestion_run_id=uuid.uuid4(), subject="synthetic",
            priority="low", status="open", category="onboarding",
            created_at=datetime(2026, 9, 1, 10, tzinfo=UTC), customer_source_id="CUST-001",
            customer_id=customer_id,
        ))


# ---------------------------------------------------------------------------
# Criterion 1: the run contract
# ---------------------------------------------------------------------------


def test_the_run_signature_is_the_directed_one():
    parameters = inspect.signature(run_assessment).parameters

    assert list(parameters) == ["session", "as_of", "source_system", "customer_source_id",
                                "expected_fingerprint", "config", "policy"]
    assert parameters["as_of"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["as_of"].default is inspect.Parameter.empty
    assert parameters["source_system"].default == "csv_demo"
    for name in ("customer_source_id", "expected_fingerprint", "config", "policy"):
        assert parameters[name].default is None


def test_links_are_derived_exactly_once_and_before_any_context(demo, monkeypatch):
    calls: list[str] = []
    derive, build = assessments.derive_and_persist, assessments.build_contexts
    monkeypatch.setattr(assessments, "derive_and_persist",
                        lambda *a, **k: calls.append("derive") or derive(*a, **k))
    monkeypatch.setattr(assessments, "build_contexts",
                        lambda *a, **k: calls.append("build") or build(*a, **k))

    run(demo)

    assert calls.count("derive") == 1
    assert calls[0] == "derive"
    assert calls.count("build") == 50


def test_the_run_never_commits_rolls_back_or_closes(demo):
    """The transaction is the caller's: every call the run could make on it is recorded."""
    owned = ("commit", "rollback", "close", "begin", "begin_nested")
    session = demo()
    called: list[str] = []
    try:
        for name in owned:
            setattr(session, name, lambda *a, _name=name, **k: called.append(_name))
        results = run_assessment(session, as_of=ACCEPTANCE_AS_OF)
    finally:
        for name in owned:
            vars(session).pop(name, None)
        session.rollback()
        session.close()

    assert called == []
    assert len(results) == 50
    assert counts(demo)["risk_assessments"] == 0, "the caller's rollback left nothing"


def test_the_result_is_one_per_customer_in_reconciliation_order(assessed):
    sessions, results = assessed
    by_id = {row.id: source_id for source_id, row in assessments_by_customer(sessions).items()}

    order = [by_id[result.assessment_id] for result in results]
    assert len(results) == 50
    assert order[:4] == ["CUST-007", "CUST-025", "CUST-036", "CUST-009"]
    assert all(result.created for result in results)
    assert [(by_id[result.assessment_id], result.brief_id is not None) for result in results
            if result.payload_hash is not None] == [(one, True) for one in BRIEFED]


def test_a_named_customer_is_the_only_one_assessed(demo):
    (result,) = run(demo, customer_source_id=MERIDIAN)

    assert result.created and result.brief_id is not None
    assert list(assessments_by_customer(demo)) == [MERIDIAN]


def test_a_named_customer_outside_the_scope_propagates_m2s_error(demo):
    before = counts(demo)

    with pytest.raises(UnknownCustomerError):
        run(demo, customer_source_id="CUST-999")

    assert counts(demo) == before


def test_no_as_of_falls_back_to_the_latest_ticket(demo, caplog):
    caplog.set_level(logging.INFO, logger=EVENTS_LOGGER)

    run(demo, as_of=None)

    (scope_line,) = [fields for name, fields in events(caplog)
                     if name == "vs01.scope_resolved"]
    assert scope_line["as_of"] == "2026-08-27"
    assert scope_line["as_of_source"] == "MAX_TICKET_CREATED_AT"
    assert {row.as_of for row in assessments_by_customer(demo).values()} == {date(2026, 8, 27)}


def test_no_as_of_and_no_ticket_propagates_the_scope_error(e1_sessions):
    with pytest.raises(ScopeResolutionError):
        run(e1_sessions, as_of=None)


# ---------------------------------------------------------------------------
# Criterion 2: a pinned run
# ---------------------------------------------------------------------------


def test_a_pinned_run_over_the_clean_snapshot_assesses(demo):
    pinned = default_risk_rules().pinned_fingerprint(SOURCE_SYSTEM)

    assert pinned == PINNED
    assert len(run(demo, expected_fingerprint=pinned)) == 50


def test_a_pinned_run_over_a_changed_snapshot_fails_closed_and_writes_nothing(demo):
    add_synthetic_ticket(demo)
    before = counts(demo)

    with pytest.raises(FingerprintMismatchError):
        run(demo, expected_fingerprint=PINNED)

    assert counts(demo) == before
    assert before["document_customer_links"] == 0, "it failed before deriving anything"


# ---------------------------------------------------------------------------
# Criteria 3-5: assessments, positions and briefs
# ---------------------------------------------------------------------------


def test_fifty_assessments_and_cust_007_is_the_only_worthy_one(assessed):
    sessions, _ = assessed
    rows = assessments_by_customer(sessions)
    meridian = rows[MERIDIAN]

    assert len(rows) == 50
    assert [customer for customer, row in rows.items() if row.executive_worthy] == [MERIDIAN]
    assert (meridian.band, meridian.rules_version, meridian.linker_version) == (
        "CRITICAL", 1, "1")
    assert meridian.ranking_key == [-3, -3, -5, "CUST-007"]
    assert meridian.signals["contract_document_ids"] == ["DOC-006"]
    assert meridian.satisfied_rules == [
        "R-CRIT-001", "R-ELEV-001", "R-ELEV-002", "R-WATCH-001", "R-WATCH-002", "R-WATCH-003"]
    assert {row.layer1_fingerprint for row in rows.values()} == {PINNED}
    assert {row.as_of for row in rows.values()} == {ACCEPTANCE_AS_OF}
    assert {row.source_system for row in rows.values()} == {SOURCE_SYSTEM}


def test_the_stored_signals_are_the_contexts_projection(assessed):
    from app.analysts import build_contexts

    sessions, _ = assessed
    rows = assessments_by_customer(sessions)
    with sessions() as session:
        scope = resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=ACCEPTANCE_AS_OF)
        for customer in (MERIDIAN, "CUST-025", "CUST-042", "CUST-001"):
            contexts = build_contexts(session, scope, customer)
            assert rows[customer].signals == contexts.commercial.signals.to_payload()
            assert rows[customer].band == contexts.commercial.band
            assert rows[customer].ranking_key == list(reconcile(contexts).ranking_key)


def test_fifteen_positions_over_ten_assessments_each_in_ordinal_order(assessed):
    sessions, _ = assessed
    with sessions() as session:
        rows = session.execute(
            select(Customer.source_id, RiskPosition.ordinal, RiskPosition.function,
                   RiskPosition.proposed_action, RiskPosition.object_ref, RiskPosition.stance,
                   RiskPosition.citations)
            .join(RiskAssessment, RiskPosition.assessment_id == RiskAssessment.id)
            .join(Customer, RiskAssessment.customer_id == Customer.id)
            .order_by(Customer.source_id, RiskPosition.ordinal)
        ).all()

    assert len(rows) == 15
    assert len({row[0] for row in rows}) == 10
    by_customer: dict[str, list[int]] = {}
    for row in rows:
        by_customer.setdefault(row[0], []).append(row[1])
    assert all(ordinals == list(range(len(ordinals))) for ordinals in by_customer.values())
    assert [tuple(row[2:6]) for row in rows if row[0] == MERIDIAN] == MERIDIAN_POSITIONS


def test_each_position_stores_its_evidence_as_projected(assessed):
    from app.analysts import build_contexts

    sessions, _ = assessed
    with sessions() as session:
        scope = resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=ACCEPTANCE_AS_OF)
        expected = reconcile(build_contexts(session, scope, MERIDIAN)).ordered_positions
        stored = session.execute(
            select(RiskPosition.rationale, RiskPosition.citations)
            .join(RiskAssessment, RiskPosition.assessment_id == RiskAssessment.id)
            .join(Customer, RiskAssessment.customer_id == Customer.id)
            .where(Customer.source_id == MERIDIAN)
            .order_by(RiskPosition.ordinal)
        ).all()

    assert [(row.rationale, row.citations) for row in stored] == [
        (one.rationale, one.to_payload()["evidence"]) for one in expected]


def test_exactly_three_briefs_each_a_policy_1_template_1_draft(assessed):
    sessions, results = assessed
    found = briefs_by_customer(sessions)

    assert sorted(found) == BRIEFED
    for customer in BRIEFED:
        (brief,) = found[customer]
        assert (brief.policy_version, brief.template_version, brief.status) == (1, "1", "DRAFT")
    assert {result.payload_hash for result in results if result.payload_hash} == {
        found[customer][0].payload_hash for customer in BRIEFED}


# ---------------------------------------------------------------------------
# Criterion 6: an identical re-run
# ---------------------------------------------------------------------------


def test_an_identical_re_run_reads_everything_back_and_inserts_nothing(assessed):
    sessions, first = assessed
    before = counts(sessions)

    second = run(sessions)

    assert counts(sessions) == before
    assert [(one.assessment_id, one.brief_id, one.payload_hash) for one in second] == [
        (one.assessment_id, one.brief_id, one.payload_hash) for one in first]
    assert not any(one.created for one in second)


def test_a_third_run_is_still_a_read(assessed):
    sessions, first = assessed
    run(sessions)
    before = counts(sessions)

    assert [one.payload_hash for one in run(sessions)] == [one.payload_hash for one in first]
    assert counts(sessions) == before


# ---------------------------------------------------------------------------
# Criterion 7: identity
# ---------------------------------------------------------------------------


def test_a_synthetic_ticket_mints_new_assessments_on_own_stamp_links_only(assessed):
    """§A25 test 13, and §0.6.13.1's stamp filter: the old fingerprint's links stay in the table."""
    sessions, first = assessed
    add_synthetic_ticket(sessions)

    second = run(sessions)

    assert all(one.created for one in second)
    assert {one.assessment_id for one in second}.isdisjoint(one.assessment_id for one in first)
    assert counts(sessions)["risk_assessments"] == 100
    with sessions() as session:
        stamps = session.execute(
            select(DocumentCustomerLink.layer1_fingerprint, func.count())
            .group_by(DocumentCustomerLink.layer1_fingerprint)
        ).all()
    assert len(stamps) == 2 and all(total == 11 for _, total in stamps)
    (new_fingerprint,) = {fingerprint for fingerprint, _ in stamps} - {PINNED}
    newest = {row.assessment_id: row for rows in briefs_by_customer(sessions).values()
              for row in rows}
    (meridian,) = [one for one in second if one.brief_id is not None][:1]
    payload = newest[meridian.assessment_id].decision_payload
    assert payload["scope"]["layer1_fingerprint"] == new_fingerprint
    assert len(payload["document_evidence"]) == 6
    assert {entry["layer1_fingerprint"] for entry in payload["document_evidence"]} == {
        new_fingerprint}


@pytest.mark.parametrize("change", [{"rules_version": 2}, {"linker_version": "2"}])
def test_a_rules_or_linker_version_change_mints_new_assessments(assessed, change):
    sessions, first = assessed
    config = replace(default_risk_rules(), **change)

    second = run(sessions, config=config)

    assert all(one.created for one in second)
    assert counts(sessions)["risk_assessments"] == 100
    assert counts(sessions)["risk_briefs"] == 6


def test_a_linker_version_change_appends_links_under_the_new_version(assessed):
    sessions, _ = assessed
    run(sessions, config=replace(default_risk_rules(), linker_version="2"))

    with sessions() as session:
        versions = session.execute(
            select(DocumentCustomerLink.linker_version, func.count())
            .group_by(DocumentCustomerLink.linker_version)
            .order_by(DocumentCustomerLink.linker_version)
        ).all()
    assert [tuple(row) for row in versions] == [("1", 11), ("2", 11)]
    payload = meridian_briefs(sessions)[-1].decision_payload
    assert {entry["linker_version"] for entry in payload["document_evidence"]} == {"2"}
    assert payload["versions"]["linker"] == "2"


def meridian_briefs(sessions) -> list[RiskBrief]:
    with sessions() as session:
        return list(session.scalars(
            select(RiskBrief)
            .join(RiskAssessment, RiskBrief.assessment_id == RiskAssessment.id)
            .join(Customer, RiskAssessment.customer_id == Customer.id)
            .where(Customer.source_id == MERIDIAN)
            .order_by(RiskAssessment.linker_version, RiskAssessment.rules_version,
                      RiskBrief.policy_version)
        ))


def test_a_policy_version_change_adds_a_brief_under_the_same_assessment(assessed, tmp_path):
    sessions, first = assessed
    data = policy_data()
    data["policy_version"] = 2
    before = counts(sessions)

    second = run(sessions, policy=load_policy(tmp_path, data))

    assert [one.assessment_id for one in second] == [one.assessment_id for one in first]
    assert not any(one.created for one in second)
    after = counts(sessions)
    assert after["risk_assessments"] == before["risk_assessments"]
    assert after["risk_positions"] == before["risk_positions"]
    assert after["risk_briefs"] == before["risk_briefs"] + 3
    versions = [brief.policy_version for brief in briefs_by_customer(sessions)[MERIDIAN]]
    assert versions == [1, 2]


def test_a_flipped_resolution_is_a_new_brief_whose_dissent_is_support(assessed, tmp_path):
    """§A25 test 3 through the run: same policy version, a different payload, a new brief."""
    sessions, first = assessed
    data = policy_data()
    data["conflicts"][0]["resolve_to"] = "ACCELERATE_DEAL_CLOSE"

    second = run(sessions, policy=load_policy(tmp_path, data))

    assert second[0].payload_hash != first[0].payload_hash
    assert counts(sessions)["risk_briefs"] == 4, "only CUST-007's payload changed"
    (flipped,) = [row for row in briefs_by_customer(sessions)[MERIDIAN]
                  if row.payload_hash == second[0].payload_hash]
    resolution = flipped.decision_payload["reconciliation"]["resolutions"][0]
    assert resolution["resolved_action"] == "ACCELERATE_DEAL_CLOSE"
    assert [one["function"] for one in resolution["dissent"]] == ["SUPPORT"]


def test_a_reloaded_equal_policy_reads_the_existing_brief(assessed, tmp_path):
    """§0.6.6: a policy that alters nothing hashed reads the existing brief back."""
    sessions, first = assessed
    data = policy_data()
    before = counts(sessions)

    second = run(sessions, policy=load_policy(tmp_path, data))

    assert [one.payload_hash for one in second] == [one.payload_hash for one in first]
    assert counts(sessions) == before


def test_a_template_only_change_keeps_the_hash_and_updates_nothing(assessed, tmp_path,
                                                                   monkeypatch):
    sessions, first = assessed
    stored = meridian_brief(sessions)
    changed = tmp_path / "brief.txt"
    changed.write_text("CHANGED ${customer}\n" + briefs.TEMPLATE_PATH.read_text(
        encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(briefs, "TEMPLATE_PATH", changed)
    monkeypatch.setattr(assessments, "TEMPLATE_VERSION", "2")

    second = run(sessions)

    assert [one.payload_hash for one in second] == [one.payload_hash for one in first]
    assert not any(one.created for one in second)
    again = meridian_brief(sessions)
    assert (again.narrative, again.template_version) == (stored.narrative, "1")
    assert not again.narrative.startswith("CHANGED")


# ---------------------------------------------------------------------------
# Criterion 8: payload and hash, on the stored rows
# ---------------------------------------------------------------------------


def test_every_stored_payload_re_hashes_to_its_stored_hash(assessed):
    sessions, _ = assessed
    for rows in briefs_by_customer(sessions).values():
        for brief in rows:
            assert payload_hash(brief.decision_payload) == brief.payload_hash


def test_cust_007s_payload_holds_its_six_own_stamp_links(assessed):
    sessions, _ = assessed
    payload = meridian_brief(sessions).decision_payload

    assert [(one["source"]["id"], one["basis"]) for one in payload["document_evidence"]] == [
        ("DOC-005", "EXACT_NAME"), ("DOC-005", "ID_TOKEN"), ("DOC-006", "EXACT_NAME"),
        ("DOC-006", "ID_TOKEN"), ("DOC-009", "EXACT_NAME"), ("DOC-009", "ID_TOKEN")]
    assert payload["scope"] == {"source_system": SOURCE_SYSTEM, "as_of": "2026-09-18",
                                "layer1_fingerprint": PINNED}
    assert payload["versions"] == {"rules": 1, "linker": "1", "policy": 1}


def test_the_hash_is_identical_in_another_process(assessed, e1_engine):
    """§A25 test 12: a different interpreter and hash seed, the same payload_hash."""
    sessions, first = assessed
    script = (
        "import sys, datetime;"
        "from sqlalchemy import create_engine;"
        "from sqlalchemy.orm import Session;"
        "from app.decisions.assessment import run_assessment;"
        "session = Session(create_engine(sys.argv[1]));"
        "results = run_assessment(session, as_of=datetime.date(2026, 9, 18));"
        "print(' '.join(one.payload_hash for one in results if one.payload_hash));"
        "session.rollback()"
    )
    url = e1_engine.url.render_as_string(hide_password=False)
    for seed in ("1", "4242"):
        completed = subprocess.run(
            [sys.executable, "-c", script, url], cwd=REPO, capture_output=True, text=True,
            check=True, env={**os.environ, "PYTHONHASHSEED": seed,
                             "PYTHONDONTWRITEBYTECODE": "1"},
        )
        assert completed.stdout.split() == [one.payload_hash for one in first
                                            if one.payload_hash]


# ---------------------------------------------------------------------------
# Criteria 9-10: cited spans and citation resolution
# ---------------------------------------------------------------------------


def test_cust_007s_spans_are_the_re_measured_ones_and_resolve_to_their_phrases(assessed):
    sessions, _ = assessed
    payload = meridian_brief(sessions).decision_payload
    with sessions() as session:
        texts = {
            source_id: citable_text(title, body)
            for source_id, title, body in session.execute(
                select(Document.source_id, Document.title, Document.body_text))
        }

    spans = {entry["target"]: entry["citation"] for entry in payload["cited_spans"]}
    assert list(spans) == [target.name for target in SPAN_TARGETS]
    for target in SPAN_TARGETS:
        start = texts[target.document_id].index(target.phrase)
        assert texts[target.document_id].count(target.phrase) == 1
        assert spans[target.name] == {"kind": "document", "document_id": target.document_id,
                                      "start": start, "end": start + len(target.phrase)}
        assert texts[target.document_id][start:start + len(target.phrase)] == target.phrase
    assert [(one["start"], one["end"]) for one in spans.values()] == [
        (238, 330), (153, 238), (238, 333)]


def test_no_target_applies_to_cust_025_or_cust_036(assessed):
    sessions, _ = assessed
    found = briefs_by_customer(sessions)

    for customer in ("CUST-025", "CUST-036"):
        (brief,) = found[customer]
        assert brief.decision_payload["cited_spans"] == []
        assert brief.decision_payload["document_evidence"] == []
        assert "Meridian" not in brief.narrative


def test_every_citation_of_every_brief_resolves(assessed):
    """§A25 test 8, checked by a resolver written from the plan, not the module under test."""
    sessions, _ = assessed
    checked = 0
    with sessions() as session:
        for rows in briefs_by_customer(sessions).values():
            for brief in rows:
                for citation in citation_values(brief.decision_payload):
                    assert resolves_independently(session, citation), citation
                    checked += 1
    assert checked > 0


def test_every_citation_of_every_assessment_resolves(assessed):
    sessions, _ = assessed
    with sessions() as session:
        stored = session.scalars(select(RiskPosition.citations)).all()
        for citations in stored:
            for citation in citation_values(citations):
                assert resolves_independently(session, citation), citation


def phrase_edit(sessions, document: str, new_body) -> None:
    with sessions.begin() as session:
        session.execute(update(Document).where(Document.source_id == document).values(
            body_text=new_body))


@pytest.mark.parametrize(("edit", "message"), [
    (lambda body: body.replace("within 14 days", "within fourteen days"), "does not occur"),
    (lambda body: body + "\n" + SPAN_TARGETS[0].phrase, "more than once"),
    (lambda body: None, "does not occur"),
])
def test_a_missing_or_repeated_phrase_raises_and_nothing_is_durable(demo, edit, message):
    with demo() as session:
        body = session.scalar(select(Document.body_text).where(Document.source_id == "DOC-003"))
    phrase_edit(demo, "DOC-003", edit(body))
    before = counts(demo)

    with pytest.raises(CitationResolutionError, match=message) as raised:
        run(demo)

    assert "DOC_003_ESCALATION_RULE" in str(raised.value)
    assert "DOC-003" in str(raised.value)
    assert counts(demo) == before


def test_an_absent_target_document_raises(demo):
    with demo.begin() as session:
        session.execute(delete(Document).where(Document.source_id == "DOC-003"))
    before = counts(demo)

    with pytest.raises(CitationResolutionError, match="DOC_003_ESCALATION_RULE names DOC-003"):
        run(demo)

    assert counts(demo) == before


def test_a_resolved_text_that_differs_from_the_phrase_raises(demo, monkeypatch):
    resolve = assessments.resolve_document_citation
    monkeypatch.setattr(
        assessments, "resolve_document_citation",
        lambda session, scope, citation: ("tampered" if citation.document_id == "DOC-006"
                                          else resolve(session, scope, citation)))

    with pytest.raises(CitationResolutionError, match="DOC_006_TERM_AND_NOTICE resolves"):
        run(demo)


def test_a_document_citation_past_its_text_raises_and_nothing_is_durable(assessed):
    """A planted unresolvable citation: DOC-005's links outlive a truncated body."""
    sessions, _ = assessed
    # The record_hash is left alone, so the snapshot identity -- and with it the
    # own-stamp links persisted by the first run -- does not move.
    phrase_edit(sessions, "DOC-005", "short")
    before = counts(sessions)

    with pytest.raises(CitationResolutionError, match="runs past the end"):
        run(sessions, config=replace(default_risk_rules(), rules_version=9))

    assert counts(sessions) == before


@pytest.mark.parametrize(("planted", "message"), [
    (RecordCitation("support_tickets", "TKT-999", "priority"), "not in source_system"),
    (RecordCitation("deals", "DEAL-001", "expected_close_date"), None),
])
def test_a_planted_record_citation_is_resolved_by_the_row_and_null_rule(demo, monkeypatch,
                                                                       planted, message):
    citations = assessments.payload_citations
    monkeypatch.setattr(assessments, "payload_citations",
                        lambda payload: (*citations(payload), planted))
    with demo.begin() as session:
        session.execute(update(Deal).where(Deal.source_id == "DEAL-001").values(
            expected_close_date=None))

    if message is None:
        assert len(run(demo)) == 50, "a NULL field outside DR21's four is accepted"
    else:
        with pytest.raises(CitationResolutionError, match=message):
            run(demo)


@pytest.mark.parametrize("field", ["created_at", "body_text", "amount", "currency"])
def test_a_null_field_the_brief_states_fails_resolution(demo, monkeypatch, field):
    """DR21: documents.body_text, support_tickets.created_at, deals.amount and deals.currency."""
    target = {"created_at": ("support_tickets", "TKT-039", SupportTicket),
              "body_text": ("documents", "DOC-012", Document),
              "amount": ("deals", "DEAL-002", Deal),
              "currency": ("deals", "DEAL-002", Deal)}[field]
    entity, source_id, model = target
    with demo.begin() as session:
        session.execute(update(model).where(model.source_id == source_id).values({field: None}))
    citations = assessments.payload_citations
    monkeypatch.setattr(assessments, "payload_citations", lambda payload: (
        *citations(payload), RecordCitation(entity, source_id, field)))

    with pytest.raises(CitationResolutionError, match=f"{source_id} {field}, which is NULL"):
        run(demo)


@pytest.mark.parametrize(("dates", "message"), [
    (lambda found: {key: value for key, value in found.items() if key != "TKT-076"},
     "TKT-076 is not in source_system"),
    (lambda found: {**found, "TKT-076": None}, "TKT-076 has no created_at"),
])
def test_a_visible_ticket_without_a_readable_date_fails_the_brief(demo, monkeypatch, dates,
                                                                 message):
    read = assessments.ticket_created_at
    monkeypatch.setattr(assessments, "ticket_created_at",
                        lambda *args: dates(read(*args)))
    before = counts(demo)

    with pytest.raises(CitationResolutionError, match=message):
        run(demo)

    assert counts(demo) == before


def test_a_naive_created_at_propagates_m1s_error_unchanged(demo, monkeypatch):
    read = assessments.ticket_created_at
    monkeypatch.setattr(assessments, "ticket_created_at", lambda *args: {
        key: value.replace(tzinfo=None) for key, value in read(*args).items()})

    with pytest.raises(ContractViolationError, match="naive datetime"):
        run(demo)


# ---------------------------------------------------------------------------
# Criterion 11: the stored narrative
# ---------------------------------------------------------------------------


def test_the_stored_narrative_states_the_deal_in_its_currency(assessed):
    sessions, _ = assessed
    narrative = meridian_brief(sessions).narrative

    assert "amount USD 5,361.44" in narrative
    assert "Active projects (S13): none. CUST-007 has no active project." in narrative
    assert "a 9-day span from 2026-08-18 to 2026-08-27, ticket count 5" in narrative
    assert "Escalation window: 2026-08-18 to 2026-08-31, ticket count 5" in narrative


def test_the_multi_currency_customer_is_never_totalled(assessed):
    """§A25 test 14's customer: its stored signals carry each currency, and no total."""
    sessions, _ = assessed
    signals = assessments_by_customer(sessions)["CUST-042"].signals

    assert sorted(signals["exposure_by_currency"]) == ["INR", "USD"]


# ---------------------------------------------------------------------------
# Criterion 11: the golden file (§0.6.10)
# ---------------------------------------------------------------------------

#: The approved CUST-007 narrative at ACCEPTANCE_AS_OF, pinned byte for byte.
GOLDEN = REPO / "tests" / "golden" / "vs01_cust007_brief.txt"
#: The CUST-007 payload_hash the golden narrative was approved against.
MERIDIAN_PAYLOAD_HASH = "e93c29cfb6094284d7ea6fe84bf966ad0b40995fccdc4e2a671b502a7f16c946"

#: §0.6.7's provenance map for §A27.3's six ticket facts: the golden lines that
#: state each, where the payload lists the tickets it counts, and the ticket
#: fields its provenance path cites.
TICKET_FACTS = [
    ("5 tickets in a 9-day span", [
        "Ticket span: a 9-day span from 2026-08-18 to 2026-08-27, ticket count 5: "
        "TKT-073, TKT-075, TKT-076, TKT-079, TKT-080",
    ], "ticket_span", ["created_at"]),
    ("4 open", [
        "- S1 open_ticket_count: 4",
        "- open_ticket_count = 4, counting TKT-075, TKT-076, TKT-079, TKT-080",
    ], "open_ticket_count", ["resolved_at"]),
    ("3 open high-priority", [
        "- S2 open_high_priority_count: 3",
        "- open_high_priority_count = 3, counting TKT-075, TKT-076, TKT-080",
    ], "open_high_priority_count", ["priority", "resolved_at"]),
    ("4 high-priority in total", [
        "- S2b high_priority_total: 4",
        "- high_priority_total = 4, counting TKT-073, TKT-075, TKT-076, TKT-080",
    ], "high_priority_total", ["priority"]),
    ("3 open high-priority SLA breaches", [
        "- S8 open_sla_breach_high_count: 3",
        "- open_sla_breach_high_count = 3, counting TKT-075, TKT-076, TKT-080",
    ], "open_sla_breach_high_count", ["created_at", "priority", "resolved_at"]),
    ("dominant category performance", [
        "- S10 dominant_ticket_category: performance",
        "- dominant_ticket_category = performance, counting TKT-073, TKT-075, TKT-076, TKT-079, "
        "TKT-080; category counts billing 1, integration 1, performance 3; lookback 2026-06-21 "
        "to 2026-09-18",
    ], "dominant_ticket_category", ["created_at", "category"]),
]


def golden_lines() -> list[str]:
    return GOLDEN.read_bytes().decode("utf-8").splitlines()


def test_the_cust_007_brief_is_the_golden_file_byte_for_byte(assessed):
    """The stored narrative's UTF-8 bytes against the pinned file, with no normalisation."""
    sessions, results = assessed
    brief = meridian_brief(sessions)

    assert brief.narrative.encode("utf-8") == GOLDEN.read_bytes()
    assert brief.payload_hash == MERIDIAN_PAYLOAD_HASH
    assert payload_hash(brief.decision_payload) == MERIDIAN_PAYLOAD_HASH
    assert MERIDIAN_PAYLOAD_HASH in [one.payload_hash for one in results]


def test_the_stored_payload_and_its_span_texts_re_render_the_golden_bytes(assessed):
    """The golden narrative is a function of the payload read back from JSONB and the phrases."""
    sessions, _ = assessed
    payload = meridian_brief(sessions).decision_payload
    phrases = {target.name: target.phrase for target in SPAN_TARGETS}

    assert briefs.render_brief(payload, phrases).encode("utf-8") == GOLDEN.read_bytes()


def test_rendering_inside_the_run_issues_no_sql(demo, e1_engine, monkeypatch):
    """
    §0.6.10: the narrative's inputs are the payload and the span texts only.

    Each render runs while the run's session is open, and the database sees
    no statement from it. CUST-007's render is the golden file.
    """
    statements: list[str] = []
    rendered: list[tuple[str, int, str]] = []
    real = assessments.render_brief

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    def watched(payload, span_texts):
        before = len(statements)
        narrative = real(payload, span_texts)
        rendered.append((payload["customer"]["id"], len(statements) - before, narrative))
        return narrative

    monkeypatch.setattr(assessments, "render_brief", watched)
    event.listen(e1_engine, "before_cursor_execute", record)
    try:
        run(demo)
    finally:
        event.remove(e1_engine, "before_cursor_execute", record)

    assert statements, "the listener saw no SQL at all, so it would pass watching nothing"
    assert [(customer, issued) for customer, issued, _ in rendered] == [
        (customer, 0) for customer in BRIEFED]
    assert rendered[0][2].encode("utf-8") == GOLDEN.read_bytes()


@pytest.mark.parametrize(("fact", "lines", "source", "fields"), TICKET_FACTS,
                         ids=[row[0] for row in TICKET_FACTS])
def test_the_golden_brief_states_each_a27_3_ticket_fact_on_a_resolving_path(
        assessed, fact, lines, source, fields):
    sessions, _ = assessed
    payload = meridian_brief(sessions).decision_payload
    evidence = payload["support_evidence"]
    stated = golden_lines()

    for line in lines:
        assert line in stated, (fact, line)
    if source == "ticket_span":
        span = evidence["ticket_span"]
        counted = span["ticket_ids"]
        assert (span["ticket_count"], span["ticket_span_days"]) == (5, 9)
        # The 9-day span is not the 14-day escalation window, which is stated beside it.
        assert "Escalation window: 2026-08-18 to 2026-08-31, ticket count 5" in stated
    else:
        derivation = {one["fact"]: one for one in evidence["derivations"]}[source]
        counted = derivation["ticket_ids"]
        assert derivation["value"] == payload["signals"][source]
    tickets = {one["id"]: one for one in evidence["tickets"]}
    with sessions() as session:
        for ticket_id in counted:
            cited = {one["citation"]["field"]: one["citation"]
                     for one in tickets[ticket_id]["evidence"]}
            for field in fields:
                assert resolves_independently(session, cited[field]), (ticket_id, field)
                assert f"  - CANONICAL_FACT record support_tickets {ticket_id} {field}" in stated


def test_the_golden_brief_states_deal_001_on_its_five_cited_fields(assessed):
    sessions, _ = assessed
    (deal,) = meridian_brief(sessions).decision_payload["commercial_evidence"]["deals"]
    stated = golden_lines()

    assert "- DEAL-001: stage negotiation, probability 90%, amount USD 5,361.44" in stated
    assert [one["citation"]["field"] for one in deal["evidence"]] == [
        "is_active", "stage", "probability", "amount", "currency"]
    with sessions() as session:
        for one in deal["evidence"]:
            assert resolves_independently(session, one["citation"]), one
            assert (f"  - CANONICAL_FACT record deals DEAL-001 {one['citation']['field']}"
                    in stated)


@pytest.mark.parametrize("target", SPAN_TARGETS, ids=lambda target: target.name)
def test_the_golden_brief_quotes_each_document_fact_as_one_resolving_span(assessed, target):
    sessions, _ = assessed
    spans = {entry["target"]: entry["citation"]
             for entry in meridian_brief(sessions).decision_payload["cited_spans"]}
    citation = spans[target.name]
    printed = f"{target.document_id} [{citation['start']}, {citation['end']})"
    with sessions() as session:
        title, body = session.execute(select(Document.title, Document.body_text).where(
            Document.source_system == SOURCE_SYSTEM,
            Document.source_id == target.document_id)).one()

    assert f'- {target.name}, {printed}: "{target.phrase}"' in golden_lines()
    assert citable_text(title, body)[citation["start"]:citation["end"]] == target.phrase


def test_the_golden_brief_states_the_absence_the_conflict_the_policy_and_the_dissent(assessed):
    """§A27.4 and §A27.5, with the dissent's own evidence."""
    sessions, _ = assessed
    payload = meridian_brief(sessions).decision_payload
    text = GOLDEN.read_bytes().decode("utf-8")
    dissent_section = text.split("6. RECORDED DISSENT\n", 1)[1].split("\n\n", 1)[0]

    assert payload["signals"]["active_project_count"] == 0
    for line in [
        "Active projects (S13): none. CUST-007 has no active project.",
        "- Conflict over DEAL-001:",
        "  - SALES ADVANCE ACCELERATE_DEAL_CLOSE",
        "  - SUPPORT RESTRAIN PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED",
        "  Resolved by policy CONF-001 (policy version 1): "
        "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED prevails, as SUPPORT proposed",
    ]:
        assert line in golden_lines(), line
    (dissent,) = payload["reconciliation"]["dissent"]
    assert dissent_section.splitlines()[0] == (
        "- Overruled by CONF-001: SALES ADVANCE ACCELERATE_DEAL_CLOSE on DEAL-001")
    with sessions() as session:
        for one in dissent["evidence"]:
            assert resolves_independently(session, one["citation"]), one
            assert (f"  - CANONICAL_FACT record deals DEAL-001 {one['citation']['field']}"
                    in dissent_section.splitlines())


def test_every_citation_the_golden_brief_prints_is_a_payload_citation_that_resolves(assessed):
    """
    The printed citations and the payload's are the same set, and each resolves.

    Records print as `record <entity> <id> <field>`, documents as
    `<document> [start, end)`; the rule id a record may carry is not part of it.
    """
    sessions, _ = assessed
    payload = meridian_brief(sessions).decision_payload
    printed: set[str] = set()
    for line in golden_lines():
        record = re.fullmatch(r"\s*- [A-Z_]+ record (\S+) (\S+) (\S+)(?: \(rule \S+\))?", line)
        if record:
            printed.add(canonical_json({"kind": "record", "entity": record[1], "id": record[2],
                                        "field": record[3]}))
        document = re.search(r"(DOC-\d+) \[(\d+), (\d+)\)", line)
        if document:
            printed.add(canonical_json({"kind": "document", "document_id": document[1],
                                        "start": int(document[2]), "end": int(document[3])}))
    in_payload = {canonical_json(citation) for citation in citation_values(payload)}

    assert len(printed) == 36
    assert printed == in_payload
    with sessions() as session:
        for citation in citation_values(payload):
            assert resolves_independently(session, citation), citation


# ---------------------------------------------------------------------------
# Criterion 12: events
# ---------------------------------------------------------------------------


def test_the_corpus_run_emits_the_directed_sequence(demo, caplog):
    caplog.set_level(logging.INFO, logger=EVENTS_LOGGER)

    results = run(demo)

    emitted = events(caplog)
    assert [name for name, _ in emitted] == [
        "vs01.scope_resolved", "vs01.links_derived", "vs01.conflict_detected",
        "vs01.conflict_resolved", "vs01.brief_generated", "vs01.brief_generated",
        "vs01.brief_generated"]
    for name, fields in emitted:
        assert list(fields) == EVENT_FIELDS[name]
        assert all(type(value) in (str, int, bool) for value in fields.values())
    assert emitted[0][1] == {"source_system": SOURCE_SYSTEM, "as_of": "2026-09-18",
                             "layer1_fingerprint": PINNED, "as_of_source": "EXPLICIT"}
    assert emitted[1][1] == {"source_system": SOURCE_SYSTEM, "layer1_fingerprint": PINNED,
                             "linker_version": "1", "inserted": 11}
    assert emitted[2][1] == {"customer": MERIDIAN, "object_ref": "DEAL-001",
                             "policy_id": "CONF-001", "policy_version": 1}
    assert emitted[3][1] == {**emitted[2][1],
                             "resolved_action": "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED"}
    hashes = [one.payload_hash for one in results if one.payload_hash]
    assert [(fields["customer"], fields["payload_hash"], fields["created"])
            for _, fields in emitted[4:]] == [
        (customer, digest, True) for customer, digest in zip(BRIEFED, hashes, strict=True)]
    assert emitted[4][1]["citation_count"] == 36
    for record in caplog.records:
        if record.name == EVENTS_LOGGER:
            assert record.levelno == logging.INFO


def test_a_re_run_emits_the_same_sequence_with_nothing_inserted_or_created(assessed, caplog):
    sessions, first = assessed
    caplog.set_level(logging.INFO, logger=EVENTS_LOGGER)

    run(sessions)

    emitted = events(caplog)
    assert emitted[1][1]["inserted"] == 0
    briefs_emitted = [fields for name, fields in emitted if name == "vs01.brief_generated"]
    assert [fields["created"] for fields in briefs_emitted] == [False, False, False]
    assert [fields["payload_hash"] for fields in briefs_emitted] == [
        one.payload_hash for one in first if one.payload_hash]
    assert briefs_emitted[0]["citation_count"] == 36


def test_no_event_carries_document_text_an_email_or_an_amount(demo, caplog):
    caplog.set_level(logging.INFO, logger=EVENTS_LOGGER)
    run(demo)
    with demo() as session:
        emails = [one for one in session.scalars(select(Customer.email)) if one]

    for _, fields in events(caplog):
        rendered = " ".join(str(value) for value in fields.values())
        for forbidden in ("Meridian", "5361.44", "5,361", *emails,
                          *(target.phrase for target in SPAN_TARGETS)):
            assert forbidden not in rendered


def test_a_run_that_raises_emits_nothing(demo, caplog):
    caplog.set_level(logging.INFO, logger=EVENTS_LOGGER)
    with demo.begin() as session:
        session.execute(text("UPDATE deals SET stage = 'negotiation', probability = 90 "
                             "WHERE source_id = 'DEAL-037'"))

    with pytest.raises(UnresolvableConflictError):
        run(demo)

    assert events(caplog) == []


# ---------------------------------------------------------------------------
# Criterion 13: failures
# ---------------------------------------------------------------------------


def test_the_deal_037_edit_raises_unwrapped_and_nothing_is_durable(demo):
    """M6's §0.5.5 shape on real rows: the whole run fails, and the rollback leaves nothing."""
    with demo.begin() as session:
        session.execute(text("UPDATE deals SET stage = 'negotiation', probability = 90 "
                             "WHERE source_id = 'DEAL-037'"))
    before = counts(demo)

    with pytest.raises(UnresolvableConflictError) as raised:
        run(demo)

    assert type(raised.value) is UnresolvableConflictError
    assert raised.value.object_ref == "DEAL-037"
    assert counts(demo) == before
    assert before["document_customer_links"] == 0


def test_a_rendering_failure_rolls_back_the_assessment_and_its_positions(demo, monkeypatch,
                                                                         tmp_path):
    monkeypatch.setattr(briefs, "TEMPLATE_PATH", tmp_path / "absent.txt")
    before = counts(demo)

    with pytest.raises(briefs.BriefRenderError):
        run(demo)

    assert counts(demo) == before


# ---------------------------------------------------------------------------
# Criterion 14: the DOC-005 leave-out
# ---------------------------------------------------------------------------


def test_doc005_leave_out_changes_no_band_signal_escalation_or_resolution(assessed):
    """§A25 test 4: in-process, against a dedicated test database."""
    sessions, _ = assessed
    full = meridian_brief(sessions).decision_payload
    with sessions.begin() as session:
        session.execute(delete(Document).where(Document.source_id == "DOC-005"))

    run(sessions)

    (left_out,) = [brief for brief in briefs_by_customer(sessions)[MERIDIAN]
                   if brief.decision_payload["scope"]["layer1_fingerprint"] != PINNED]
    payload = left_out.decision_payload
    assert counts(sessions)["risk_assessments"] == 100, "a new snapshot, new assessments"
    assert canonical_json(payload["band"]) == canonical_json(full["band"])
    assert canonical_json(payload["signals"]) == canonical_json(full["signals"])
    assert payload["signals"]["policy_escalation_state"] is True
    assert canonical_json(payload["reconciliation"]["resolutions"]) == canonical_json(
        full["reconciliation"]["resolutions"])
    assert [one["source"]["id"] for one in payload["document_evidence"]] == [
        "DOC-006", "DOC-006", "DOC-009", "DOC-009"]


# ---------------------------------------------------------------------------
# Criteria 15, 15a, 15b: §A27.3, §A27.5 and the support and commercial evidence
# ---------------------------------------------------------------------------


def test_cust_007s_support_and_commercial_evidence_are_the_observed_values(assessed):
    sessions, _ = assessed
    payload = meridian_brief(sessions).decision_payload
    evidence = payload["support_evidence"]

    assert [(one["id"], one["created_date"], one["priority"], one["category"], one["is_open"])
            for one in evidence["tickets"]] == [
        ("TKT-073", "2026-08-18", "high", "performance", False),
        ("TKT-075", "2026-08-20", "high", "performance", True),
        ("TKT-076", "2026-08-23", "high", "integration", True),
        ("TKT-079", "2026-08-25", "medium", "billing", True),
        ("TKT-080", "2026-08-27", "high", "performance", True)]
    assert evidence["escalation_window"] == {"start": "2026-08-18", "end": "2026-08-31",
                                             "count": 5}
    span = evidence["ticket_span"]
    assert (span["ticket_ids"], span["first_ticket_date"], span["last_ticket_date"],
            span["ticket_span_days"]) == (
        ["TKT-073", "TKT-075", "TKT-076", "TKT-079", "TKT-080"], "2026-08-18", "2026-08-27", 9)
    derived = {one["fact"]: one for one in evidence["derivations"]}
    assert [(fact, one["value"], one["ticket_ids"]) for fact, one in derived.items()] == [
        ("open_ticket_count", 4, ["TKT-075", "TKT-076", "TKT-079", "TKT-080"]),
        ("open_high_priority_count", 3, ["TKT-075", "TKT-076", "TKT-080"]),
        ("high_priority_total", 4, ["TKT-073", "TKT-075", "TKT-076", "TKT-080"]),
        ("open_sla_breach_high_count", 3, ["TKT-075", "TKT-076", "TKT-080"]),
        ("dominant_ticket_category", "performance",
         ["TKT-073", "TKT-075", "TKT-076", "TKT-079", "TKT-080"])]
    assert derived["dominant_ticket_category"]["category_counts"] == {
        "billing": 1, "integration": 1, "performance": 3}
    assert derived["dominant_ticket_category"]["lookback"] == {"start": "2026-06-21",
                                                               "end": "2026-09-18"}
    assert evidence["backlog_ticket_ids"] == []
    path = evidence["escalation_path"]
    assert (path["account_owner"]["id"], path["account_owner_manager"]["id"]) == (
        "EMP-007", "EMP-002")
    assert sorted(one["id"] for one in path["assignees"]) == [
        "EMP-017", "EMP-018", "EMP-020", "EMP-021"]
    assert [one["id"] for one in path["assignee_managers"]] == ["EMP-004"]
    (deal,) = payload["commercial_evidence"]["deals"]
    assert (deal["id"], deal["stage"], deal["probability"], deal["amount"]) == (
        "DEAL-001", "negotiation", "90", {"amount": "5361.44", "currency": "USD"})
    assert [one["citation"]["field"] for one in deal["evidence"]] == [
        "is_active", "stage", "probability", "amount", "currency"]


@pytest.mark.parametrize(("customer", "window", "span", "backlog", "counts_", "counted"), [
    ("CUST-025", {"start": "2026-07-10", "end": "2026-07-23", "count": 1}, ["TKT-063"],
     ["TKT-039"], {"billing": 1, "onboarding": 1}, ["TKT-063", "TKT-072"]),
    ("CUST-036", {"start": "2026-08-24", "end": "2026-09-06", "count": 1}, ["TKT-078"],
     [], {"performance": 1}, ["TKT-078"]),
])
def test_the_watch_briefs_support_evidence(assessed, customer, window, span, backlog,
                                           counts_, counted):
    """§0.6.15 criterion 15b: MP2's one-ticket case, twice."""
    sessions, _ = assessed
    (brief,) = briefs_by_customer(sessions)[customer]
    evidence = brief.decision_payload["support_evidence"]

    assert evidence["escalation_window"] == window
    assert evidence["ticket_span"]["ticket_ids"] == span
    assert evidence["ticket_span"]["ticket_span_days"] == 0
    assert evidence["backlog_ticket_ids"] == backlog
    dominant = evidence["derivations"][4]
    assert (dominant["category_counts"], dominant["ticket_ids"]) == (counts_, counted)
    expected = "billing" if customer == "CUST-025" else "performance"
    assert dominant["value"] == expected


def test_every_a27_3_and_a27_5_fact_is_in_the_brief_with_its_provenance(assessed):
    sessions, _ = assessed
    brief = meridian_brief(sessions)
    payload, narrative = brief.decision_payload, brief.narrative
    derived = {one["fact"]: one for one in payload["support_evidence"]["derivations"]}
    tickets = {one["id"]: one for one in payload["support_evidence"]["tickets"]}

    # 5 tickets in a 9-day span, cited to each ticket's created_at.
    span = payload["support_evidence"]["ticket_span"]
    assert (span["ticket_count"], span["ticket_span_days"]) == (5, 9)
    for ticket_id in span["ticket_ids"]:
        assert tickets[ticket_id]["evidence"][0]["citation"]["field"] == "created_at"
    # 4 open; 3 open high-priority; 4 high-priority in total, TKT-073 included; 3 breaches.
    assert [derived[fact]["value"] for fact in (
        "open_ticket_count", "open_high_priority_count", "high_priority_total",
        "open_sla_breach_high_count")] == [4, 3, 4, 3]
    assert "TKT-073" in derived["high_priority_total"]["ticket_ids"]
    assert [one["citation"]["field"] for one in tickets["TKT-073"]["evidence"]] == [
        "created_at", "priority", "category", "resolved_at"]
    # Dominant category performance, over every counted ticket's category.
    assert derived["dominant_ticket_category"]["value"] == "performance"
    # DEAL-001 negotiation at 90% for USD 5,361.44, cited field by field.
    assert "DEAL-001: stage negotiation, probability 90%, amount USD 5,361.44" in narrative
    # The three document facts, each one exact span.
    for target in SPAN_TARGETS:
        assert target.phrase in narrative
    # §A27.4 and §A27.5: no active project; the conflict, the policy, the winner, the dissent.
    assert "CUST-007 has no active project." in narrative
    assert "- Conflict over DEAL-001:" in narrative
    assert "Resolved by policy CONF-001" in narrative
    assert "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED prevails" in narrative
    assert "- Overruled by CONF-001: SALES ADVANCE ACCELERATE_DEAL_CLOSE on DEAL-001" in narrative
    (dissent,) = payload["reconciliation"]["dissent"]
    assert dissent["proposed_action"] == "ACCELERATE_DEAL_CLOSE"
    assert [one["citation"]["field"] for one in dissent["evidence"]] == [
        "is_active", "stage", "probability"]


def test_no_brief_holds_another_customers_identifiers(assessed):
    """§A25 test 9: a brief for X names no other customer's source id."""
    sessions, _ = assessed
    with sessions() as session:
        customers = session.scalars(select(Customer.source_id)).all()
    for owner, rows in briefs_by_customer(sessions).items():
        for brief in rows:
            stored = canonical_json(brief.decision_payload) + brief.narrative
            for other in customers:
                if other != owner:
                    assert other not in stored, (owner, other)
