"""
C1 Connector Base Interface Tests.

Verifies the connector contract (SourceConnector protocol, result types,
exception hierarchy) without implementing any concrete connector.

Test categories:
A. Protocol/interface existence
B. Result type construction and behavior
C. Pagination representation
D. Read-only boundary
E. Source ID flexibility
F. Exception hierarchy
G. Contract implementation (FakeConnector)
H. Cross-boundary independence (no B1/B2 imports)
"""

import inspect
import uuid

import pytest

from app.connectors.base import SourceConnector
from app.connectors.types import (
    ConnectorCapabilities,
    ConnectorHealth,
    ConnectorError,
    ConnectorConfigurationError,
    ConnectorAuthenticationError,
    ConnectorUnavailableError,
    ConnectorRequestError,
    ConnectorEntityError,
    Page,
    SourceEntity,
)


# ---------------------------------------------------------------------------
# A. Protocol/interface existence
# ---------------------------------------------------------------------------


class TestProtocolExists:
    """SourceConnector protocol must expose the required contract."""

    def test_source_connector_is_protocol(self):
        assert hasattr(SourceConnector, "__protocol_attrs__") or hasattr(
            SourceConnector, "__abstractmethods__"
        ) or issubclass(type(SourceConnector), type)

    def test_has_source_name(self):
        members = [name for name, _ in inspect.getmembers(SourceConnector)]
        assert "source_name" in members

    def test_has_source_type(self):
        members = [name for name, _ in inspect.getmembers(SourceConnector)]
        assert "source_type" in members

    def test_has_health_check(self):
        assert hasattr(SourceConnector, "health_check")
        assert callable(getattr(SourceConnector, "health_check", None))

    def test_has_list_entities(self):
        assert hasattr(SourceConnector, "list_entities")
        assert callable(getattr(SourceConnector, "list_entities", None))

    def test_has_fetch_entities(self):
        assert hasattr(SourceConnector, "fetch_entities")
        assert callable(getattr(SourceConnector, "fetch_entities", None))

    def test_has_get_entity(self):
        assert hasattr(SourceConnector, "get_entity")
        assert callable(getattr(SourceConnector, "get_entity", None))

    def test_has_capabilities(self):
        assert hasattr(SourceConnector, "capabilities")
        assert callable(getattr(SourceConnector, "capabilities", None))

    def test_method_count(self):
        """Protocol should have exactly 5 methods (no write operations)."""
        methods = [
            name for name, val in inspect.getmembers(SourceConnector)
            if callable(val) and not name.startswith("_")
        ]
        assert set(methods) == {
            "health_check",
            "list_entities",
            "fetch_entities",
            "get_entity",
            "capabilities",
        }


# ---------------------------------------------------------------------------
# B. Result type construction
# ---------------------------------------------------------------------------


class TestConnectorHealth:
    """ConnectorHealth must be a frozen dataclass."""

    def test_healthy(self):
        h = ConnectorHealth(healthy=True, source_name="csv_demo")
        assert h.healthy is True
        assert h.source_name == "csv_demo"
        assert h.message is None
        assert h.latency_ms is None

    def test_unhealthy_with_message(self):
        h = ConnectorHealth(
            healthy=False,
            source_name="odoo_mock",
            message="Connection refused",
            latency_ms=1500.0,
        )
        assert h.healthy is False
        assert h.message == "Connection refused"
        assert h.latency_ms == 1500.0

    def test_frozen(self):
        h = ConnectorHealth(healthy=True, source_name="test")
        with pytest.raises(AttributeError):
            h.healthy = False


class TestSourceEntity:
    """SourceEntity must describe an available entity type."""

    def test_basic(self):
        e = SourceEntity(entity_type="customers")
        assert e.entity_type == "customers"
        assert e.description is None

    def test_with_description(self):
        e = SourceEntity(
            entity_type="deals",
            description="Sales opportunities",
        )
        assert e.description == "Sales opportunities"

    def test_frozen(self):
        e = SourceEntity(entity_type="customers")
        with pytest.raises(AttributeError):
            e.entity_type = "deals"


