"""
POST /api/v1/ingestion/runs against the migrated test database.

Runs execute synchronously through E1: the response is the completed run.
Requests that are invalid, unsupported or name an unknown source create no run.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Iterator
from http.server import HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.connectors import ConnectorProvider
from app.api.v1.schemas import EntityType, IngestionRunRequest
from app.connectors import (
    ConnectorCapabilities,
    ConnectorConfigurationError,
    ConnectorHealth,
    CsvConnector,
    CsvConnectorConfig,
    registry,
)
from app.ingestion.orchestrator import ENTITY_ORDER
from app.main import create_app
from app.persistence.models import (
    Customer,
    Deal,
    Document,
    Employee,
    IngestionRun,
    Organization,
    Project,
    SupportTicket,
)

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
BAD_FIXTURE_DIR = REPO / "data" / "fixtures" / "csv_demo_bad"
RUNS = "/api/v1/ingestion/runs"
SOURCES = ("csv_demo", "odoo_mock", "rest_mock")
MODELS = {"organizations": Organization, "employees": Employee, "customers": Customer,
          "deals": Deal, "projects": Project, "support_tickets": SupportTicket,
          "documents": Document}
DEMO_COUNTS = {"organizations": 1, "employees": 24, "customers": 50, "deals": 44, "projects": 22,
               "support_tickets": 80, "documents": 12}

sys.path.insert(0, str(REPO / "docker"))
import mock_source  # noqa: E402


def _client(sessions, build=registry.build_connector, sources=SOURCES) -> TestClient:
    app = create_app(sessions=sessions, connectors=ConnectorProvider(build, sources))
    return TestClient(app, raise_server_exceptions=False)


def _csv_from(directory: Path):
    return lambda source: registry.build_connector(source, data_directory=directory)


def _table_counts(sessions) -> dict[str, int]:
    with sessions() as session:
        return {entity: session.scalar(select(func.count()).select_from(model))
                for entity, model in MODELS.items()}


def _run_count(sessions) -> int:
    with sessions() as session:
        return session.scalar(select(func.count()).select_from(IngestionRun))


def _entity(entity_type: str, fetched: int, **overrides) -> dict[str, object]:
    return {"entity_type": entity_type, "status": "completed", "records_fetched": fetched,
            "records_inserted": fetched, "records_updated": 0, "records_unchanged": 0,
            "records_rejected": 0, "records_failed": 0, "warnings": 0,
            "batches_committed": 1, "batches_failed": 0, "failure": None, **overrides}


class ContractBreakingConnector:
    """Healthy connector whose fetch_entities violates the Page contract."""

    source_name = "csv_demo"
    source_type = "csv"

    def health_check(self):
        return ConnectorHealth(healthy=True, source_name="csv_demo")

    def list_entities(self):
        return []

    def fetch_entities(self, entity_type, cursor=None, page_size=100):
        return {"items": []}

    def get_entity(self, entity_type, source_id):
        return {}

    def capabilities(self):
        return ConnectorCapabilities(supported_entity_types=["customers"])


@pytest.fixture(scope="module")
def mock_source_url() -> Iterator[str]:
    previous = dict(mock_source.ODOO_DATA), dict(mock_source.REST_DATA)
    odoo, rest = mock_source.load_source_data(DEMO_DIR)
    mock_source.ODOO_DATA.update(odoo)
    mock_source.REST_DATA.update(rest)
    server = HTTPServer(("127.0.0.1", 0), mock_source.MockSourceHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        for store, saved in zip((mock_source.ODOO_DATA, mock_source.REST_DATA), previous,
                                strict=True):
            store.clear()
            store.update(saved)


# --- successful runs ---------------------------------------------------------


def test_demo_ingestion_returns_201_with_the_completed_run(e1_sessions):
    client = _client(e1_sessions)
    response = client.post(RUNS, json={"source": "csv_demo"})
    assert response.status_code == 201
    body = response.json()
    assert response.headers["location"] == f"{RUNS}/{body['run_id']}"
    assert {key: body[key] for key in (
        "source_system", "source_entity", "mode", "status", "records_fetched",
        "records_raw_persisted", "records_inserted", "records_updated", "records_unchanged",
        "records_rejected", "records_failed", "warnings", "batches_committed",
        "batches_failed", "error_summary")} == {
        "source_system": "csv_demo", "source_entity": None, "mode": "full", "status": "SUCCESS",
        "records_fetched": 233, "records_raw_persisted": 233, "records_inserted": 233,
        "records_updated": 0, "records_unchanged": 0, "records_rejected": 0,
        "records_failed": 0, "warnings": 0, "batches_committed": 7, "batches_failed": 0,
        "error_summary": None}
    assert body["finished_at"] is not None
    assert body["entities"] == [_entity(entity, DEMO_COUNTS[entity]) for entity in ENTITY_ORDER]
    assert _table_counts(e1_sessions) == DEMO_COUNTS

    detail = client.get(response.headers["location"]).json()
    assert detail == {key: value for key, value in body.items()
                      if key not in ("batches_committed", "entities")}


def test_repeating_the_request_is_a_noop_without_duplicates(e1_sessions):
    client = _client(e1_sessions)
    assert client.post(RUNS, json={"source": "csv_demo"}).status_code == 201
    again = client.post(RUNS, json={"source": "csv_demo", "mode": "full", "dry_run": False})
    assert again.status_code == 201
    body = again.json()
    assert (body["status"], body["records_inserted"], body["records_updated"],
            body["records_unchanged"]) == ("NOOP", 0, 0, 233)
    assert body["entities"] == [
        _entity(entity, DEMO_COUNTS[entity], records_inserted=0,
                records_unchanged=DEMO_COUNTS[entity])
        for entity in ENTITY_ORDER]
    assert _table_counts(e1_sessions) == DEMO_COUNTS
    assert client.get(RUNS).json()["total"] == 2


def test_requested_entities_run_in_dependency_order_with_the_page_size(e1_sessions):
    body = _client(e1_sessions).post(RUNS, json={
        "source": "csv_demo", "entities": ["deals", "customers"], "page_size": 25}).json()
    assert body["source_entity"] is None
    assert [(e["entity_type"], e["records_fetched"], e["batches_committed"])
            for e in body["entities"]] == [("customers", 50, 2), ("deals", 44, 2)]
    assert _table_counts(e1_sessions) == {**dict.fromkeys(DEMO_COUNTS, 0),
                                          "customers": 50, "deals": 44}


def test_a_single_entity_run_records_its_entity(e1_sessions):
    body = _client(e1_sessions).post(RUNS, json={"source": "csv_demo",
                                                 "entities": ["customers"]}).json()
    assert (body["source_entity"], body["records_inserted"]) == ("customers", 50)


@pytest.mark.parametrize("source", ["odoo_mock", "rest_mock"])
def test_http_sources_ingest_through_the_same_route(e1_sessions, mock_source_url, source):
    client = _client(e1_sessions,
                     lambda name: registry.build_connector(name, base_url=mock_source_url))
    body = client.post(RUNS, json={"source": source}).json()
    assert (body["source_system"], body["status"], body["records_inserted"]) == (
        source, "SUCCESS", 233)


def test_bad_fixture_is_partial_success_without_source_values(e1_sessions):
    response = _client(e1_sessions, _csv_from(BAD_FIXTURE_DIR)).post(
        RUNS, json={"source": "csv_demo"})
    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["records_fetched"], body["records_inserted"],
            body["records_unchanged"], body["records_rejected"], body["warnings"],
            body["error_summary"]) == ("PARTIAL_SUCCESS", 8, 4, 1, 3, 3, "3 records rejected")
    assert [entity for entity in body["entities"] if entity["records_fetched"]] == [
        _entity("customers", 4, records_inserted=2, records_unchanged=1, records_rejected=1,
                warnings=2),
        _entity("deals", 4, records_inserted=2, records_rejected=2, warnings=1),
    ]
    for value in ("suspended", "12,50,000.00", "31/12/2026", "CUST-999", "raw_record",
                  "raw_value"):
        assert value not in response.text


def test_a_failed_health_check_is_reported_as_a_failed_run(e1_sessions, tmp_path):
    response = _client(e1_sessions, _csv_from(tmp_path / "missing")).post(
        RUNS, json={"source": "csv_demo"})
    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["records_fetched"], body["error_summary"]) == (
        "FAILED", 0, "connector health check failed; 7 entities skipped")
    assert {entity["status"] for entity in body["entities"]} == {"skipped"}
    assert str(tmp_path) not in response.text


# --- rejected requests create no run -----------------------------------------


def test_dry_run_is_rejected_as_unsupported(e1_sessions):
    response = _client(e1_sessions).post(RUNS, json={"source": "csv_demo", "dry_run": True})
    assert response.status_code == 422
    error = response.json()["error"]
    assert (error["code"], error["message"], error["details"]) == (
        "UNSUPPORTED_OPTION",
        "dry_run is not supported: every Layer 1 ingestion run persists its results",
        {"option": "dry_run"})
    assert _run_count(e1_sessions) == 0


@pytest.mark.parametrize("body", [
    {},
    {"source": ""},
    {"source": 5},
    {"source": "csv_demo", "mode": "incremental"},
    {"source": "csv_demo", "entities": ["invoices"]},
    {"source": "csv_demo", "entities": []},
    {"source": "csv_demo", "entities": "customers"},
    {"source": "csv_demo", "page_size": 0},
    {"source": "csv_demo", "page_size": 10_001},
    {"source": "csv_demo", "page_size": "10"},
    {"source": "csv_demo", "page_size": 1.5},
    {"source": "csv_demo", "dry_run": "yes"},
    {"source": "csv_demo", "dry_run": 1},
    {"source": "csv_demo", "base_url": "http://attacker.example"},
    {"source": "csv_demo", "data_directory": "/etc"},
])
def test_invalid_bodies_are_rejected_without_creating_a_run(e1_sessions, body):
    response = _client(e1_sessions).post(RUNS, json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert "attacker.example" not in response.text
    assert _run_count(e1_sessions) == 0


def test_a_non_json_body_is_rejected(e1_sessions):
    response = _client(e1_sessions).post(RUNS, content=b"source=csv_demo",
                                         headers={"content-type": "application/json"})
    assert (response.status_code, response.json()["error"]["code"]) == (422, "INVALID_REQUEST")
    assert _run_count(e1_sessions) == 0


def test_an_unknown_source_is_rejected_without_echoing_it(e1_sessions):
    response = _client(e1_sessions).post(RUNS, json={"source": "salesforce-xyz"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert (error["code"], error["message"], error["details"]) == (
        "SOURCE_NOT_FOUND", "source is not configured", {"available_sources": list(SOURCES)})
    assert "salesforce-xyz" not in response.text
    assert _run_count(e1_sessions) == 0


def test_entities_the_source_cannot_provide_are_rejected(e1_sessions, tmp_path):
    def build(source):
        return CsvConnector(CsvConnectorConfig.from_dict({
            "source_name": "csv_demo", "data_directory": str(DEMO_DIR),
            "entities": {"customers": {"file": "customers.csv", "id_column": "customer_id"}},
        }))

    response = _client(e1_sessions, build).post(RUNS, json={"source": "csv_demo",
                                                            "entities": ["deals"]})
    assert response.status_code == 422
    error = response.json()["error"]
    assert (error["code"], error["message"], error["details"]) == (
        "INVALID_INGESTION_REQUEST", "ingestion request is not valid for this source",
        {"source": "csv_demo",
         "reason": "entity types ['deals'] are not available from 'csv_demo'"})
    assert _run_count(e1_sessions) == 0


def test_a_misconfigured_source_creates_no_run(e1_sessions):
    def build(source):
        raise ConnectorConfigurationError("broken at /private/path", source_name=source)

    response = _client(e1_sessions, build).post(RUNS, json={"source": "rest_mock"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "SOURCE_MISCONFIGURED"
    assert "/private/path" not in response.text
    assert _run_count(e1_sessions) == 0


def test_a_system_failure_returns_a_generic_error_and_the_run_is_failed(e1_sessions, caplog):
    client = _client(e1_sessions, lambda source: ContractBreakingConnector())
    with caplog.at_level(logging.ERROR, logger="app.api.errors"):
        response = client.post(RUNS, json={"source": "csv_demo"},
                               headers={"X-Request-ID": "req-system"})
    assert response.status_code == 500
    assert response.json()["error"] == {"code": "INTERNAL_ERROR",
                                        "message": "internal server error", "details": None,
                                        "request_id": "req-system"}
    assert any(record.getMessage().endswith("failure=ConnectorContractError")
               for record in caplog.records)
    runs = client.get(RUNS).json()["items"]
    assert [(run["status"], run["error_summary"]) for run in runs] == [
        ("FAILED", "run aborted by system failure: ConnectorContractError")]


# --- observability and contract ----------------------------------------------


def test_request_entity_types_are_exactly_the_e1_entity_order():
    assert [entity.value for entity in EntityType] == list(ENTITY_ORDER)
    assert IngestionRunRequest(source="csv_demo").model_dump() == {
        "source": "csv_demo", "entities": None, "mode": "full", "dry_run": False,
        "page_size": 100}


def test_the_request_id_is_logged_with_the_run_id(e1_sessions, caplog):
    client = _client(e1_sessions)
    with caplog.at_level(logging.INFO, logger="app.api.v1.ingestion"):
        body = client.post(RUNS, json={"source": "csv_demo", "entities": ["customers"]},
                           headers={"X-Request-ID": "req-7"}).json()
    assert [record.getMessage() for record in caplog.records] == [
        "ingestion_run_requested request_id=req-7 source=csv_demo entities=customers",
        f"ingestion_run_finished request_id=req-7 run_id={body['run_id']} status=SUCCESS",
    ]


def test_all_entities_are_logged_as_all(e1_sessions, tmp_path, caplog):
    client = _client(e1_sessions, _csv_from(tmp_path / "missing"))
    with caplog.at_level(logging.INFO, logger="app.api.v1.ingestion"):
        client.post(RUNS, json={"source": "csv_demo"}, headers={"X-Request-ID": "req-8"})
    assert caplog.records[0].getMessage() == (
        "ingestion_run_requested request_id=req-8 source=csv_demo entities=all")


def test_openapi_documents_the_ingestion_trigger(e1_sessions):
    spec = create_app(sessions=e1_sessions).openapi()
    operation = spec["paths"][RUNS]["post"]
    responses = operation["responses"]

    def schema(status):
        return responses[status]["content"]["application/json"]["schema"]

    assert set(responses) == {"201", "422", "500"}
    assert schema("201") == {"$ref": "#/components/schemas/IngestionRunCreatedResponse"}
    assert schema("422") == schema("500") == {"$ref": "#/components/schemas/ErrorResponse"}
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/IngestionRunRequest"}
    request = spec["components"]["schemas"]["IngestionRunRequest"]
    assert set(request["properties"]) == {"source", "entities", "mode", "dry_run", "page_size"}
    assert request["required"] == ["source"]
    assert request["additionalProperties"] is False
    assert request["properties"]["dry_run"]["default"] is False
