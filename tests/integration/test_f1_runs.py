"""
GET /api/v1/ingestion/runs, /runs/{run_id} and /runs/{run_id}/errors against the test database.

Runs are produced by real E1 ingestions of the committed demo data and the E2
bad fixture; derived counts are also checked on runs written through the E1
repositories.
"""

from __future__ import annotations

import csv
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from e1_support import CSV_ROWS, csv_row
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text

from app.api.dependencies import read_snapshot
from app.api.ingestion_errors import SAFE_MESSAGES
from app.connectors.registry import build_connector
from app.ingestion.orchestrator import IngestionRequest, RunSummary, run_ingestion
from app.main import create_app
from app.persistence.models import IngestionError
from app.persistence.repositories import errors, runs

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
BAD_FIXTURE_DIR = REPO / "data" / "fixtures" / "csv_demo_bad"
T0 = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)
RUNS = "/api/v1/ingestion/runs"
# Source values present in the persisted diagnostics of the bad fixture.
FORBIDDEN = ("suspended", "12,50,000.00", "31/12/2026", "CUST-999", "raw_record", "raw_value")
UNRESOLVED_MESSAGE = ("customer_source_id does not resolve to a customers record from this "
                      "source system; customer_id left null")


def _ingest(sessions, directory: Path, at: datetime, entities=None) -> RunSummary:
    return run_ingestion(build_connector("csv_demo", data_directory=directory), sessions,
                         IngestionRequest(entities=entities), clock=lambda: at)


@pytest.fixture
def client(e1_sessions):
    return TestClient(create_app(sessions=e1_sessions), raise_server_exceptions=False)


@pytest.fixture
def history(e1_sessions, tmp_path) -> dict[str, RunSummary]:
    return {
        "demo": _ingest(e1_sessions, DEMO_DIR, T0, ["customers", "deals"]),
        "bad": _ingest(e1_sessions, BAD_FIXTURE_DIR, T0 + timedelta(hours=1)),
        "failed": _ingest(e1_sessions, tmp_path / "missing", T0 + timedelta(hours=2)),
    }


def _from_summary(summary: RunSummary) -> dict[str, object]:
    data = summary.to_dict()
    return {
        "run_id": data["run_id"], "source_system": "csv_demo", "source_entity": None,
        "mode": "full", "status": data["status"],
        "started_at": summary.started_at, "finished_at": summary.finished_at,
        **{key: data[key] for key in (
            "records_fetched", "records_raw_persisted", "records_inserted", "records_updated",
            "records_unchanged", "records_rejected", "records_failed", "warnings",
            "batches_failed", "error_summary")},
    }


def _parsed(item: dict[str, object]) -> dict[str, object]:
    return {**item, "started_at": datetime.fromisoformat(str(item["started_at"])),
            "finished_at": (None if item["finished_at"] is None
                            else datetime.fromisoformat(str(item["finished_at"])))}


def _error_envelope(response, status: int, code: str) -> dict[str, object]:
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    return error


# --- runs list and detail ----------------------------------------------------


def test_runs_list_is_empty_without_runs(client):
    response = client.get(RUNS)
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_runs_are_listed_newest_first_with_the_run_summary_counts(client, history):
    body = client.get(RUNS).json()
    assert (body["total"], body["limit"], body["offset"]) == (3, 50, 0)
    assert [_parsed(item) for item in body["items"]] == [
        _from_summary(history[name]) for name in ("failed", "bad", "demo")]
    demo = body["items"][2]
    assert (demo["status"], demo["records_fetched"], demo["records_raw_persisted"],
            demo["records_inserted"], demo["records_failed"], demo["batches_failed"]) == (
        "SUCCESS", 94, 94, 94, 0, 0)
    bad = body["items"][1]
    assert (bad["status"], bad["records_fetched"], bad["records_inserted"],
            bad["records_unchanged"], bad["records_rejected"], bad["warnings"]) == (
        "PARTIAL_SUCCESS", 8, 4, 1, 3, 3)
    assert body["items"][0]["status"] == "FAILED"


@pytest.mark.parametrize("name", ["demo", "bad", "failed"])
def test_run_detail_matches_the_run_summary(client, history, name):
    summary = history[name]
    response = client.get(f"{RUNS}/{summary.run_id}")
    assert response.status_code == 200
    assert _parsed(response.json()) == _from_summary(summary)


