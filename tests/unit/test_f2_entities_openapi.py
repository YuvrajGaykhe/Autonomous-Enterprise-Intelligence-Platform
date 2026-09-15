"""
F2 canonical entity routes: published contract and database-free request handling.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.request_id import REQUEST_ID_HEADER
from app.api.v1.schemas import ENTITY_PAGES, ENTITY_RECORDS, EntityType
from app.main import create_app
from app.persistence.repositories import entity_queries
from app.persistence.repositories.canonical import ENTITY_MODELS

ENTITIES = "/api/v1/entities"
ERROR_REF = {"$ref": "#/components/schemas/ErrorResponse"}
PROVENANCE = {"id", "source_system", "source_entity", "source_id", "source_updated_at",
              "ingested_at", "ingestion_run_id", "record_hash"}
PAGE_MODELS = {
    "organizations": ("OrganizationListResponse", "OrganizationCanonical"),
    "employees": ("EmployeeListResponse", "EmployeeCanonical"),
    "customers": ("CustomerListResponse", "CustomerCanonical"),
    "deals": ("DealListResponse", "DealCanonical"),
    "projects": ("ProjectListResponse", "ProjectCanonical"),
    "support_tickets": ("SupportTicketListResponse", "SupportTicketCanonical"),
    "documents": ("DocumentListResponse", "DocumentCanonical"),
}


@pytest.fixture(scope="module")
def spec() -> dict:
    return create_app(sessions=sessionmaker()).openapi()


@pytest.fixture(scope="module")
def client() -> TestClient:
    # An unbound session factory: any request that reached the database would fail.
    return TestClient(create_app(sessions=sessionmaker()), raise_server_exceptions=False)


def _schema(response: dict) -> dict:
    return response["content"]["application/json"]["schema"]


def test_every_canonical_entity_type_has_a_list_and_a_detail_route(spec):
    published = {(method, path) for path, methods in spec["paths"].items()
                 for method in methods if path.startswith(ENTITIES)}
    assert published == {(method, path) for entity in EntityType for method, path in (
        ("get", f"{ENTITIES}/{entity.value}"), ("get", f"{ENTITIES}/{entity.value}/{{entity_id}}"))}
    assert {entity.value for entity in EntityType} == set(PAGE_MODELS) == set(ENTITY_MODELS)


@pytest.mark.parametrize("entity_type", sorted(PAGE_MODELS))
def test_entity_routes_reference_typed_models_and_the_error_envelope(spec, entity_type):
    page, record = PAGE_MODELS[entity_type]
    listing = spec["paths"][f"{ENTITIES}/{entity_type}"]["get"]
    detail = spec["paths"][f"{ENTITIES}/{entity_type}/{{entity_id}}"]["get"]
    assert set(listing["responses"]) == {"200", "422"}
    assert _schema(listing["responses"]["200"]) == {"$ref": f"#/components/schemas/{page}"}
    assert _schema(listing["responses"]["422"]) == ERROR_REF
    assert set(detail["responses"]) == {"200", "404", "422"}
    assert _schema(detail["responses"]["200"]) == {"$ref": f"#/components/schemas/{record}"}
    assert _schema(detail["responses"]["404"]) == ERROR_REF
    assert _schema(detail["responses"]["422"]) == ERROR_REF
    items = spec["components"]["schemas"][page]["properties"]["items"]
    assert items == {"type": "array", "items": {"$ref": f"#/components/schemas/{record}"},
                     "title": "Items"}
    assert set(spec["components"]["schemas"][page]["required"]) == {
        "items", "total", "limit", "offset"}


@pytest.mark.parametrize("entity_type", sorted(PAGE_MODELS))
def test_list_parameters_are_explicit_and_bounded(spec, entity_type):
    parameters = {parameter["name"]: parameter for parameter in
                  spec["paths"][f"{ENTITIES}/{entity_type}"]["get"]["parameters"]}
    assert set(parameters) == {"source_system", "limit", "offset"}
    assert all(parameter["in"] == "query" and not parameter["required"]
               for parameter in parameters.values())
    limit, offset = parameters["limit"]["schema"], parameters["offset"]["schema"]
    assert (limit["minimum"], limit["maximum"], limit["default"]) == (1, 500, 50)
    assert (offset["minimum"], offset["maximum"], offset["default"]) == (0, 2_147_483_647, 0)
    source = parameters["source_system"]["schema"]["anyOf"][0]
    assert (source["minLength"], source["maxLength"]) == (1, 100)
    detail = spec["paths"][f"{ENTITIES}/{entity_type}/{{entity_id}}"]["get"]["parameters"]
    assert [(p["name"], p["in"], p["required"], p["schema"]["format"]) for p in detail] == [
        ("entity_id", "path", True, "uuid")]


@pytest.mark.parametrize("entity_type", sorted(PAGE_MODELS))
def test_records_expose_exactly_the_canonical_columns_with_provenance(spec, entity_type):
    columns = {column.name for column in ENTITY_MODELS[entity_type].__table__.columns}
    record = ENTITY_RECORDS[EntityType(entity_type)]
    assert set(record.model_fields) == columns
    assert PROVENANCE <= columns
    properties = spec["components"]["schemas"][PAGE_MODELS[entity_type][1]]["properties"]
    assert set(properties) == columns
    assert ENTITY_PAGES[EntityType(entity_type)].__name__ == PAGE_MODELS[entity_type][0]


@pytest.mark.parametrize(("record", "field"), [
    ("DealCanonical", "amount"), ("DealCanonical", "probability"), ("ProjectCanonical", "budget")])
def test_decimal_fields_are_published_as_strings_never_numbers(spec, record, field):
    types = {option.get("type") for option in
             spec["components"]["schemas"][record]["properties"][field]["anyOf"]}
    assert types == {"string", "null"}


def _envelope(response, status: int, code: str) -> dict:
    assert response.status_code == status
    error = response.json()["error"]
    assert (error["code"], error["request_id"]) == (code, response.headers[REQUEST_ID_HEADER])
    return error


@pytest.mark.parametrize("path", [f"{ENTITIES}/invoices", f"{ENTITIES}/invoices/{uuid.uuid4()}",
                                  f"{ENTITIES}/Customers", ENTITIES])
def test_unknown_entity_types_are_unknown_routes(client, path):
    _envelope(client.get(path), 404, "NOT_FOUND")


@pytest.mark.parametrize("query", ["limit=0", "limit=501", "offset=-1", "offset=2147483648",
                                   "source_system=", "limit=ten", "source_system=" + "x" * 101])
def test_invalid_list_parameters_are_rejected_before_the_database(client, query):
    error = _envelope(client.get(f"{ENTITIES}/customers?{query}"), 422, "INVALID_REQUEST")
    assert error["message"] == "request validation failed"


@pytest.mark.parametrize("entity_id", ["not-a-uuid", "123", "CUST-001"])
def test_malformed_entity_ids_are_rejected_before_the_database(client, entity_id):
    error = _envelope(client.get(f"{ENTITIES}/deals/{entity_id}"), 422, "INVALID_REQUEST")
    assert [detail["loc"] for detail in error["details"]] == [["path", "entity_id"]]


def test_the_query_repository_rejects_unknown_entity_types():
    with pytest.raises(ValueError, match="unknown canonical entity type"):
        entity_queries.list_entities(None, "invoices", source_system=None,  # type: ignore[arg-type]
                                     limit=1, offset=0)
    with pytest.raises(ValueError, match="unknown canonical entity type"):
        entity_queries.get_entity(None, "invoices", uuid.uuid4())  # type: ignore[arg-type]
