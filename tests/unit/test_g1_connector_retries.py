"""
G1 retry_scheduled events from the C4 Odoo mock and C5 REST connectors.

Retry behaviour is unchanged: the same requests, backoff delays and final
exceptions as before, with one WARNING retry_scheduled event logged before
each scheduled sleep. Events carry the source name, attempt numbers, delay
and a reason label only: never URLs, endpoints, headers or credentials.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from app.connectors import odoo, rest
from app.connectors.odoo import OdooConnectorConfig, OdooMockConnector
from app.connectors.rest import RestConnector, RestConnectorConfig
from app.connectors.types import (
    ConnectorAuthenticationError,
    ConnectorRequestError,
    ConnectorUnavailableError,
)
from app.core.logging import JsonFormatter

# Synthetic, clearly fake values that must never reach a log line.
API_KEY = "g1-synthetic-api-key-not-a-secret"
BASE_URL = "http://g1-private-host.example:9443"
ENTITIES = ("organizations", "employees", "customers", "deals", "projects", "support_tickets",
            "documents")
PRIVATE = (API_KEY, "g1-private-host", "9443", "/rest/customers", "/odoo/customers", "X-Api-Key")


def _script(*outcomes):
    """A transport answering each request with the next outcome (the last one repeats)."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        outcome = outcomes[min(len(requests), len(outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        status, headers = outcome
        return httpx.Response(status, headers=headers, json={"items": [], "status": status})

    return httpx.MockTransport(handler), requests


def _rest(monkeypatch, transport) -> RestConnector:
    monkeypatch.setenv("G1_REST_API_KEY", API_KEY)
    connector = RestConnector(RestConnectorConfig.from_dict({
        "source_name": "rest_mock", "source_type": "rest", "base_url": BASE_URL, "timeout": 5,
        "health_endpoint": "/health",
        "auth": {"mechanism": "api_key", "header_name": "X-Api-Key",
                 "env_var": "G1_REST_API_KEY"},
        "entities": {name: {"path": f"/rest/{name}", "description": name} for name in ENTITIES},
    }))
    connector._client = httpx.Client(base_url=BASE_URL, headers=connector._client.headers,
                                     transport=transport)
    return connector


def _odoo(transport) -> OdooMockConnector:
    connector = OdooMockConnector(OdooConnectorConfig.from_dict({
        "source_name": "odoo_mock", "source_type": "mock", "base_url": BASE_URL, "timeout": 5,
    }))
    connector._client = httpx.Client(base_url=BASE_URL, transport=transport)
    return connector


@pytest.fixture
def sleeps(monkeypatch, caplog):
    """Record each sleep with the number of retry events logged before it; never sleep."""
    recorded: list[tuple[float, int]] = []

    def sleep(seconds: float) -> None:
        recorded.append((seconds, len(_retry_events(caplog))))

    monkeypatch.setattr(rest.time, "sleep", sleep)
    monkeypatch.setattr(odoo.time, "sleep", sleep)
    caplog.set_level(logging.DEBUG, logger="app.connectors")
    return recorded


def _retry_events(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if getattr(record, "event", None) == "retry_scheduled"]


def _fields(caplog) -> list[dict]:
    return [record.event_fields for record in _retry_events(caplog)]


def _assert_private(caplog) -> None:
    rendered = caplog.text + "\n".join(JsonFormatter().format(r) for r in caplog.records)
    for private in PRIVATE:
        assert private not in rendered


# --- C5 REST ------------------------------------------------------------------------


@pytest.mark.parametrize("status", [502, 503, 504])
def test_rest_transient_errors_log_each_scheduled_retry_with_its_backoff(monkeypatch, caplog,
                                                                         sleeps, status):
    transport, requests = _script((status, {}))
    connector = _rest(monkeypatch, transport)
    with pytest.raises(ConnectorRequestError, match=str(status)):
        connector._get_json("/rest/customers")
    assert len(requests) == 3
    assert sleeps == [(0.5, 1), (1.0, 2)]
    assert _fields(caplog) == [
        {"source": "rest_mock", "attempt": 1, "max_attempts": 3, "delay_seconds": 0.5,
         "reason": f"http_{status}"},
        {"source": "rest_mock", "attempt": 2, "max_attempts": 3, "delay_seconds": 1.0,
         "reason": f"http_{status}"},
    ]
    assert {(r.name, r.levelno) for r in _retry_events(caplog)} == {
        ("app.connectors.rest", logging.WARNING)}
    assert all(request.headers["X-Api-Key"] == API_KEY for request in requests)
    _assert_private(caplog)