@pytest.mark.parametrize(("query", "expected"), [
    ({"status": "FAILED"}, ["failed"]),
    ({"status": "PARTIAL_SUCCESS"}, ["bad"]),
    ({"status": "NOOP"}, []),
    ({"source_system": "csv_demo"}, ["failed", "bad", "demo"]),
    ({"source_system": "odoo_mock"}, []),
    ({"source_system": "csv_demo", "status": "SUCCESS"}, ["demo"]),
])
def test_runs_can_be_filtered_by_source_system_and_status(client, history, query, expected):
    body = client.get(RUNS, params=query).json()
    assert [item["run_id"] for item in body["items"]] == [
        str(history[name].run_id) for name in expected]
    assert body["total"] == len(expected)


@pytest.mark.parametrize(("query", "expected", "limit", "offset"), [
    ({"limit": 1}, ["failed"], 1, 0),
    ({"limit": 1, "offset": 1}, ["bad"], 1, 1),
    ({"limit": 2, "offset": 2}, ["demo"], 2, 2),
    ({"offset": 3}, [], 50, 3),
    ({"limit": 500}, ["failed", "bad", "demo"], 500, 0),
])
def test_runs_are_paginated_with_limit_and_offset(client, history, query, expected, limit, offset):
    body = client.get(RUNS, params=query).json()
    assert [item["run_id"] for item in body["items"]] == [
        str(history[name].run_id) for name in expected]
    assert (body["total"], body["limit"], body["offset"]) == (3, limit, offset)


@pytest.mark.parametrize("query", [
    {"status": "DONE"}, {"status": "success"}, {"limit": 0}, {"limit": 501}, {"offset": -1},
    {"offset": 2_147_483_648}, {"limit": "many"}, {"source_system": ""},
    {"source_system": "x" * 101},
])
def test_invalid_run_list_parameters_are_rejected(client, query):
    error = _error_envelope(client.get(RUNS, params=query), 422, "INVALID_REQUEST")
    assert error["details"]


def test_unknown_and_malformed_run_ids(client, history):
    missing = uuid.uuid4()
    for path in (f"{RUNS}/{missing}", f"{RUNS}/{missing}/errors"):
        error = _error_envelope(client.get(path), 404, "RUN_NOT_FOUND")
        assert (error["message"], error["details"]) == ("ingestion run does not exist", None)
    for path in (f"{RUNS}/not-a-uuid", f"{RUNS}/not-a-uuid/errors"):
        _error_envelope(client.get(path), 422, "INVALID_REQUEST")


def test_failed_records_and_batches_are_derived_per_run(client, e1_sessions):
    running, other = uuid.uuid4(), uuid.uuid4()
    batch_failed = errors.ErrorEntry(severity="ERROR", error_code="BATCH_FAILED",
                                     message="batch 0 rolled back", source_system="csv_demo")
    with e1_sessions.begin() as session:
        runs.create_run(session, run_id=running, source_system="csv_demo",
                        source_entity="customers", mode=runs.RunMode.FULL, started_at=T0)
        runs.create_run(session, run_id=other, source_system="csv_demo", source_entity=None,
                        mode=runs.RunMode.FULL, started_at=T0 - timedelta(days=1))
        runs.add_run_counts(session, running, runs.RunCounts(
            fetched=10, inserted=3, updated=1, unchanged=1, rejected=2, warnings=4))
        errors.add_errors(session, running, [
            batch_failed, batch_failed,
            errors.ErrorEntry(severity="ERROR", error_code="CONNECTOR_FAILED", message="failed"),
        ], created_at=T0)
        errors.add_errors(session, other, [batch_failed], created_at=T0)

    detail = client.get(f"{RUNS}/{running}").json()
    assert {key: detail[key] for key in (
        "status", "source_entity", "finished_at", "records_fetched", "records_raw_persisted",
        "records_failed", "warnings", "batches_failed", "error_summary")} == {
        "status": "RUNNING", "source_entity": "customers", "finished_at": None,
        "records_fetched": 10, "records_raw_persisted": 0, "records_failed": 3, "warnings": 4,
        "batches_failed": 2, "error_summary": None}
    listed = {item["run_id"]: item["batches_failed"] for item in client.get(RUNS).json()["items"]}
    assert listed == {str(running): 2, str(other): 1}


# --- run errors --------------------------------------------------------------


def _finding(code: str, field_name: str, severity: str, message: str | None = None):
    return {"code": code, "field_name": field_name, "severity": severity,
            "message": SAFE_MESSAGES[code] if message is None else message}