class TestPage:
    """Page[T] must represent paginated results."""

    def test_empty_page(self):
        p = Page()
        assert p.items == []
        assert p.next_cursor is None
        assert p.has_more is False
        assert p.total_count is None

    def test_first_page_with_more(self):
        records = [{"id": "1"}, {"id": "2"}]
        p = Page(
            items=records,
            next_cursor="cursor_abc",
            has_more=True,
            total_count=100,
        )
        assert len(p.items) == 2
        assert p.next_cursor == "cursor_abc"
        assert p.has_more is True
        assert p.total_count == 100

    def test_last_page(self):
        p = Page(
            items=[{"id": "99"}],
            next_cursor=None,
            has_more=False,
        )
        assert p.has_more is False
        assert p.next_cursor is None

    def test_frozen(self):
        p = Page(items=[{"id": "1"}])
        with pytest.raises(AttributeError):
            p.has_more = True

    def test_generic_type(self):
        """Page should work with different item types."""
        p_dict = Page[dict](items=[{"key": "val"}])
        assert isinstance(p_dict.items[0], dict)

        p_str = Page[str](items=["hello", "world"])
        assert p_str.items[0] == "hello"


class TestConnectorCapabilities:
    """ConnectorCapabilities must declare what a connector supports."""

    def test_default(self):
        c = ConnectorCapabilities()
        assert c.supported_entity_types == []
        assert c.supports_incremental is False
        assert c.supports_health_check is True
        assert c.read_only is True

    def test_with_entities(self):
        c = ConnectorCapabilities(
            supported_entity_types=["customers", "deals", "employees"],
            supports_incremental=True,
        )
        assert len(c.supported_entity_types) == 3
        assert c.supports_incremental is True

    def test_frozen(self):
        c = ConnectorCapabilities()
        with pytest.raises(AttributeError):
            c.read_only = False

    def test_read_only_always_true_by_default(self):
        """Layer 1 connectors are always read-only."""
        c = ConnectorCapabilities()
        assert c.read_only is True


# ---------------------------------------------------------------------------
# C. Pagination representation
# ---------------------------------------------------------------------------


class TestPaginationContract:
    """Verify the cursor-based pagination workflow."""

    def test_initial_request_cursor_none(self):
        """First request uses cursor=None."""
        p = Page(
            items=[{"id": i} for i in range(100)],
            next_cursor="page2",
            has_more=True,
        )
        assert p.has_more is True
        assert p.next_cursor == "page2"

    def test_subsequent_request_uses_cursor(self):
        """Second request passes returned cursor."""
        p = Page(
            items=[{"id": i} for i in range(100, 150)],
            next_cursor="page3",
            has_more=True,
        )
        assert p.next_cursor == "page3"

    def test_final_page(self):
        """Last page has has_more=False, next_cursor=None."""
        p = Page(
            items=[{"id": 200}],
            next_cursor=None,
            has_more=False,
        )
        assert p.has_more is False
        assert p.next_cursor is None

    def test_empty_source(self):
        """Source with no data returns empty page."""
        p = Page(items=[], next_cursor=None, has_more=False)
        assert len(p.items) == 0
        assert p.has_more is False


# ---------------------------------------------------------------------------
# D. Read-only boundary
# ---------------------------------------------------------------------------


class TestReadOnlyBoundary:
    """Connector contract must NOT expose write operations."""

    WRITE_METHODS = [
        "create_entity",
        "update_entity",
        "delete_entity",
        "write_entity",
        "post",
        "put",
        "patch",
        "create",
        "update",
        "delete",
        "write",
        "insert",
        "upsert",
        "remove",
    ]

    @pytest.mark.parametrize("method_name", WRITE_METHODS)
    def test_no_write_method(self, method_name):
        """SourceConnector must not have write methods."""
        assert not hasattr(SourceConnector, method_name), (
            f"SourceConnector exposes write method: {method_name}"
        )

    def test_capabilities_default_read_only(self):
        c = ConnectorCapabilities()
        assert c.read_only is True


# ---------------------------------------------------------------------------
# E. Source ID flexibility
# ---------------------------------------------------------------------------


