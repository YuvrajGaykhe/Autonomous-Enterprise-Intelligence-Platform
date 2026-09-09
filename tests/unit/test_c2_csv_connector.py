"""
C2 CSV Connector Tests.

Comprehensive tests for the CsvConnector against the SourceConnector
contract. Uses pytest tmp_path for isolated test fixtures.

Test categories:
A. Connector construction
B. Capabilities
C. Health
D. Entity discovery
E. CSV parsing
F. Source IDs
G. Pagination
H. Cursor continuity
I. get_entity
J. Unknown columns
K. Missing required columns
L. Raw value preservation
M. No canonical transformation
N. Read-only
O. B3 compatibility
P. Cross-boundary (C2 → B3, not C2 → B2)
"""

import csv
import inspect
import os
import uuid
from pathlib import Path

import pytest

from app.connectors.base import SourceConnector
from app.connectors.csv import CsvConnector, CsvConnectorConfig
from app.connectors.types import (
    ConnectorCapabilities,
    ConnectorConfigurationError,
    ConnectorEntityError,
    ConnectorHealth,
    ConnectorRequestError,
    Page,
    SourceEntity,
)
from app.schemas.source.csv import (
    CsvOrganizationSource,
    CsvEmployeeSource,
    CsvCustomerSource,
    CsvDealSource,
    CsvProjectSource,
    CsvSupportTicketSource,
    CsvDocumentSource,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


ENTITY_CONFIGS = {
    "organizations": {"file": "organizations.csv", "id_column": "organization_id"},
    "employees": {"file": "employees.csv", "id_column": "employee_id"},
    "customers": {"file": "customers.csv", "id_column": "customer_id"},
    "deals": {"file": "deals.csv", "id_column": "deal_id"},
    "projects": {"file": "projects.csv", "id_column": "project_id"},
    "support_tickets": {"file": "support_tickets.csv", "id_column": "ticket_id"},
    "documents": {"file": "documents.csv", "id_column": "document_id"},
}


def _make_config(tmp_path: Path, entities: dict | None = None) -> CsvConnectorConfig:
    """Create a CsvConnectorConfig pointing at tmp_path."""
    return CsvConnectorConfig.from_dict({
        "source_name": "csv_test",
        "source_type": "csv",
        "data_directory": str(tmp_path),
        "entities": entities or ENTITY_CONFIGS,
    })


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    """Write a CSV file with given headers and rows."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def _create_customers_csv(tmp_path: Path, count: int = 5) -> Path:
    """Create a customers.csv with N rows."""
    headers = [
        "customer_id", "customer_name", "email_address",
        "customer_segment", "industry_name", "account_owner_id",
        "status", "created_date",
    ]
    rows = [
        [
            f"CUST-{i:03d}",
            f"Customer {i}",
            f"cust{i}@example.com",
            "Enterprise" if i % 2 == 0 else "SMB",
            "Technology",
            f"EMP-{i:03d}",
            "active",
            "2024-01-15",
        ]
        for i in range(1, count + 1)
    ]
    file_path = tmp_path / "customers.csv"
    _write_csv(file_path, headers, rows)
    return file_path


def _create_all_entity_csvs(tmp_path: Path) -> None:
    """Create minimal CSV files for all 7 entities."""
    _write_csv(tmp_path / "organizations.csv",
               ["organization_id", "organization_name", "industry", "country", "status"],
               [["ORG-001", "Acme Corp", "Technology", "India", "active"]])

    _write_csv(tmp_path / "employees.csv",
               ["employee_id", "employee_name", "email_address", "department",
                "title", "manager_id", "status", "hire_date", "is_active", "organization_id"],
               [["EMP-001", "Alice", "alice@acme.com", "Engineering",
                 "Developer", "EMP-MGR-001", "active", "2024-03-15", "true", "ORG-001"]])

    _create_customers_csv(tmp_path, count=3)

    _write_csv(tmp_path / "deals.csv",
               ["deal_id", "deal_name", "customer_id", "owner_id", "stage",
                "amount", "currency", "probability", "expected_close_date", "is_active"],
               [["DEAL-001", "Big Deal", "CUST-001", "EMP-001", "negotiation",
                 "150000.50", "INR", "0.75", "2026-12-31", "true"]])

    _write_csv(tmp_path / "projects.csv",
               ["project_id", "project_name", "customer_id", "owner_id", "status",
                "start_date", "end_date", "budget", "is_active"],
               [["PROJ-001", "Migration", "CUST-001", "EMP-001", "in_progress",
                 "2026-01-01", "2026-12-31", "500000.00", "true"]])

    _write_csv(tmp_path / "support_tickets.csv",
               ["ticket_id", "customer_id", "assignee_id", "priority", "status",
                "category", "subject", "description", "created_date", "resolved_date"],
               [["TKT-001", "CUST-001", "EMP-001", "high", "open",
                 "auth", "Login issue", "Cannot log in", "2026-09-01", ""]])

    _write_csv(tmp_path / "documents.csv",
               ["document_id", "title", "document_type", "body_text", "source_uri",
                "owner_id", "created_date", "updated_date"],
               [["DOC-001", "Handbook", "policy", "Full content here",
                 "https://internal.acme.com/handbook.pdf", "EMP-001", "2026-01-01", "2026-06-15"]])


# ---------------------------------------------------------------------------
# A. Connector construction
# ---------------------------------------------------------------------------


class TestConnectorConstruction:
    """Test CsvConnector initialization."""

    def test_from_dict_config(self, tmp_path):
        config = _make_config(tmp_path)
        connector = CsvConnector(config)
        assert connector.source_name == "csv_test"
        assert connector.source_type == "csv"

    def test_from_yaml_config(self, tmp_path):
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(
            "source_name: yaml_test\n"
            "source_type: csv\n"
            f"data_directory: {tmp_path}\n"
            "entities:\n"
            "  customers:\n"
            "    file: customers.csv\n"
            "    id_column: customer_id\n"
        )
        config = CsvConnectorConfig.from_yaml(yaml_path)
        connector = CsvConnector(config)
        assert connector.source_name == "yaml_test"

    def test_missing_yaml_raises(self, tmp_path):
        with pytest.raises(ConnectorConfigurationError):
            CsvConnectorConfig.from_yaml(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises(self, tmp_path):
        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text("not: valid: yaml: [[[")
        with pytest.raises(ConnectorConfigurationError):
            CsvConnectorConfig.from_yaml(yaml_path)

    def test_satisfies_protocol(self, tmp_path):
        config = _make_config(tmp_path)
        connector = CsvConnector(config)
        assert isinstance(connector, SourceConnector)


# ---------------------------------------------------------------------------
# B. Capabilities
# ---------------------------------------------------------------------------


class TestCapabilities:
    """CSV connector capabilities."""

    def test_read_only(self, tmp_path):
        connector = CsvConnector(_make_config(tmp_path))
        caps = connector.capabilities()
        assert caps.read_only is True

    def test_seven_entities(self, tmp_path):
        connector = CsvConnector(_make_config(tmp_path))
        caps = connector.capabilities()
        assert len(caps.supported_entity_types) == 7

    def test_entity_types(self, tmp_path):
        connector = CsvConnector(_make_config(tmp_path))
        caps = connector.capabilities()
        expected = {
            "customers", "deals", "documents", "employees",
            "organizations", "projects", "support_tickets",
        }
        assert set(caps.supported_entity_types) == expected

    def test_no_incremental(self, tmp_path):
        connector = CsvConnector(_make_config(tmp_path))
        caps = connector.capabilities()
        assert caps.supports_incremental is False

    def test_health_check_supported(self, tmp_path):
        connector = CsvConnector(_make_config(tmp_path))
        caps = connector.capabilities()
        assert caps.supports_health_check is True


# ---------------------------------------------------------------------------
# C. Health
# ---------------------------------------------------------------------------


class TestHealth:
    """CSV connector health checks."""

    def test_healthy_with_all_files(self, tmp_path):
        _create_all_entity_csvs(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        h = connector.health_check()
        assert h.healthy is True
        assert isinstance(h, ConnectorHealth)

    def test_unhealthy_missing_directory(self, tmp_path):
        config = _make_config(tmp_path / "nonexistent")
        connector = CsvConnector(config)
        h = connector.health_check()
        assert h.healthy is False
        assert "not found" in h.message.lower()

    def test_unhealthy_missing_files(self, tmp_path):
        connector = CsvConnector(_make_config(tmp_path))
        h = connector.health_check()
        assert h.healthy is False
        assert "missing" in h.message.lower()

    def test_source_name_in_health(self, tmp_path):
        connector = CsvConnector(_make_config(tmp_path))
        h = connector.health_check()
        assert h.source_name == "csv_test"


# ---------------------------------------------------------------------------
# D. Entity discovery
# ---------------------------------------------------------------------------


class TestEntityDiscovery:
    """list_entities must return entities whose files exist."""

    def test_all_entities_found(self, tmp_path):
        _create_all_entity_csvs(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        entities = connector.list_entities()
        assert len(entities) == 7
        assert all(isinstance(e, SourceEntity) for e in entities)

    def test_only_existing_files(self, tmp_path):
        _create_customers_csv(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        entities = connector.list_entities()
        entity_types = [e.entity_type for e in entities]
        assert "customers" in entity_types
        assert "deals" not in entity_types

    def test_empty_directory(self, tmp_path):
        connector = CsvConnector(_make_config(tmp_path))
        entities = connector.list_entities()
        assert entities == []

    def test_entity_types_match_spec(self, tmp_path):
        _create_all_entity_csvs(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        types = {e.entity_type for e in connector.list_entities()}
        expected = {
            "organizations", "employees", "customers", "deals",
            "projects", "support_tickets", "documents",
        }
        assert types == expected


# ---------------------------------------------------------------------------
# E. CSV parsing
# ---------------------------------------------------------------------------


class TestCsvParsing:
    """Test CSV parsing edge cases."""

    def test_quoted_values(self, tmp_path):
        _write_csv(tmp_path / "customers.csv",
                    ["customer_id", "customer_name"],
                    [["CUST-001", '"Acme, Inc."']])
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        # csv.DictReader handles quoting
        assert page.items[0]["customer_id"] == "CUST-001"

    def test_commas_inside_quotes(self, tmp_path):
        headers = ["customer_id", "customer_name"]
        path = tmp_path / "customers.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerow(["CUST-001", "Acme, Corp & Co."])
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        assert page.items[0]["customer_name"] == "Acme, Corp & Co."

    def test_empty_fields(self, tmp_path):
        _write_csv(tmp_path / "customers.csv",
                    ["customer_id", "customer_name", "email_address"],
                    [["CUST-001", "Test", ""]])
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        assert page.items[0]["email_address"] == ""

    def test_unicode(self, tmp_path):
        _write_csv(tmp_path / "customers.csv",
                    ["customer_id", "customer_name"],
                    [["CUST-001", "Müller GmbH"]])
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        assert page.items[0]["customer_name"] == "Müller GmbH"

    def test_multiline_text(self, tmp_path):
        headers = ["document_id", "title", "body_text"]
        path = tmp_path / "documents.csv"
        body = "Line 1\nLine 2\nLine 3"
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerow(["DOC-001", "Test Doc", body])
        config = _make_config(tmp_path, {
            "documents": {"file": "documents.csv", "id_column": "document_id"},
        })
        connector = CsvConnector(config)
        page = connector.fetch_entities("documents")
        assert page.items[0]["body_text"] == body


# ---------------------------------------------------------------------------
# F. Source IDs
# ---------------------------------------------------------------------------


class TestSourceIds:
    """Source IDs must come from configured ID columns."""

    def test_customer_id_from_csv(self, tmp_path):
        _create_customers_csv(tmp_path, count=3)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        ids = [r["customer_id"] for r in page.items]
        assert ids == ["CUST-001", "CUST-002", "CUST-003"]

    def test_ids_are_strings(self, tmp_path):
        _create_customers_csv(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        for row in page.items:
            assert isinstance(row["customer_id"], str)

    def test_ids_stable_across_calls(self, tmp_path):
        _create_customers_csv(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        ids1 = [r["customer_id"] for r in connector.fetch_entities("customers").items]
        ids2 = [r["customer_id"] for r in connector.fetch_entities("customers").items]
        assert ids1 == ids2


# ---------------------------------------------------------------------------
# G. Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    """Cursor-based pagination tests."""

    def test_single_page(self, tmp_path):
        _create_customers_csv(tmp_path, count=3)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers", page_size=10)
        assert len(page.items) == 3
        assert page.has_more is False
        assert page.next_cursor is None
        assert page.total_count == 3

    def test_multiple_pages(self, tmp_path):
        _create_customers_csv(tmp_path, count=5)
        connector = CsvConnector(_make_config(tmp_path))
        p1 = connector.fetch_entities("customers", page_size=2)
        assert len(p1.items) == 2
        assert p1.has_more is True
        assert p1.next_cursor is not None

        p2 = connector.fetch_entities("customers", cursor=p1.next_cursor, page_size=2)
        assert len(p2.items) == 2
        assert p2.has_more is True

        p3 = connector.fetch_entities("customers", cursor=p2.next_cursor, page_size=2)
        assert len(p3.items) == 1
        assert p3.has_more is False
        assert p3.next_cursor is None

    def test_page_size_one(self, tmp_path):
        _create_customers_csv(tmp_path, count=3)
        connector = CsvConnector(_make_config(tmp_path))
        p1 = connector.fetch_entities("customers", page_size=1)
        assert len(p1.items) == 1
        assert p1.has_more is True

    def test_page_size_larger_than_data(self, tmp_path):
        _create_customers_csv(tmp_path, count=3)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers", page_size=100)
        assert len(page.items) == 3
        assert page.has_more is False

    def test_empty_dataset(self, tmp_path):
        _write_csv(tmp_path / "customers.csv",
                    ["customer_id", "customer_name"], [])
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        assert len(page.items) == 0
        assert page.has_more is False
        assert page.total_count == 0

    def test_invalid_page_size_zero(self, tmp_path):
        _create_customers_csv(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        with pytest.raises(ConnectorRequestError):
            connector.fetch_entities("customers", page_size=0)

    def test_invalid_page_size_negative(self, tmp_path):
        _create_customers_csv(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        with pytest.raises(ConnectorRequestError):
            connector.fetch_entities("customers", page_size=-1)

    def test_invalid_cursor(self, tmp_path):
        _create_customers_csv(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        with pytest.raises(ConnectorRequestError):
            connector.fetch_entities("customers", cursor="not_a_number")

    def test_total_count(self, tmp_path):
        _create_customers_csv(tmp_path, count=10)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers", page_size=3)
        assert page.total_count == 10


# ---------------------------------------------------------------------------
# H. Cursor continuity
# ---------------------------------------------------------------------------


class TestCursorContinuity:
    """No duplicates, no skips across pages."""

    def test_no_duplicates_no_skips(self, tmp_path):
        _create_customers_csv(tmp_path, count=7)
        connector = CsvConnector(_make_config(tmp_path))

        all_ids = []
        cursor = None
        while True:
            page = connector.fetch_entities("customers", cursor=cursor, page_size=2)
            all_ids.extend(r["customer_id"] for r in page.items)
            if not page.has_more:
                break
            cursor = page.next_cursor

        expected = [f"CUST-{i:03d}" for i in range(1, 8)]
        assert all_ids == expected

    def test_deterministic_ordering(self, tmp_path):
        _create_customers_csv(tmp_path, count=5)
        connector = CsvConnector(_make_config(tmp_path))

        all_ids_1 = []
        cursor = None
        while True:
            page = connector.fetch_entities("customers", cursor=cursor, page_size=2)
            all_ids_1.extend(r["customer_id"] for r in page.items)
            if not page.has_more:
                break
            cursor = page.next_cursor

        all_ids_2 = []
        cursor = None
        while True:
            page = connector.fetch_entities("customers", cursor=cursor, page_size=2)
            all_ids_2.extend(r["customer_id"] for r in page.items)
            if not page.has_more:
                break
            cursor = page.next_cursor

        assert all_ids_1 == all_ids_2


# ---------------------------------------------------------------------------
# I. get_entity
# ---------------------------------------------------------------------------


class TestGetEntity:
    """Single record retrieval."""

    def test_existing_entity(self, tmp_path):
        _create_customers_csv(tmp_path, count=3)
        connector = CsvConnector(_make_config(tmp_path))
        record = connector.get_entity("customers", "CUST-002")
        assert record["customer_id"] == "CUST-002"
        assert record["customer_name"] == "Customer 2"

    def test_missing_entity_raises(self, tmp_path):
        _create_customers_csv(tmp_path, count=3)
        connector = CsvConnector(_make_config(tmp_path))
        with pytest.raises(ConnectorEntityError):
            connector.get_entity("customers", "NONEXISTENT")

    def test_unconfigured_entity_type_raises(self, tmp_path):
        connector = CsvConnector(_make_config(tmp_path))
        with pytest.raises(ConnectorEntityError):
            connector.get_entity("unknown_type", "ID-001")


# ---------------------------------------------------------------------------
# J. Unknown columns
# ---------------------------------------------------------------------------


class TestUnknownColumns:
    """CSV with extra columns must still be readable."""

    def test_extra_columns_preserved_in_dict(self, tmp_path):
        _write_csv(tmp_path / "customers.csv",
                    ["customer_id", "customer_name", "new_future_field"],
                    [["CUST-001", "Test", "extra_value"]])
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        row = page.items[0]
        assert row["customer_id"] == "CUST-001"
        assert row["new_future_field"] == "extra_value"


# ---------------------------------------------------------------------------
# K. Missing required columns
# ---------------------------------------------------------------------------


class TestMissingRequiredColumns:
    """Missing ID column should cause retrieval failure."""

    def test_missing_id_column_get_entity(self, tmp_path):
        _write_csv(tmp_path / "customers.csv",
                    ["name", "email"],
                    [["Test", "test@example.com"]])
        connector = CsvConnector(_make_config(tmp_path))
        with pytest.raises(ConnectorEntityError):
            connector.get_entity("customers", "CUST-001")


# ---------------------------------------------------------------------------
# L. Raw value preservation
# ---------------------------------------------------------------------------


class TestRawValuePreservation:
    """Source values must remain exactly as they appear in CSV."""

    def test_whitespace_preserved(self, tmp_path):
        _write_csv(tmp_path / "customers.csv",
                    ["customer_id", "customer_name", "email_address"],
                    [["CUST-001", "  Acme Corp  ", "  user@example.com  "]])
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        row = page.items[0]
        assert row["customer_name"] == "  Acme Corp  "
        assert row["email_address"] == "  user@example.com  "

    def test_leading_zeros_preserved(self, tmp_path):
        _write_csv(tmp_path / "customers.csv",
                    ["customer_id", "customer_name"],
                    [["00123", "Test"]])
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        assert page.items[0]["customer_id"] == "00123"

    def test_monetary_string_preserved(self, tmp_path):
        _write_csv(tmp_path / "deals.csv",
                    ["deal_id", "deal_name", "amount", "probability"],
                    [["DEAL-001", "Test", "125000.50", "0.75"]])
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("deals")
        row = page.items[0]
        assert row["amount"] == "125000.50"
        assert isinstance(row["amount"], str)
        assert row["probability"] == "0.75"
        assert isinstance(row["probability"], str)


# ---------------------------------------------------------------------------
# M. No canonical transformation
# ---------------------------------------------------------------------------


class TestNoCanonicalTransformation:
    """C2 must not produce canonical types."""

    def test_no_uuid_in_records(self, tmp_path):
        _create_customers_csv(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        for row in page.items:
            for val in row.values():
                if isinstance(val, str):
                    try:
                        uuid.UUID(val)
                        pytest.fail(f"UUID found in source record: {val}")
                    except ValueError:
                        pass

    def test_no_decimal_in_records(self, tmp_path):
        from decimal import Decimal
        _write_csv(tmp_path / "deals.csv",
                    ["deal_id", "deal_name", "amount"],
                    [["DEAL-001", "Test", "100000.00"]])
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("deals")
        for row in page.items:
            for val in row.values():
                assert not isinstance(val, Decimal)

    def test_no_canonical_field_names(self, tmp_path):
        _create_customers_csv(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        row = page.items[0]
        # CSV uses customer_name, not canonical "name"
        assert "customer_name" in row
        # Canonical provenance fields should not exist
        assert "ingestion_run_id" not in row
        assert "ingested_at" not in row
        assert "record_hash" not in row
        assert "source_system" not in row
        assert "source_entity" not in row


# ---------------------------------------------------------------------------
# N. Read-only
# ---------------------------------------------------------------------------


class TestReadOnly:
    """CSV connector must have no write operations."""

    WRITE_METHODS = [
        "create_entity", "update_entity", "delete_entity",
        "write_entity", "post", "put", "patch",
        "create", "update", "delete", "write", "insert",
    ]

    def test_no_write_methods(self, tmp_path):
        connector = CsvConnector(_make_config(tmp_path))
        for method in self.WRITE_METHODS:
            assert not hasattr(connector, method)

    def test_no_database_imports(self):
        import app.connectors.csv as csv_mod
        source = inspect.getsource(csv_mod)
        import_lines = [
            line.strip() for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            assert "sqlalchemy" not in line
            assert "app.persistence" not in line
            assert "app.core.database" not in line

    def test_no_http_imports(self):
        import app.connectors.csv as csv_mod
        source = inspect.getsource(csv_mod)
        import_lines = [
            line.strip() for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            assert "httpx" not in line
            assert "import requests" not in line


# ---------------------------------------------------------------------------
# O. B3 compatibility
# ---------------------------------------------------------------------------


class TestB3Compatibility:
    """CSV records must be compatible with B3 source schemas."""

    def test_organization_row(self, tmp_path):
        _create_all_entity_csvs(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("organizations")
        row = page.items[0]
        org = CsvOrganizationSource(**row)
        assert org.organization_id == "ORG-001"
        assert org.organization_name == "Acme Corp"

    def test_employee_row(self, tmp_path):
        _create_all_entity_csvs(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("employees")
        row = page.items[0]
        emp = CsvEmployeeSource(**row)
        assert emp.employee_id == "EMP-001"

    def test_customer_row(self, tmp_path):
        _create_all_entity_csvs(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        row = page.items[0]
        cust = CsvCustomerSource(**row)
        assert cust.customer_id == "CUST-001"

    def test_deal_row(self, tmp_path):
        _create_all_entity_csvs(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("deals")
        row = page.items[0]
        deal = CsvDealSource(**row)
        assert deal.deal_id == "DEAL-001"
        assert deal.amount == "150000.50"

    def test_project_row(self, tmp_path):
        _create_all_entity_csvs(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("projects")
        row = page.items[0]
        proj = CsvProjectSource(**row)
        assert proj.project_id == "PROJ-001"

    def test_support_ticket_row(self, tmp_path):
        _create_all_entity_csvs(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("support_tickets")
        row = page.items[0]
        ticket = CsvSupportTicketSource(**row)
        assert ticket.ticket_id == "TKT-001"

    def test_document_row(self, tmp_path):
        _create_all_entity_csvs(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("documents")
        row = page.items[0]
        doc = CsvDocumentSource(**row)
        assert doc.document_id == "DOC-001"


# ---------------------------------------------------------------------------
# P. Cross-boundary (C2 → B3, not C2 → B2)
# ---------------------------------------------------------------------------


class TestCrossBoundary:
    """C2 outputs must be compatible with B3 but NOT directly with B2."""

    def test_csv_row_is_not_canonical(self, tmp_path):
        """CSV dict does not have canonical provenance fields."""
        _create_customers_csv(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        row = page.items[0]
        canonical_fields = {"id", "source_system", "source_entity",
                            "source_id", "ingestion_run_id", "ingested_at",
                            "record_hash"}
        assert not canonical_fields.intersection(row.keys())

    def test_csv_row_compatible_with_b3(self, tmp_path):
        """CSV rows must validate against B3 source schemas."""
        _create_customers_csv(tmp_path)
        connector = CsvConnector(_make_config(tmp_path))
        page = connector.fetch_entities("customers")
        for row in page.items:
            cust = CsvCustomerSource(**row)
            assert cust.customer_id == row["customer_id"]

    def test_csv_module_no_canonical_import(self):
        """csv.py must not import canonical schemas."""
        import app.connectors.csv as csv_mod
        source = inspect.getsource(csv_mod)
        import_lines = [
            line.strip() for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            assert "app.schemas.canonical" not in line