BAD_FIXTURE_ERRORS = {
    ("ERROR", "UNKNOWN_ENUM_VALUE", "customers", "CUST-903"):
        [_finding("UNKNOWN_ENUM_VALUE", "status", "ERROR")],
    ("ERROR", "INVALID_DECIMAL", "deals", "DEAL-903"):
        [_finding("INVALID_DECIMAL", "amount", "ERROR")],
    ("ERROR", "INVALID_DATE", "deals", "DEAL-904"):
        [_finding("INVALID_DATE", "expected_close_date", "ERROR")],
    ("WARNING", "MISSING_RECOMMENDED_FIELD", "customers", "CUST-902"):
        [_finding("MISSING_RECOMMENDED_FIELD", "email", "WARNING")],
    ("WARNING", "DUPLICATE_SOURCE_RECORD", "customers", "CUST-901"):
        [_finding("DUPLICATE_SOURCE_RECORD", "source_id", "WARNING")],
    ("WARNING", "UNRESOLVED_REFERENCE", "deals", "DEAL-902"):
        [_finding("UNRESOLVED_REFERENCE", "customer_id", "WARNING", UNRESOLVED_MESSAGE)],
}


def test_bad_fixture_errors_expose_safe_structured_findings_only(client, history):
    response = client.get(f"{RUNS}/{history['bad'].run_id}/errors")
    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["limit"], body["offset"]) == (6, 50, 0)
    actual = {}
    for item in body["items"]:
        assert set(item) == {"id", "severity", "code", "message", "source_system",
                             "source_entity", "source_id", "created_at", "findings"}
        assert item["source_system"] == "csv_demo"
        assert datetime.fromisoformat(item["created_at"]).utcoffset() is not None
        expected_message = (UNRESOLVED_MESSAGE if item["code"] == "UNRESOLVED_REFERENCE"
                            else SAFE_MESSAGES[item["code"]])
        assert item["message"] == expected_message
        actual[(item["severity"], item["code"], item["source_entity"], item["source_id"])] = \
            item["findings"]
    assert actual == BAD_FIXTURE_ERRORS


def test_no_api_response_contains_persisted_source_values(client, history, e1_sessions):
    run_id = history["bad"].run_id
    texts = [client.get(path).text for path in (
        f"{RUNS}/{run_id}/errors", f"{RUNS}/{run_id}/errors?severity=ERROR",
        f"{RUNS}/{run_id}/errors?limit=1&offset=2", f"{RUNS}/{run_id}", RUNS)]
    for value in FORBIDDEN:
        for body in texts:
            assert value not in body, value
    # Persistence is unchanged: the full diagnostics remain stored for debugging.
    with e1_sessions() as session:
        stored = {row.source_id: row for row in session.scalars(
            select(IngestionError).where(IngestionError.ingestion_run_id == run_id))}
    assert "suspended" in stored["CUST-903"].message
    assert "31/12/2026" in stored["DEAL-904"].message
    assert "raw_record" in stored["DEAL-903"].detail
    assert "CUST-999" in stored["DEAL-902"].detail


