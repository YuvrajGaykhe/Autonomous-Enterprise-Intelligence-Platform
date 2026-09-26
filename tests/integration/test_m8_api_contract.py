"""
M8's cross-route contract, discovered from OpenAPI and scoped to /api/v1/risk (§0.7.13).

H4 proves the shared contract over every published route. This module proves
it over the six risk operations alone, discovered from the application's own
OpenAPI document, so a risk route that forgets the contract fails here by name:

1. Operations    exactly §0.7.8's six, and no other under /api/v1/risk.
2. Correlation   every risk response carries X-Request-ID, a client's own id
                 is echoed, and every error body repeats it.
3. Envelope      every risk failure has the one documented error shape.
4. Verbs         a write verb on a GET-only risk path, PUT, PATCH or DELETE on
                 either POST path, and GET on /decision are each 405 with the
                 envelope and an Allow header naming only the path's own verbs.
5. Documented    every documented risk error response references ErrorResponse.

The routes run against the real migrated test database, empty, because the
contract is about shape: no failure here depends on stored rows.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.errors import ErrorCode
from app.api.request_id import REQUEST_ID_HEADER
from app.main import create_app

pytestmark = pytest.mark.integration

RISK = "/api/v1/risk"
#: §0.7.8's six operations.
RISK_OPERATIONS = {
    ("POST", "/api/v1/risk/assessments"),
    ("GET", "/api/v1/risk/assessments"),
    ("GET", "/api/v1/risk/assessments/{assessment_id}"),
    ("GET", "/api/v1/risk/briefs/{brief_id}"),
    ("POST", "/api/v1/risk/briefs/{brief_id}/decision"),
    ("GET", "/api/v1/risk/briefs/{brief_id}/decisions"),
}
WRITE_VERBS = ("POST", "PUT", "PATCH", "DELETE")
#: A body each POST accepts in shape, so a request reaches the route itself.
VALID_BODIES = {
    "/api/v1/risk/assessments": {"as_of": "2026-09-18", "customer_source_id": "CUST-007"},
    "/api/v1/risk/briefs/{brief_id}/decision": {"actor": "ceo@example.invalid",
                                               "decision": "APPROVED", "payload_hash": "0" * 64},
}


@pytest.fixture
def client(e1_sessions):
    return TestClient(create_app(sessions=e1_sessions), raise_server_exceptions=False)


@pytest.fixture
def spec(client):
    return client.get("/openapi.json").json()


def _risk_paths(spec) -> dict[str, set[str]]:
    """Each published risk path with the verbs it publishes."""
    return {path: {method.upper() for method in operations}
            for path, operations in spec["paths"].items()
            if path == RISK or path.startswith(RISK + "/")}


def _risk_operations(spec) -> set[tuple[str, str]]:
    return {(verb, path) for path, verbs in _risk_paths(spec).items() for verb in verbs}


def _concrete(path: str, identifier: str | None = None) -> str:
    """Substitute an id, by default one that names nothing, for each path parameter."""
    value = identifier or str(uuid.uuid4())
    return path.replace("{assessment_id}", value).replace("{brief_id}", value)


def _assert_envelope(response, expected_code: str | None = None) -> dict:
    """The documented error shape, H4's, with the header's request id repeated."""
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


def _refused(client, verb: str, path: str, published: set[str]) -> None:
    response = client.request(verb, _concrete(path))

    assert response.status_code == 405, f"{verb} {path}"
    allowed = {one.strip() for one in response.headers["Allow"].split(",")}
    assert allowed and allowed <= published and verb not in allowed, f"{verb} {path}: {allowed}"
    _assert_envelope(response, ErrorCode.METHOD_NOT_ALLOWED)


# ---------------------------------------------------------------------------
# 1. Operations
# ---------------------------------------------------------------------------


def test_exactly_the_six_risk_operations_are_published(spec):
    assert _risk_operations(spec) == RISK_OPERATIONS


def test_the_verb_sweeps_below_cover_three_get_only_paths_and_two_post_paths(spec):
    """Guards the sweeps against silently covering nothing."""
    paths = _risk_paths(spec)

    assert sorted(path for path, verbs in paths.items() if verbs == {"GET"}) == [
        "/api/v1/risk/assessments/{assessment_id}", "/api/v1/risk/briefs/{brief_id}",
        "/api/v1/risk/briefs/{brief_id}/decisions"]
    assert sorted(path for path, verbs in paths.items() if "POST" in verbs) == sorted(VALID_BODIES)


# ---------------------------------------------------------------------------
# 2. Correlation
# ---------------------------------------------------------------------------


def test_every_risk_operation_answers_with_a_request_id(client, spec):
    for verb, path in sorted(_risk_operations(spec)):
        response = client.request(verb, _concrete(path), json=VALID_BODIES.get(path))

        assert response.headers.get(REQUEST_ID_HEADER), f"{verb} {path}"


def test_every_risk_operation_echoes_the_callers_request_id(client, spec):
    headers = {REQUEST_ID_HEADER: "m8-contract-id"}
    for verb, path in sorted(_risk_operations(spec)):
        response = client.request(verb, _concrete(path), json=VALID_BODIES.get(path),
                                  headers=headers)

        assert response.headers[REQUEST_ID_HEADER] == "m8-contract-id", f"{verb} {path}"
        if response.status_code >= 400:
            assert response.json()["error"]["request_id"] == "m8-contract-id", f"{verb} {path}"


# ---------------------------------------------------------------------------
# 3. Envelope
# ---------------------------------------------------------------------------


def test_every_risk_operation_refuses_an_invalid_request_with_the_envelope(client, spec):
    """A malformed path id, an out-of-range page and an empty body are each 422 INVALID_REQUEST."""
    for verb, path in sorted(_risk_operations(spec)):
        if verb == "POST":
            response = client.post(_concrete(path), json={})
        elif "{" in path:
            response = client.get(_concrete(path, "not-a-uuid"))
        else:
            response = client.get(path, params={"limit": 0})

        assert response.status_code == 422, f"{verb} {path}"
        _assert_envelope(response, ErrorCode.INVALID_REQUEST)


@pytest.mark.parametrize(("verb", "path", "body", "status", "code"), [
    ("GET", "/api/v1/risk/assessments/{assessment_id}", None, 404, ErrorCode.ASSESSMENT_NOT_FOUND),
    ("GET", "/api/v1/risk/briefs/{brief_id}", None, 404, ErrorCode.BRIEF_NOT_FOUND),
    ("GET", "/api/v1/risk/briefs/{brief_id}/decisions", None, 404, ErrorCode.BRIEF_NOT_FOUND),
    ("POST", "/api/v1/risk/briefs/{brief_id}/decision",
     VALID_BODIES["/api/v1/risk/briefs/{brief_id}/decision"], 404, ErrorCode.BRIEF_NOT_FOUND),
    ("POST", "/api/v1/risk/assessments",
     VALID_BODIES["/api/v1/risk/assessments"], 422, ErrorCode.CUSTOMER_NOT_FOUND),
    ("POST", "/api/v1/risk/assessments", {"as_of": None}, 422, ErrorCode.SCOPE_UNRESOLVED),
])
def test_every_risk_failure_of_its_own_uses_the_envelope(client, verb, path, body, status, code):
    """§0.7.9's codes a request can reach with no stored rows, each in the one error shape."""
    response = client.request(verb, _concrete(path), json=body)

    assert response.status_code == status
    _assert_envelope(response, code)


