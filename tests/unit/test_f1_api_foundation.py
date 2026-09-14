"""
F1 API foundation: request IDs, structured errors, readiness without a database.
"""

from __future__ import annotations

import logging
import re

import pytest
from fastapi import Query
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main
from app.api.errors import ApiError
from app.api.request_id import REQUEST_ID_HEADER, resolve_request_id
from app.main import DATABASE_CONNECT_TIMEOUT_SECONDS, create_app

HEX_ID = re.compile(r"[0-9a-f]{32}")
# Synthetic credentials for an unreachable server (nothing listens on port 9).
UNREACHABLE_URL = "postgresql://f1_probe:f1-synthetic-password@127.0.0.1:9/f1_unreachable"


def _unreachable_sessions() -> sessionmaker:
    engine = create_engine(UNREACHABLE_URL, hide_parameters=True,
                           connect_args={"connect_timeout": 2})
    return sessionmaker(bind=engine)


@pytest.fixture
def app():
    application = create_app(sessions=_unreachable_sessions())

    @application.get("/test/api-error")
    def raise_api_error() -> None:
        raise ApiError(409, "TEST_CONFLICT", "conflict for test", {"reason": "test"})

    @application.get("/test/crash")
    def crash() -> None:
        raise RuntimeError("crash text that must stay private")

    @application.get("/test/validated")
    def validated(limit: int = Query(ge=1)) -> dict[str, int]:
        return {"limit": limit}

    return application


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def _assert_envelope(response, status: int, code: str, message: str, details=None) -> None:
    assert response.status_code == status
    body = response.json()
    assert body == {"error": {"code": code, "message": message, "details": details,
                              "request_id": response.headers[REQUEST_ID_HEADER]}}


# --- request IDs -------------------------------------------------------------


@pytest.mark.parametrize("candidate", ["a", "A" * 64, "req-1.2_3", "0123456789abcdef"])
def test_safe_client_request_ids_are_reused(candidate):
    assert resolve_request_id(candidate) == candidate


@pytest.mark.parametrize("candidate", [None, "", "A" * 65, "has space", "semi;colon", "é", "a/b"])
def test_unsafe_or_missing_request_ids_are_replaced(candidate):
    generated = resolve_request_id(candidate)
    assert HEX_ID.fullmatch(generated)
    assert generated != resolve_request_id(candidate)


def test_every_response_carries_a_generated_request_id(client):
    first = client.get("/api/v1/health")
    second = client.get("/api/v1/health")
    assert HEX_ID.fullmatch(first.headers[REQUEST_ID_HEADER])
    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


def test_a_safe_client_request_id_is_echoed(client):
    response = client.get("/api/v1/health", headers={REQUEST_ID_HEADER: "demo-request-7"})
    assert response.headers[REQUEST_ID_HEADER] == "demo-request-7"


def test_an_unsafe_client_request_id_is_not_echoed(client):
    response = client.get("/test/api-error", headers={REQUEST_ID_HEADER: "x" * 65})
    request_id = response.headers[REQUEST_ID_HEADER]
    assert HEX_ID.fullmatch(request_id)
    assert response.json()["error"]["request_id"] == request_id


# --- structured errors -------------------------------------------------------


def test_api_errors_use_the_envelope(client):
    response = client.get("/test/api-error", headers={REQUEST_ID_HEADER: "req-409"})
    _assert_envelope(response, 409, "TEST_CONFLICT", "conflict for test", {"reason": "test"})
    assert response.json()["error"]["request_id"] == "req-409"


def test_unknown_routes_return_not_found(client):
    _assert_envelope(client.get("/api/v1/does-not-exist"), 404, "NOT_FOUND", "Not Found")


def test_health_is_only_mounted_under_api_v1(client):
    _assert_envelope(client.get("/health"), 404, "NOT_FOUND", "Not Found")


