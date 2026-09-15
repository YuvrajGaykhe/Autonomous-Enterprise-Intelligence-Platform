"""
GET /api/v1/entities/{entity_type} and /{entity_type}/{id} against the test database.

Records come from real E1 ingestions of the committed demo data and the E2 bad
fixture; expected identities and values are read from the CSV files themselves.
"""

from __future__ import annotations

import csv
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import event, update

from app.connectors.registry import build_connector
from app.ingestion.orchestrator import IngestionRequest, RunSummary, run_ingestion
from app.main import create_app
from app.persistence.models import Customer

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
BAD_FIXTURE_DIR = REPO / "data" / "fixtures" / "csv_demo_bad"
CSV_ENTITIES = yaml.safe_load(
    (REPO / "config" / "connectors" / "csv_demo.yaml").read_text(encoding="utf-8"))["entities"]
T0 = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
ENTITIES = "/api/v1/entities"
TYPES = ("organizations", "employees", "customers", "deals", "projects", "support_tickets",
         "documents")
HEX64 = re.compile(r"[0-9a-f]{64}")


def _ingest(sessions, directory: Path, at: datetime) -> RunSummary:
    return run_ingestion(build_connector("csv_demo", data_directory=directory), sessions,
                         IngestionRequest(), clock=lambda: at)


def _csv_rows(directory: Path, entity: str) -> list[dict[str, str]]:
    with (directory / CSV_ENTITIES[entity]["file"]).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _csv_ids(directory: Path, entity: str) -> list[str]:
    return sorted({row[CSV_ENTITIES[entity]["id_column"]] for row in _csv_rows(directory, entity)})


def _customer(source_system: str, source_id: str) -> Customer:
    return Customer(source_system=source_system, source_entity="customers", source_id=source_id,
                    ingestion_run_id=uuid.uuid4(), record_hash="0" * 64, name="Synthetic",
                    is_active=True)


@pytest.fixture
def client(e1_sessions):
    return TestClient(create_app(sessions=e1_sessions), raise_server_exceptions=False)


@pytest.fixture
def demo(e1_sessions) -> RunSummary:
    return _ingest(e1_sessions, DEMO_DIR, T0)


