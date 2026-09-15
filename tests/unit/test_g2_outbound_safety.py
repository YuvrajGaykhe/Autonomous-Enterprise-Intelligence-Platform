"""
G2 outbound request safety (spec Section 14).

app.core.security validates connector URLs, endpoint paths and timeouts, and
builds the read-only client every HTTP connector uses: GET only, same origin
only, no redirects. The Odoo mock and Generic REST connectors reject unsafe
configuration with messages that never quote the configured value, and their
clients refuse writes and other hosts before anything reaches the network.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import httpx
import pytest

from app.connectors import registry
from app.connectors.odoo import OdooConnectorConfig, OdooMockConnector
from app.connectors.rest import RestConnector, RestConnectorConfig
from app.connectors.types import ConnectorConfigurationError
from app.core import security
from app.core.security import (
    MAX_TIMEOUT_SECONDS,
    OutboundRequestRefused,
    SecurityConstraintError,
    UnsafeConfigurationError,
    read_only_client,
    validate_base_url,
    validate_request_path,
    validate_timeout,
)

REPO = Path(__file__).resolve().parents[2]
# Synthetic, clearly fake credential that must never appear in an error message.
CANARY = "g2-synthetic-credential-canary"
# TEST-NET-1 (RFC 5737): never routable, so a request that escaped a guard fails loudly.
BASE_URL = "http://192.0.2.1:9"
ENTITIES = ("organizations", "employees", "customers", "deals", "projects", "support_tickets",
            "documents")

EMPTY = "must be a non-empty string"
SPACE = "must not contain whitespace or control characters"
SCHEME = "must be an http or https URL"
HOST = "must include a host"
CREDENTIALS = "must not embed credentials; supply them through environment variables"
QUERY = "must not include a query string or fragment"
INVALID = "is not a valid URL"
PORT = "must use a port from 1 to 65535"
SINGLE_SLASH = "must be a path starting with a single '/'"
BACKSLASH = "must not contain backslashes"
DOTDOT = "must not contain '..' segments"
TIMEOUT = "must be a finite number of seconds greater than 0 and at most 300"


def _rest_config(**overrides: object) -> dict[str, object]:
    return {"source_name": "rest_mock", "source_type": "rest", "base_url": BASE_URL,
            "timeout": 5, "health_endpoint": "/health", "auth": {"mechanism": "none"},
            "entities": {name: {"path": f"/rest/{name}"} for name in ENTITIES}, **overrides}


def _odoo_config(**overrides: object) -> dict[str, object]:
    return {"source_name": "odoo_mock", "source_type": "mock", "base_url": BASE_URL,
            "timeout": 5, **overrides}


def _recording(client: httpx.Client, status: int = 200, headers: dict | None = None):
    """Route the client's real send path (event hooks included) to an in-memory transport."""
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(status, headers=headers, json={"ok": True})

    client._transport = httpx.MockTransport(handler)
    return sent


# --- base_url -------------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "http://localhost:8080", "https://mock-source:8080/api", "http://localhost:8080/",
    "HTTP://MOCK-SOURCE", "http://[::1]:8080", "http://mock-source:8080/odoo/v1",
    "http://localhost:1", "https://localhost:65535",
])
def test_safe_base_urls_are_returned_unchanged(url):
    assert validate_base_url(url) == url


@pytest.mark.parametrize(("value", "message"), [
    (None, EMPTY), ("", EMPTY), (8080, EMPTY), (b"http://localhost", EMPTY),
    (" http://localhost", SPACE), ("http://local host", SPACE), ("http://localhost\n", SPACE),
    ("http://localhost\t", SPACE), ("http://localhost\x00", SPACE), ("http://localhost\x7f", SPACE),
    ("not-a-url", SCHEME), ("ftp://localhost", SCHEME), ("httpfoo://localhost", SCHEME),
    ("file:///etc/passwd", SCHEME), ("localhost:8080", SCHEME),
    ("http://", HOST), ("http:/localhost", HOST), ("http://:8080", HOST),
    ("http://user:pw@localhost", CREDENTIALS), ("https://token@localhost:8443", CREDENTIALS),
    ("http://localhost?", QUERY), ("http://localhost/?key=1", QUERY), ("http://localhost#top", QUERY),
    ("http://localhost:notaport", INVALID), ("http://[::1", INVALID),
    ("http://localhost:0", PORT), ("http://localhost:65536", PORT), ("http://localhost:-1", PORT),
    ("http://localhost:99999999", PORT),
])
def test_unsafe_base_urls_are_rejected_by_rule(value, message):
    with pytest.raises(UnsafeConfigurationError) as caught:
        validate_base_url(value)
    assert str(caught.value) == message


