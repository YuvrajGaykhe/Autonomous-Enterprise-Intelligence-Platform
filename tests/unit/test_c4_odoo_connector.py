"""
C4 Odoo Mock Connector Tests.

Tests the OdooMockConnector against both mocked HTTP responses and
the live C3 mock-source service (integration tests at bottom).

Test categories:
A. Identity (source_name, source_type)
B. Entity support (list_entities, capabilities)
C. Health check (healthy, unavailable, timeout, malformed)
D. Fetch entities (pagination, cursor, page_size)
E. Get entity (lookup, missing)
F. Validation (malformed responses)
G. Arguments (invalid entity, cursor, page_size)
H. Error mapping (connection, timeout, HTTP errors)
I. Read-only / source boundary
J. Configuration
K. Determinism
L. Integration against C3 mock-source
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.connectors.odoo import (
    OdooConnectorConfig,
    OdooMockConnector,
    SUPPORTED_ENTITIES,
)
from app.connectors.types import (
    ConnectorCapabilities,
    ConnectorConfigurationError,
    ConnectorEntityError,
    ConnectorHealth,
    ConnectorRequestError,
    ConnectorUnavailableError,
    Page,
    SourceEntity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(**overrides: Any) -> OdooConnectorConfig:
    """Create a test configuration."""
    defaults = {
        "source_name": "odoo",
        "source_type": "mock",
        "base_url": "http://localhost:9999",
        "timeout": 5,
    }
    defaults.update(overrides)
    return OdooConnectorConfig.from_dict(defaults)


def _make_connector(**overrides: Any) -> OdooMockConnector:
    """Create a connector with test config."""
    return OdooMockConnector(_make_config(**overrides))


# A simple fake HTTP server that serves canned responses
class _FakeOdooHandler(BaseHTTPRequestHandler):
    """Fake HTTP handler for unit testing."""

    # Class-level response registry: path -> (status, body_dict)
    responses: dict[str, tuple[int, dict]] = {}
    # Track all requests made
    request_log: list[tuple[str, str]] = []

    def do_GET(self) -> None:
        _FakeOdooHandler.request_log.append(("GET", self.path))

        path = self.path.split("?")[0]
        if path in self.responses:
            status, body = self.responses[path]
        else:
            # Default: check path patterns
            for pattern, (status, body) in self.responses.items():
                if self.path.startswith(pattern.rstrip("*")):
                    break
            else:
                status, body = 404, {"error": "not_found"}

        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        _FakeOdooHandler.request_log.append(("POST", self.path))
        self.send_response(405)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        pass  # Silence test logs


@pytest.fixture(scope="module")
def fake_server():
    """Start a fake HTTP server for unit tests."""
    _FakeOdooHandler.responses = {
        "/health": (200, {
            "status": "healthy",
            "service": "mock-source",
            "entities": SUPPORTED_ENTITIES,
            "routes": ["/health", "/odoo/{entity}", "/rest/{entity}"],
        }),
        "/odoo/customers": (200, {
            "data": [
                {"id": 1, "name": "Acme Industries", "email": "contact@acme.example",
                 "x_studio_segment": "Enterprise", "industry_id": "Manufacturing",
                 "user_id": 2, "active": True, "create_date": "2025-01-15 00:00:00",
                 "customer_rank": 1},
                {"id": 2, "name": "Widget Corp", "email": "info@widget.example",
                 "x_studio_segment": "SMB", "industry_id": "Retail",
                 "user_id": 2, "active": True, "create_date": "2025-03-20 00:00:00",
                 "customer_rank": 1},
                {"id": 3, "name": "DataFlow Systems", "email": "hello@dataflow.example",
                 "x_studio_segment": "Enterprise", "industry_id": "Technology",
                 "user_id": 1, "active": True, "create_date": "2025-06-10 00:00:00",
                 "customer_rank": 1},
            ],
            "pagination": {
                "offset": 0, "limit": 100, "total": 3, "has_more": False,
            },
        }),
        "/odoo/customers/1": (200, {
            "data": {"id": 1, "name": "Acme Industries", "email": "contact@acme.example",
                     "x_studio_segment": "Enterprise", "industry_id": "Manufacturing",
                     "user_id": 2, "active": True, "create_date": "2025-01-15 00:00:00",
                     "customer_rank": 1},
        }),
        "/odoo/customers/9999": (404, {
            "error": "not_found",
            "message": "Record not found: /odoo/customers/9999",
        }),
        "/odoo/organizations": (200, {
            "data": [
                {"id": 1, "name": "Acme Corp", "industry_id": "Technology",
                 "country_id": "India", "active": True},
            ],
            "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
        }),
        "/odoo/employees": (200, {
            "data": [
                {"id": 1, "name": "Alice Engineer", "work_email": "alice@acme.example",
                 "department_id": "Engineering", "job_title": "Senior Developer",
                 "parent_id": None, "active": True, "x_hire_date": "2024-03-15",
                 "company_id": 1},
            ],
            "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
        }),
        "/odoo/deals": (200, {
            "data": [
                {"id": 1, "name": "Acme Platform Deal", "partner_id": 1,
                 "user_id": 2, "stage_id": "negotiation",
                 "expected_revenue": 150000.50, "company_currency": "INR",
                 "probability": 75.0, "date_deadline": "2026-12-31", "active": True},
            ],
            "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
        }),
        "/odoo/projects": (200, {
            "data": [
                {"id": 1, "name": "Platform Migration", "partner_id": 1,
                 "user_id": 1, "stage_id": "in_progress",
                 "date_start": "2026-01-01", "date": "2026-12-31",
                 "x_budget": 500000.0, "active": True},
            ],
            "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
        }),
        "/odoo/support_tickets": (200, {
            "data": [
                {"id": 1, "partner_id": 1, "user_id": 1, "priority": "high",
                 "stage_id": "open", "category_id": "auth",
                 "name": "Login issue", "description": "Cannot login",
                 "create_date": "2026-09-01 00:00:00", "close_date": None},
            ],
            "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
        }),
        "/odoo/documents": (200, {
            "data": [
                {"id": 1, "name": "Handbook", "type": "policy",
                 "datas": None, "url": "https://example.com/doc.pdf",
                 "owner_id": 1, "create_date": "2026-01-01 00:00:00",
                 "write_date": "2026-06-15 00:00:00"},
            ],
            "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
        }),
    }
    _FakeOdooHandler.request_log = []

    server = HTTPServer(("127.0.0.1", 0), _FakeOdooHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
def connector(fake_server):
    """Create a connector pointed at the fake server."""
    return _make_connector(base_url=fake_server)


# ---------------------------------------------------------------------------
# A. Identity
# ---------------------------------------------------------------------------


class TestIdentity:
    def test_source_name(self, connector):
        assert connector.source_name == "odoo"

    def test_source_type(self, connector):
        assert connector.source_type == "mock"


# ---------------------------------------------------------------------------
# B. Entity support
# ---------------------------------------------------------------------------


class TestEntitySupport:
    def test_list_entities_returns_seven(self, connector):
        entities = connector.list_entities()
        assert len(entities) == 7

    def test_list_entities_types(self, connector):
        entities = connector.list_entities()
        types = {e.entity_type for e in entities}
        expected = {
            "organizations", "employees", "customers", "deals",
            "projects", "support_tickets", "documents",
        }
        assert types == expected

    def test_list_entities_deterministic(self, connector):
        e1 = connector.list_entities()
        e2 = connector.list_entities()
        assert [e.entity_type for e in e1] == [e.entity_type for e in e2]

    def test_list_entities_sorted(self, connector):
        entities = connector.list_entities()
        types = [e.entity_type for e in entities]
        assert types == sorted(types)

    def test_list_entities_have_descriptions(self, connector):
        entities = connector.list_entities()
        for e in entities:
            assert e.description is not None
            assert len(e.description) > 0

    def test_list_entities_returns_source_entity(self, connector):
        entities = connector.list_entities()
        for e in entities:
            assert isinstance(e, SourceEntity)

    def test_capabilities_entities(self, connector):
        caps = connector.capabilities()
        assert len(caps.supported_entity_types) == 7

    def test_capabilities_no_incremental(self, connector):
        caps = connector.capabilities()
        assert caps.supports_incremental is False

    def test_capabilities_health_check(self, connector):
        caps = connector.capabilities()
        assert caps.supports_health_check is True

    def test_capabilities_read_only(self, connector):
        caps = connector.capabilities()
        assert caps.read_only is True

    def test_capabilities_type(self, connector):
        caps = connector.capabilities()
        assert isinstance(caps, ConnectorCapabilities)


# ---------------------------------------------------------------------------
# C. Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_healthy_source(self, connector):
        health = connector.health_check()
        assert health.healthy is True
        assert health.source_name == "odoo"
        assert health.latency_ms is not None
        assert health.latency_ms >= 0

    def test_healthy_has_message(self, connector):
        health = connector.health_check()
        assert health.message is not None

    def test_health_type(self, connector):
        health = connector.health_check()
        assert isinstance(health, ConnectorHealth)

    def test_unavailable_source(self):
        conn = _make_connector(base_url="http://127.0.0.1:1", timeout=0.5)
        health = conn.health_check()
        assert health.healthy is False
        assert health.source_name == "odoo"

    def test_timeout_source(self):
        conn = _make_connector(base_url="http://192.0.2.1:9999", timeout=0.5)
        health = conn.health_check()
        assert health.healthy is False

    def test_malformed_health_response(self, fake_server):
        old_resp = _FakeOdooHandler.responses["/health"]
        _FakeOdooHandler.responses["/health"] = (200, {"status": "broken"})
        try:
            conn = _make_connector(base_url=fake_server)
            health = conn.health_check()
            assert health.healthy is False
        finally:
            _FakeOdooHandler.responses["/health"] = old_resp


# ---------------------------------------------------------------------------
# D. Fetch entities
# ---------------------------------------------------------------------------


class TestFetchEntities:
    def test_fetch_customers(self, connector):
        page = connector.fetch_entities("customers")
        assert isinstance(page, Page)
        assert len(page.items) > 0

    def test_fetch_returns_dicts(self, connector):
        page = connector.fetch_entities("customers")
        for item in page.items:
            assert isinstance(item, dict)

    def test_fetch_odoo_fields(self, connector):
        page = connector.fetch_entities("customers")
        cust = page.items[0]
        assert "id" in cust
        assert "name" in cust
        assert "x_studio_segment" in cust
        assert "user_id" in cust

    def test_fetch_first_page_cursor_none(self, connector):
        page = connector.fetch_entities("customers", cursor=None)
        assert isinstance(page, Page)

    def test_fetch_total_count(self, connector):
        page = connector.fetch_entities("customers")
        assert page.total_count == 3

    def test_fetch_no_more(self, connector):
        page = connector.fetch_entities("customers")
        assert page.has_more is False
        assert page.next_cursor is None

    def test_fetch_all_entities(self, connector):
        for entity in SUPPORTED_ENTITIES:
            page = connector.fetch_entities(entity)
            assert len(page.items) > 0

    def test_fetch_with_page_size(self, fake_server):
        # Set up paginated response
        old_resp = _FakeOdooHandler.responses.get("/odoo/customers")
        _FakeOdooHandler.responses["/odoo/customers"] = (200, {
            "data": [
                {"id": 1, "name": "Acme", "email": None,
                 "x_studio_segment": None, "industry_id": None,
                 "user_id": None, "active": True, "create_date": None,
                 "customer_rank": 1},
            ],
            "pagination": {
                "offset": 0, "limit": 1, "total": 3,
                "has_more": True, "next_offset": 1,
            },
        })
        try:
            conn = _make_connector(base_url=fake_server)
            page = conn.fetch_entities("customers", page_size=1)
            assert len(page.items) == 1
            assert page.has_more is True
            assert page.next_cursor == "1"
            assert page.total_count == 3
        finally:
            if old_resp:
                _FakeOdooHandler.responses["/odoo/customers"] = old_resp

    def test_fetch_with_cursor(self, fake_server):
        old = _FakeOdooHandler.responses.get("/odoo/customers")
        _FakeOdooHandler.responses["/odoo/customers"] = (200, {
            "data": [
                {"id": 2, "name": "Widget", "email": None,
                 "x_studio_segment": None, "industry_id": None,
                 "user_id": None, "active": True, "create_date": None,
                 "customer_rank": 1},
            ],
            "pagination": {
                "offset": 1, "limit": 1, "total": 3,
                "has_more": True, "next_offset": 2,
            },
        })
        try:
            conn = _make_connector(base_url=fake_server)
            page = conn.fetch_entities("customers", cursor="1", page_size=1)
            assert page.items[0]["name"] == "Widget"
            assert page.next_cursor == "2"
        finally:
            if old:
                _FakeOdooHandler.responses["/odoo/customers"] = old

    def test_fetch_last_page(self, fake_server):
        old = _FakeOdooHandler.responses.get("/odoo/customers")
        _FakeOdooHandler.responses["/odoo/customers"] = (200, {
            "data": [
                {"id": 3, "name": "DataFlow", "email": None,
                 "x_studio_segment": None, "industry_id": None,
                 "user_id": None, "active": True, "create_date": None,
                 "customer_rank": 1},
            ],
            "pagination": {
                "offset": 2, "limit": 1, "total": 3,
                "has_more": False,
            },
        })
        try:
            conn = _make_connector(base_url=fake_server)
            page = conn.fetch_entities("customers", cursor="2", page_size=1)
            assert page.has_more is False
            assert page.next_cursor is None
        finally:
            if old:
                _FakeOdooHandler.responses["/odoo/customers"] = old


# ---------------------------------------------------------------------------
# E. Get entity
# ---------------------------------------------------------------------------


class TestGetEntity:
    def test_get_customer_by_id(self, connector):
        record = connector.get_entity("customers", "1")
        assert isinstance(record, dict)
        assert record["id"] == 1
        assert record["name"] == "Acme Industries"

    def test_get_returns_odoo_fields(self, connector):
        record = connector.get_entity("customers", "1")
        assert "x_studio_segment" in record
        assert "user_id" in record
        assert "create_date" in record

    def test_get_missing_record_raises(self, connector):
        with pytest.raises(ConnectorEntityError):
            connector.get_entity("customers", "9999")

    def test_get_missing_record_has_context(self, connector):
        with pytest.raises(ConnectorEntityError) as exc_info:
            connector.get_entity("customers", "9999")
        assert exc_info.value.entity_type == "customers"
        assert exc_info.value.source_id == "9999"


# ---------------------------------------------------------------------------
# F. Validation (malformed responses)
# ---------------------------------------------------------------------------


class TestValidation:
    def test_malformed_collection_no_data(self, fake_server):
        old = _FakeOdooHandler.responses.get("/odoo/customers")
        _FakeOdooHandler.responses["/odoo/customers"] = (200, {
            "pagination": {"offset": 0, "limit": 100, "total": 0, "has_more": False},
        })
        try:
            conn = _make_connector(base_url=fake_server)
            with pytest.raises(ConnectorRequestError, match="missing 'data'"):
                conn.fetch_entities("customers")
        finally:
            if old:
                _FakeOdooHandler.responses["/odoo/customers"] = old

    def test_malformed_collection_no_pagination(self, fake_server):
        old = _FakeOdooHandler.responses.get("/odoo/customers")
        _FakeOdooHandler.responses["/odoo/customers"] = (200, {
            "data": [],
        })
        try:
            conn = _make_connector(base_url=fake_server)
            with pytest.raises(ConnectorRequestError, match="missing.*pagination"):
                conn.fetch_entities("customers")
        finally:
            if old:
                _FakeOdooHandler.responses["/odoo/customers"] = old

    def test_malformed_pagination_missing_fields(self, fake_server):
        old = _FakeOdooHandler.responses.get("/odoo/customers")
        _FakeOdooHandler.responses["/odoo/customers"] = (200, {
            "data": [],
            "pagination": {"offset": 0},
        })
        try:
            conn = _make_connector(base_url=fake_server)
            with pytest.raises(ConnectorRequestError, match="missing fields"):
                conn.fetch_entities("customers")
        finally:
            if old:
                _FakeOdooHandler.responses["/odoo/customers"] = old

    def test_malformed_entity_payload(self, fake_server):
        old = _FakeOdooHandler.responses.get("/odoo/customers")
        _FakeOdooHandler.responses["/odoo/customers"] = (200, {
            "data": [{"bad_field": "invalid"}],
            "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
        })
        try:
            conn = _make_connector(base_url=fake_server)
            with pytest.raises(ConnectorRequestError, match="Malformed.*payload"):
                conn.fetch_entities("customers")
        finally:
            if old:
                _FakeOdooHandler.responses["/odoo/customers"] = old

    def test_malformed_detail_no_data(self, fake_server):
        old = _FakeOdooHandler.responses.get("/odoo/customers/1")
        _FakeOdooHandler.responses["/odoo/customers/1"] = (200, {
            "result": {"id": 1, "name": "Acme"},
        })
        try:
            conn = _make_connector(base_url=fake_server)
            with pytest.raises(ConnectorRequestError, match="missing 'data'"):
                conn.get_entity("customers", "1")
        finally:
            if old:
                _FakeOdooHandler.responses["/odoo/customers/1"] = old


# ---------------------------------------------------------------------------
# G. Arguments (invalid inputs)
# ---------------------------------------------------------------------------


class TestArguments:
    def test_invalid_entity_type_fetch(self, connector):
        with pytest.raises(ConnectorEntityError, match="Unsupported"):
            connector.fetch_entities("not_an_entity")

    def test_invalid_entity_type_get(self, connector):
        with pytest.raises(ConnectorEntityError, match="Unsupported"):
            connector.get_entity("not_an_entity", "1")

    def test_invalid_entity_type_has_context(self, connector):
        with pytest.raises(ConnectorEntityError) as exc_info:
            connector.fetch_entities("invalid")
        assert exc_info.value.entity_type == "invalid"

    def test_invalid_cursor_non_numeric(self, connector):
        with pytest.raises(ConnectorRequestError, match="Invalid cursor"):
            connector.fetch_entities("customers", cursor="abc")

    def test_invalid_cursor_negative(self, connector):
        with pytest.raises(ConnectorRequestError, match="non-negative"):
            connector.fetch_entities("customers", cursor="-1")

    def test_invalid_cursor_float(self, connector):
        with pytest.raises(ConnectorRequestError, match="Invalid cursor"):
            connector.fetch_entities("customers", cursor="1.5")

    def test_invalid_page_size_zero(self, connector):
        with pytest.raises(ConnectorRequestError, match="page_size"):
            connector.fetch_entities("customers", page_size=0)

    def test_invalid_page_size_negative(self, connector):
        with pytest.raises(ConnectorRequestError, match="page_size"):
            connector.fetch_entities("customers", page_size=-1)


# ---------------------------------------------------------------------------
# H. Error mapping
# ---------------------------------------------------------------------------


class TestErrorMapping:
    def test_connection_failure(self):
        conn = _make_connector(base_url="http://127.0.0.1:1", timeout=0.5)
        with pytest.raises(ConnectorUnavailableError):
            conn.fetch_entities("customers")

    def test_timeout_failure(self):
        conn = _make_connector(base_url="http://192.0.2.1:9999", timeout=0.5)
        with pytest.raises(ConnectorUnavailableError):
            conn.fetch_entities("customers")

    def test_http_400(self, fake_server):
        old_resp = _FakeOdooHandler.responses.get("/odoo/customers")
        _FakeOdooHandler.responses["/odoo/customers"] = (400, {
            "error": "invalid_parameter",
        })
        try:
            conn = _make_connector(base_url=fake_server)
            with pytest.raises(ConnectorRequestError, match="HTTP 400"):
                conn.fetch_entities("customers")
        finally:
            if old_resp:
                _FakeOdooHandler.responses["/odoo/customers"] = old_resp

    def test_http_500(self, fake_server):
        old_resp = _FakeOdooHandler.responses.get("/odoo/customers")
        _FakeOdooHandler.responses["/odoo/customers"] = (500, {
            "error": "server_error",
        })
        try:
            conn = _make_connector(base_url=fake_server)
            with pytest.raises(ConnectorRequestError, match="HTTP 500"):
                conn.fetch_entities("customers")
        finally:
            if old_resp:
                _FakeOdooHandler.responses["/odoo/customers"] = old_resp


# ---------------------------------------------------------------------------
# I. Read-only / source boundary
# ---------------------------------------------------------------------------


class TestReadOnlyBoundary:
    def test_no_write_methods(self, connector):
        """Connector exposes no write methods."""
        public_methods = [
            m for m in dir(connector)
            if not m.startswith("_") and callable(getattr(connector, m))
        ]
        write_names = {"create", "update", "delete", "put", "post", "patch"}
        for method in public_methods:
            assert method not in write_names, f"Found write method: {method}"

    def test_no_canonical_import(self):
        """Connector module must not import canonical schemas."""
        source = inspect.getsource(
            __import__("app.connectors.odoo", fromlist=["OdooMockConnector"])
        )
        assert "app.schemas.canonical" not in source
        assert "from app.schemas.canonical" not in source

    def test_no_persistence_import(self):
        """Connector module must not import persistence modules."""
        import app.connectors.odoo as odoo_mod
        source = inspect.getsource(odoo_mod)
        # Check import lines only (not docstrings/comments)
        import_lines = [
            line.strip() for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        joined = "\n".join(import_lines)
        assert "sqlalchemy" not in joined.lower()
        assert "app.persistence" not in joined
        assert "app.models" not in joined

    def test_capabilities_read_only(self, connector):
        assert connector.capabilities().read_only is True


# ---------------------------------------------------------------------------
# J. Configuration
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_config_from_dict(self):
        config = OdooConnectorConfig.from_dict({
            "source_name": "odoo",
            "source_type": "mock",
            "base_url": "http://localhost:8080",
            "timeout": 5,
        })
        assert config.source_name == "odoo"
        assert config.base_url == "http://localhost:8080"
        assert config.timeout == 5.0

    def test_config_from_yaml(self, tmp_path):
        yaml_path = tmp_path / "odoo.yaml"
        yaml_path.write_text(
            "source_name: odoo\n"
            "source_type: mock\n"
            "base_url: http://mock-source:8080\n"
            "timeout: 10\n"
        )
        config = OdooConnectorConfig.from_yaml(yaml_path)
        assert config.source_name == "odoo"
        assert config.base_url == "http://mock-source:8080"

    def test_config_missing_file(self, tmp_path):
        with pytest.raises(ConnectorConfigurationError):
            OdooConnectorConfig.from_yaml(tmp_path / "nonexistent.yaml")

    def test_config_missing_base_url(self):
        with pytest.raises(ConnectorConfigurationError, match="base_url"):
            OdooConnectorConfig.from_dict({
                "source_name": "odoo",
                "source_type": "mock",
            })

    def test_config_invalid_base_url(self):
        with pytest.raises(ConnectorConfigurationError, match="Invalid base_url"):
            OdooConnectorConfig.from_dict({
                "base_url": "not-a-url",
            })

    def test_config_invalid_timeout(self):
        with pytest.raises(ConnectorConfigurationError, match="timeout"):
            OdooConnectorConfig.from_dict({
                "base_url": "http://localhost:8080",
                "timeout": -1,
            })

    def test_config_strips_trailing_slash(self):
        config = OdooConnectorConfig.from_dict({
            "base_url": "http://localhost:8080/",
        })
        assert config.base_url == "http://localhost:8080"

    def test_config_defaults(self):
        config = OdooConnectorConfig.from_dict({
            "base_url": "http://localhost:8080",
        })
        assert config.source_name == "odoo"
        assert config.source_type == "mock"
        assert config.timeout == 10.0


# ---------------------------------------------------------------------------
# K. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_fetch_deterministic(self, connector):
        p1 = connector.fetch_entities("customers")
        p2 = connector.fetch_entities("customers")
        assert [i["name"] for i in p1.items] == [i["name"] for i in p2.items]

    def test_get_deterministic(self, connector):
        r1 = connector.get_entity("customers", "1")
        r2 = connector.get_entity("customers", "1")
        assert r1 == r2

    def test_list_entities_deterministic(self, connector):
        e1 = [e.entity_type for e in connector.list_entities()]
        e2 = [e.entity_type for e in connector.list_entities()]
        assert e1 == e2


# ---------------------------------------------------------------------------
# L. Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    def test_satisfies_source_connector_protocol(self, connector):
        from app.connectors.base import SourceConnector
        assert isinstance(connector, SourceConnector)