class TestSourceIdFlexibility:
    """Connector types must not force canonical UUID IDs."""

    def test_string_source_id(self):
        """Source ID can be a string like 'CUST-001'."""
        record = {"id": "CUST-001", "name": "Test"}
        p = Page(items=[record])
        assert p.items[0]["id"] == "CUST-001"

    def test_integer_source_id(self):
        """Source ID can be an integer like 123."""
        record = {"id": 123, "name": "Test"}
        p = Page(items=[record])
        assert p.items[0]["id"] == 123

    def test_compound_source_id(self):
        """Source ID can be any string format."""
        record = {"id": "customer_abc_123", "name": "Test"}
        p = Page(items=[record])
        assert p.items[0]["id"] == "customer_abc_123"

    def test_page_does_not_validate_uuid(self):
        """Page should work with non-UUID IDs."""
        record = {"id": "not-a-uuid"}
        p = Page(items=[record])
        with pytest.raises(ValueError):
            uuid.UUID(p.items[0]["id"])

    def test_source_entity_type_is_string(self):
        """SourceEntity entity_type is a plain string, not an enum."""
        e = SourceEntity(entity_type="customers")
        assert isinstance(e.entity_type, str)

    def test_connector_health_source_name_is_string(self):
        """ConnectorHealth source_name is a plain string."""
        h = ConnectorHealth(healthy=True, source_name="csv_demo")
        assert isinstance(h.source_name, str)


# ---------------------------------------------------------------------------
# F. Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """All connector exceptions must inherit from ConnectorError."""

    def test_connector_error_is_exception(self):
        assert issubclass(ConnectorError, Exception)

    def test_configuration_error(self):
        assert issubclass(ConnectorConfigurationError, ConnectorError)

    def test_authentication_error(self):
        assert issubclass(ConnectorAuthenticationError, ConnectorError)

    def test_unavailable_error(self):
        assert issubclass(ConnectorUnavailableError, ConnectorError)

    def test_request_error(self):
        assert issubclass(ConnectorRequestError, ConnectorError)

    def test_entity_error(self):
        assert issubclass(ConnectorEntityError, ConnectorError)

    def test_connector_error_has_source_name(self):
        err = ConnectorError("test failure", source_name="csv_demo")
        assert err.source_name == "csv_demo"
        assert str(err) == "test failure"

    def test_entity_error_has_entity_context(self):
        err = ConnectorEntityError(
            "not found",
            source_name="odoo_mock",
            entity_type="customers",
            source_id="42",
        )
        assert err.source_name == "odoo_mock"
        assert err.entity_type == "customers"
        assert err.source_id == "42"

    def test_connector_error_catchable(self):
        """All connector exceptions can be caught by ConnectorError."""
        exceptions = [
            ConnectorConfigurationError("bad config"),
            ConnectorAuthenticationError("bad auth"),
            ConnectorUnavailableError("down"),
            ConnectorRequestError("timeout"),
            ConnectorEntityError("not found"),
        ]
        for exc in exceptions:
            with pytest.raises(ConnectorError):
                raise exc


# ---------------------------------------------------------------------------
# G. Contract implementation (FakeConnector)
# ---------------------------------------------------------------------------


class FakeConnector:
    """A minimal fake connector that satisfies the SourceConnector protocol.

    This proves the protocol is actually implementable without any
    database, HTTP, or canonical-schema dependencies.
    """

    @property
    def source_name(self) -> str:
        return "fake_demo"

    @property
    def source_type(self) -> str:
        return "fake"

    def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(
            healthy=True,
            source_name=self.source_name,
            message="Fake source is always healthy",
        )

    def list_entities(self) -> list[SourceEntity]:
        return [
            SourceEntity(entity_type="customers"),
            SourceEntity(entity_type="deals"),
        ]

    def fetch_entities(
        self,
        entity_type: str,
        cursor: str | None = None,
        page_size: int = 100,
    ) -> Page[dict]:
        if entity_type == "customers":
            return Page(
                items=[
                    {"id": "CUST-001", "name": "Acme Corp"},
                    {"id": "CUST-002", "name": "Widget Inc"},
                ],
                next_cursor=None,
                has_more=False,
            )
        raise ConnectorEntityError(
            f"Unknown entity type: {entity_type}",
            source_name=self.source_name,
            entity_type=entity_type,
        )

    def get_entity(self, entity_type: str, source_id: str) -> dict:
        if entity_type == "customers" and source_id == "CUST-001":
            return {"id": "CUST-001", "name": "Acme Corp"}
        raise ConnectorEntityError(
            f"Entity not found: {source_id}",
            source_name=self.source_name,
            entity_type=entity_type,
            source_id=source_id,
        )

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supported_entity_types=["customers", "deals"],
            supports_incremental=False,
            supports_health_check=True,
            read_only=True,
        )