def _page(client, entity: str, **params) -> dict:
    response = client.get(f"{ENTITIES}/{entity}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _all(client, entity: str, **params) -> dict:
    return _page(client, entity, limit=500, **params)


# --- listing -------------------------------------------------------------------


@pytest.mark.parametrize("entity", TYPES)
def test_an_empty_database_has_empty_pages(client, entity):
    assert _page(client, entity) == {"items": [], "total": 0, "limit": 50, "offset": 0}


@pytest.mark.parametrize("entity", TYPES)
def test_every_ingested_record_is_queryable_with_provenance(client, demo, entity):
    page = _all(client, entity)
    expected_ids = _csv_ids(DEMO_DIR, entity)
    assert page["total"] == len(page["items"]) == len(expected_ids)
    assert [item["source_id"] for item in page["items"]] == expected_ids
    for item in page["items"]:
        assert (item["source_system"], item["source_entity"], item["ingestion_run_id"]) == (
            "csv_demo", entity, str(demo.run_id))
        uuid.UUID(item["id"])
        assert HEX64.fullmatch(item["record_hash"])
        assert datetime.fromisoformat(item["ingested_at"]).tzinfo is not None
        assert "source_updated_at" in item


def test_the_whole_demo_dataset_is_exposed_exactly_once(client, demo):
    totals = [_page(client, entity, limit=1)["total"] for entity in TYPES]
    assert sum(totals) == demo.to_dict()["records_inserted"] == 233
    ids = [item["id"] for entity in TYPES for item in _all(client, entity)["items"]]
    assert len(ids) == len(set(ids)) == 233


@pytest.mark.parametrize(("limit", "offset"), [
    (1, 0), (7, 0), (7, 7), (7, 49), (50, 0), (500, 45), (10, 50), (10, 1000)])
def test_pages_are_explicit_slices_of_one_stable_order(client, demo, limit, offset):
    full = _all(client, "customers")["items"]
    assert _page(client, "customers", limit=limit, offset=offset) == {
        "items": full[offset:offset + limit], "total": 50, "limit": limit, "offset": offset}


def test_records_are_ordered_by_source_system_then_source_id(client, demo, e1_sessions):
    with e1_sessions.begin() as session:
        session.add_all([_customer("zzz_source", "CUST-000"), _customer("aaa_source", "CUST-999")])
        # An update rewrites the row at the end of the table, so physical order is not id order.
        session.execute(update(Customer).where(Customer.source_id == "CUST-001")
                        .values(name="Renamed"))
    identities = [(item["source_system"], item["source_id"])
                  for item in _all(client, "customers")["items"]]
    assert identities == [("aaa_source", "CUST-999"),
                          *(("csv_demo", source_id) for source_id in _csv_ids(DEMO_DIR, "customers")),
                          ("zzz_source", "CUST-000")]


def test_records_of_one_source_system_are_ordered_by_source_entity_before_source_id(
        client, demo, e1_sessions):
    # source_entity is the source's own resource type; the identity triple is what is unique.
    with e1_sessions.begin() as session:
        account = _customer("csv_demo", "ZZZ-1")
        account.source_entity = "accounts"
        session.add(account)
    identities = [(item["source_entity"], item["source_id"])
                  for item in _all(client, "customers", source_system="csv_demo")["items"]]
    assert identities == [("accounts", "ZZZ-1"),
                          *(("customers", source_id)
                            for source_id in _csv_ids(DEMO_DIR, "customers"))]


def test_records_can_be_filtered_by_source_system(client, demo, e1_sessions):
    with e1_sessions.begin() as session:
        session.add(_customer("rest_mock", "C-1"))
    assert _page(client, "customers")["total"] == 51
    csv_page = _all(client, "customers", source_system="csv_demo")
    assert csv_page["total"] == len(csv_page["items"]) == 50
    assert {item["source_system"] for item in csv_page["items"]} == {"csv_demo"}
    rest_page = _page(client, "customers", source_system="rest_mock")
    assert (rest_page["total"], [item["source_id"] for item in rest_page["items"]]) == (1, ["C-1"])
    assert _page(client, "customers", source_system="odoo_mock") == {
        "items": [], "total": 0, "limit": 50, "offset": 0}
    assert _page(client, "deals", source_system="rest_mock")["total"] == 0


# --- detail --------------------------------------------------------------------


@pytest.mark.parametrize("entity", TYPES)
def test_detail_returns_exactly_the_listed_record(client, demo, entity):
    for item in _all(client, entity)["items"][:3]:
        response = client.get(f"{ENTITIES}/{entity}/{item['id']}")
        assert response.status_code == 200
        assert response.json() == item


def test_unknown_ids_and_ids_of_another_entity_type_are_not_found(client, demo):
    customer_id = _all(client, "customers")["items"][0]["id"]
    for path, entity in ((f"{ENTITIES}/deals/{customer_id}", "deals"),
                         (f"{ENTITIES}/customers/{uuid.uuid4()}", "customers")):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json() == {"error": {
            "code": "ENTITY_NOT_FOUND", "message": "entity does not exist",
            "details": {"entity_type": entity}, "request_id": response.headers["x-request-id"]}}


# --- values, idempotency and the bad fixture -------------------------------------


def test_business_fields_round_trip_without_float_conversion(client, demo):
    deals = {item["source_id"]: item for item in _all(client, "deals")["items"]}
    customers = {item["source_id"]: item["id"] for item in _all(client, "customers")["items"]}
    for row in _csv_rows(DEMO_DIR, "deals"):
        deal = deals[row["deal_id"]]
        assert (deal["amount"], deal["probability"], deal["currency"]) == (
            row["amount"], row["probability"], row["currency"])
        assert (deal["customer_source_id"], deal["customer_id"]) == (
            row["customer_id"], customers[row["customer_id"]])
    documents = {item["source_id"]: item for item in _all(client, "documents")["items"]}
    for row in _csv_rows(DEMO_DIR, "documents"):
        assert documents[row["document_id"]]["body_text"] == row["body_text"]


def test_repeated_ingestion_changes_no_record_and_creates_no_duplicate(client, e1_sessions, demo):
    before = {entity: _all(client, entity) for entity in TYPES}
    again = _ingest(e1_sessions, DEMO_DIR, T0 + timedelta(hours=1))
    assert again.status.value == "NOOP"
    assert {entity: _all(client, entity) for entity in TYPES} == before


def test_the_bad_fixture_exposes_only_accepted_records(client, e1_sessions):
    run = _ingest(e1_sessions, BAD_FIXTURE_DIR, T0)
    customers = _all(client, "customers")["items"]
    deals = _all(client, "deals")["items"]
    assert [item["source_id"] for item in customers] == ["CUST-901", "CUST-902"]
    assert [item["source_id"] for item in deals] == ["DEAL-901", "DEAL-902"]
    records = {item["source_id"]: item for item in (*customers, *deals)}
    assert records["CUST-902"]["email"] is None
    assert records["DEAL-901"]["customer_id"] == records["CUST-901"]["id"]
    assert (records["DEAL-902"]["customer_id"], records["DEAL-902"]["customer_source_id"]) == (
        None, "CUST-999")
    assert {item["ingestion_run_id"] for item in records.values()} == {str(run.run_id)}
    for entity in TYPES:
        text = client.get(f"{ENTITIES}/{entity}", params={"limit": 500}).text
        for value in ("suspended", "12,50,000.00", "31/12/2026", "raw_record", "raw_value",
                      "raw_payload"):
            assert value not in text, (entity, value)


# --- query count ---------------------------------------------------------------


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


def test_entity_reads_issue_a_constant_number_of_queries(client, e1_engine, demo):
    one = _statements(e1_engine, client, f"{ENTITIES}/customers?limit=1")
    many = _statements(e1_engine, client, f"{ENTITIES}/customers?limit=500")
    assert one == many == 2
    customer_id = _all(client, "customers")["items"][0]["id"]
    assert _statements(e1_engine, client, f"{ENTITIES}/customers/{customer_id}") == 1
