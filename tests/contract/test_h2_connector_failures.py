"""
H2 connector failure and configuration contract.

The contract a connector owes Layer 1 is not only "what it returns when the
source answers" but "how it fails when the source does not". Spec Section 15
requires connector contract coverage, and Section 5 fixes the failure
vocabulary every connector shares:

    ConnectorConfigurationError  the configuration cannot be used at all
    ConnectorEntityError         the entity type or record does not exist
    ConnectorRequestError        the source answered, but not usably
    ConnectorUnavailableError    the source could not be reached

These tests drive each connector into those states with real, badly-behaved
sources: configuration files that are not usable, a CSV tree that has been
tampered with, and an HTTP server that answers with the wrong status, the
wrong shape, or not at all.

No assertion here quotes a configured value: rejection messages name the
broken rule, because a base_url or an environment variable may carry a
credential (G2).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.connectors.csv import CsvConnector, CsvConnectorConfig
from app.connectors.odoo import OdooConnectorConfig, OdooMockConnector
from app.connectors.rest import RestConnector, RestConnectorConfig
from app.connectors.types import (
    ConnectorConfigurationError,
    ConnectorEntityError,
    ConnectorRequestError,
    ConnectorUnavailableError,
)

pytestmark = pytest.mark.contract


# ---------------------------------------------------------------------------
# A canned-response source
# ---------------------------------------------------------------------------


class CannedHandler(BaseHTTPRequestHandler):
    """Serves exactly what a test registers for a path, however malformed."""

    #: path (without query) -> (status, body bytes, content type)
    routes: dict[str, tuple[int, bytes, str]] = {}

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming
        path = self.path.split("?")[0]
        status, body, content_type = self.routes.get(
            path, (404, b'{"error": "not found"}', "application/json")
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output clean."""