@pytest.mark.parametrize(("retry_after", "delay"), [
    ("2", 2.0), ("0.25", 0.25), ("30", 4.0), (None, 4.0), ("soon", 4.0),
])
def test_rest_rate_limits_log_the_delay_actually_slept(monkeypatch, caplog, sleeps,
                                                       retry_after, delay):
    headers = {} if retry_after is None else {"Retry-After": retry_after}
    transport, requests = _script((429, headers))
    with pytest.raises(ConnectorRequestError, match="Rate limited"):
        _rest(monkeypatch, transport)._get_json("/rest/customers")
    assert len(requests) == 3
    assert sleeps == [(delay, 1), (delay, 2)]
    assert [(f["attempt"], f["delay_seconds"], f["reason"]) for f in _fields(caplog)] == [
        (1, delay, "http_429"), (2, delay, "http_429")]
    _assert_private(caplog)


@pytest.mark.parametrize("error", [httpx.ConnectError("refused g1-private-host"),
                                   httpx.ReadTimeout("timed out g1-private-host")])
def test_rest_network_errors_log_the_exception_class(monkeypatch, caplog, sleeps, error):
    transport, requests = _script(error)
    with pytest.raises(ConnectorUnavailableError):
        _rest(monkeypatch, transport)._get_json("/rest/customers")
    assert len(requests) == 3
    assert sleeps == [(0.5, 1), (1.0, 2)]
    assert [(f["attempt"], f["reason"]) for f in _fields(caplog)] == [
        (1, type(error).__name__), (2, type(error).__name__)]
    _assert_private(caplog)


def test_rest_recovery_logs_only_the_retries_that_happened(monkeypatch, caplog, sleeps):
    transport, requests = _script((503, {}), (200, {}))
    assert _rest(monkeypatch, transport)._get_json("/rest/customers") == {
        "items": [], "status": 200}
    assert len(requests) == 2
    assert sleeps == [(0.5, 1)]
    assert [(f["attempt"], f["reason"]) for f in _fields(caplog)] == [(1, "http_503")]


@pytest.mark.parametrize(("status", "error"), [
    (500, ConnectorRequestError), (404, ConnectorRequestError), (400, ConnectorRequestError),
    (401, ConnectorAuthenticationError), (403, ConnectorAuthenticationError),
])
def test_rest_errors_that_are_not_retried_log_no_retry(monkeypatch, caplog, sleeps, status, error):
    transport, requests = _script((status, {}))
    with pytest.raises(error):
        _rest(monkeypatch, transport)._get_json("/rest/customers")
    assert (len(requests), sleeps, _retry_events(caplog)) == (1, [], [])


def test_rest_success_logs_nothing(monkeypatch, caplog, sleeps):
    transport, requests = _script((200, {}))
    _rest(monkeypatch, transport)._get_json("/rest/customers")
    assert (len(requests), sleeps, caplog.records) == (1, [], [])


def test_retry_events_render_as_structured_json(monkeypatch, caplog, sleeps):
    transport, _ = _script((503, {}), (200, {}))
    _rest(monkeypatch, transport)._get_json("/rest/customers")
    (record,) = _retry_events(caplog)
    payload = json.loads(JsonFormatter().format(record))
    payload.pop("timestamp")
    assert payload == {"level": "WARNING", "logger": "app.connectors.rest",
                       "event": "retry_scheduled", "source": "rest_mock", "attempt": 1,
                       "max_attempts": 3, "delay_seconds": 0.5, "reason": "http_503"}


# --- C4 Odoo mock -------------------------------------------------------------------


@pytest.mark.parametrize("error", [httpx.ConnectError("refused g1-private-host"),
                                   httpx.ConnectTimeout("timed out g1-private-host")])
def test_odoo_network_errors_log_each_scheduled_retry(caplog, sleeps, error):
    transport, requests = _script(error)
    with pytest.raises(ConnectorUnavailableError):
        _odoo(transport)._get_json("/odoo/customers")
    assert len(requests) == 3
    assert sleeps == [(0.5, 1), (0.5, 2)]
    assert _fields(caplog) == [
        {"source": "odoo_mock", "attempt": 1, "max_attempts": 3, "delay_seconds": 0.5,
         "reason": type(error).__name__},
        {"source": "odoo_mock", "attempt": 2, "max_attempts": 3, "delay_seconds": 0.5,
         "reason": type(error).__name__},
    ]
    assert {(r.name, r.levelno) for r in _retry_events(caplog)} == {
        ("app.connectors.odoo", logging.WARNING)}
    _assert_private(caplog)


def test_odoo_recovery_logs_only_the_retries_that_happened(caplog, sleeps):
    transport, requests = _script(httpx.ReadTimeout("slow"), (200, {}))
    assert _odoo(transport)._get_json("/odoo/customers") == {"items": [], "status": 200}
    assert len(requests) == 2
    assert sleeps == [(0.5, 1)]
    assert [(f["attempt"], f["reason"]) for f in _fields(caplog)] == [(1, "ReadTimeout")]


@pytest.mark.parametrize("status", [404, 500, 503])
def test_odoo_http_errors_are_not_retried_and_log_no_retry(caplog, sleeps, status):
    transport, requests = _script((status, {}))
    with pytest.raises(ConnectorRequestError):
        _odoo(transport)._get_json("/odoo/customers")
    assert (len(requests), sleeps, _retry_events(caplog)) == (1, [], [])
