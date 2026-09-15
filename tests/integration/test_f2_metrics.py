"""
GET /api/v1/metrics/ingestion against the test database.

Metrics are checked against real E1 ingestions of the committed demo data and
the E2 bad fixture (reconciled with each run report and with the entity
routes), and against runs, errors and raw records written through the E1
repositories to cover RUNNING and FAILED runs, durations and every error class.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.api.connectors import ConnectorProvider
from app.connectors.registry import build_connector
from app.ingestion.orchestrator import IngestionRequest, RunSummary, run_ingestion
from app.main import create_app
from app.persistence.models import Customer, IngestionError, IngestionRun, SourceRecord
from app.persistence.repositories import errors, runs
from app.persistence.repositories.canonical import ENTITY_MODELS

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
BAD_FIXTURE_DIR = REPO / "data" / "fixtures" / "csv_demo_bad"
T0 = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
METRICS = "/api/v1/metrics/ingestion"
CONFIGURED = ["csv_demo", "odoo_mock", "rest_mock"]
STATUSES = ("RUNNING", "SUCCESS", "PARTIAL_SUCCESS", "FAILED", "NOOP")
SCALARS = ("runs_total", "records_fetched_total", "records_raw_persisted_total",
           "records_inserted_total", "records_updated_total", "records_unchanged_total",
           "records_rejected_total", "records_failed_total", "warnings_total",
           "batches_failed_total", "connector_request_failures_total", "validation_errors_total",
           "ingestion_duration_seconds_total")
BREAKDOWNS = ("runs_by_status", "errors_by_severity", "canonical_records")
# Rejected source values and raw diagnostics of the bad fixture, stored messages, credentials.
FORBIDDEN = ("suspended", "12,50,000.00", "31/12/2026", "CUST-999", "raw_record", "raw_value",
             "raw_payload", "rolled back", "health check failed", "changeme", "postgresql://")


def _zero() -> dict:
    return {
        **dict.fromkeys(SCALARS, 0), "ingestion_duration_seconds_total": 0.0,
        "runs_by_status": dict.fromkeys(STATUSES, 0),
        "errors_by_severity": {"ERROR": 0, "WARNING": 0, "INFO": 0},
        "canonical_records": dict.fromkeys(ENTITY_MODELS, 0),
    }


def _empty_source(name: str) -> dict:
    return {**_zero(), "source_system": name, "last_run": None, "last_successful_run": None}


def _ingest(sessions, directory: Path, at: datetime) -> RunSummary:
    return run_ingestion(build_connector("csv_demo", data_directory=directory), sessions,
                         IngestionRequest(), clock=lambda: at)


@pytest.fixture
def client(e1_sessions):
    return TestClient(create_app(sessions=e1_sessions), raise_server_exceptions=False)


def _metrics(client) -> dict:
    response = client.get(METRICS)
    assert response.status_code == 200, response.text
    return response.json()


def _reference(run_id: uuid.UUID, status: str, started: datetime,
               finished: datetime | None) -> dict:
    return {"run_id": str(run_id), "status": status, "started_at": started,
            "finished_at": finished}


def _parsed(source: dict) -> dict:
    parsed = dict(source)
    for key in ("last_run", "last_successful_run"):
        if parsed[key] is not None:
            reference = dict(parsed[key])
            for moment in ("started_at", "finished_at"):
                if reference[moment] is not None:
                    reference[moment] = datetime.fromisoformat(reference[moment])
            parsed[key] = reference
    return parsed


def _assert_totals_are_sums_over_sources(body: dict) -> None:
    sources = body["sources"]
    for key in SCALARS:
        assert body["totals"][key] == pytest.approx(sum(source[key] for source in sources)), key
    for group in BREAKDOWNS:
        assert body["totals"][group] == {
            name: sum(source[group][name] for source in sources)
            for name in body["totals"][group]}, group


# --- empty database ---------------------------------------------------------------


def test_an_empty_database_reports_zeros_for_every_configured_source(client):
    assert _metrics(client) == {"totals": _zero(),
                                "sources": [_empty_source(name) for name in CONFIGURED]}


def test_sources_come_from_the_provider_without_building_connectors(e1_sessions):
    def refuse(source: str):
        raise AssertionError(f"metrics must not build connector {source}")

    provider = ConnectorProvider(build=refuse, sources=("zeta_source", "alpha_source"))
    client = TestClient(create_app(sessions=e1_sessions, connectors=provider))
    assert _metrics(client)["sources"] == [_empty_source("alpha_source"),
                                           _empty_source("zeta_source")]


# --- real E1 ingestion history ------------------------------------------------------


@pytest.fixture
def history(e1_sessions, tmp_path) -> list[RunSummary]:
    return [
        _ingest(e1_sessions, DEMO_DIR, T0),
        _ingest(e1_sessions, DEMO_DIR, T0 + timedelta(hours=1)),
        _ingest(e1_sessions, BAD_FIXTURE_DIR, T0 + timedelta(hours=2)),
        _ingest(e1_sessions, tmp_path / "missing", T0 + timedelta(hours=3)),
    ]


def test_csv_ingestion_history_reconciles_with_run_reports_and_entities(client, history):
    reports = [summary.to_dict() for summary in history]
    assert [report["status"] for report in reports] == [
        "SUCCESS", "NOOP", "PARTIAL_SUCCESS", "FAILED"]
    body = _metrics(client)
    assert [source["source_system"] for source in body["sources"]] == CONFIGURED
    csv_demo = _parsed(body["sources"][0])
    for metric, report_key in (
            ("records_fetched_total", "records_fetched"),
            ("records_raw_persisted_total", "records_raw_persisted"),
            ("records_inserted_total", "records_inserted"),
            ("records_updated_total", "records_updated"),
            ("records_unchanged_total", "records_unchanged"),
            ("records_rejected_total", "records_rejected"),
            ("records_failed_total", "records_failed"),
            ("warnings_total", "warnings"),
            ("batches_failed_total", "batches_failed")):
        assert csv_demo[metric] == sum(report[report_key] for report in reports), metric
    assert csv_demo["records_inserted_total"] == 233 + 4
    assert csv_demo["runs_total"] == 4
    assert csv_demo["runs_by_status"] == {"RUNNING": 0, "SUCCESS": 1, "PARTIAL_SUCCESS": 1,
                                          "FAILED": 1, "NOOP": 1}
    # Bad fixture: 3 rejected records and 3 warnings; failed run: one connector finding.
    assert csv_demo["errors_by_severity"] == {"ERROR": 4, "WARNING": 3, "INFO": 0}
    assert (csv_demo["validation_errors_total"], csv_demo["connector_request_failures_total"]) \
        == (3, 1)
    assert csv_demo["ingestion_duration_seconds_total"] == pytest.approx(sum(
        (summary.finished_at - summary.started_at).total_seconds() for summary in history))
    entity_totals = {entity: client.get(f"/api/v1/entities/{entity}",
                                        params={"limit": 1}).json()["total"]
                     for entity in ENTITY_MODELS}
    assert csv_demo["canonical_records"] == entity_totals
    failed, bad = history[3], history[2]
    assert csv_demo["last_run"] == _reference(failed.run_id, "FAILED", failed.started_at,
                                              failed.finished_at)
    assert csv_demo["last_successful_run"] == _reference(bad.run_id, "PARTIAL_SUCCESS",
                                                         bad.started_at, bad.finished_at)
    assert body["sources"][1:] == [_empty_source("odoo_mock"), _empty_source("rest_mock")]
    _assert_totals_are_sums_over_sources(body)


def test_metrics_never_expose_messages_source_values_or_raw_records(client, history):
    text = client.get(METRICS).text
    for value in FORBIDDEN:
        assert value not in text, value


# --- runs written through the E1 repositories ---------------------------------------


def _run(session, run_id: uuid.UUID, source: str, started: datetime, *,
         counts: runs.RunCounts | None = None, status: runs.RunStatus | None = None,
         finished: datetime | None = None) -> None:
    runs.create_run(session, run_id=run_id, source_system=source, source_entity=None,
                    mode=runs.RunMode.FULL, started_at=started)
    if counts is not None:
        runs.add_run_counts(session, run_id, counts)
    if status is not None:
        runs.finish_run(session, run_id, status=status, finished_at=finished,
                        error_summary="summary text that metrics never return")


def _entry(severity: str, code: str, source_system: str | None = "rest_mock"):
    return errors.ErrorEntry(severity=severity, error_code=code, message=f"{code} rolled back",
                             source_system=source_system)


def _raw(run_id: uuid.UUID, source_system: str, source_id: str) -> SourceRecord:
    return SourceRecord(source_system=source_system, source_entity="customers",
                        source_id=source_id, ingestion_run_id=run_id,
                        raw_payload={"raw_value": "suspended"}, content_hash="0" * 64)


def _customer(source_system: str, source_id: str) -> Customer:
    return Customer(source_system=source_system, source_entity="customers", source_id=source_id,
                    ingestion_run_id=uuid.uuid4(), record_hash="0" * 64, name="Synthetic",
                    is_active=True)


def test_counts_errors_durations_and_latest_runs_are_attributed_per_source(client, e1_sessions):
    done, failed, running = uuid.UUID(int=10), uuid.UUID(int=11), uuid.UUID(int=12)
    legacy_old, legacy_low, legacy_high = uuid.UUID(int=19), uuid.UUID(int=20), uuid.UUID(int=21)
    with e1_sessions.begin() as session:
        _run(session, done, "rest_mock", T0, counts=runs.RunCounts(
            fetched=10, inserted=4, updated=2, unchanged=1, rejected=1, warnings=3),
            status=runs.RunStatus.SUCCESS, finished=T0 + timedelta(seconds=90))
        _run(session, failed, "rest_mock", T0 + timedelta(minutes=5),
             status=runs.RunStatus.FAILED, finished=T0 + timedelta(minutes=5, seconds=30))
        _run(session, running, "rest_mock", T0 + timedelta(minutes=10),
             counts=runs.RunCounts(fetched=5, inserted=5))
        # Two NOOP runs of 50 ms sum to 0.1 s; with the 0.2 s SUCCESS run the total does not add
        # up exactly in binary floating point. legacy_low and legacy_high start together, so the
        # newest run (a NOOP, which counts as successful) is chosen by id.
        _run(session, legacy_old, "legacy_erp", T0 - timedelta(hours=1),
             status=runs.RunStatus.NOOP, finished=T0 - timedelta(hours=1, milliseconds=-50))
        _run(session, legacy_low, "legacy_erp", T0, status=runs.RunStatus.SUCCESS,
             finished=T0 + timedelta(milliseconds=200))
        _run(session, legacy_high, "legacy_erp", T0, status=runs.RunStatus.NOOP,
             finished=T0 + timedelta(milliseconds=50))
        errors.add_errors(session, done, [
            _entry("ERROR", "BATCH_FAILED"), _entry("ERROR", "BATCH_FAILED"),
            _entry("ERROR", "CONNECTOR_FAILED", source_system=None),
            _entry("ERROR", "INVALID_DATE"), _entry("WARNING", "UNRESOLVED_REFERENCE"),
            _entry("INFO", "RUN_NOTE"),
        ], created_at=T0)
        errors.add_errors(session, failed, [_entry("ERROR", "CONNECTOR_UNHEALTHY")],
                          created_at=T0)
        # The same (severity, code) in two source systems: totals must add them.
        errors.add_errors(session, legacy_low, [_entry("ERROR", "INVALID_DATE", "legacy_erp")],
                          created_at=T0)
        # Raw records and errors are attributed through their run, whatever their own columns say.
        session.add_all([_raw(done, "odoo_mock", "C-1"), _raw(done, "odoo_mock", "C-2"),
                         _raw(legacy_low, "legacy_erp", "L-1"),
                         _customer("rest_mock", "C-1"), _customer("rest_mock", "C-2"),
                         # legacy_erp has runs but no canonical records.
                         # Canonical records whose source system has no persisted run.
                         _customer("archive_source", "A-1")])

    body = _metrics(client)
    assert [source["source_system"] for source in body["sources"]] == [
        "archive_source", "csv_demo", "legacy_erp", "odoo_mock", "rest_mock"]
    archive = {**_empty_source("archive_source"),
               "canonical_records": {**dict.fromkeys(ENTITY_MODELS, 0), "customers": 1}}
    legacy_last = _reference(legacy_high, "NOOP", T0, T0 + timedelta(milliseconds=50))
    legacy = {
        **_empty_source("legacy_erp"), "runs_total": 3,
        "runs_by_status": {**dict.fromkeys(STATUSES, 0), "NOOP": 2, "SUCCESS": 1},
        "records_raw_persisted_total": 1, "ingestion_duration_seconds_total": 0.3,
        "errors_by_severity": {"ERROR": 1, "WARNING": 0, "INFO": 0},
        "validation_errors_total": 1,
        "last_run": legacy_last, "last_successful_run": legacy_last,
    }
    rest = {
        **_empty_source("rest_mock"), "runs_total": 3,
        "runs_by_status": {**dict.fromkeys(STATUSES, 0), "RUNNING": 1, "SUCCESS": 1,
                           "FAILED": 1},
        "records_fetched_total": 15, "records_raw_persisted_total": 2,
        "records_inserted_total": 9, "records_updated_total": 2, "records_unchanged_total": 1,
        "records_rejected_total": 1, "records_failed_total": 2, "warnings_total": 3,
        "batches_failed_total": 2, "errors_by_severity": {"ERROR": 5, "WARNING": 1, "INFO": 1},
        "connector_request_failures_total": 2, "validation_errors_total": 1,
        "ingestion_duration_seconds_total": 120.0,
        "canonical_records": {**dict.fromkeys(ENTITY_MODELS, 0), "customers": 2},
        "last_run": _reference(running, "RUNNING", T0 + timedelta(minutes=10), None),
        "last_successful_run": _reference(done, "SUCCESS", T0, T0 + timedelta(seconds=90)),
    }
    assert [_parsed(source) for source in body["sources"]] == [
        archive, _empty_source("csv_demo"), legacy, _empty_source("odoo_mock"), rest]
    _assert_totals_are_sums_over_sources(body)
    assert body["totals"]["ingestion_duration_seconds_total"] == 120.3
    assert body["totals"]["runs_by_status"] == {"RUNNING": 1, "SUCCESS": 2, "PARTIAL_SUCCESS": 0,
                                                "FAILED": 1, "NOOP": 2}
    assert (body["totals"]["errors_by_severity"], body["totals"]["canonical_records"]["customers"]) \
        == ({"ERROR": 6, "WARNING": 1, "INFO": 1}, 3)
    assert body["totals"]["validation_errors_total"] == 2


# --- read-only, deterministic, constant cost -------------------------------------------


def _statements(engine, client) -> int:
    executed: list[str] = []

    def count(conn, cursor, statement, parameters, context, executemany):
        executed.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        assert client.get(METRICS).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", count)
    return len(executed)


def test_metrics_are_read_only_repeatable_and_constant_cost(client, e1_engine, e1_sessions):
    empty = _statements(e1_engine, client)
    _ingest(e1_sessions, DEMO_DIR, T0)
    _ingest(e1_sessions, BAD_FIXTURE_DIR, T0 + timedelta(hours=1))
    assert empty == _statements(e1_engine, client) == 12

    def table_counts() -> dict[str, int]:
        with e1_sessions() as session:
            return {model.__tablename__: session.execute(
                select(func.count()).select_from(model)).scalar_one()
                for model in (IngestionRun, IngestionError, SourceRecord, *ENTITY_MODELS.values())}

    before = table_counts()
    first, second = _metrics(client), _metrics(client)
    assert first == second
    assert table_counts() == before
