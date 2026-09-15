"""
F1 OpenAPI contract: every route is published with accurate request, response and error models.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import sessionmaker

from app.main import create_app

ERROR_REF = {"$ref": "#/components/schemas/ErrorResponse"}
F1_OPERATIONS = {
    ("get", "/api/v1/health"),
    ("get", "/api/v1/sources"),
    ("get", "/api/v1/sources/{source}/health"),
    ("post", "/api/v1/ingestion/runs"),
    ("get", "/api/v1/ingestion/runs"),
    ("get", "/api/v1/ingestion/runs/{run_id}"),
    ("get", "/api/v1/ingestion/runs/{run_id}/errors"),
}


@pytest.fixture(scope="module")
def spec() -> dict:
    return create_app(sessions=sessionmaker()).openapi()


def _operations(spec):
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            yield method, path, operation


def _schema(response):
    return response["content"]["application/json"]["schema"]


# F2 adds a list and a detail route per canonical entity type (tests/unit/test_f2_entities_openapi.py).
ENTITY_TYPES = ("organizations", "employees", "customers", "deals", "projects", "support_tickets",
                "documents")
F2_ENTITY_OPERATIONS = {
    ("get", path) for entity in ENTITY_TYPES
    for path in (f"/api/v1/entities/{entity}", f"/api/v1/entities/{entity}/{{entity_id}}")
}


F2_METRICS_OPERATIONS = {("get", "/api/v1/metrics/ingestion")}


def test_exactly_the_f1_and_f2_operations_are_published(spec):
    assert {(method, path) for method, path, _ in _operations(spec)} == \
        F1_OPERATIONS | F2_ENTITY_OPERATIONS | F2_METRICS_OPERATIONS


def test_api_metadata(spec):
    assert (spec["info"]["title"], spec["info"]["version"]) == ("AI CEO — Layer 1", "0.1.0")


def test_the_framework_validation_error_schema_is_never_advertised(spec):
    schemas = spec["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas


def test_every_error_response_uses_the_error_envelope(spec):
    for method, path, operation in _operations(spec):
        for status, response in operation["responses"].items():
            if int(status) < 400 or (path, status) == ("/api/v1/health", "503"):
                continue
            assert _schema(response) == ERROR_REF, (method, path, status)


def test_operations_with_parameters_or_a_body_document_validation_errors(spec):
    for method, path, operation in _operations(spec):
        if operation.get("parameters") or operation.get("requestBody"):
            assert _schema(operation["responses"]["422"]) == ERROR_REF, (method, path)


def test_success_responses_reference_named_models(spec):
    expected = {
        ("get", "/api/v1/health"): ("200", "HealthResponse"),
        ("get", "/api/v1/sources"): ("200", "SourceListResponse"),
        ("get", "/api/v1/sources/{source}/health"): ("200", "SourceHealthResponse"),
        ("post", "/api/v1/ingestion/runs"): ("201", "IngestionRunCreatedResponse"),
        ("get", "/api/v1/ingestion/runs"): ("200", "RunListResponse"),
        ("get", "/api/v1/ingestion/runs/{run_id}"): ("200", "IngestionRunResponse"),
        ("get", "/api/v1/ingestion/runs/{run_id}/errors"): ("200", "ErrorListResponse"),
        ("get", "/api/v1/metrics/ingestion"): ("200", "IngestionMetricsResponse"),
    }
    for entity, (page, record) in {
        "organizations": ("OrganizationListResponse", "OrganizationCanonical"),
        "employees": ("EmployeeListResponse", "EmployeeCanonical"),
        "customers": ("CustomerListResponse", "CustomerCanonical"),
        "deals": ("DealListResponse", "DealCanonical"),
        "projects": ("ProjectListResponse", "ProjectCanonical"),
        "support_tickets": ("SupportTicketListResponse", "SupportTicketCanonical"),
        "documents": ("DocumentListResponse", "DocumentCanonical"),
    }.items():
        expected[("get", f"/api/v1/entities/{entity}")] = ("200", page)
        expected[("get", f"/api/v1/entities/{entity}/{{entity_id}}")] = ("200", record)
    for method, path, operation in _operations(spec):
        status, model = expected[(method, path)]
        assert _schema(operation["responses"][status]) == {
            "$ref": f"#/components/schemas/{model}"}, (method, path)


def test_the_ingestion_request_body_is_closed_and_requires_only_the_source(spec):
    operation = spec["paths"]["/api/v1/ingestion/runs"]["post"]
    assert operation["requestBody"]["required"] is True
    assert _schema(operation["requestBody"]) == {"$ref": "#/components/schemas/IngestionRunRequest"}
    request = spec["components"]["schemas"]["IngestionRunRequest"]
    assert request["additionalProperties"] is False
    assert request["required"] == ["source"]
    assert set(request["properties"]) == {"source", "entities", "mode", "dry_run", "page_size"}


def test_operation_ids_are_unique(spec):
    ids = [operation["operationId"] for _, _, operation in _operations(spec)]
    assert len(ids) == len(set(ids))


def test_the_error_envelope_schema(spec):
    schemas = spec["components"]["schemas"]
    assert schemas["ErrorResponse"]["required"] == ["error"]
    assert set(schemas["ErrorBody"]["properties"]) == {"code", "message", "details", "request_id"}
    assert set(schemas["ErrorBody"]["required"]) == {"code", "message", "request_id"}


def test_no_schema_exposes_raw_payloads_or_connection_details(spec):
    text = json.dumps(spec["components"])
    for forbidden in ("raw_record", "raw_value", "raw_payload", "base_url", "data_directory",
                      "password", "api_key", "env_var"):
        assert forbidden not in text