def test_wrong_method_returns_method_not_allowed_with_allow_header(client):
    response = client.post("/api/v1/health")
    _assert_envelope(response, 405, "METHOD_NOT_ALLOWED", "Method Not Allowed")
    assert response.headers["allow"] == "GET"


def test_validation_errors_list_location_message_and_type_without_the_input(client):
    response = client.get("/test/validated", params={"limit": "-987654"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "INVALID_REQUEST"
    assert error["message"] == "request validation failed"
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert error["details"] == [{"loc": ["query", "limit"],
                                 "message": "Input should be greater than or equal to 1",
                                 "type": "greater_than_equal"}]
    assert "987654" not in response.text


def test_unhandled_exceptions_return_a_generic_internal_error(client, caplog):
    with caplog.at_level(logging.ERROR, logger="app.api.errors"):
        response = client.get("/test/crash", headers={REQUEST_ID_HEADER: "req-crash"})
    _assert_envelope(response, 500, "INTERNAL_ERROR", "internal server error")
    assert response.headers[REQUEST_ID_HEADER] == "req-crash"
    assert "private" not in response.text
    messages = [record.getMessage() for record in caplog.records]
    assert messages == ["request_failed request_id=req-crash method=GET path=/test/crash "
                        "failure=RuntimeError"]


def test_unhandled_exceptions_still_propagate_to_the_server(app):
    with pytest.raises(RuntimeError):
        TestClient(app).get("/test/crash")


# --- readiness ---------------------------------------------------------------


def test_health_reports_unhealthy_503_when_the_database_is_unreachable(client, caplog):
    with caplog.at_level(logging.WARNING, logger="app.api.v1.health"):
        response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "service": "ai-ceo-layer1",
                               "version": "0.1.0", "checks": {"database": "unavailable"}}
    assert [record.getMessage() for record in caplog.records] == [
        "readiness_check_failed dependency=database failure=OperationalError"]
    for secret in ("f1-synthetic-password", "f1_probe", "127.0.0.1", "postgresql"):
        assert secret not in response.text
        assert secret not in caplog.text


def test_default_engine_hides_parameters_and_never_echoes_sql(monkeypatch):
    captured = {}
    real_create_engine = main.create_engine

    def spy(url, **kwargs):
        captured.update(kwargs)
        return real_create_engine(url, **kwargs)

    monkeypatch.setattr(main, "create_engine", spy)
    engine = create_app().state.sessions.kw["bind"]
    assert captured == {"echo": False, "hide_parameters": True, "pool_pre_ping": True,
                        "connect_args": {"connect_timeout": 5}}
    assert DATABASE_CONNECT_TIMEOUT_SECONDS == 5
    assert (engine.hide_parameters, engine.echo) == (True, False)
    engine.dispose()


def test_an_injected_session_factory_is_used_as_is():
    sessions = _unreachable_sessions()
    assert create_app(sessions=sessions).state.sessions is sessions


def _track_dispose(engine, disposed, monkeypatch):
    monkeypatch.setattr(engine, "dispose", lambda *args, **kwargs: disposed.append(engine))
    return engine


def test_only_the_app_owned_engine_is_disposed_on_shutdown(monkeypatch):
    disposed: list = []
    real_create_engine = main.create_engine
    monkeypatch.setattr(main, "create_engine", lambda url, **kwargs: _track_dispose(
        real_create_engine(url, **kwargs), disposed, monkeypatch))
    owned = create_app()
    with TestClient(owned):
        assert disposed == []
    assert disposed == [owned.state.sessions.kw["bind"]]

    injected = _unreachable_sessions()
    _track_dispose(injected.kw["bind"], disposed, monkeypatch)
    with TestClient(create_app(sessions=injected)):
        pass
    assert len(disposed) == 1


def test_openapi_documents_both_health_responses(app):
    operation = app.openapi()["paths"]["/api/v1/health"]["get"]
    schema_ref = "#/components/schemas/HealthResponse"
    for status in ("200", "503"):
        assert operation["responses"][status]["content"]["application/json"]["schema"] == {
            "$ref": schema_ref}