@pytest.mark.parametrize("url", [
    f"http://user:{CANARY}@localhost", f"http://{CANARY}@localhost", f"http://localhost/?token={CANARY}",
    f"http://localhost#{CANARY}", f"ftp://{CANARY}", f"http://local {CANARY}",
    f"http://localhost:{CANARY}",
])
def test_rejections_never_quote_the_url(url):
    with pytest.raises(UnsafeConfigurationError) as caught:
        validate_base_url(url)
    assert CANARY not in str(caught.value)
    assert caught.value.__cause__ is None


def test_security_errors_share_a_base_and_configuration_errors_are_value_errors():
    assert issubclass(UnsafeConfigurationError, SecurityConstraintError)
    assert issubclass(UnsafeConfigurationError, ValueError)
    assert issubclass(OutboundRequestRefused, SecurityConstraintError)
    assert not issubclass(OutboundRequestRefused, ValueError)


# --- endpoint paths -------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/health", "/rest/customers", "/a/b.c/d", "/a..b",
                                  "/a/.../b", "/rest/support_tickets"])
def test_safe_paths_are_returned_unchanged(path):
    assert validate_request_path(path) == path


@pytest.mark.parametrize(("value", "message"), [
    (None, EMPTY), ("", EMPTY), (5, EMPTY),
    ("/rest customers", SPACE), ("/health\n", SPACE), ("/x\x00", SPACE),
    ("rest/customers", SINGLE_SLASH), ("http://attacker.example/x", SINGLE_SLASH),
    ("//attacker.example/x", SINGLE_SLASH), ("health", SINGLE_SLASH),
    ("/a\\b", BACKSLASH), ("\\/x", SINGLE_SLASH),
    ("/customers?limit=1", QUERY), ("/customers#x", QUERY),
    ("/a/../b", DOTDOT), ("/..", DOTDOT), ("/rest/..", DOTDOT),
])
def test_unsafe_paths_are_rejected_by_rule(value, message):
    with pytest.raises(UnsafeConfigurationError) as caught:
        validate_request_path(value)
    assert str(caught.value) == message


def test_path_rejections_never_quote_the_path():
    for path in (f"http://{CANARY}/x", f"/x?token={CANARY}", f"/{CANARY}/../x", f"/{CANARY} x"):
        with pytest.raises(UnsafeConfigurationError) as caught:
            validate_request_path(path)
        assert CANARY not in str(caught.value)


# --- timeouts -------------------------------------------------------------------------


@pytest.mark.parametrize(("value", "seconds"), [
    (10, 10.0), (0.5, 0.5), ("10", 10.0), (" 2.5 ", 2.5), (300, 300.0), (MAX_TIMEOUT_SECONDS, 300.0),
    (0.001, 0.001),
])
def test_finite_positive_bounded_timeouts_are_accepted(value, seconds):
    result = validate_timeout(value)
    assert result == seconds and type(result) is float


@pytest.mark.parametrize("value", [
    0, 0.0, -1, "-1", 300.0001, 301, math.nan, math.inf, -math.inf, "inf", "nan", True, False,
    None, "abc", "", [5], {"seconds": 5},
])
def test_unbounded_or_non_numeric_timeouts_are_rejected(value):
    with pytest.raises(UnsafeConfigurationError) as caught:
        validate_timeout(value)
    assert str(caught.value) == TIMEOUT


def test_the_timeout_bound_is_five_minutes():
    assert MAX_TIMEOUT_SECONDS == 300.0


# --- read-only client -----------------------------------------------------------------


def test_the_client_uses_the_configuration_and_never_follows_redirects():
    client = read_only_client("http://mock-source:8080", 7, {"X-Api-Key": "k"})
    assert client.base_url == httpx.URL("http://mock-source:8080")
    assert client.timeout == httpx.Timeout(7.0)
    assert client.headers["X-Api-Key"] == "k"
    assert client.follow_redirects is False