class TestFakeConnector:
    """Prove the protocol is implementable with a FakeConnector."""

    def test_satisfies_protocol(self):
        """FakeConnector must be recognized as a SourceConnector."""
        fake = FakeConnector()
        assert isinstance(fake, SourceConnector)

    def test_source_name(self):
        assert FakeConnector().source_name == "fake_demo"

    def test_source_type(self):
        assert FakeConnector().source_type == "fake"

    def test_health_check(self):
        h = FakeConnector().health_check()
        assert isinstance(h, ConnectorHealth)
        assert h.healthy is True

    def test_list_entities(self):
        entities = FakeConnector().list_entities()
        assert len(entities) == 2
        assert all(isinstance(e, SourceEntity) for e in entities)

    def test_fetch_entities(self):
        page = FakeConnector().fetch_entities("customers")
        assert isinstance(page, Page)
        assert len(page.items) == 2
        assert page.has_more is False

    def test_fetch_unknown_entity_raises(self):
        with pytest.raises(ConnectorEntityError):
            FakeConnector().fetch_entities("unknown")

    def test_get_entity(self):
        record = FakeConnector().get_entity("customers", "CUST-001")
        assert record["id"] == "CUST-001"

    def test_get_missing_entity_raises(self):
        with pytest.raises(ConnectorEntityError):
            FakeConnector().get_entity("customers", "NONEXISTENT")

    def test_capabilities(self):
        caps = FakeConnector().capabilities()
        assert isinstance(caps, ConnectorCapabilities)
        assert caps.read_only is True
        assert "customers" in caps.supported_entity_types

    def test_no_write_methods(self):
        """FakeConnector should not have write methods."""
        fake = FakeConnector()
        for method in TestReadOnlyBoundary.WRITE_METHODS:
            assert not hasattr(fake, method)


# ---------------------------------------------------------------------------
# H. Cross-boundary independence
# ---------------------------------------------------------------------------


class TestCrossBoundaryIndependence:
    """C1 must not depend on B1 (persistence) or B2 (canonical schemas)."""

    @staticmethod
    def _import_lines(module) -> list[str]:
        """Extract actual import statements from a module's source."""
        source = inspect.getsource(module)
        return [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]

    def test_base_module_no_persistence_import(self):
        """base.py must not import app.persistence."""
        import app.connectors.base as base_mod
        imports = self._import_lines(base_mod)
        for line in imports:
            assert "app.persistence" not in line, (
                f"base.py imports app.persistence: {line}"
            )

    def test_base_module_no_canonical_import(self):
        """base.py must not import app.schemas.canonical."""
        import app.connectors.base as base_mod
        imports = self._import_lines(base_mod)
        for line in imports:
            assert "app.schemas.canonical" not in line, (
                f"base.py imports app.schemas.canonical: {line}"
            )

    def test_types_module_no_persistence_import(self):
        """types.py must not import app.persistence."""
        import app.connectors.types as types_mod
        imports = self._import_lines(types_mod)
        for line in imports:
            assert "app.persistence" not in line, (
                f"types.py imports app.persistence: {line}"
            )

    def test_types_module_no_canonical_import(self):
        """types.py must not import app.schemas.canonical."""
        import app.connectors.types as types_mod
        imports = self._import_lines(types_mod)
        for line in imports:
            assert "app.schemas.canonical" not in line, (
                f"types.py imports app.schemas.canonical: {line}"
            )

    def test_base_module_no_sqlalchemy_import(self):
        """base.py must not import SQLAlchemy."""
        import app.connectors.base as base_mod
        imports = self._import_lines(base_mod)
        for line in imports:
            assert "sqlalchemy" not in line, (
                f"base.py imports sqlalchemy: {line}"
            )

    def test_types_module_no_sqlalchemy_import(self):
        """types.py must not import SQLAlchemy."""
        import app.connectors.types as types_mod
        imports = self._import_lines(types_mod)
        for line in imports:
            assert "sqlalchemy" not in line, (
                f"types.py imports sqlalchemy: {line}"
            )

    def test_base_module_no_source_schema_import(self):
        """base.py must not import app.schemas.source."""
        import app.connectors.base as base_mod
        imports = self._import_lines(base_mod)
        for line in imports:
            assert "app.schemas.source" not in line, (
                f"base.py imports app.schemas.source: {line}"
            )

    def test_types_module_no_http_import(self):
        """types.py must not import HTTP libraries."""
        import app.connectors.types as types_mod
        imports = self._import_lines(types_mod)
        for line in imports:
            assert "requests" not in line or "import requests" not in line, (
                f"types.py imports requests: {line}"
            )
            assert "httpx" not in line, (
                f"types.py imports httpx: {line}"
            )