@pytest.fixture
def canned() -> Iterator[str]:
    """A source that answers with whatever the test registers."""
    CannedHandler.routes = {}
    server = HTTPServer(("127.0.0.1", 0), CannedHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        CannedHandler.routes = {}


def route(path: str, status: int = 200, body: object = None, *, raw: bytes | None = None) -> None:
    payload = raw if raw is not None else json.dumps(body).encode("utf-8")
    CannedHandler.routes[path] = (status, payload, "application/json")


def odoo_at(base_url: str) -> OdooMockConnector:
    return OdooMockConnector(OdooConnectorConfig.from_dict({
        "source_name": "odoo_mock", "source_type": "mock",
        "base_url": base_url, "timeout": 5,
    }))


def rest_at(base_url: str, **overrides: object) -> RestConnector:
    config = {
        "source_name": "rest_mock", "source_type": "rest",
        "base_url": base_url, "timeout": 5, "health_endpoint": "/health",
        "auth": {"mechanism": "none"},
        "entities": {"customers": {"path": "/rest/customers"}},
    }
    config.update(overrides)
    return RestConnector(RestConnectorConfig.from_dict(config))


def a_dead_port() -> str:
    """A port nothing is listening on."""
    probe = HTTPServer(("127.0.0.1", 0), CannedHandler)
    port = probe.server_address[1]
    probe.server_close()
    return f"http://127.0.0.1:{port}"


# ---------------------------------------------------------------------------
# CSV configuration
# ---------------------------------------------------------------------------


def _write_yaml(tmp_path, text: str):
    path = tmp_path / "csv_demo.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_csv_configuration_file_must_hold_a_mapping(tmp_path):
    with pytest.raises(ConnectorConfigurationError, match="must be a YAML mapping"):
        CsvConnectorConfig.from_yaml(_write_yaml(tmp_path, "- not\n- a mapping\n"))


def test_an_unparseable_csv_configuration_file_is_refused(tmp_path):
    with pytest.raises(ConnectorConfigurationError, match="Failed to parse configuration"):
        CsvConnectorConfig.from_yaml(_write_yaml(tmp_path, "entities: [unclosed\n"))


def test_a_missing_csv_configuration_file_is_refused(tmp_path):
    with pytest.raises(ConnectorConfigurationError, match="not found"):
        CsvConnectorConfig.from_yaml(tmp_path / "absent.yaml")


def test_csv_entities_must_be_a_mapping(tmp_path):
    config = "source_name: csv_demo\ndata_directory: data/demo\nentities:\n  - customers\n"
    with pytest.raises(ConnectorConfigurationError, match="'entities' must be a mapping"):
        CsvConnectorConfig.from_yaml(_write_yaml(tmp_path, config))


def test_each_csv_entity_must_be_a_mapping(tmp_path):
    config = ("source_name: csv_demo\ndata_directory: data/demo\n"
              "entities:\n  customers: customers.csv\n")
    with pytest.raises(ConnectorConfigurationError, match="configuration must be a mapping"):
        CsvConnectorConfig.from_yaml(_write_yaml(tmp_path, config))


@pytest.mark.parametrize(
    "entity_cfg",
    ["{}", "{file: customers.csv}", "{id_column: customer_id}",
     "{file: '', id_column: customer_id}", "{file: customers.csv, id_column: ''}"],
)
def test_a_csv_entity_needs_both_a_file_and_an_id_column(tmp_path, entity_cfg):
    config = ("source_name: csv_demo\ndata_directory: data/demo\n"
              f"entities:\n  customers: {entity_cfg}\n")
    with pytest.raises(ConnectorConfigurationError, match="requires 'file' and 'id_column'"):
        CsvConnectorConfig.from_yaml(_write_yaml(tmp_path, config))


def test_the_committed_csv_configuration_loads(tmp_path):
    """The rejections above must not be the only thing from_yaml can do."""
    from app.connectors.registry import CONNECTOR_CONFIG_DIR

    config = CsvConnectorConfig.from_yaml(CONNECTOR_CONFIG_DIR / "csv_demo.yaml")
    assert sorted(config.entities) == [
        "customers", "deals", "documents", "employees",
        "organizations", "projects", "support_tickets",
    ]


# ---------------------------------------------------------------------------
# CSV runtime failures
# ---------------------------------------------------------------------------


def _csv_connector(directory) -> CsvConnector:
    return CsvConnector(CsvConnectorConfig.from_dict({
        "source_name": "csv_demo", "source_type": "csv",
        "data_directory": str(directory),
        "entities": {"customers": {"file": "customers.csv", "id_column": "customer_id"}},
    }))


def test_a_missing_data_directory_is_unhealthy_rather_than_fatal(tmp_path):
    """Health reports the problem; it does not raise (spec Section 16)."""
    health = _csv_connector(tmp_path / "absent").health_check()
    assert health.healthy is False
    assert "not found" in health.message


def test_a_data_path_that_is_not_a_directory_is_unhealthy(tmp_path):
    """A file where a directory belongs is a configuration fault, reported."""
    path = tmp_path / "demo"
    path.write_text("not a directory", encoding="utf-8")
    health = _csv_connector(path).health_check()
    assert health.healthy is False
    assert "not a directory" in health.message


def test_a_source_path_that_is_not_a_regular_file_is_refused(tmp_path):
    """G2 import safety: a directory named like the CSV is refused at read."""
    (tmp_path / "customers.csv").mkdir()
    with pytest.raises(ConnectorRequestError, match="was refused: is not a regular file"):
        _csv_connector(tmp_path).fetch_entities("customers", None, 10)


def test_an_undecodable_source_file_is_a_request_error(tmp_path):
    """Bytes that are not UTF-8 are refused, not silently mangled."""
    (tmp_path / "customers.csv").write_bytes(b"customer_id\n\xff\xfe\x00bad\n")
    with pytest.raises(ConnectorRequestError, match="Failed to read CSV file"):
        _csv_connector(tmp_path).fetch_entities("customers", None, 10)


def test_an_unconfigured_entity_is_refused_before_any_file_is_touched(tmp_path):
    with pytest.raises(ConnectorEntityError, match="is not configured"):
        _csv_connector(tmp_path).get_entity("deals", "DEAL-001")


def test_a_negative_cursor_offset_is_refused(tmp_path):
    (tmp_path / "customers.csv").write_text("customer_id\nCUST-001\n", encoding="utf-8")
    with pytest.raises(ConnectorRequestError, match="non-negative"):
        _csv_connector(tmp_path).fetch_entities("customers", "-5", 10)


# ---------------------------------------------------------------------------
# Odoo configuration
# ---------------------------------------------------------------------------


def test_an_odoo_configuration_file_must_hold_a_mapping(tmp_path):
    path = tmp_path / "odoo.yaml"
    path.write_text("- not a mapping\n", encoding="utf-8")
    with pytest.raises(ConnectorConfigurationError, match="must be a YAML mapping"):
        OdooConnectorConfig.from_yaml(path)


def test_an_unparseable_odoo_configuration_file_is_refused(tmp_path):
    path = tmp_path / "odoo.yaml"
    path.write_text("base_url: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConnectorConfigurationError, match="Failed to parse configuration"):
        OdooConnectorConfig.from_yaml(path)


# ---------------------------------------------------------------------------
# Odoo runtime failures
# ---------------------------------------------------------------------------


def test_an_odoo_health_check_reports_an_error_status(canned):
    route("/health", status=503, body={"status": "down"})
    health = odoo_at(canned).health_check()
    assert health.healthy is False
    assert "HTTP 503" in health.message


def test_an_odoo_health_check_reports_malformed_json(canned):
    route("/health", raw=b"not json at all")
    health = odoo_at(canned).health_check()
    assert health.healthy is False
    assert "malformed JSON" in health.message


def test_an_odoo_health_check_reports_an_unreachable_source():
    health = odoo_at(a_dead_port()).health_check()
    assert health.healthy is False
    assert health.message


def test_an_odoo_health_check_never_raises(canned, monkeypatch):
    """Any unexpected client failure becomes an unhealthy report."""
    connector = odoo_at(canned)
    monkeypatch.setattr(connector._client, "get",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    health = connector.health_check()
    assert health.healthy is False
    assert health.latency_ms is not None


def test_odoo_refuses_a_collection_whose_data_is_not_a_list(canned):
    route("/odoo/customers", body={
        "data": {"id": 1},
        "pagination": {"offset": 0, "limit": 10, "total": 1, "has_more": False},
    })
    with pytest.raises(ConnectorRequestError, match="Expected 'data' to be a list"):
        odoo_at(canned).fetch_entities("customers", None, 10)


def test_odoo_refuses_a_collection_missing_pagination(canned):
    route("/odoo/customers", body={"data": []})
    with pytest.raises(ConnectorRequestError, match="missing 'data' or 'pagination'"):
        odoo_at(canned).fetch_entities("customers", None, 10)


def test_odoo_refuses_incomplete_pagination(canned):
    route("/odoo/customers", body={"data": [], "pagination": {"offset": 0}})
    with pytest.raises(ConnectorRequestError, match="missing fields"):
        odoo_at(canned).fetch_entities("customers", None, 10)


def test_odoo_derives_a_cursor_when_the_source_omits_next_offset(canned):
    """has_more without next_offset still advances, from offset + page length."""
    route("/odoo/organizations", body={
        "data": [{"id": 1, "name": "Acme Corp", "industry_id": None,
                  "country_id": None, "active": True, "write_date": None}],
        "pagination": {"offset": 0, "limit": 1, "total": 5, "has_more": True},
    })
    page = odoo_at(canned).fetch_entities("organizations", None, 1)
    assert page.has_more is True
    assert page.next_cursor == "1"


def test_odoo_reraises_a_non_404_error_from_a_record_lookup(canned):
    """Only 404 means "no such record"; anything else stays a request error."""
    route("/odoo/customers/1", status=500, body={"error": "boom"})
    with pytest.raises(ConnectorRequestError) as exc:
        odoo_at(canned).get_entity("customers", "1")
    assert not isinstance(exc.value, ConnectorEntityError)


def test_odoo_refuses_a_record_missing_its_data_envelope(canned):
    route("/odoo/customers/1", body={"result": {}})
    with pytest.raises(ConnectorRequestError, match="missing 'data'"):
        odoo_at(canned).get_entity("customers", "1")


def test_odoo_refuses_a_record_that_fails_its_source_schema(canned):
    """A payload that is not an Odoo customer is refused, not passed on."""
    route("/odoo/customers/1", body={"data": {"unexpected": "shape"}})
    with pytest.raises(ConnectorRequestError, match="Malformed customers payload"):
        odoo_at(canned).get_entity("customers", "1")


def test_odoo_refuses_malformed_json_from_a_data_endpoint(canned):
    route("/odoo/customers", raw=b"{not json")
    with pytest.raises(ConnectorRequestError, match="Malformed JSON"):
        odoo_at(canned).fetch_entities("customers", None, 10)


def test_odoo_reports_an_unexpected_client_failure_as_unavailable(canned, monkeypatch):
    connector = odoo_at(canned)
    monkeypatch.setattr(connector._client, "get",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(ConnectorUnavailableError, match="Unexpected error"):
        connector.fetch_entities("customers", None, 10)


# ---------------------------------------------------------------------------
# REST configuration
# ---------------------------------------------------------------------------


def test_a_rest_configuration_file_must_hold_a_mapping(tmp_path):
    path = tmp_path / "rest.yaml"
    path.write_text("- not a mapping\n", encoding="utf-8")
    with pytest.raises(ConnectorConfigurationError, match="must be a YAML mapping"):
        RestConnectorConfig.from_yaml(path)


def test_an_unparseable_rest_configuration_file_is_refused(tmp_path):
    path = tmp_path / "rest.yaml"
    path.write_text("entities: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConnectorConfigurationError, match="Failed to parse configuration"):
        RestConnectorConfig.from_yaml(path)


def test_rest_entities_must_be_a_mapping(canned):
    with pytest.raises(ConnectorConfigurationError, match="'entities' must be a mapping"):
        rest_at(canned, entities=["customers"])


def test_each_rest_entity_must_be_a_mapping(canned):
    with pytest.raises(ConnectorConfigurationError, match="configuration must be a mapping"):
        rest_at(canned, entities={"customers": "/rest/customers"})


def test_a_rest_entity_needs_a_path(canned):
    with pytest.raises(ConnectorConfigurationError, match="requires a 'path'"):
        rest_at(canned, entities={"customers": {"description": "no path"}})


def test_a_non_mapping_auth_section_falls_back_to_no_authentication(canned):
    """A malformed auth block must not silently become partial credentials."""
    connector = rest_at(canned, auth="bearer")
    assert connector._config.auth.mechanism == "none"


# ---------------------------------------------------------------------------
# REST authentication
# ---------------------------------------------------------------------------


def test_a_credential_mechanism_without_an_env_var_is_refused(canned, monkeypatch):
    """Construction defers the error; the first request raises it."""
    connector = rest_at(canned, auth={"mechanism": "bearer"})
    with pytest.raises(ConnectorConfigurationError, match="requires 'env_var'"):
        connector.fetch_entities("customers", None, 10)


def test_a_missing_credential_environment_variable_is_refused(canned, monkeypatch):
    monkeypatch.delenv("H2_TEST_TOKEN", raising=False)
    connector = rest_at(canned, auth={"mechanism": "bearer", "env_var": "H2_TEST_TOKEN"})
    with pytest.raises(ConnectorConfigurationError) as exc:
        connector.fetch_entities("customers", None, 10)
    assert "H2_TEST_TOKEN" in str(exc.value)


def test_a_credential_that_appears_before_the_first_request_is_used(canned, monkeypatch):
    """Deferred auth resolves once the environment provides the credential."""
    monkeypatch.delenv("H2_TEST_TOKEN", raising=False)
    connector = rest_at(canned, auth={"mechanism": "bearer", "env_var": "H2_TEST_TOKEN"})
    monkeypatch.setenv("H2_TEST_TOKEN", "synthetic-token-value")
    route("/rest/customers", body={
        "data": [], "pagination": {"offset": 0, "limit": 10, "total": 0, "has_more": False},
    })
    assert connector.fetch_entities("customers", None, 10).items == []
    assert connector._client.headers["Authorization"].startswith("Bearer ")


def test_a_credential_is_never_written_into_the_configuration(canned, monkeypatch):
    """Credentials come from the environment, never from the config object."""
    monkeypatch.setenv("H2_TEST_TOKEN", "synthetic-token-value")
    connector = rest_at(canned, auth={"mechanism": "bearer", "env_var": "H2_TEST_TOKEN"})
    assert "synthetic-token-value" not in repr(connector._config)


# ---------------------------------------------------------------------------
# REST runtime failures
# ---------------------------------------------------------------------------


def test_a_rest_health_check_reports_malformed_json(canned):
    route("/health", raw=b"<html>down</html>")
    health = rest_at(canned).health_check()
    assert health.healthy is False


def test_a_rest_health_check_reports_an_unreachable_source():
    health = rest_at(a_dead_port()).health_check()
    assert health.healthy is False


def test_a_rest_health_check_never_raises(canned, monkeypatch):
    connector = rest_at(canned)
    monkeypatch.setattr(connector._client, "get",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    health = connector.health_check()
    assert health.healthy is False
    assert health.latency_ms is not None


def test_rest_refuses_a_collection_whose_data_is_not_a_list(canned):
    route("/rest/customers", body={
        "data": {"id": "CUST-001"},
        "pagination": {"offset": 0, "limit": 10, "total": 1, "has_more": False},
    })
    with pytest.raises(ConnectorRequestError):
        rest_at(canned).fetch_entities("customers", None, 10)


def test_rest_derives_a_cursor_when_the_source_omits_next_offset(canned):
    route("/rest/customers", body={
        "data": [{"id": "CUST-001", "name": "Acme Industries", "email": None,
                  "segment": None, "industry": None, "ownerId": None,
                  "status": "active", "createdAt": None, "isActive": True}],
        "pagination": {"offset": 0, "limit": 1, "total": 5, "has_more": True},
    })
    page = rest_at(canned).fetch_entities("customers", None, 1)
    assert page.has_more is True
    assert page.next_cursor == "1"


def test_rest_reraises_a_non_404_error_from_a_record_lookup(canned):
    route("/rest/customers/CUST-001", status=500, body={"error": "boom"})
    with pytest.raises(ConnectorRequestError) as exc:
        rest_at(canned).get_entity("customers", "CUST-001")
    assert not isinstance(exc.value, ConnectorEntityError)


def test_rest_refuses_a_record_that_fails_its_source_schema(canned):
    route("/rest/customers/CUST-001", body={"data": {"unexpected": "shape"}})
    with pytest.raises(ConnectorRequestError):
        rest_at(canned).get_entity("customers", "CUST-001")


def test_rest_refuses_malformed_json_from_a_data_endpoint(canned):
    route("/rest/customers", raw=b"{not json")
    with pytest.raises(ConnectorRequestError, match="Malformed JSON"):
        rest_at(canned).fetch_entities("customers", None, 10)


def test_rest_reports_an_unexpected_client_failure_as_unavailable(canned, monkeypatch):
    connector = rest_at(canned)
    monkeypatch.setattr(connector._client, "get",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(ConnectorUnavailableError, match="Unexpected error"):
        connector.fetch_entities("customers", None, 10)


def test_an_unreachable_source_is_unavailable_from_both_http_connectors():
    """The same network condition maps to the same class from both."""
    dead = a_dead_port()
    for connector in (odoo_at(dead), rest_at(dead)):
        with pytest.raises(ConnectorUnavailableError):
            connector.fetch_entities("customers", None, 10)