def test_the_client_validates_its_arguments():
    with pytest.raises(UnsafeConfigurationError, match=CREDENTIALS):
        read_only_client(f"http://user:{CANARY}@localhost", 5)
    with pytest.raises(UnsafeConfigurationError, match="finite number"):
        read_only_client("http://localhost", math.inf)


def test_get_requests_to_the_configured_origin_are_sent():
    client = read_only_client(BASE_URL + "/api", 5)
    sent = _recording(client)
    assert client.get("/rest/customers", params={"limit": 1}).status_code == 200
    assert client.get(BASE_URL + "/api/health").status_code == 200
    assert [str(request.url) for request in sent] == [
        "http://192.0.2.1:9/api/rest/customers?limit=1", "http://192.0.2.1:9/api/health"]


def test_method_names_are_normalised_by_httpx_before_the_guard_sees_them():
    client = read_only_client(BASE_URL, 5)
    sent = _recording(client)
    client.request("get", "/rest/customers")
    with pytest.raises(OutboundRequestRefused, match="^POST requests are not allowed"):
        client.request("post", "/rest/customers")
    assert [request.method for request in sent] == ["GET"]


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"])
def test_every_method_other_than_get_is_refused_before_sending(method):
    client = read_only_client(BASE_URL, 5)
    sent = _recording(client)
    with pytest.raises(OutboundRequestRefused) as caught:
        client.request(method, "/rest/customers")
    assert str(caught.value) == \
        f"{method} requests are not allowed; source connectors are read-only"
    assert sent == []


@pytest.mark.parametrize("target", [
    "http://attacker.example/x", "https://192.0.2.1:9/x", "http://192.0.2.1:10/x",
    "http://192.0.2.1/x", "http://192.0.2.2:9/x",
])
def test_requests_to_another_origin_are_refused_before_sending(target):
    client = read_only_client(BASE_URL, 5)
    sent = _recording(client)
    with pytest.raises(OutboundRequestRefused) as caught:
        client.get(target)
    assert str(caught.value) == "request target is outside the configured base_url origin"
    assert "attacker" not in str(caught.value) and "192.0.2" not in str(caught.value)
    assert sent == []


def test_redirects_are_returned_not_followed():
    client = read_only_client(BASE_URL, 5)
    sent = _recording(client, 302, {"Location": "http://attacker.example/steal"})
    response = client.get("/rest/customers")
    assert response.status_code == 302
    assert len(sent) == 1


def test_security_module_has_no_connector_or_application_dependencies():
    source = security.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "from app." not in text and "import app." not in text


# --- connectors -----------------------------------------------------------------------


@pytest.mark.parametrize("config_class", [OdooConnectorConfig, RestConnectorConfig])
@pytest.mark.parametrize(("url", "rule"), [
    (f"http://user:{CANARY}@localhost", CREDENTIALS), (f"http://localhost/?key={CANARY}", QUERY),
    (f"ftp://{CANARY}", SCHEME), ("http://", HOST), (["http://localhost"], EMPTY),
])
def test_connectors_reject_unsafe_base_urls_without_quoting_them(config_class, url, rule):
    factory = _odoo_config if config_class is OdooConnectorConfig else _rest_config
    with pytest.raises(ConnectorConfigurationError) as caught:
        config_class.from_dict(factory(base_url=url))
    assert str(caught.value) == f"Invalid base_url: {rule}"
    assert CANARY not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


@pytest.mark.parametrize("config_class", [OdooConnectorConfig, RestConnectorConfig])
@pytest.mark.parametrize("timeout", [math.nan, math.inf, True, 0, 301, "soon"])
def test_connectors_reject_unbounded_timeouts(config_class, timeout):
    factory = _odoo_config if config_class is OdooConnectorConfig else _rest_config
    with pytest.raises(ConnectorConfigurationError) as caught:
        config_class.from_dict(factory(timeout=timeout))
    assert str(caught.value) == f"Invalid timeout: {TIMEOUT}"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


@pytest.mark.parametrize("config_class", [OdooConnectorConfig, RestConnectorConfig])
def test_connectors_keep_accepting_their_existing_configuration(config_class):
    factory = _odoo_config if config_class is OdooConnectorConfig else _rest_config
    config = config_class.from_dict(factory(base_url="http://mock-source:8080/", timeout="10"))
    assert (config.base_url, config.timeout) == ("http://mock-source:8080", 10.0)


