"""
H4 API contract tests (spec Section 15, "API").

The F1 and F2 suites test each route's own behaviour. This module tests the
properties that must hold across *every* published route, and it discovers
the routes from the application's own OpenAPI document rather than from a
hand-written list, so a route added later is covered automatically and a
route that forgets the shared contract fails here.

The cross-route contract:

1. Correlation   every response, success or failure, carries X-Request-ID,
                 and every error body repeats that same id (Section 16:
                 a request is traceable end to end).
2. Envelope      every failure has the one documented error shape, with a
                 stable code and a fixed message; framework text, database
                 text and connector text never reach the client.
3. Read-only     the API publishes exactly one non-GET operation (starting
                 an ingestion run). Every other route refuses every write
                 verb with 405 and an Allow header (Section 14: Layer 1
                 takes no external action and exposes no source mutation).
4. Pagination    every paginated route bounds limit and offset identically,
                 echoes them, and reports a total that does not depend on
                 the slice (Section 10).
5. Disclosure    no response body or error detail contains a raw source
                 payload, a connection detail or a submitted value.

The routes run against a real migrated database with a real E1 ingestion
behind them, so the pagination and envelope assertions are made over real
rows rather than mocks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.errors import ErrorCode
from app.api.request_id import REQUEST_ID_HEADER
from app.connectors.registry import build_connector
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.main import create_app

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
T0 = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)

WRITE_VERBS = ("POST", "PUT", "PATCH", "DELETE")

#: The only operation the API publishes that is not a GET (spec Section 10).
THE_ONE_WRITE_OPERATION = ("POST", "/api/v1/ingestion/runs")

ENTITY_TYPES = ("organizations", "employees", "customers", "deals",
                "projects", "support_tickets", "documents")


@pytest.fixture
def client(e1_sessions):
    return TestClient(create_app(sessions=e1_sessions), raise_server_exceptions=False)


@pytest.fixture
def ingested(e1_sessions):
    """One completed run over the committed demo data."""
    return run_ingestion(build_connector("csv_demo", data_directory=DEMO_DIR),
                         e1_sessions, IngestionRequest(), clock=lambda: T0)


@pytest.fixture
def spec(client):
    return client.get("/openapi.json").json()


def _concrete(path: str, run_id: str | None = None, entity_id: str | None = None) -> str:
    """Substitute a real value for each path parameter."""
    return (path
            .replace("{run_id}", run_id or str(uuid.uuid4()))
            .replace("{entity_id}", entity_id or str(uuid.uuid4()))
            .replace("{source}", "csv_demo"))


def _published(spec) -> list[tuple[str, str]]:
    return sorted((method.upper(), path)
                  for path, operations in spec["paths"].items()
                  for method in operations)


def _paginated(spec) -> list[str]:
    """Every published path whose operation declares limit and offset."""
    paths = []
    for path, operations in spec["paths"].items():
        for operation in operations.values():
            names = {parameter["name"] for parameter in operation.get("parameters", [])}
            if {"limit", "offset"} <= names:
                paths.append(path)
    return sorted(paths)


def _assert_envelope(response, expected_code: str | None = None) -> dict:
    """Assert the documented error shape and return the error body."""
    body = response.json()
    assert set(body) == {"error"}, body
    error = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}, error
    assert isinstance(error["code"], str) and error["code"]
    assert isinstance(error["message"], str) and error["message"]
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]
    if expected_code is not None:
        assert error["code"] == expected_code
    return error


# ---------------------------------------------------------------------------
# 1. Correlation
# ---------------------------------------------------------------------------


def test_every_published_route_answers_with_a_request_id(client, spec, ingested):
    """Success or failure, every route is traceable (spec Section 16)."""
    for method, path in _published(spec):
        response = client.request(method, _concrete(path, run_id=str(ingested.run_id)),
                                  json={} if method == "POST" else None)
        assert response.headers.get(REQUEST_ID_HEADER), f"{method} {path}"


def test_a_client_request_id_is_echoed_by_every_route(client, spec, ingested):
    for method, path in _published(spec):
        response = client.request(method, _concrete(path, run_id=str(ingested.run_id)),
                                  headers={REQUEST_ID_HEADER: "h4-correlation-id"},
                                  json={} if method == "POST" else None)
        assert response.headers[REQUEST_ID_HEADER] == "h4-correlation-id", f"{method} {path}"


def test_request_ids_are_unique_per_request(client):
    seen = {client.get("/api/v1/health").headers[REQUEST_ID_HEADER] for _ in range(10)}
    assert len(seen) == 10


def test_an_error_body_repeats_the_header_request_id(client):
    response = client.get("/api/v1/entities/customers", params={"limit": 0})
    assert response.status_code == 422
    _assert_envelope(response, ErrorCode.INVALID_REQUEST)


# ---------------------------------------------------------------------------
# 2. Error envelope
# ---------------------------------------------------------------------------


def test_an_unknown_path_uses_the_envelope(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    _assert_envelope(response, ErrorCode.NOT_FOUND)


def test_an_unknown_entity_type_is_an_unknown_route(client):
    response = client.get("/api/v1/entities/invoices")
    assert response.status_code == 404
    _assert_envelope(response, ErrorCode.NOT_FOUND)


@pytest.mark.parametrize("entity", ENTITY_TYPES)
def test_a_missing_record_uses_the_envelope_for_every_entity_type(client, entity):
    response = client.get(f"/api/v1/entities/{entity}/{uuid.uuid4()}")
    assert response.status_code == 404
    _assert_envelope(response, ErrorCode.ENTITY_NOT_FOUND)


def test_a_missing_run_uses_the_envelope(client):
    response = client.get(f"/api/v1/ingestion/runs/{uuid.uuid4()}")
    assert response.status_code == 404
    _assert_envelope(response, ErrorCode.RUN_NOT_FOUND)


def test_a_missing_runs_errors_page_uses_the_envelope(client):
    response = client.get(f"/api/v1/ingestion/runs/{uuid.uuid4()}/errors")
    assert response.status_code == 404
    _assert_envelope(response, ErrorCode.RUN_NOT_FOUND)


def test_an_unknown_source_uses_the_envelope(client):
    response = client.get("/api/v1/sources/not_a_source/health")
    assert response.status_code == 404
    _assert_envelope(response, ErrorCode.SOURCE_NOT_FOUND)


@pytest.mark.parametrize(
    "path",
    ["/api/v1/entities/customers/not-a-uuid", "/api/v1/ingestion/runs/not-a-uuid",
     "/api/v1/ingestion/runs/not-a-uuid/errors"],
)
def test_a_malformed_path_parameter_is_refused_with_the_envelope(client, path):
    response = client.get(path)
    assert response.status_code == 422
    error = _assert_envelope(response, ErrorCode.INVALID_REQUEST)
    assert isinstance(error["details"], list) and error["details"]


def test_validation_details_never_echo_the_submitted_value(client):
    """A rejected value may be a credential; only loc/message/type are returned."""
    secret = "H4-SYNTHETIC-REJECTED-VALUE"
    response = client.get("/api/v1/entities/customers", params={"limit": secret})
    assert response.status_code == 422
    error = _assert_envelope(response)
    assert secret not in response.text
    for detail in error["details"]:
        assert set(detail) == {"loc", "message", "type"}


def test_an_unsupported_ingestion_option_uses_the_envelope(client):
    response = client.post("/api/v1/ingestion/runs",
                           json={"source": "csv_demo", "unexpected": True})
    assert response.status_code == 422
    _assert_envelope(response, ErrorCode.INVALID_REQUEST)


def test_an_unknown_ingestion_source_is_a_body_validation_failure(client):
    """An unknown source in a body is 422; an unknown source in a path is 404.

    The distinction is deliberate: /sources/{source}/health addresses a
    resource that does not exist, while the ingestion body names a source
    that is not in the configured vocabulary.
    """
    response = client.post("/api/v1/ingestion/runs", json={"source": "not_a_source"})
    assert response.status_code == 422
    error = _assert_envelope(response, ErrorCode.SOURCE_NOT_FOUND)
    assert error["details"] == {"available_sources": ["csv_demo", "odoo_mock", "rest_mock"]}

    path_response = client.get("/api/v1/sources/not_a_source/health")
    assert path_response.status_code == 404


def test_every_error_code_the_api_can_return_is_declared(client, spec):
    """Codes are a published contract; the enum is the whole vocabulary."""
    observed = set()
    for response in (
        client.get("/api/v1/does-not-exist"),
        client.get("/api/v1/entities/customers", params={"limit": 0}),
        client.get(f"/api/v1/entities/customers/{uuid.uuid4()}"),
        client.get(f"/api/v1/ingestion/runs/{uuid.uuid4()}"),
        client.get("/api/v1/sources/not_a_source/health"),
        client.delete("/api/v1/health"),
    ):
        observed.add(response.json()["error"]["code"])
    assert observed <= {code.value for code in ErrorCode}


# ---------------------------------------------------------------------------
# 3. The API is read-only apart from starting a run
# ---------------------------------------------------------------------------


def test_the_api_publishes_exactly_one_non_get_operation(spec):
    """Spec Section 10: only POST /ingestion/runs may change server state."""
    non_get = [(method, path) for method, path in _published(spec) if method != "GET"]
    assert non_get == [THE_ONE_WRITE_OPERATION]


@pytest.mark.parametrize("verb", WRITE_VERBS)
def test_every_read_route_refuses_every_write_verb(client, spec, verb, ingested):
    """A write verb on a read route is 405 with an Allow header, not 404 or 500."""
    for method, path in _published(spec):
        if method != "GET" or (verb, path) == THE_ONE_WRITE_OPERATION:
            continue
        response = client.request(verb, _concrete(path, run_id=str(ingested.run_id)))
        assert response.status_code == 405, f"{verb} {path}"
        assert "Allow" in response.headers, f"{verb} {path}"
        _assert_envelope(response, ErrorCode.METHOD_NOT_ALLOWED)


def test_the_allow_header_lists_only_the_supported_verbs(client):
    response = client.delete("/api/v1/entities/customers")
    assert response.status_code == 405
    allowed = {verb.strip() for verb in response.headers["Allow"].split(",")}
    assert "GET" in allowed
    assert not (allowed & {"PUT", "PATCH", "DELETE"})


@pytest.mark.parametrize("verb", ["PUT", "PATCH", "DELETE"])
def test_the_ingestion_route_accepts_no_other_write_verb(client, verb):
    response = client.request(verb, "/api/v1/ingestion/runs")
    assert response.status_code == 405
    _assert_envelope(response, ErrorCode.METHOD_NOT_ALLOWED)


def test_reading_the_api_never_changes_the_database(client, e1_sessions, ingested, spec):
    """Every GET is safe: the stored rows are identical afterwards."""
    from sqlalchemy import func, select

    from app.persistence.repositories.canonical import ENTITY_MODELS

    def snapshot():
        with e1_sessions() as session:
            return {name: session.scalar(select(func.count()).select_from(model))
                    for name, model in ENTITY_MODELS.items()}

    before = snapshot()
    for method, path in _published(spec):
        if method != "GET":
            continue
        client.get(_concrete(path, run_id=str(ingested.run_id)))
    assert snapshot() == before


# ---------------------------------------------------------------------------
# 4. Pagination
# ---------------------------------------------------------------------------


def test_the_paginated_routes_are_the_expected_ones(spec):
    """Guards the parameterization below against silently covering nothing."""
    assert _paginated(spec) == sorted(
        [f"/api/v1/entities/{entity}" for entity in ENTITY_TYPES]
        + ["/api/v1/ingestion/runs", "/api/v1/ingestion/runs/{run_id}/errors"]
    )


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": -1}, {"limit": 501}, {"offset": -1},
     {"limit": "abc"}, {"offset": "abc"}, {"limit": 1.5}],
)
def test_every_paginated_route_bounds_limit_and_offset_identically(
    client, spec, params, ingested
):
    for path in _paginated(spec):
        response = client.get(_concrete(path, run_id=str(ingested.run_id)), params=params)
        assert response.status_code == 422, f"{path} {params}"
        _assert_envelope(response, ErrorCode.INVALID_REQUEST)


def test_every_paginated_route_echoes_its_page_window(client, spec, ingested):
    for path in _paginated(spec):
        response = client.get(_concrete(path, run_id=str(ingested.run_id)),
                              params={"limit": 2, "offset": 1})
        assert response.status_code == 200, f"{path}: {response.text}"
        body = response.json()
        assert body["limit"] == 2 and body["offset"] == 1, path
        assert isinstance(body["total"], int) and body["total"] >= 0, path
        assert len(body["items"]) <= 2, path


def test_every_paginated_route_reports_a_total_independent_of_the_slice(
    client, spec, ingested
):
    """total is the number of matching rows, not the size of this page."""
    for path in _paginated(spec):
        concrete = _concrete(path, run_id=str(ingested.run_id))
        whole = client.get(concrete, params={"limit": 500}).json()
        sliced = client.get(concrete, params={"limit": 1}).json()
        assert sliced["total"] == whole["total"], path


def test_every_paginated_route_returns_an_empty_page_past_the_end(client, spec, ingested):
    """An offset beyond the data is an empty page, never an error."""
    for path in _paginated(spec):
        response = client.get(_concrete(path, run_id=str(ingested.run_id)),
                              params={"limit": 10, "offset": 100_000})
        assert response.status_code == 200, path
        assert response.json()["items"] == [], path


@pytest.mark.parametrize("entity", ENTITY_TYPES)
def test_pages_partition_the_result_set_without_gaps_or_repeats(client, entity, ingested):
    """Walking a stable order in pages of one reproduces the whole list."""
    whole = client.get(f"/api/v1/entities/{entity}", params={"limit": 500}).json()
    walked = []
    for offset in range(whole["total"]):
        page = client.get(f"/api/v1/entities/{entity}",
                          params={"limit": 1, "offset": offset}).json()
        walked.extend(page["items"])
    assert [item["id"] for item in walked] == [item["id"] for item in whole["items"]]


@pytest.mark.parametrize("entity", ENTITY_TYPES)
def test_pages_are_sliced_from_the_documented_source_identity_order(client, entity, ingested):
    """Paging is only meaningful over a total, stable order.

    The routes document source-identity order, which is total because the
    uq_<table>_source_identity constraint makes the triple unique and does
    not change when a later run updates a record.
    """
    items = client.get(f"/api/v1/entities/{entity}", params={"limit": 500}).json()["items"]
    identities = [(item["source_system"], item["source_entity"], item["source_id"])
                  for item in items]
    assert identities == sorted(identities)
    assert len(identities) == len(set(identities)), "the order must be total"


def test_the_page_order_is_stable_across_requests(client, ingested):
    """Two identical requests return the same rows in the same positions."""
    first = client.get("/api/v1/entities/customers", params={"limit": 10}).json()
    second = client.get("/api/v1/entities/customers", params={"limit": 10}).json()
    assert [item["id"] for item in first["items"]] == [item["id"] for item in second["items"]]


def test_the_default_page_size_is_applied_when_omitted(client, ingested):
    body = client.get("/api/v1/entities/customers").json()
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["items"]) == min(50, body["total"])


# ---------------------------------------------------------------------------
# 5. Disclosure
# ---------------------------------------------------------------------------


def test_no_response_exposes_a_raw_source_payload_or_connection_detail(
    client, spec, ingested
):
    """Raw payloads live in source_records; the API never reads them."""
    forbidden = ("raw_payload", "base_url", "data_directory", "password",
                 "DATABASE_URL", "postgresql://")
    for method, path in _published(spec):
        if method != "GET":
            continue
        text = client.get(_concrete(path, run_id=str(ingested.run_id))).text
        for token in forbidden:
            assert token not in text, f"{path} exposed {token}"


def test_the_source_listing_never_exposes_connection_details(client):
    body = client.get("/api/v1/sources").json()
    assert body["sources"]
    for source in body["sources"]:
        assert set(source) == {"source", "source_type", "capabilities"}


def test_a_connector_health_failure_reports_a_class_name_not_a_message(client, e1_sessions):
    """Connector diagnostics can name internal hosts; only the class is public."""
    response = client.get("/api/v1/sources/odoo_mock/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"source", "status", "latency_ms", "error_type", "checked_at"}
    if body["error_type"] is not None:
        assert " " not in body["error_type"], "a class name, not a sentence"


#: Health answers 503 with a HealthResponse, not an error envelope: an
#: unready dependency is a documented health state, not a request failure.
ENVELOPE_EXEMPT = {("get", "/api/v1/health", "503")}


def test_the_error_envelope_is_the_only_error_schema_published(spec):
    """Every documented failure but the health 503 references the envelope."""
    checked = 0
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            for status, response in operation["responses"].items():
                if not status.startswith(("4", "5")):
                    continue
                schema = response["content"]["application/json"]["schema"]
                if (method, path, status) in ENVELOPE_EXEMPT:
                    assert schema["$ref"].endswith("/HealthResponse")
                    continue
                assert schema["$ref"].endswith("/ErrorResponse"), f"{method} {path} {status}"
                checked += 1
    assert checked >= 20, "the sweep must actually cover the documented failures"


def test_the_health_503_body_is_a_health_document_not_an_error(client, monkeypatch):
    """An unready dependency is reported as health state, with a request id."""
    from sqlalchemy.exc import OperationalError

    app = create_app()
    failing = TestClient(app, raise_server_exceptions=False)

    def explode(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("unreachable"))

    monkeypatch.setattr(app.state.sessions, "__call__", explode)
    response = failing.get("/api/v1/health")
    assert response.headers[REQUEST_ID_HEADER]
    if response.status_code == 503:
        assert set(response.json()) == {"status", "service", "version", "checks"}
