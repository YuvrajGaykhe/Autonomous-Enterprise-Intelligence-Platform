"""
F1 connector registry, connector provider and /api/v1/sources routes (no database).
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from http.server import HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.connectors import ConnectorProvider, UnknownSourceError
from app.connectors import (
    ConnectorCapabilities,
    ConnectorConfigurationError,
    ConnectorHealth,
    ConnectorUnavailableError,
    CsvConnector,
    OdooMockConnector,
    Page,
    RestConnector,
    registry,
)
from app.main import create_app

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
ALL_ENTITIES = ["customers", "deals", "documents", "employees", "organizations", "projects",
                "support_tickets"]
SOURCES = ("csv_demo", "odoo_mock", "rest_mock")

sys.path.insert(0, str(REPO / "docker"))
import mock_source  # noqa: E402


def _load_ingest_demo():
    spec = importlib.util.spec_from_file_location("ingest_demo_f1", REPO / "scripts" / "ingest_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeConnector:
    source_type = "fake"

    def __init__(self, *, health=None, raises=None, supports_health_check=True) -> None:
        self.source_name = "csv_demo"
        self._health = health
        self._raises = raises
        self._supports_health_check = supports_health_check
        self.health_calls = 0

    def health_check(self):
        self.health_calls += 1
        if self._raises is not None:
            raise self._raises
        return self._health

    def list_entities(self):
        return []

    def fetch_entities(self, entity_type, cursor=None, page_size=100):
        return Page()

    def get_entity(self, entity_type, source_id):
        return {}

    def capabilities(self):
        return ConnectorCapabilities(supported_entity_types=["customers"],
                                     supports_health_check=self._supports_health_check)


def _client(build=registry.build_connector, sources=SOURCES) -> TestClient:
    app = create_app(sessions=sessionmaker(), connectors=ConnectorProvider(build, sources))
    return TestClient(app, raise_server_exceptions=False)


def _fake_client(connector: FakeConnector) -> TestClient:
    return _client(lambda source: connector, ("csv_demo",))


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


# --- registry ----------------------------------------------------------------


def test_registry_maps_the_three_committed_sources_to_existing_files():
    assert registry.SOURCE_CONFIG_FILES == {"csv_demo": "csv_demo.yaml", "odoo_mock": "odoo.yaml",
                                            "rest_mock": "rest.yaml"}
    assert registry.PROJECT_ROOT == REPO
    assert registry.CONNECTOR_CONFIG_DIR == REPO / "config" / "connectors"
    for name in registry.SOURCE_CONFIG_FILES.values():
        assert (registry.CONNECTOR_CONFIG_DIR / name).is_file()


def test_committed_configurations_build_the_expected_connectors():
    csv_connector = registry.build_connector("csv_demo")
    odoo = registry.build_connector("odoo_mock")
    rest = registry.build_connector("rest_mock")
    assert isinstance(csv_connector, CsvConnector) and csv_connector.source_name == "csv_demo"
    assert isinstance(odoo, OdooMockConnector) and odoo.source_name == "odoo_mock"
    assert isinstance(rest, RestConnector) and rest.source_name == "rest_mock"
    assert odoo._config.base_url == rest._config.base_url == "http://mock-source:8080"


def test_csv_data_directory_resolves_against_the_project_root_not_the_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert registry.build_connector("csv_demo").health_check().healthy is True
    assert registry.build_connector("csv_demo", data_directory=tmp_path).health_check().healthy \
        is False


def test_http_base_url_override_is_applied():
    odoo = registry.build_connector("odoo_mock", base_url="http://localhost:8080/")
    rest = registry.build_connector("rest_mock", base_url="http://localhost:8081")
    assert (odoo._config.base_url, rest._config.base_url) == (
        "http://localhost:8080", "http://localhost:8081")


@pytest.mark.parametrize(("source", "overrides"), [
    ("salesforce", {}),
    ("csv_demo", {"base_url": "http://localhost:8080"}),
    ("odoo_mock", {"data_directory": Path("data/demo")}),
    ("rest_mock", {"data_directory": Path("data/demo")}),
    ("rest_mock", {"base_url": "ftp://localhost"}),
    ("odoo_mock", {"base_url": "ftp://localhost"}),
])
def test_invalid_connector_requests_are_rejected(source, overrides):
    with pytest.raises(ConnectorConfigurationError):
        registry.build_connector(source, **overrides)


def test_non_mapping_http_configuration_is_rejected(tmp_path, monkeypatch):
    (tmp_path / "odoo.yaml").write_text("- not\n- a mapping\n", encoding="utf-8")
    monkeypatch.setattr(registry, "CONNECTOR_CONFIG_DIR", tmp_path)
    with pytest.raises(ConnectorConfigurationError, match="must be a YAML mapping"):
        registry.build_connector("odoo_mock")


def test_ingest_demo_cli_reuses_the_registry():
    ingest_demo = _load_ingest_demo()
    assert ingest_demo.build_connector is registry.build_connector
    assert ingest_demo.SOURCE_CONFIG_FILES is registry.SOURCE_CONFIG_FILES
    with pytest.raises(SystemExit):
        ingest_demo.parse_args(["--source", "salesforce"])
    assert ingest_demo.parse_args(["--source", "rest_mock"]).source == "rest_mock"


# --- connector provider ------------------------------------------------------


def test_provider_builds_each_connector_once_on_first_use():
    built: list[str] = []

    def build(source):
        built.append(source)
        return FakeConnector()

    provider = ConnectorProvider(build, ["rest_mock", "csv_demo"])
    assert provider.source_names == ("csv_demo", "rest_mock")
    assert built == []
    first = provider.get("csv_demo")
    assert provider.get("csv_demo") is first
    assert built == ["csv_demo"]
    provider.get("rest_mock")
    assert built == ["csv_demo", "rest_mock"]


def test_provider_rejects_unknown_sources_without_building():
    built: list[str] = []
    provider = ConnectorProvider(lambda source: built.append(source) or FakeConnector(),
                                 ["csv_demo"])
    with pytest.raises(UnknownSourceError):
        provider.get("odoo_mock")
    assert built == []


def test_provider_does_not_cache_failed_builds():
    attempts: list[str] = []

    def build(source):
        attempts.append(source)
        if len(attempts) == 1:
            raise ConnectorConfigurationError("broken", source_name=source)
        return FakeConnector()

    provider = ConnectorProvider(build, ["csv_demo"])
    with pytest.raises(ConnectorConfigurationError):
        provider.get("csv_demo")
    assert isinstance(provider.get("csv_demo"), FakeConnector)
    assert attempts == ["csv_demo", "csv_demo"]


def test_default_provider_serves_the_committed_sources():
    assert ConnectorProvider().source_names == SOURCES
    assert create_app(sessions=sessionmaker()).state.connectors.source_names == SOURCES


# --- GET /api/v1/sources -----------------------------------------------------


def test_sources_lists_every_configured_connector_and_its_capabilities():
    response = _client().get("/api/v1/sources")
    assert response.status_code == 200
    capabilities = {"supported_entity_types": ALL_ENTITIES, "supports_incremental": False,
                    "supports_health_check": True, "read_only": True}
    assert response.json() == {"sources": [
        {"source": "csv_demo", "source_type": "csv", "capabilities": capabilities},
        {"source": "odoo_mock", "source_type": "mock", "capabilities": capabilities},
        {"source": "rest_mock", "source_type": "rest", "capabilities": capabilities},
    ]}
    for internal in ("mock-source", "8080", "data/demo", "base_url", "http"):
        assert internal not in response.text


def test_a_misconfigured_source_returns_a_structured_error(caplog):
    def build(source):
        if source == "odoo_mock":
            raise ConnectorConfigurationError("Invalid base_url: 'ftp://internal-host'",
                                              source_name=source)
        return registry.build_connector(source)

    with caplog.at_level(logging.ERROR, logger="app.api.v1.sources"):
        response = _client(build).get("/api/v1/sources")
    assert response.status_code == 500
    assert response.json()["error"] | {"request_id": None} == {
        "code": "SOURCE_MISCONFIGURED", "message": "source connector configuration is invalid",
        "details": {"source": "odoo_mock"}, "request_id": None}
    assert "internal-host" not in response.text and "internal-host" not in caplog.text
    assert [record.getMessage() for record in caplog.records] == [
        "source_misconfigured source=odoo_mock failure=ConnectorConfigurationError"]


# --- GET /api/v1/sources/{source}/health -------------------------------------


def test_unknown_source_health_returns_not_found_without_echoing_the_name():
    response = _client().get("/api/v1/sources/salesforce-xyz/health")
    assert response.status_code == 404
    error = response.json()["error"]
    assert (error["code"], error["message"], error["details"]) == (
        "SOURCE_NOT_FOUND", "source is not configured",
        {"available_sources": ["csv_demo", "odoo_mock", "rest_mock"]})
    assert "salesforce-xyz" not in response.text


def test_misconfigured_source_health_returns_a_structured_error():
    def build(source):
        raise ConnectorConfigurationError("broken", source_name=source)

    response = _client(build).get("/api/v1/sources/rest_mock/health")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "SOURCE_MISCONFIGURED"


def test_csv_health_is_healthy_for_the_committed_dataset(caplog):
    before = datetime.now(UTC)
    with caplog.at_level(logging.INFO, logger="app.api.v1.sources"):
        response = _client().get("/api/v1/sources/csv_demo/health")
    after = datetime.now(UTC)
    assert response.status_code == 200
    body = response.json()
    checked_at = datetime.fromisoformat(body.pop("checked_at"))
    assert checked_at.utcoffset() is not None and before <= checked_at <= after
    assert body == {"source": "csv_demo", "status": "healthy", "latency_ms": None,
                    "error_type": None}
    assert [record.getMessage() for record in caplog.records] == [
        "connector_health_check source=csv_demo status=healthy error_type=None"]


def test_csv_health_is_unhealthy_without_exposing_the_data_path(tmp_path, caplog):
    missing = tmp_path / "private-directory-name"
    client = _client(lambda source: registry.build_connector(source, data_directory=missing))
    with caplog.at_level(logging.INFO, logger="app.api.v1.sources"):
        response = client.get("/api/v1/sources/csv_demo/health")
    assert response.status_code == 200
    assert (response.json()["status"], response.json()["error_type"]) == ("unhealthy", None)
    assert "private-directory-name" not in response.text
    assert "private-directory-name" not in caplog.text


def test_a_raising_health_check_is_unhealthy_with_only_the_exception_class(caplog):
    connector = FakeConnector(raises=ConnectorUnavailableError("down at http://secret-host:1"))
    with caplog.at_level(logging.INFO, logger="app.api.v1.sources"):
        response = _fake_client(connector).get("/api/v1/sources/csv_demo/health")
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["latency_ms"], body["error_type"]) == (
        "unhealthy", None, "ConnectorUnavailableError")
    assert "secret-host" not in response.text and "secret-host" not in caplog.text
    assert caplog.records[0].getMessage() == (
        "connector_health_check source=csv_demo status=unhealthy "
        "error_type=ConnectorUnavailableError")


def test_only_healthy_true_counts_as_healthy():
    truthy = FakeConnector(health=ConnectorHealth(healthy="yes", source_name="csv_demo"))
    assert _fake_client(truthy).get("/api/v1/sources/csv_demo/health").json()["status"] == \
        "unhealthy"


def test_connector_latency_is_reported():
    connector = FakeConnector(health=ConnectorHealth(healthy=True, source_name="csv_demo",
                                                     message="details stay private",
                                                     latency_ms=12.5))
    response = _fake_client(connector).get("/api/v1/sources/csv_demo/health")
    assert (response.json()["status"], response.json()["latency_ms"]) == ("healthy", 12.5)
    assert "details stay private" not in response.text


def test_a_connector_without_health_checks_is_reported_unsupported():
    connector = FakeConnector(supports_health_check=False)
    body = _fake_client(connector).get("/api/v1/sources/csv_demo/health").json()
    assert (body["status"], body["latency_ms"], body["error_type"]) == ("unsupported", None, None)
    assert connector.health_calls == 0


def test_a_health_check_that_breaks_the_connector_contract_is_an_internal_error(caplog):
    connector = FakeConnector(health={"healthy": True})
    with caplog.at_level(logging.ERROR, logger="app.api.errors"):
        response = _fake_client(connector).get("/api/v1/sources/csv_demo/health")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert caplog.records[0].getMessage().endswith("failure=ConnectorContractError")


@pytest.mark.parametrize("source", ["odoo_mock", "rest_mock"])
def test_http_sources_are_healthy_through_the_mock_source(mock_source_url, source):
    client = _client(lambda name: registry.build_connector(name, base_url=mock_source_url))
    body = client.get(f"/api/v1/sources/{source}/health").json()
    assert (body["source"], body["status"], body["error_type"]) == (source, "healthy", None)
    assert isinstance(body["latency_ms"], float) and body["latency_ms"] >= 0
    assert "127.0.0.1" not in str(body)


@pytest.mark.parametrize("source", ["odoo_mock", "rest_mock"])
def test_unreachable_http_sources_are_unhealthy_without_exposing_the_url(source):
    client = _client(lambda name: registry.build_connector(name, base_url="http://127.0.0.1:9"))
    response = client.get(f"/api/v1/sources/{source}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "unhealthy"
    assert "127.0.0.1" not in response.text


def test_openapi_documents_the_source_routes():
    paths = create_app(sessions=sessionmaker()).openapi()["paths"]

    def schema(path, status):
        return paths[path]["get"]["responses"][status]["content"]["application/json"]["schema"]

    assert schema("/api/v1/sources", "200") == {"$ref": "#/components/schemas/SourceListResponse"}
    assert schema("/api/v1/sources", "500") == {"$ref": "#/components/schemas/ErrorResponse"}
    health = "/api/v1/sources/{source}/health"
    assert schema(health, "200") == {"$ref": "#/components/schemas/SourceHealthResponse"}
    assert schema(health, "404") == {"$ref": "#/components/schemas/ErrorResponse"}
    assert schema(health, "500") == {"$ref": "#/components/schemas/ErrorResponse"}