def test_credentials_and_private_values_never_reach_error_responses(client, e1_sessions, tmp_path):
    for entity, header in CSV_ROWS.items():
        rows = []
        if entity == "customers":
            rows = [csv_row("customers", customer_id="CUST-801",
                            status="Bearer f1SyntheticCredential0000"),
                    csv_row("customers", customer_id="CUST-802",
                            status="private-status-value-7")]
        with open(tmp_path / f"{entity}.csv", "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(header))
            writer.writeheader()
            writer.writerows(rows)
    summary = _ingest(e1_sessions, tmp_path, T0)
    assert summary.counts.rejected == 2

    body = client.get(f"{RUNS}/{summary.run_id}/errors").json()
    assert [(item["code"], item["source_id"]) for item in body["items"]] and {
        item["source_id"] for item in body["items"]} == {"CUST-801", "CUST-802"}
    text_body = client.get(f"{RUNS}/{summary.run_id}/errors").text
    for value in ("f1SyntheticCredential0000", "Bearer", "private-status-value-7",
                  "raw_record", "raw_value"):
        assert value not in text_body
    with e1_sessions() as session:
        stored = session.scalars(select(IngestionError).where(
            IngestionError.source_id == "CUST-802")).one()
    assert "private-status-value-7" in stored.message


@pytest.mark.parametrize(("severity", "total"), [("ERROR", 3), ("WARNING", 3), ("INFO", 0)])
def test_errors_can_be_filtered_by_severity(client, history, severity, total):
    body = client.get(f"{RUNS}/{history['bad'].run_id}/errors",
                      params={"severity": severity}).json()
    assert body["total"] == total == len(body["items"])
    assert {item["severity"] for item in body["items"]} <= {severity}


@pytest.mark.parametrize("query", [{"severity": "FATAL"}, {"severity": "error"}, {"limit": 0},
                                   {"limit": 501}, {"offset": -1}])
def test_invalid_error_list_parameters_are_rejected(client, history, query):
    _error_envelope(client.get(f"{RUNS}/{history['bad'].run_id}/errors", params=query), 422,
                    "INVALID_REQUEST")


def test_errors_are_paginated_in_a_stable_order(client, history):
    path = f"{RUNS}/{history['bad'].run_id}/errors"
    full = [item["id"] for item in client.get(path).json()["items"]]
    assert full == [item["id"] for item in client.get(path).json()["items"]]
    pages = [client.get(path, params={"limit": 4, "offset": offset}).json()
             for offset in (0, 4, 8)]
    assert [len(page["items"]) for page in pages] == [4, 2, 0]
    assert all(page["total"] == 6 and page["limit"] == 4 for page in pages)
    assert [item["id"] for page in pages for item in page["items"]] == full


def test_run_level_errors_have_trusted_messages_and_no_findings(client, history):
    body = client.get(f"{RUNS}/{history['failed'].run_id}/errors").json()
    assert body["total"] == 1
    item = body["items"][0]
    assert (item["severity"], item["code"], item["message"], item["source_entity"],
            item["source_id"], item["findings"]) == (
        "ERROR", "CONNECTOR_UNHEALTHY",
        "connector health check failed (unhealthy); no entities were fetched", None, None, [])


def test_order_ties_are_broken_by_id(client, e1_sessions):
    low, high = uuid.UUID(int=1), uuid.UUID(int=2)
    with e1_sessions.begin() as session:
        for run_id in (low, high):
            runs.create_run(session, run_id=run_id, source_system="csv_demo", source_entity=None,
                            mode=runs.RunMode.FULL, started_at=T0)
        session.add_all([
            IngestionError(id=uuid.UUID(int=number), ingestion_run_id=low, severity="ERROR",
                           error_code="BATCH_FAILED", message="batch rolled back", created_at=at)
            for number, at in ((9, T0), (8, T0), (7, T0 + timedelta(seconds=1)),
                               (6, T0 - timedelta(seconds=1)))
        ])
    assert [item["run_id"] for item in client.get(RUNS).json()["items"]] == [str(high), str(low)]
    assert [item["id"] for item in client.get(f"{RUNS}/{low}/errors").json()["items"]] == [
        str(uuid.UUID(int=number)) for number in (6, 8, 9, 7)]


def test_a_run_without_errors_has_an_empty_error_page(client, history):
    assert client.get(f"{RUNS}/{history['demo'].run_id}/errors").json() == {
        "items": [], "total": 0, "limit": 50, "offset": 0}


# --- snapshot, query count, OpenAPI ------------------------------------------


def test_reads_use_one_read_only_repeatable_read_snapshot(e1_sessions):
    with read_snapshot(e1_sessions) as session:
        assert session.execute(text("SHOW transaction_isolation")).scalar() == "repeatable read"
        assert session.execute(text("SHOW transaction_read_only")).scalar() == "on"


def _statements(engine, client, path: str) -> int:
    executed: list[str] = []

    def count(conn, cursor, statement, parameters, context, executemany):
        executed.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        assert client.get(path).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", count)
    return len(executed)


def test_listing_runs_issues_a_constant_number_of_queries(client, e1_engine, history):
    one = _statements(e1_engine, client, f"{RUNS}?limit=1")
    three = _statements(e1_engine, client, f"{RUNS}?limit=3")
    assert one == three == 4
    assert _statements(e1_engine, client, f"{RUNS}?offset=10") == 2
    assert _statements(e1_engine, client, f"{RUNS}/{history['bad'].run_id}") == 3
    assert _statements(e1_engine, client, f"{RUNS}/{history['bad'].run_id}/errors") == 3


def test_openapi_documents_the_run_routes(e1_sessions):
    spec = create_app(sessions=e1_sessions).openapi()

    def schema(path, status):
        return spec["paths"][path]["get"]["responses"][status]["content"]["application/json"][
            "schema"]

    error = {"$ref": "#/components/schemas/ErrorResponse"}
    assert schema(RUNS, "200") == {"$ref": "#/components/schemas/RunListResponse"}
    assert schema(RUNS, "422") == error
    for path, model in ((RUNS + "/{run_id}", "IngestionRunResponse"),
                        (RUNS + "/{run_id}/errors", "ErrorListResponse")):
        assert schema(path, "200") == {"$ref": f"#/components/schemas/{model}"}
        assert schema(path, "404") == error
        assert schema(path, "422") == error
    finding = spec["components"]["schemas"]["ErrorFinding"]["properties"]
    assert set(finding) == {"code", "field_name", "severity", "message"}