# ---------------------------------------------------------------------------
# 4. Verbs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verb", WRITE_VERBS)
def test_a_write_verb_on_a_get_only_risk_path_is_405(client, spec, verb):
    for path, published in sorted(_risk_paths(spec).items()):
        if published == {"GET"}:
            _refused(client, verb, path, published)


@pytest.mark.parametrize("verb", ["PUT", "PATCH", "DELETE"])
def test_put_patch_and_delete_on_either_post_path_are_405(client, spec, verb):
    for path, published in sorted(_risk_paths(spec).items()):
        if "POST" in published:
            _refused(client, verb, path, published)


def test_get_on_the_decision_path_is_405(client, spec):
    """Recording is POST only: nothing reads through /decision."""
    path = "/api/v1/risk/briefs/{brief_id}/decision"

    _refused(client, "GET", path, _risk_paths(spec)[path])


# ---------------------------------------------------------------------------
# 5. Documented errors
# ---------------------------------------------------------------------------


def test_every_documented_risk_error_references_the_envelope(spec):
    checked = 0
    for path, operations in spec["paths"].items():
        if not path.startswith(RISK + "/"):
            continue
        for method, operation in operations.items():
            for status, response in operation["responses"].items():
                if status.startswith(("4", "5")):
                    schema = response["content"]["application/json"]["schema"]
                    assert schema["$ref"].endswith("/ErrorResponse"), f"{method} {path} {status}"
                    checked += 1
    assert checked >= 13, "the sweep must cover §0.7.8's thirteen documented risk failures"
