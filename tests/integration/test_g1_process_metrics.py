"""
G1 in-process ingestion counters: the "process" block of GET /api/v1/metrics/ingestion.

Runs started through POST /api/v1/ingestion/runs update the counters of the
application that executed them, at the points where E1 commits; for an API
process that ran every ingestion against an empty database they equal the
database-derived totals. Counters start at zero with each application
(process restart), ignore runs executed elsewhere, and leave the
database-derived metrics unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from e1_support import NOW, csv_row
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.v1 import metrics as metrics_route
from app.connectors import (
    ConnectorCapabilities,
    ConnectorHealth,
    ConnectorUnavailableError,
    Page,
)
from app.connectors.registry import build_connector
from app.ingestion import orchestrator
from app.ingestion.errors import ConnectorContractError
from app.ingestion.orchestrator import ENTITY_ORDER, IngestionRequest, run_ingestion
from app.main import create_app
from app.observability.metrics import ProcessMetrics
from app.persistence.models import IngestionRun
from app.persistence.repositories.runs import RunStatus

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
BAD_FIXTURE_DIR = REPO / "data" / "fixtures" / "csv_demo_bad"
METRICS = "/api/v1/metrics/ingestion"
RUNS = "/api/v1/ingestion/runs"
STARTED = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
STATUSES = [status.value for status in RunStatus]
# Process counters and the database-derived totals that share their definition.
SHARED = ("records_fetched_total", "records_inserted_total", "records_updated_total",
          "records_unchanged_total", "records_rejected_total",
          "connector_request_failures_total", "validation_errors_total")


class Sources:
    """A connector provider for csv_demo whose connector is chosen per test step."""

    source_names = ("csv_demo",)

    def __init__(self, connector) -> None:
        self.connector = connector

    def get(self, source: str):
        return self.connector


class Connector:
    """In-memory csv_demo connector; page_factory replaces the pages when given."""

    source_type = "fake"

    def __init__(self, pages, *, page_factory=None, on_fetch=None):
        self.pages = pages
        self.page_factory = page_factory
        self.on_fetch = on_fetch

    @property
    def source_name(self):
        return "csv_demo"

    def health_check(self):
        return ConnectorHealth(healthy=True, source_name="csv_demo")

    def list_entities(self):
        return []

    def fetch_entities(self, entity_type, cursor=None, page_size=100):
        if self.on_fetch is not None:
            self.on_fetch()
        if self.page_factory is not None:
            return self.page_factory()
        index = int(cursor or 0)
        pages = self.pages.get(entity_type, [[]])
        has_more = index + 1 < len(pages)
        return Page(items=list(pages[index]), next_cursor=str(index + 1) if has_more else None,
                    has_more=has_more)

    def get_entity(self, entity_type, source_id):
        raise NotImplementedError

    def capabilities(self):
        return ConnectorCapabilities(supported_entity_types=sorted(ENTITY_ORDER))


class Recorder:
    """A RunObserver that records every notification in order."""

    def __init__(self):
        self.calls: list[tuple] = []

    def run_started(self):
        self.calls.append(("run_started",))

    def batch_committed(self, counts):
        self.calls.append(("batch_committed", counts))

    def batch_failed(self, records):
        self.calls.append(("batch_failed", records))

    def connector_failed(self):
        self.calls.append(("connector_failed",))

    def run_finished(self, status, duration_seconds):
        self.calls.append(("run_finished", RunStatus(status), duration_seconds))


def _unavailable() -> None:
    raise ConnectorUnavailableError("source down at a private host")


def _csv(directory: Path):
    return build_connector("csv_demo", data_directory=directory)


def _app(e1_sessions, connector=None, started=STARTED):
    sources = Sources(_csv(DEMO_DIR) if connector is None else connector)
    metrics = ProcessMetrics(clock=lambda: started)
    client = TestClient(create_app(sessions=e1_sessions, connectors=sources,
                                   process_metrics=metrics), raise_server_exceptions=False)
    return client, sources, metrics


def _metrics(client) -> dict:
    response = client.get(METRICS)
    assert response.status_code == 200, response.text
    return response.json()


def _zero_process(started: datetime = STARTED) -> dict:
    return {
        "started_at": started.isoformat().replace("+00:00", "Z"), "runs_total": 0,
        "runs_by_status": dict.fromkeys(STATUSES, 0), **dict.fromkeys(SHARED, 0),
        "ingestion_duration_seconds": {"count": 0, "sum": 0.0},
    }


def _start(client, status_code=201, **body) -> dict:
    response = client.post(RUNS, json={"source": "csv_demo", **body})
    assert response.status_code == status_code, response.text
    return response.json()


def _assert_process_matches_database(body: dict) -> None:
    process, totals = body["process"], body["totals"]
    for name in SHARED:
        assert process[name] == totals[name], name
    assert process["runs_by_status"] == totals["runs_by_status"]
    assert process["runs_total"] == totals["runs_total"]
    assert process["ingestion_duration_seconds"]["sum"] == pytest.approx(
        totals["ingestion_duration_seconds_total"])


# --- lifecycle -----------------------------------------------------------------------------


def test_a_new_application_reports_zero_counters_from_its_start(e1_sessions):
    client, _, _ = _app(e1_sessions)
    assert _metrics(client)["process"] == _zero_process()


def test_the_default_start_time_is_application_creation(e1_sessions):
    before = datetime.now(UTC)
    client = TestClient(create_app(sessions=e1_sessions, connectors=Sources(_csv(DEMO_DIR))))
    after = datetime.now(UTC)
    started = datetime.fromisoformat(_metrics(client)["process"]["started_at"])
    assert before <= started <= after


# --- counting real runs -------------------------------------------------------------------


def test_api_runs_are_counted_as_the_database_records_them(e1_sessions):
    client, sources, _ = _app(e1_sessions)
    reports = [_start(client)]
    reports.append(_start(client))
    sources.connector = _csv(BAD_FIXTURE_DIR)
    reports.append(_start(client))
    sources.connector = _csv(REPO / "data" / "missing-directory")
    reports.append(_start(client))
    assert [report["status"] for report in reports] == [
        "SUCCESS", "NOOP", "PARTIAL_SUCCESS", "FAILED"]

    body = _metrics(client)
    process = body["process"]
    assert process["runs_by_status"] == {**dict.fromkeys(STATUSES, 0), "SUCCESS": 1, "NOOP": 1,
                                         "PARTIAL_SUCCESS": 1, "FAILED": 1}
    assert process["runs_total"] == 4
    for name, key in (("records_fetched_total", "records_fetched"),
                      ("records_inserted_total", "records_inserted"),
                      ("records_updated_total", "records_updated"),
                      ("records_unchanged_total", "records_unchanged"),
                      ("records_rejected_total", "records_rejected")):
        assert process[name] == sum(report[key] for report in reports), name
    assert (process["validation_errors_total"], process["connector_request_failures_total"]) == (
        3, 1)
    with e1_sessions() as session:
        durations = [(run.finished_at - run.started_at).total_seconds()
                     for run in session.scalars(select(IngestionRun))]
    assert process["ingestion_duration_seconds"] == {"count": 4,
                                                     "sum": round(sum(durations), 6)}
    _assert_process_matches_database(body)


def test_a_failed_batch_counts_its_records_as_fetched_only(e1_sessions):
    client, _, _ = _app(e1_sessions, Connector({
        "customers": [[csv_row("customers", customer_name="N" * 300)]]}))
    assert _start(client, entities=["customers"])["status"] == "FAILED"
    body = _metrics(client)
    assert (body["process"]["records_fetched_total"], body["process"]["records_inserted_total"],
            body["process"]["runs_by_status"]["FAILED"]) == (1, 0, 1)
    _assert_process_matches_database(body)


def test_a_system_failure_counts_one_failed_run_with_its_duration(e1_sessions):
    client, _, _ = _app(e1_sessions, Connector({}, page_factory=lambda: {"items": []}))
    assert client.post(RUNS, json={"source": "csv_demo", "entities": ["customers"]}) \
        .status_code == 500
    body = _metrics(client)
    assert body["process"]["runs_by_status"] == {**dict.fromkeys(STATUSES, 0), "FAILED": 1}
    assert body["process"]["ingestion_duration_seconds"]["count"] == 1
    _assert_process_matches_database(body)


def test_runs_in_progress_are_running(e1_sessions):
    seen = []
    metrics = ProcessMetrics(clock=lambda: STARTED)

    def observe() -> None:
        process = metrics_route._process(metrics)
        seen.append((process.runs_total, process.runs_by_status.model_dump(),
                     process.ingestion_duration_seconds.count))

    connector = Connector({"customers": [[csv_row("customers")]]}, on_fetch=observe)
    client = TestClient(create_app(sessions=e1_sessions, connectors=Sources(connector),
                                   process_metrics=metrics))
    _start(client, entities=["customers"])
    assert seen == [(1, {**dict.fromkeys(STATUSES, 0), "RUNNING": 1}, 0)]
    assert _metrics(client)["process"]["runs_by_status"] == {**dict.fromkeys(STATUSES, 0),
                                                             "SUCCESS": 1}


def test_a_failed_page_fetch_is_a_connector_request_failure(e1_sessions):
    client, _, _ = _app(e1_sessions, Connector({}, on_fetch=_unavailable))
    assert _start(client, entities=["customers"])["status"] == "FAILED"
    body = _metrics(client)
    assert (body["process"]["connector_request_failures_total"],
            body["process"]["runs_by_status"]["FAILED"]) == (1, 1)
    _assert_process_matches_database(body)


@pytest.mark.parametrize("body", [
    {"dry_run": True}, {"entities": ["customers"], "mode": "incremental"},
    {"source": "unknown_source"}, {"page_size": 0},
])
def test_rejected_requests_count_nothing(e1_sessions, body):
    client, _, _ = _app(e1_sessions)
    assert client.post(RUNS, json={"source": "csv_demo", **body}).status_code == 422
    assert _metrics(client)["process"] == _zero_process()


# --- scope: this process only ----------------------------------------------------------------


def test_a_restarted_application_starts_again_at_zero_and_the_database_is_unchanged(e1_sessions):
    first, _, _ = _app(e1_sessions)
    _start(first)
    before = _metrics(first)
    restarted, _, _ = _app(e1_sessions, started=STARTED + timedelta(hours=1))
    after = _metrics(restarted)
    assert after["process"] == _zero_process(STARTED + timedelta(hours=1))
    assert (after["totals"], after["sources"]) == (before["totals"], before["sources"])
    assert _metrics(first) == before


def test_runs_executed_outside_this_application_are_not_counted(e1_sessions):
    client, _, _ = _app(e1_sessions)
    run_ingestion(_csv(DEMO_DIR), e1_sessions, clock=lambda: NOW)
    body = _metrics(client)
    assert body["process"] == _zero_process()
    assert body["totals"]["runs_total"] == 1 and body["totals"]["records_inserted_total"] > 0


def test_metrics_requests_are_repeatable_and_count_nothing(e1_sessions):
    client, _, _ = _app(e1_sessions)
    _start(client)
    first, second = _metrics(client), _metrics(client)
    assert first == second
    assert first["process"]["runs_total"] == 1


# --- the E1 observer contract ----------------------------------------------------------------


def test_the_observer_is_told_about_each_committed_batch_and_the_finish(e1_sessions):
    recorder = Recorder()
    pages = {"customers": [[csv_row("customers"),
                            csv_row("customers", customer_id="CUST-002", status="bogus")],
                           [csv_row("customers", customer_id="CUST-003",
                                    customer_name="Third Co", email_address="t@example.com")]]}
    summary = run_ingestion(Connector(pages), e1_sessions,
                            IngestionRequest(entities=["customers"], page_size=2),
                            clock=lambda: NOW, observer=recorder)
    names = [call[0] for call in recorder.calls]
    assert names == ["run_started", "batch_committed", "batch_committed", "run_finished"]
    assert [call[1] for call in recorder.calls[1:3]] == [
        orchestrator.runs.RunCounts(fetched=2, inserted=1, rejected=1),
        orchestrator.runs.RunCounts(fetched=1, inserted=1)]
    assert recorder.calls[-1] == ("run_finished", RunStatus.PARTIAL_SUCCESS,
                                  (summary.finished_at - summary.started_at).total_seconds())


def test_the_observer_hears_connector_failures_once_each(e1_sessions):
    recorder = Recorder()
    run_ingestion(_csv(REPO / "data" / "missing-directory"), e1_sessions,
                  clock=lambda: NOW, observer=recorder)
    assert recorder.calls == [("run_started",), ("connector_failed",),
                              ("run_finished", RunStatus.FAILED, 0.0)]


def test_the_observer_hears_a_failed_page_fetch(e1_sessions):
    recorder = Recorder()
    run_ingestion(Connector({}, on_fetch=_unavailable), e1_sessions,
                  IngestionRequest(entities=["customers"]), clock=lambda: NOW, observer=recorder)
    assert recorder.calls == [("run_started",), ("connector_failed",),
                              ("run_finished", RunStatus.FAILED, 0.0)]


def test_a_failed_batch_is_reported_with_its_record_count(e1_sessions):
    recorder = Recorder()
    run_ingestion(Connector({"customers": [[csv_row("customers", customer_name="N" * 300),
                                            csv_row("customers", customer_id="CUST-002")]]}),
                  e1_sessions, IngestionRequest(entities=["customers"]), clock=lambda: NOW,
                  observer=recorder)
    assert recorder.calls == [("run_started",), ("batch_failed", 2),
                              ("run_finished", RunStatus.FAILED, 0.0)]


def test_a_system_failure_finishes_the_run_once_even_if_marking_it_failed_fails(
        e1_sessions, monkeypatch):
    recorder = Recorder()

    def unavailable(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(orchestrator.runs, "finish_run", unavailable)
    moments = iter([NOW, NOW + timedelta(seconds=1), NOW + timedelta(seconds=2),
                    NOW + timedelta(seconds=3)])
    with pytest.raises(RuntimeError, match="database unavailable"):
        run_ingestion(Connector({"customers": [[csv_row("customers")]]}), e1_sessions,
                      IngestionRequest(entities=["customers"]), clock=lambda: next(moments),
                      observer=recorder)
    assert [call[0] for call in recorder.calls] == ["run_started", "batch_committed",
                                                    "run_finished"]
    assert recorder.calls[-1] == ("run_finished", RunStatus.FAILED, 3.0)


def test_a_contract_failure_reports_a_failed_finish(e1_sessions):
    recorder = Recorder()
    with pytest.raises(ConnectorContractError):
        run_ingestion(Connector({}, page_factory=lambda: {"items": []}), e1_sessions,
                      IngestionRequest(entities=["customers"]), clock=lambda: NOW,
                      observer=recorder)
    assert recorder.calls == [("run_started",), ("run_finished", RunStatus.FAILED, 0.0)]


def test_invalid_requests_notify_nothing(e1_sessions):
    recorder = Recorder()
    with pytest.raises(orchestrator.IngestionRequestError):
        run_ingestion(Connector({}), e1_sessions, IngestionRequest(entities=["invoices"]),
                      clock=lambda: NOW, observer=recorder)
    assert recorder.calls == []
