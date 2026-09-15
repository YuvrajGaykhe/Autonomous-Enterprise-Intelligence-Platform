"""
G1 ingestion events from E1 against the test database.

    batch_fetched       INFO     one per fetched page, before the quality gate
    record_normalized   DEBUG    one per record the quality gate accepted
    record_rejected     WARNING  one per record the quality gate quarantined
    run_finished        INFO     once per finished run, with duration_seconds

Events carry the run ID and identifiers only, and logging (at any level)
leaves run behaviour, counts and persisted rows unchanged.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from e1_support import NOW, csv_row
from sqlalchemy import select

from app.connectors import (
    ConnectorCapabilities,
    ConnectorHealth,
    ConnectorUnavailableError,
    Page,
)
from app.connectors.registry import build_connector
from app.core.logging import JsonFormatter
from app.ingestion import orchestrator
from app.ingestion.errors import ConnectorContractError, IngestionCode
from app.ingestion.orchestrator import ENTITY_ORDER, IngestionRequest, run_ingestion
from app.persistence.models import IngestionError, IngestionRun
from app.validation import QualityFinding, QualityGateResult, QuarantineRecord, Severity, Stage

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
BAD_FIXTURE_DIR = REPO / "data" / "fixtures" / "csv_demo_bad"
SECRET = "G1_SYNTHETIC_REJECTED_VALUE"
SYSTEM_CODES = {code.value for code in IngestionCode}


class Connector:
    """In-memory connector: pages per entity, an optional failure per (entity, page)."""

    source_type = "fake"

    def __init__(self, pages, *, healthy=True, failures=None, page_factory=None):
        self.pages = pages
        self.healthy = healthy
        self.failures = dict(failures or {})
        self.page_factory = page_factory

    @property
    def source_name(self):
        return "csv_demo"

    def health_check(self):
        return ConnectorHealth(healthy=self.healthy, source_name="csv_demo")

    def list_entities(self):
        return []

    def fetch_entities(self, entity_type, cursor=None, page_size=100):
        index = int(cursor or 0)
        failure = self.failures.pop((entity_type, index), None)
        if failure is not None:
            raise failure
        if self.page_factory is not None:
            return self.page_factory()
        pages = self.pages.get(entity_type, [[]])
        has_more = index + 1 < len(pages)
        return Page(items=list(pages[index]), next_cursor=str(index + 1) if has_more else None,
                    has_more=has_more)

    def get_entity(self, entity_type, source_id):
        raise NotImplementedError

    def capabilities(self):
        return ConnectorCapabilities(supported_entity_types=sorted(ENTITY_ORDER))


class TickingClock:
    """Each reading is 1.25 seconds after the previous one."""

    def __init__(self):
        self.moment = NOW

    def __call__(self):
        current = self.moment
        self.moment += timedelta(seconds=1.25)
        return current


def _customers():
    return {"customers": [
        [csv_row("customers"), csv_row("customers", customer_id="CUST-002", status=SECRET)],
        [csv_row("customers", customer_id="CUST-003", customer_name="Third Co",
                 email_address="third@example.com")],
    ]}


def _events(caplog, *names):
    return [(record.event, record.levelno, record.event_fields) for record in caplog.records
            if record.name.startswith("app.ingestion") and hasattr(record, "event")
            and (not names or record.event in names)]


def _run_row(sessions, run_id):
    with sessions() as session:
        return session.get(IngestionRun, run_id)


def _error_rows(sessions, run_id):
    with sessions() as session:
        return session.scalars(select(IngestionError).where(
            IngestionError.ingestion_run_id == run_id).order_by(IngestionError.id)).all()


def test_events_follow_the_run_page_by_page(e1_sessions, caplog):
    with caplog.at_level(logging.DEBUG, logger="app.ingestion"):
        summary = run_ingestion(Connector(_customers()), e1_sessions,
                                IngestionRequest(entities=["customers"], page_size=2),
                                clock=TickingClock())
    run_id = summary.run_id
    assert [name for name, _, _ in _events(caplog)] == [
        "run_started",
        "batch_fetched", "record_normalized", "record_rejected", "batch_committed",
        "batch_fetched", "record_normalized", "batch_committed",
        "run_finished",
    ]
    (rejected_row,) = [row for row in _error_rows(e1_sessions, run_id) if row.severity == "ERROR"]
    assert _events(caplog, "batch_fetched", "record_normalized", "record_rejected") == [
        ("batch_fetched", logging.INFO, {"run_id": run_id, "entity": "customers", "page": 0,
                                          "records": 2, "has_more": True}),
        ("record_normalized", logging.DEBUG, {"run_id": run_id, "entity": "customers", "page": 0,
                                              "record_index": 0, "source_id": "CUST-001"}),
        ("record_rejected", logging.WARNING, {
            "run_id": run_id, "entity": "customers", "page": 0, "record_index": 1,
            "source_id": "CUST-002", "stage": json.loads(rejected_row.detail)["stage"],
            "codes": rejected_row.error_code}),
        ("batch_fetched", logging.INFO, {"run_id": run_id, "entity": "customers", "page": 1,
                                          "records": 1, "has_more": False}),
        ("record_normalized", logging.DEBUG, {"run_id": run_id, "entity": "customers", "page": 1,
                                              "record_index": 0, "source_id": "CUST-003"}),
    ]
    assert rejected_row.source_id == "CUST-002"


def test_run_finished_is_emitted_once_with_the_persisted_duration(e1_sessions, caplog):
    with caplog.at_level(logging.INFO, logger="app.ingestion"):
        summary = run_ingestion(Connector(_customers()), e1_sessions,
                                IngestionRequest(entities=["customers"], page_size=2),
                                clock=TickingClock())
    run = _run_row(e1_sessions, summary.run_id)
    ((_, level, fields),) = _events(caplog, "run_finished")
    duration = (run.finished_at - run.started_at).total_seconds()
    assert duration > 0
    assert (level, fields) == (logging.INFO, {
        "run_id": summary.run_id, "status": "PARTIAL_SUCCESS", "fetched": 3, "inserted": 2,
        "updated": 0, "unchanged": 0, "rejected": 1, "failed": 0, "warnings": 0,
        "duration_seconds": duration})
    assert duration == (summary.finished_at - summary.started_at).total_seconds()


def test_record_normalized_is_debug_only(e1_sessions, caplog):
    with caplog.at_level(logging.INFO, logger="app.ingestion"):
        run_ingestion(Connector(_customers()), e1_sessions,
                      IngestionRequest(entities=["customers"], page_size=2), clock=TickingClock())
    names = [name for name, _, _ in _events(caplog)]
    assert "record_normalized" not in names
    assert names.count("batch_fetched") == 2 and names.count("record_rejected") == 1


def test_record_normalized_is_not_even_built_when_debug_is_disabled(e1_sessions, caplog,
                                                                    monkeypatch):
    built = []
    real = orchestrator.log_event

    def spy(logger, level, event, /, **fields):
        built.append(event)
        real(logger, level, event, **fields)

    monkeypatch.setattr(orchestrator, "log_event", spy)
    with caplog.at_level(logging.INFO, logger="app.ingestion"):
        run_ingestion(Connector(_customers()), e1_sessions,
                      IngestionRequest(entities=["customers"], page_size=2), clock=TickingClock())
    assert "record_normalized" not in built
    assert built.count("record_rejected") == 1 and built.count("batch_fetched") == 2


def test_record_indexes_are_positions_in_the_fetched_page(e1_sessions, caplog):
    page = [csv_row("customers", customer_id="CUST-010", status=SECRET),
            csv_row("customers", customer_id="CUST-011", customer_name="Eleven Co",
                    email_address="eleven@example.com"),
            csv_row("customers", customer_id="CUST-012", customer_name="Twelve Co",
                    email_address="twelve@example.com")]
    with caplog.at_level(logging.DEBUG, logger="app.ingestion"):
        run_ingestion(Connector({"customers": [page]}), e1_sessions,
                      IngestionRequest(entities=["customers"]), clock=TickingClock())
    assert [(f["record_index"], f["source_id"])
            for _, _, f in _events(caplog, "record_normalized")] == [(1, "CUST-011"),
                                                                    (2, "CUST-012")]
    assert [(f["record_index"], f["source_id"])
            for _, _, f in _events(caplog, "record_rejected")] == [(0, "CUST-010")]


def test_record_rejected_lists_each_finding_code_once_in_finding_order(caplog):
    run_id = uuid.uuid4()

    def finding(code: str, field_name: str) -> QualityFinding:
        return QualityFinding(severity=Severity.ERROR, code=code, message="synthetic",
                              record_index=0, source_id="CUST-1", field_name=field_name,
                              raw_value=SECRET)

    rejected = QuarantineRecord(
        ingestion_run_id=run_id, source_system="csv_demo", entity_type="customers",
        record_index=0, stage=Stage.VALIDATION, source_id="CUST-1", canonical_id=None,
        findings=(finding("REQUIRED_FIELD_MISSING", "email"), finding("INVALID_DATE", "created_at"),
                  finding("REQUIRED_FIELD_MISSING", "name")),
        raw_record={"customer_name": SECRET})
    gate = QualityGateResult(source_system="csv_demo", entity_type="customers",
                             ingestion_run_id=run_id, total_records=1, valid=(),
                             quarantined=(rejected,), warnings=())
    with caplog.at_level(logging.DEBUG, logger="app.ingestion"):
        orchestrator._log_quality_gate(SimpleNamespace(run_id=run_id), "customers", 3, gate)
    assert _events(caplog) == [("record_rejected", logging.WARNING, {
        "run_id": run_id, "entity": "customers", "page": 3, "record_index": 0,
        "source_id": "CUST-1", "stage": "validation",
        "codes": "REQUIRED_FIELD_MISSING,INVALID_DATE"})]
    assert SECRET not in caplog.text


@pytest.mark.parametrize("level", [logging.DEBUG, logging.CRITICAL])
def test_logging_level_does_not_change_the_run(e1_sessions, caplog, level):
    with caplog.at_level(level, logger="app.ingestion"):
        summary = run_ingestion(Connector(_customers()), e1_sessions,
                                IngestionRequest(entities=["customers"], page_size=2),
                                clock=TickingClock())
    report = summary.to_dict()
    for key in ("run_id", "started_at", "finished_at"):
        report.pop(key)
    assert report["status"] == "PARTIAL_SUCCESS"
    assert (report["records_fetched"], report["records_inserted"], report["records_rejected"],
            report["batches_committed"]) == (3, 2, 1, 2)
    assert [(row.severity, row.error_code, row.source_id)
            for row in _error_rows(e1_sessions, summary.run_id)] == [
        ("ERROR", _error_rows(e1_sessions, summary.run_id)[0].error_code, "CUST-002")]
    run = _run_row(e1_sessions, summary.run_id)
    assert (run.records_fetched, run.records_inserted, run.records_rejected) == (3, 2, 1)


def test_events_carry_identifiers_never_rejected_values(e1_sessions, caplog):
    with caplog.at_level(logging.DEBUG, logger="app"):
        run_ingestion(Connector(_customers(),
                                failures={("deals", 0): ConnectorUnavailableError(SECRET)}),
                      e1_sessions, IngestionRequest(entities=["customers", "deals"], page_size=2),
                      clock=TickingClock())
    rendered = caplog.text + "\n".join(JsonFormatter().format(record)
                                       for record in caplog.records)
    for private in (SECRET, "raw_value", "raw_record", "raw_payload", "email", "Acme Industries"):
        assert private not in rendered
    run_ids = {fields["run_id"] for _, _, fields in _events(caplog)}
    assert len(run_ids) == 1


def test_a_connector_failure_fetches_no_batch_and_still_finishes_once(e1_sessions, caplog):
    connector = Connector({}, failures={("customers", 0): ConnectorUnavailableError(SECRET)})
    with caplog.at_level(logging.DEBUG, logger="app.ingestion"):
        summary = run_ingestion(connector, e1_sessions, IngestionRequest(entities=["customers"]),
                                clock=TickingClock())
    assert [name for name, _, _ in _events(caplog)] == [
        "run_started", "entity_failed", "run_finished"]
    assert _events(caplog, "run_finished")[0][2]["status"] == summary.status.value == "FAILED"


def test_a_failed_batch_is_reported_in_run_finished(e1_sessions, caplog):
    too_long = "N" * 300
    connector = Connector({"customers": [[csv_row("customers", customer_name=too_long)]]})
    with caplog.at_level(logging.DEBUG, logger="app.ingestion"):
        summary = run_ingestion(connector, e1_sessions, IngestionRequest(entities=["customers"]),
                                clock=TickingClock())
    assert [name for name, _, _ in _events(caplog)] == [
        "run_started", "batch_fetched", "record_normalized", "batch_failed", "run_finished"]
    ((_, _, fields),) = _events(caplog, "run_finished")
    assert (fields["status"], fields["fetched"], fields["failed"], fields["inserted"]) == (
        "FAILED", 1, 1, 0)
    assert summary.records_failed == 1
    assert too_long not in caplog.text


def test_a_failed_health_check_finishes_once_without_batches(e1_sessions, caplog):
    with caplog.at_level(logging.DEBUG, logger="app.ingestion"):
        run_ingestion(Connector(_customers(), healthy=False), e1_sessions,
                      IngestionRequest(entities=["customers"]), clock=TickingClock())
    assert [name for name, _, _ in _events(caplog)] == [
        "run_started", "connector_health_check_failed", "run_finished"]


def test_a_system_failure_logs_run_failed_and_no_run_finished(e1_sessions, caplog):
    connector = Connector({}, page_factory=lambda: {"items": []})
    with caplog.at_level(logging.DEBUG, logger="app.ingestion"), \
            pytest.raises(ConnectorContractError):
        run_ingestion(connector, e1_sessions, IngestionRequest(entities=["customers"]),
                      clock=TickingClock())
    assert [name for name, _, _ in _events(caplog)] == ["run_started", "run_failed"]


def test_bad_fixture_events_reconcile_with_the_run_and_quarantine(e1_sessions, caplog):
    with caplog.at_level(logging.DEBUG, logger="app.ingestion"):
        summary = run_ingestion(build_connector("csv_demo", data_directory=BAD_FIXTURE_DIR),
                                e1_sessions, clock=TickingClock())
    counts = summary.counts
    events = _events(caplog)
    normalized = [fields for name, _, fields in events if name == "record_normalized"]
    rejected = [fields for name, _, fields in events if name == "record_rejected"]
    fetched = [fields for name, _, fields in events if name == "batch_fetched"]
    assert len(normalized) == counts.inserted + counts.updated + counts.unchanged
    assert len(rejected) == counts.rejected > 0
    assert sum(fields["records"] for fields in fetched) == counts.fetched
    quarantine = sorted((row.source_entity, row.source_id, row.error_code)
                        for row in _error_rows(e1_sessions, summary.run_id)
                        if row.severity == "ERROR" and row.error_code not in SYSTEM_CODES)
    assert sorted((fields["entity"], fields["source_id"], fields["codes"].split(",")[0])
                  for fields in rejected) == quarantine
    rendered = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    for value in ("suspended", "12,50,000.00", "31/12/2026", "CUST-999"):
        assert value not in rendered


def test_run_finished_renders_typed_json(e1_sessions, caplog):
    with caplog.at_level(logging.INFO, logger="app.ingestion"):
        summary = run_ingestion(Connector(_customers()), e1_sessions,
                                IngestionRequest(entities=["customers"], page_size=2),
                                clock=TickingClock())
    (record,) = [r for r in caplog.records if getattr(r, "event", None) == "run_finished"]
    payload = json.loads(JsonFormatter().format(record))
    assert payload["run_id"] == str(summary.run_id)
    assert isinstance(payload["duration_seconds"], float) and payload["duration_seconds"] > 0
    assert isinstance(payload["fetched"], int) and payload["logger"] == "app.ingestion.orchestrator"
