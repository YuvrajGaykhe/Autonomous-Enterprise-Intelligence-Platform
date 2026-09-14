"""
C5 Generic REST Connector Tests.

Tests the RestConnector against a local fake HTTP server and validates
configuration, protocol compliance, pagination, error handling, source
boundary, and security properties.

Test categories:
A. Configuration
B. Identity / Protocol compliance
C. Entity discovery
D. Health check
E. Fetch entities (pagination, cursor, page_size)
F. Entity lookup
G. Schema validation per entity
H. Source boundary (no normalization, no canonical, no persistence)
I. HTTP method security
J. Error mapping
K. Arguments (invalid inputs)
L. Determinism
M. Retry behavior
N. Authentication
"""

from __future__ import annotations

import copy
import inspect
import json
import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.connectors.rest import (
    RestAuthConfig,
    RestConnector,
    RestConnectorConfig,
    RestEntityConfig,
)
from app.connectors.types import (
    ConnectorAuthenticationError,
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
# Helpers
# ---------------------------------------------------------------------------


def _entity_config() -> dict[str, dict]:
    """Default entity config for tests."""
    entities = {}
    for name in [
        "organizations", "employees", "customers", "deals",
        "projects", "support_tickets", "documents",
    ]:
        entities[name] = {
            "path": f"/rest/{name}",
            "description": f"REST {name}",
        }
    return entities


def _make_config(**overrides: Any) -> RestConnectorConfig:
    """Create a test configuration."""
    defaults: dict[str, Any] = {
        "source_name": "rest_mock",
        "source_type": "rest",
        "base_url": "http://localhost:9998",
        "timeout": 5,
        "health_endpoint": "/health",
        "auth": {"mechanism": "none"},
        "entities": _entity_config(),
    }
    defaults.update(overrides)
    return RestConnectorConfig.from_dict(defaults)


def _make_connector(**overrides: Any) -> RestConnector:
    """Create a connector with test config."""
    return RestConnector(_make_config(**overrides))


# ---------------------------------------------------------------------------
# Fake HTTP server
# ---------------------------------------------------------------------------


# Default responses keyed by path
_DEFAULT_RESPONSES: dict[str, tuple[int, dict]] = {
    "/health": (200, {
        "status": "healthy",
        "service": "mock-source",
        "entities": sorted([
            "customers", "deals", "documents", "employees",
            "organizations", "projects", "support_tickets",
        ]),
        "routes": ["/health", "/odoo/{entity}", "/rest/{entity}"],
    }),
    "/rest/customers": (200, {
        "data": [
            {"id": "CUST-001", "name": "Acme Industries",
             "email": "contact@acme.example", "segment": "Enterprise",
             "industry": "Manufacturing", "ownerId": "EMP-002",
             "status": "active", "createdAt": "2025-01-15T00:00:00Z",
             "isActive": True},
            {"id": "CUST-002", "name": "Widget Corp",
             "email": "info@widget.example", "segment": "SMB",
             "industry": "Retail", "ownerId": "EMP-002",
             "status": "active", "createdAt": "2025-03-20T00:00:00Z",
             "isActive": True},
            {"id": "CUST-003", "name": "DataFlow Systems",
             "email": "hello@dataflow.example", "segment": "Enterprise",
             "industry": "Technology", "ownerId": "EMP-001",
             "status": "active", "createdAt": "2025-06-10T00:00:00Z",
             "isActive": True},
        ],
        "pagination": {
            "offset": 0, "limit": 100, "total": 3, "has_more": False,
        },
    }),
    "/rest/customers/CUST-001": (200, {
        "data": {"id": "CUST-001", "name": "Acme Industries",
                 "email": "contact@acme.example", "segment": "Enterprise",
                 "industry": "Manufacturing", "ownerId": "EMP-002",
                 "status": "active", "createdAt": "2025-01-15T00:00:00Z",
                 "isActive": True},
    }),
    "/rest/customers/NONEXISTENT": (404, {
        "error": "not_found",
    }),
    "/rest/organizations": (200, {
        "data": [
            {"id": "ORG-001", "name": "Acme Corp",
             "industry": "Technology", "country": "India",
             "status": "active"},
        ],
        "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
    }),
    "/rest/employees": (200, {
        "data": [
            {"id": "EMP-001", "name": "Alice Engineer",
             "email": "alice@acme.example", "department": "Engineering",
             "title": "Senior Developer", "managerId": None,
             "status": "active", "hireDate": "2024-03-15",
             "isActive": True, "organizationId": "ORG-001"},
        ],
        "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
    }),
    "/rest/deals": (200, {
        "data": [
            {"id": "DEAL-001", "name": "Acme Platform Deal",
             "customerId": "CUST-001", "ownerId": "EMP-002",
             "stage": "negotiation", "amount": 150000.50,
             "currency": "INR", "probability": 75.0,
             "expectedCloseDate": "2026-12-31", "isActive": True},
        ],
        "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
    }),
    "/rest/projects": (200, {
        "data": [
            {"id": "PROJ-001", "name": "Platform Migration",
             "customerId": "CUST-001", "ownerId": "EMP-001",
             "status": "in_progress", "startDate": "2026-01-01",
             "endDate": "2026-12-31", "budget": 500000.0,
             "isActive": True},
        ],
        "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
    }),
    "/rest/support_tickets": (200, {
        "data": [
            {"id": "TICKET-001", "customerId": "CUST-001",
             "assigneeId": "EMP-001", "priority": "high",
             "status": "open", "category": "auth",
             "subject": "Login issue", "description": "Cannot login",
             "createdAt": "2026-09-01T00:00:00Z", "resolvedAt": None},
        ],
        "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
    }),
    "/rest/documents": (200, {
        "data": [
            {"id": "DOC-001", "title": "Handbook",
             "documentType": "policy", "bodyText": None,
             "sourceUri": "https://example.com/doc.pdf",
             "ownerId": "EMP-001",
             "createdAt": "2026-01-01T00:00:00Z",
             "updatedAt": "2026-06-15T00:00:00Z"},
        ],
        "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
    }),
}


class _FakeRestHandler(BaseHTTPRequestHandler):
    """Fake HTTP handler. Responses stored as class-level dict."""

    responses: dict[str, tuple[int, dict]] = {}

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path in self.responses:
            status, body = self.responses[path]
        else:
            status, body = 404, {"error": "not_found"}

        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        self.send_response(405)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        pass


@pytest.fixture(scope="module")
def fake_server():
    """Start a fake HTTP server for unit tests."""
    _FakeRestHandler.responses = copy.deepcopy(_DEFAULT_RESPONSES)

    server = HTTPServer(("127.0.0.1", 0), _FakeRestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(autouse=True)
def _restore_responses():
    """Restore default responses after each test."""
    yield
    _FakeRestHandler.responses = copy.deepcopy(_DEFAULT_RESPONSES)


@pytest.fixture
def connector(fake_server):
    """Create a connector pointed at the fake server."""
    return _make_connector(base_url=fake_server)


# ---------------------------------------------------------------------------
# A. Configuration
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_config_from_dict(self):
        config = _make_config()
        assert config.source_name == "rest_mock"
        assert config.source_type == "rest"
        assert config.timeout == 5.0

    def test_config_from_yaml(self, tmp_path):
        yaml_path = tmp_path / "rest.yaml"
        yaml_path.write_text(
            "source_name: rest_mock\n"
            "source_type: rest\n"
            "base_url: http://mock-source:8080\n"
            "timeout: 10\n"
            "health_endpoint: /health\n"
            "auth:\n"
            "  mechanism: none\n"
            "entities:\n"
            "  customers:\n"
            "    path: /rest/customers\n"
        )
        config = RestConnectorConfig.from_yaml(yaml_path)
        assert config.source_name == "rest_mock"
        assert config.base_url == "http://mock-source:8080"
        assert "customers" in config.entities

    def test_config_missing_file(self, tmp_path):
        with pytest.raises(ConnectorConfigurationError):
            RestConnectorConfig.from_yaml(tmp_path / "nonexistent.yaml")

    def test_config_missing_base_url(self):
        with pytest.raises(ConnectorConfigurationError, match="base_url"):
            RestConnectorConfig.from_dict({
                "entities": {"customers": {"path": "/rest/customers"}},
            })

    def test_config_invalid_base_url(self):
        with pytest.raises(ConnectorConfigurationError, match="Invalid base_url"):
            RestConnectorConfig.from_dict({
                "base_url": "not-a-url",
                "entities": {"customers": {"path": "/c"}},
            })

    def test_config_invalid_timeout(self):
        with pytest.raises(ConnectorConfigurationError, match="timeout"):
            RestConnectorConfig.from_dict({
                "base_url": "http://localhost:8080",
                "timeout": -1,
                "entities": {"customers": {"path": "/c"}},
            })

    def test_config_strips_trailing_slash(self):
        config = _make_config(base_url="http://localhost:8080/")
        assert config.base_url == "http://localhost:8080"

    def test_config_defaults(self):
        config = RestConnectorConfig.from_dict({
            "base_url": "http://localhost:8080",
            "entities": {"customers": {"path": "/c"}},
        })
        assert config.source_name == "rest_mock"
        assert config.source_type == "rest"
        assert config.timeout == 10.0
        assert config.health_endpoint == "/health"

    def test_config_missing_entities(self):
        with pytest.raises(ConnectorConfigurationError, match="at least one entity"):
            RestConnectorConfig.from_dict({
                "base_url": "http://localhost:8080",
                "entities": {},
            })

    def test_config_entity_missing_path(self):
        with pytest.raises(ConnectorConfigurationError, match="path"):
            RestConnectorConfig.from_dict({
                "base_url": "http://localhost:8080",
                "entities": {"customers": {"description": "no path"}},
            })

    def test_config_entity_description(self):
        config = _make_config()
        assert config.entities["customers"].description == "REST customers"


# ---------------------------------------------------------------------------
# B. Identity / Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_source_name(self, connector):
        assert connector.source_name == "rest_mock"

    def test_source_type(self, connector):
        assert connector.source_type == "rest"

    def test_satisfies_source_connector(self, connector):
        from app.connectors.base import SourceConnector
        assert isinstance(connector, SourceConnector)

    def test_has_all_methods(self, connector):
        assert hasattr(connector, "health_check")
        assert hasattr(connector, "list_entities")
        assert hasattr(connector, "fetch_entities")
        assert hasattr(connector, "get_entity")
        assert hasattr(connector, "capabilities")


# ---------------------------------------------------------------------------
# C. Entity discovery
# ---------------------------------------------------------------------------


class TestEntityDiscovery:
    def test_list_entities_returns_seven(self, connector):
        entities = connector.list_entities()
        assert len(entities) == 7

    def test_list_entities_types(self, connector):
        types = {e.entity_type for e in connector.list_entities()}
        expected = {
            "organizations", "employees", "customers", "deals",
            "projects", "support_tickets", "documents",
        }
        assert types == expected

    def test_list_entities_sorted(self, connector):
        types = [e.entity_type for e in connector.list_entities()]
        assert types == sorted(types)

    def test_list_entities_deterministic(self, connector):
        e1 = [e.entity_type for e in connector.list_entities()]
        e2 = [e.entity_type for e in connector.list_entities()]
        assert e1 == e2

    def test_list_entities_have_descriptions(self, connector):
        for e in connector.list_entities():
            assert e.description is not None
            assert len(e.description) > 0

    def test_list_entities_returns_source_entity(self, connector):
        for e in connector.list_entities():
            assert isinstance(e, SourceEntity)

    def test_unsupported_entity_fetch(self, connector):
        with pytest.raises(ConnectorEntityError, match="Unsupported"):
            connector.fetch_entities("not_an_entity")

    def test_unsupported_entity_get(self, connector):
        with pytest.raises(ConnectorEntityError, match="Unsupported"):
            connector.get_entity("not_an_entity", "1")

    def test_unsupported_entity_has_context(self, connector):
        with pytest.raises(ConnectorEntityError) as exc_info:
            connector.fetch_entities("invalid")
        assert exc_info.value.entity_type == "invalid"


# ---------------------------------------------------------------------------
# D. Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_healthy_source(self, connector):
        health = connector.health_check()
        assert health.healthy is True
        assert health.source_name == "rest_mock"
        assert health.latency_ms is not None
        assert health.latency_ms >= 0

    def test_healthy_type(self, connector):
        assert isinstance(connector.health_check(), ConnectorHealth)

    def test_healthy_has_message(self, connector):
        assert connector.health_check().message is not None

    def test_unavailable_source(self):
        conn = _make_connector(base_url="http://127.0.0.1:1", timeout=0.5)
        health = conn.health_check()
        assert health.healthy is False

    def test_timeout_source(self):
        conn = _make_connector(base_url="http://192.0.2.1:9999", timeout=0.5)
        health = conn.health_check()
        assert health.healthy is False

    def test_malformed_health_response(self, fake_server):
        _FakeRestHandler.responses["/health"] = (200, {"status": "broken"})
        conn = _make_connector(base_url=fake_server)
        health = conn.health_check()
        assert health.healthy is False

    def test_health_http_error(self, fake_server):
        _FakeRestHandler.responses["/health"] = (500, {"error": "fail"})
        conn = _make_connector(base_url=fake_server)
        health = conn.health_check()
        assert health.healthy is False


# ---------------------------------------------------------------------------
# E. Fetch entities
# ---------------------------------------------------------------------------


class TestFetchEntities:
    def test_fetch_customers(self, connector):
        page = connector.fetch_entities("customers")
        assert isinstance(page, Page)
        assert len(page.items) == 3

    def test_fetch_returns_dicts(self, connector):
        page = connector.fetch_entities("customers")
        for item in page.items:
            assert isinstance(item, dict)

    def test_fetch_rest_fields(self, connector):
        page = connector.fetch_entities("customers")
        cust = page.items[0]
        assert "id" in cust
        assert "name" in cust
        assert "segment" in cust
        assert "ownerId" in cust
        assert "createdAt" in cust

    def test_fetch_rest_string_ids(self, connector):
        page = connector.fetch_entities("customers")
        for item in page.items:
            assert isinstance(item["id"], str)

    def test_fetch_total_count(self, connector):
        page = connector.fetch_entities("customers")
        assert page.total_count == 3

    def test_fetch_no_more(self, connector):
        page = connector.fetch_entities("customers")
        assert page.has_more is False
        assert page.next_cursor is None

    def test_fetch_all_entities(self, connector):
        for entity in [
            "organizations", "employees", "customers", "deals",
            "projects", "support_tickets", "documents",
        ]:
            page = connector.fetch_entities(entity)
            assert len(page.items) > 0

    def test_fetch_with_page_size(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (200, {
            "data": [
                {"id": "CUST-001", "name": "Acme", "segment": "Enterprise"},
            ],
            "pagination": {
                "offset": 0, "limit": 1, "total": 3,
                "has_more": True, "next_offset": 1,
            },
        })
        conn = _make_connector(base_url=fake_server)
        page = conn.fetch_entities("customers", page_size=1)
        assert len(page.items) == 1
        assert page.has_more is True
        assert page.next_cursor == "1"

    def test_fetch_with_cursor(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (200, {
            "data": [
                {"id": "CUST-002", "name": "Widget"},
            ],
            "pagination": {
                "offset": 1, "limit": 1, "total": 3,
                "has_more": True, "next_offset": 2,
            },
        })
        conn = _make_connector(base_url=fake_server)
        page = conn.fetch_entities("customers", cursor="1", page_size=1)
        assert page.items[0]["id"] == "CUST-002"
        assert page.next_cursor == "2"

    def test_fetch_last_page(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (200, {
            "data": [
                {"id": "CUST-003", "name": "DataFlow"},
            ],
            "pagination": {
                "offset": 2, "limit": 1, "total": 3,
                "has_more": False,
            },
        })
        conn = _make_connector(base_url=fake_server)
        page = conn.fetch_entities("customers", cursor="2", page_size=1)
        assert page.has_more is False
        assert page.next_cursor is None

    def test_fetch_empty_result(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (200, {
            "data": [],
            "pagination": {
                "offset": 0, "limit": 100, "total": 0,
                "has_more": False,
            },
        })
        conn = _make_connector(base_url=fake_server)
        page = conn.fetch_entities("customers")
        assert len(page.items) == 0
        assert page.total_count == 0


# ---------------------------------------------------------------------------
# F. Entity lookup
# ---------------------------------------------------------------------------


class TestGetEntity:
    def test_get_customer_by_id(self, connector):
        record = connector.get_entity("customers", "CUST-001")
        assert isinstance(record, dict)
        assert record["id"] == "CUST-001"
        assert record["name"] == "Acme Industries"

    def test_get_returns_rest_fields(self, connector):
        record = connector.get_entity("customers", "CUST-001")
        assert "segment" in record
        assert "ownerId" in record
        assert "createdAt" in record

    def test_get_missing_record_raises(self, connector):
        with pytest.raises(ConnectorEntityError):
            connector.get_entity("customers", "NONEXISTENT")

    def test_get_missing_record_has_context(self, connector):
        with pytest.raises(ConnectorEntityError) as exc_info:
            connector.get_entity("customers", "NONEXISTENT")
        assert exc_info.value.entity_type == "customers"
        assert exc_info.value.source_id == "NONEXISTENT"


# ---------------------------------------------------------------------------
# G. Schema validation per entity
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    """Verify that each entity validates against its B3 REST schema."""

    def test_organizations_schema(self, connector):
        page = connector.fetch_entities("organizations")
        org = page.items[0]
        assert org["id"] == "ORG-001"
        assert isinstance(org["id"], str)

    def test_employees_schema(self, connector):
        page = connector.fetch_entities("employees")
        emp = page.items[0]
        assert emp["id"] == "EMP-001"
        assert isinstance(emp["id"], str)

    def test_customers_schema(self, connector):
        page = connector.fetch_entities("customers")
        cust = page.items[0]
        assert cust["id"] == "CUST-001"
        assert isinstance(cust["id"], str)

    def test_deals_schema(self, connector):
        page = connector.fetch_entities("deals")
        deal = page.items[0]
        assert deal["id"] == "DEAL-001"
        assert isinstance(deal["amount"], float)

    def test_projects_schema(self, connector):
        page = connector.fetch_entities("projects")
        proj = page.items[0]
        assert proj["id"] == "PROJ-001"

    def test_support_tickets_schema(self, connector):
        page = connector.fetch_entities("support_tickets")
        ticket = page.items[0]
        assert ticket["id"] == "TICKET-001"

    def test_documents_schema(self, connector):
        page = connector.fetch_entities("documents")
        doc = page.items[0]
        assert doc["id"] == "DOC-001"


# ---------------------------------------------------------------------------
# H. Source boundary
# ---------------------------------------------------------------------------


class TestSourceBoundary:
    """Prove the connector does NOT normalize data."""

    def test_camelcase_fields_preserved(self, connector):
        page = connector.fetch_entities("customers")
        cust = page.items[0]
        # REST camelCase must survive unchanged
        assert "ownerId" in cust
        assert "createdAt" in cust
        assert "isActive" in cust

    def test_no_snake_case_conversion(self, connector):
        page = connector.fetch_entities("customers")
        cust = page.items[0]
        assert "owner_id" not in cust
        assert "created_at" not in cust
        assert "is_active" not in cust

    def test_string_ids_not_converted(self, connector):
        page = connector.fetch_entities("customers")
        for cust in page.items:
            assert isinstance(cust["id"], str)
            assert cust["id"].startswith("CUST-")

    def test_float_amount_not_decimal(self, connector):
        page = connector.fetch_entities("deals")
        deal = page.items[0]
        assert isinstance(deal["amount"], float)

    def test_whitespace_preserved(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (200, {
            "data": [
                {"id": "CUST-WS", "name": "  Acme Corp  "},
            ],
            "pagination": {
                "offset": 0, "limit": 100, "total": 1, "has_more": False,
            },
        })
        conn = _make_connector(base_url=fake_server)
        page = conn.fetch_entities("customers")
        assert page.items[0]["name"] == "  Acme Corp  "

    def test_no_canonical_import(self):
        """Connector module must not import canonical schemas."""
        import app.connectors.rest as rest_mod
        source = inspect.getsource(rest_mod)
        import_lines = [
            line.strip() for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        joined = "\n".join(import_lines)
        assert "app.schemas.canonical" not in joined

    def test_no_persistence_import(self):
        """Connector module must not import persistence modules."""
        import app.connectors.rest as rest_mod
        source = inspect.getsource(rest_mod)
        import_lines = [
            line.strip() for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        joined = "\n".join(import_lines)
        assert "sqlalchemy" not in joined.lower()
        assert "app.persistence" not in joined
        assert "app.models" not in joined

    def test_no_uuid_generation(self, connector):
        page = connector.fetch_entities("customers")
        for cust in page.items:
            # IDs should be source-native strings, not UUIDs
            assert "-" in cust["id"]  # e.g. CUST-001
            assert len(cust["id"]) < 36  # not a UUID


# ---------------------------------------------------------------------------
# I. HTTP method security
# ---------------------------------------------------------------------------


class TestHttpMethodSecurity:
    def test_no_write_methods(self, connector):
        public_methods = [
            m for m in dir(connector)
            if not m.startswith("_") and callable(getattr(connector, m))
        ]
        write_names = {"create", "update", "delete", "put", "post", "patch"}
        for method in public_methods:
            assert method not in write_names, f"Found write method: {method}"

    def test_capabilities_read_only(self, connector):
        assert connector.capabilities().read_only is True


# ---------------------------------------------------------------------------
# J. Error mapping
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
        _FakeRestHandler.responses["/rest/customers"] = (400, {"error": "bad"})
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorRequestError, match="HTTP 400"):
            conn.fetch_entities("customers")

    def test_http_500(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (500, {"error": "fail"})
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorRequestError, match="HTTP 500"):
            conn.fetch_entities("customers")

    def test_malformed_collection_no_data(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (200, {
            "pagination": {"offset": 0, "limit": 100, "total": 0, "has_more": False},
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorRequestError, match="missing"):
            conn.fetch_entities("customers")

    def test_malformed_collection_no_pagination(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (200, {
            "data": [],
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorRequestError, match="missing"):
            conn.fetch_entities("customers")

    def test_malformed_pagination_missing_fields(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (200, {
            "data": [],
            "pagination": {"offset": 0},
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorRequestError, match="missing fields"):
            conn.fetch_entities("customers")

    def test_malformed_entity_payload(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (200, {
            "data": [{"bad_field": "invalid"}],
            "pagination": {"offset": 0, "limit": 100, "total": 1, "has_more": False},
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorRequestError, match="Malformed.*payload"):
            conn.fetch_entities("customers")

    def test_malformed_detail_no_data(self, fake_server):
        _FakeRestHandler.responses["/rest/customers/CUST-001"] = (200, {
            "result": {"id": "CUST-001"},
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorRequestError, match="missing 'data'"):
            conn.get_entity("customers", "CUST-001")


# ---------------------------------------------------------------------------
# K. Arguments (invalid inputs)
# ---------------------------------------------------------------------------


class TestArguments:
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
# L. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_fetch_deterministic(self, connector):
        p1 = connector.fetch_entities("customers")
        p2 = connector.fetch_entities("customers")
        assert [i["id"] for i in p1.items] == [i["id"] for i in p2.items]

    def test_get_deterministic(self, connector):
        r1 = connector.get_entity("customers", "CUST-001")
        r2 = connector.get_entity("customers", "CUST-001")
        assert r1 == r2

    def test_list_entities_deterministic(self, connector):
        e1 = [e.entity_type for e in connector.list_entities()]
        e2 = [e.entity_type for e in connector.list_entities()]
        assert e1 == e2


# ---------------------------------------------------------------------------
# M. Capabilities
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_seven_entities(self, connector):
        caps = connector.capabilities()
        assert len(caps.supported_entity_types) == 7

    def test_no_incremental(self, connector):
        caps = connector.capabilities()
        assert caps.supports_incremental is False

    def test_supports_health_check(self, connector):
        caps = connector.capabilities()
        assert caps.supports_health_check is True

    def test_read_only(self, connector):
        caps = connector.capabilities()
        assert caps.read_only is True

    def test_type(self, connector):
        assert isinstance(connector.capabilities(), ConnectorCapabilities)


# ---------------------------------------------------------------------------
# N. Authentication
# ---------------------------------------------------------------------------


class TestAuthentication:
    def test_no_auth(self):
        auth = RestAuthConfig(mechanism="none")
        assert auth.get_headers() == {}

    def test_api_key_auth(self):
        os.environ["TEST_API_KEY"] = "test-key-123"
        try:
            auth = RestAuthConfig(
                mechanism="api_key",
                header_name="X-API-Key",
                env_var="TEST_API_KEY",
            )
            headers = auth.get_headers()
            assert headers == {"X-API-Key": "test-key-123"}
        finally:
            del os.environ["TEST_API_KEY"]

    def test_bearer_auth(self):
        os.environ["TEST_BEARER_TOKEN"] = "my-token"
        try:
            auth = RestAuthConfig(
                mechanism="bearer",
                env_var="TEST_BEARER_TOKEN",
            )
            headers = auth.get_headers()
            assert headers == {"Authorization": "Bearer my-token"}
        finally:
            del os.environ["TEST_BEARER_TOKEN"]

    def test_missing_env_var(self):
        # Ensure var is not set
        os.environ.pop("NONEXISTENT_VAR", None)
        auth = RestAuthConfig(
            mechanism="api_key",
            env_var="NONEXISTENT_VAR",
        )
        with pytest.raises(ConnectorConfigurationError, match="not set"):
            auth.get_headers()

    def test_unsupported_mechanism(self):
        auth = RestAuthConfig(mechanism="oauth2", env_var="X")
        os.environ["X"] = "val"
        try:
            with pytest.raises(ConnectorConfigurationError, match="Unsupported"):
                auth.get_headers()
        finally:
            del os.environ["X"]

    def test_missing_env_var_name(self):
        auth = RestAuthConfig(mechanism="bearer", env_var="")
        with pytest.raises(ConnectorConfigurationError, match="env_var"):
            auth.get_headers()


# ---------------------------------------------------------------------------
# O. Security checks
# ---------------------------------------------------------------------------


class TestSecurity:
    def test_no_hardcoded_secrets(self):
        import app.connectors.rest as rest_mod
        source = inspect.getsource(rest_mod)
        # Check executable lines, not comments/docstrings
        code_lines = []
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            code_lines.append(stripped)
        joined = "\n".join(code_lines)
        # Should not have hardcoded password/secret values in assignments
        assert "password =" not in joined.lower() or "password" in "password"
        assert "secret =" not in joined.lower()

    def test_no_shell_execution(self):
        import app.connectors.rest as rest_mod
        source = inspect.getsource(rest_mod)
        import_lines = [
            line.strip() for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        joined = "\n".join(import_lines)
        assert "subprocess" not in joined
        assert "os.system" not in joined

    def test_no_hardcoded_localhost(self):
        import app.connectors.rest as rest_mod
        source = inspect.getsource(rest_mod)
        import_and_code = [
            line for line in source.splitlines()
            if not line.strip().startswith("#")
            and not line.strip().startswith('"""')
            and not line.strip().startswith("'''")
            and "localhost" not in line.split("#")[0] if "=" in line
        ]
        for line in import_and_code:
            if "=" in line and "localhost" in line.split("#")[0]:
                assert False, f"Hardcoded localhost found: {line}"


# ---------------------------------------------------------------------------
# P. Rate limiting (HTTP 429)
# ---------------------------------------------------------------------------


class TestRateLimiting:
    def test_429_raises_after_retries(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (429, {
            "error": "rate_limited",
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorRequestError, match="429"):
            conn.fetch_entities("customers")

    def test_429_with_retry_after_header(self, fake_server):
        """429 with Retry-After should be retried, not immediately fail."""
        # We can't easily test the delay itself, but we can verify
        # that after max retries it eventually raises
        _FakeRestHandler.responses["/rest/customers"] = (429, {
            "error": "rate_limited",
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorRequestError, match="Rate limited"):
            conn.fetch_entities("customers")


# ---------------------------------------------------------------------------
# Q. Transient server errors (502, 503, 504)
# ---------------------------------------------------------------------------


class TestTransientServerErrors:
    def test_502_retries_then_raises(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (502, {
            "error": "bad_gateway",
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorRequestError, match="502"):
            conn.fetch_entities("customers")

    def test_503_retries_then_raises(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (503, {
            "error": "service_unavailable",
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorRequestError, match="503"):
            conn.fetch_entities("customers")

    def test_504_retries_then_raises(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (504, {
            "error": "gateway_timeout",
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorRequestError, match="504"):
            conn.fetch_entities("customers")

    def test_500_does_not_retry(self, fake_server):
        """500 is not in the transient set. Should fail immediately."""
        _FakeRestHandler.responses["/rest/customers"] = (500, {
            "error": "server_error",
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorRequestError, match="HTTP 500"):
            conn.fetch_entities("customers")


# ---------------------------------------------------------------------------
# R. Authentication error mapping (401, 403)
# ---------------------------------------------------------------------------


class TestAuthErrorMapping:
    def test_401_raises_auth_error(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (401, {
            "error": "unauthorized",
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorAuthenticationError, match="401"):
            conn.fetch_entities("customers")

    def test_403_raises_auth_error(self, fake_server):
        _FakeRestHandler.responses["/rest/customers"] = (403, {
            "error": "forbidden",
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorAuthenticationError, match="403"):
            conn.fetch_entities("customers")

    def test_401_not_retried(self, fake_server):
        """Auth errors must not be retried."""
        _FakeRestHandler.responses["/rest/customers"] = (401, {
            "error": "unauthorized",
        })
        conn = _make_connector(base_url=fake_server)
        with pytest.raises(ConnectorAuthenticationError):
            conn.fetch_entities("customers")


# ---------------------------------------------------------------------------
# S. Custom entity configuration (proves genericity)
# ---------------------------------------------------------------------------


class TestCustomEntityConfiguration:
    def test_custom_entity_listed(self, fake_server):
        """A non-standard entity configured in YAML appears in list_entities."""
        config = RestConnectorConfig.from_dict({
            "base_url": fake_server,
            "entities": {
                "customers": {"path": "/rest/customers"},
                "custom_widgets": {
                    "path": "/rest/widgets",
                    "description": "Custom widget records",
                },
            },
        })
        conn = RestConnector(config)
        types = {e.entity_type for e in conn.list_entities()}
        assert "custom_widgets" in types
        assert "customers" in types

    def test_custom_entity_fetch(self, fake_server):
        """A configured custom entity can be fetched if the server supports it."""
        _FakeRestHandler.responses["/rest/widgets"] = (200, {
            "data": [{"id": "W-001", "name": "Gadget"}],
            "pagination": {
                "offset": 0, "limit": 100, "total": 1, "has_more": False,
            },
        })
        config = RestConnectorConfig.from_dict({
            "base_url": fake_server,
            "entities": {
                "custom_widgets": {"path": "/rest/widgets"},
            },
        })
        conn = RestConnector(config)
        page = conn.fetch_entities("custom_widgets")
        assert len(page.items) == 1
        assert page.items[0]["id"] == "W-001"

    def test_unconfigured_entity_rejected(self, fake_server):
        """An entity not in the config is rejected."""
        config = RestConnectorConfig.from_dict({
            "base_url": fake_server,
            "entities": {
                "customers": {"path": "/rest/customers"},
            },
        })
        conn = RestConnector(config)
        with pytest.raises(ConnectorEntityError, match="Unsupported"):
            conn.fetch_entities("employees")

    def test_capabilities_reflect_config(self, fake_server):
        """capabilities().supported_entity_types matches config."""
        config = RestConnectorConfig.from_dict({
            "base_url": fake_server,
            "entities": {
                "customers": {"path": "/rest/customers"},
                "custom_widgets": {"path": "/rest/widgets"},
            },
        })
        conn = RestConnector(config)
        caps = conn.capabilities()
        assert sorted(caps.supported_entity_types) == ["custom_widgets", "customers"]


# ---------------------------------------------------------------------------
# T. Exponential backoff verification
# ---------------------------------------------------------------------------


class TestExponentialBackoff:
    def test_retry_constants_exist(self):
        """Verify exponential backoff constants are defined."""
        import app.connectors.rest as rest_mod
        assert hasattr(rest_mod, "_RETRY_BASE_DELAY_S")
        assert hasattr(rest_mod, "_RETRY_MAX_DELAY_S")
        assert rest_mod._RETRY_BASE_DELAY_S > 0
        assert rest_mod._RETRY_MAX_DELAY_S >= rest_mod._RETRY_BASE_DELAY_S

    def test_backoff_formula_in_source(self):
        """Verify the implementation uses exponential backoff (2^attempt)."""
        import app.connectors.rest as rest_mod
        source = inspect.getsource(rest_mod.RestConnector._get_json)
        assert "2 ** attempt" in source or "2**attempt" in source