@pytest.mark.parametrize(("endpoint", "rule"), [
    ("http://attacker.example/health", SINGLE_SLASH), ("health", SINGLE_SLASH),
    ("/health?probe=1", QUERY), ("/../health", DOTDOT),
])
def test_rest_rejects_unsafe_health_endpoints(endpoint, rule):
    with pytest.raises(ConnectorConfigurationError) as caught:
        RestConnectorConfig.from_dict(_rest_config(health_endpoint=endpoint))
    assert str(caught.value) == f"Invalid health_endpoint: {rule}"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


@pytest.mark.parametrize(("path", "rule"), [
    (f"http://{CANARY}.example/customers", SINGLE_SLASH), ("//attacker.example/c", SINGLE_SLASH),
    ("/rest/customers?all=1", QUERY), ("/rest/../admin", DOTDOT), ("/rest\\customers", BACKSLASH),
])
def test_rest_rejects_unsafe_entity_paths(path, rule):
    entities = {"customers": {"path": "/rest/customers"}, "deals": {"path": path}}
    with pytest.raises(ConnectorConfigurationError) as caught:
        RestConnectorConfig.from_dict(_rest_config(entities=entities))
    assert str(caught.value) == f"Entity 'deals' has an invalid path: {rule}"
    assert CANARY not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def _connectors(monkeypatch):
    monkeypatch.setenv("G2_REST_API_KEY", CANARY)
    rest = RestConnector(RestConnectorConfig.from_dict(_rest_config(
        auth={"mechanism": "api_key", "header_name": "X-Api-Key", "env_var": "G2_REST_API_KEY"})))
    odoo = OdooMockConnector(OdooConnectorConfig.from_dict(_odoo_config()))
    return {"rest": rest, "odoo": odoo}


@pytest.mark.parametrize("name", ["rest", "odoo"])
def test_connector_clients_refuse_writes_and_other_hosts(monkeypatch, name):
    connector = _connectors(monkeypatch)[name]
    sent = _recording(connector._client)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        with pytest.raises(OutboundRequestRefused):
            connector._client.request(method, "/rest/customers")
    with pytest.raises(OutboundRequestRefused):
        connector._client.get("http://attacker.example/health")
    assert sent == []
    assert connector._client.follow_redirects is False
    assert connector._client.timeout == httpx.Timeout(5.0)


def test_rest_client_still_sends_its_credential_header_to_the_source(monkeypatch):
    connector = _connectors(monkeypatch)["rest"]
    sent = _recording(connector._client)
    connector._client.get("/rest/customers")
    assert sent[0].headers["X-Api-Key"] == CANARY
    assert str(sent[0].url) == "http://192.0.2.1:9/rest/customers"


@pytest.mark.parametrize("name", ["rest", "odoo"])
def test_connector_health_checks_go_through_the_guarded_client(monkeypatch, name):
    connector = _connectors(monkeypatch)[name]
    sent = _recording(connector._client)
    connector.health_check()
    assert [(request.method, request.url.path) for request in sent] == [("GET", "/health")]


@pytest.mark.parametrize("source", ["odoo_mock", "rest_mock"])
def test_committed_http_source_configurations_pass_validation(source):
    connector = registry.build_connector(source)
    assert connector._client.follow_redirects is False
    assert connector._client.base_url == httpx.URL("http://mock-source:8080")


@pytest.mark.parametrize("source", ["odoo_mock", "rest_mock"])
def test_registry_base_url_overrides_are_validated(source):
    with pytest.raises(ConnectorConfigurationError) as caught:
        registry.build_connector(source, base_url=f"http://operator:{CANARY}@localhost:8080")
    assert str(caught.value) == f"Invalid base_url: {CREDENTIALS}"


@pytest.mark.parametrize("source", ["odoo_mock", "rest_mock"])
def test_ingest_demo_rejects_credential_urls_without_printing_them(capsys, source):
    spec = importlib.util.spec_from_file_location("ingest_demo_g2", REPO / "scripts" / "ingest_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    status = module.main(["--source", source, "--base-url", f"http://operator:{CANARY}@localhost:8080"])
    captured = capsys.readouterr()
    assert status == 2
    assert f"Invalid base_url: {CREDENTIALS}" in captured.err
    assert CANARY not in captured.out + captured.err
