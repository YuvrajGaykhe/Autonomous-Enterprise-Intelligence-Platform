"""
C3 Mock-Source HTTP Server Tests.

Tests the deterministic mock-source service by starting it in a
background thread with CSV fixture data and making real HTTP requests.

The mock server reads from CSV files (shared demo data architecture)
and transforms them into Odoo-style and REST-style payloads.

Test categories:
A. Health
B. Odoo entity endpoints (all 7)
C. REST entity endpoints (all 7)
D. Odoo source shape
E. REST source shape
F. Source ID types
G. Relationships
H. Pagination
I. Individual lookup
J. Unknown entity
K. Unknown route
L. Read-only (405)
M. Malformed pagination
N. Determinism
O. JSON content type
P. Cross-source difference (/odoo != /rest)
Q. CSV-based data source verification
"""

import csv
import json
import threading
import time
from http.server import HTTPServer
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError

import pytest

# Import the mock server module
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "docker"))
import mock_source  # noqa: E402


# ---------------------------------------------------------------------------
# CSV fixture creation (matches B3 CSV schema field names)
# ---------------------------------------------------------------------------


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def _create_fixture_csvs(data_dir: Path) -> None:
    """Create minimal CSV fixture files matching B3 CSV schemas."""
    data_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(data_dir / "organizations.csv",
               ["organization_id", "organization_name", "industry", "country", "status"],
               [
                   ["ORG-001", "Acme Corp", "Technology", "India", "active"],
                   ["ORG-002", "GlobalTech Solutions", "Technology", "United States", "active"],
                   ["ORG-003", "Pinnacle Industries", "Manufacturing", "Germany", "active"],
               ])

    _write_csv(data_dir / "employees.csv",
               ["employee_id", "employee_name", "email_address", "department",
                "title", "manager_id", "status", "hire_date", "is_active", "organization_id"],
               [
                   ["EMP-001", "Alice Engineer", "alice@acme.example", "Engineering",
                    "Senior Developer", "", "active", "2024-03-15", "true", "ORG-001"],
                   ["EMP-002", "Bob Manager", "bob@acme.example", "Sales",
                    "Sales Manager", "", "active", "2023-06-01", "true", "ORG-001"],
                   ["EMP-003", "Carol Analyst", "carol@globaltech.example", "Analytics",
                    "Data Analyst", "EMP-002", "active", "2025-01-10", "true", "ORG-002"],
               ])

    _write_csv(data_dir / "customers.csv",
               ["customer_id", "customer_name", "email_address", "customer_segment",
                "industry_name", "account_owner_id", "status", "created_date"],
               [
                   ["CUST-001", "Acme Industries", "contact@acme-ind.example",
                    "Enterprise", "Manufacturing", "EMP-002", "active", "2025-01-15"],
                   ["CUST-002", "Widget Corp", "info@widget.example",
                    "SMB", "Retail", "EMP-002", "active", "2025-03-20"],
                   ["CUST-003", "DataFlow Systems", "hello@dataflow.example",
                    "Enterprise", "Technology", "EMP-001", "active", "2025-06-10"],
               ])

    _write_csv(data_dir / "deals.csv",
               ["deal_id", "deal_name", "customer_id", "owner_id", "stage",
                "amount", "currency", "probability", "expected_close_date", "is_active"],
               [
                   ["DEAL-001", "Acme Platform Deal", "CUST-001", "EMP-002",
                    "negotiation", "150000.50", "INR", "75.0", "2026-12-31", "true"],
                   ["DEAL-002", "Widget CRM Migration", "CUST-002", "EMP-001",
                    "qualification", "45000.00", "USD", "40.0", "2026-09-30", "true"],
                   ["DEAL-003", "DataFlow Analytics Suite", "CUST-003", "EMP-001",
                    "won", "280000.00", "EUR", "100.0", "2026-06-15", "true"],
               ])

    _write_csv(data_dir / "projects.csv",
               ["project_id", "project_name", "customer_id", "owner_id", "status",
                "start_date", "end_date", "budget", "is_active"],
               [
                   ["PROJ-001", "Platform Migration", "CUST-001", "EMP-001",
                    "in_progress", "2026-01-01", "2026-12-31", "500000.00", "true"],
                   ["PROJ-002", "CRM Integration", "CUST-002", "EMP-002",
                    "planning", "2026-04-01", "2026-10-31", "120000.00", "true"],
               ])

    _write_csv(data_dir / "support_tickets.csv",
               ["ticket_id", "customer_id", "assignee_id", "priority", "status",
                "category", "subject", "description", "created_date", "resolved_date"],
               [
                   ["TKT-001", "CUST-001", "EMP-001", "high", "open",
                    "auth", "Login not working after SSO update",
                    "Users cannot log in after the SSO provider migration.", "2026-09-01", ""],
                   ["TKT-002", "CUST-002", "EMP-003", "medium", "resolved",
                    "billing", "Invoice discrepancy Q3",
                    "Invoice totals do not match the agreed contract.", "2026-08-15", "2026-08-20"],
               ])

    _write_csv(data_dir / "documents.csv",
               ["document_id", "title", "document_type", "body_text", "source_uri",
                "owner_id", "created_date", "updated_date"],
               [
                   ["DOC-001", "Employee Handbook 2026", "policy", "",
                    "https://internal.acme.example/docs/handbook.pdf",
                    "EMP-001", "2026-01-01", "2026-06-15"],
                   ["DOC-002", "Q3 Sales Report", "report", "",
                    "https://internal.acme.example/reports/q3-sales.pdf",
                    "EMP-002", "2026-07-01", "2026-09-05"],
               ])


# ---------------------------------------------------------------------------
# Server fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mock_server(tmp_path_factory):
    """Start mock-source HTTP server with CSV fixture data."""
    data_dir = tmp_path_factory.mktemp("mock_data")
    _create_fixture_csvs(data_dir)

    # Load data from CSV fixtures
    odoo, rest = mock_source.load_source_data(data_dir)
    mock_source.ODOO_DATA.update(odoo)
    mock_source.REST_DATA.update(rest)

    server = HTTPServer(("127.0.0.1", 0), mock_source.MockSourceHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def _get(base_url: str, path: str) -> tuple[int, dict, dict]:
    """GET request returning (status_code, body_dict, headers_dict)."""
    url = f"{base_url}{path}"
    try:
        req = Request(url)
        with urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            headers = dict(resp.headers)
            return resp.status, body, headers
    except HTTPError as e:
        body = json.loads(e.read().decode("utf-8"))
        headers = dict(e.headers)
        return e.code, body, headers


def _request(base_url: str, path: str, method: str) -> tuple[int, dict]:
    """Send request with given method."""
    url = f"{base_url}{path}"
    try:
        req = Request(url, method=method)
        with urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body
    except HTTPError as e:
        body = json.loads(e.read().decode("utf-8"))
        return e.code, body


ENTITIES = [
    "organizations", "employees", "customers",
    "deals", "projects", "support_tickets", "documents",
]


# ---------------------------------------------------------------------------
# A. Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_returns_200(self, mock_server):
        status, body, _ = _get(mock_server, "/health")
        assert status == 200

    def test_health_is_healthy(self, mock_server):
        _, body, _ = _get(mock_server, "/health")
        assert body["status"] == "healthy"

    def test_health_has_entities(self, mock_server):
        _, body, _ = _get(mock_server, "/health")
        assert "entities" in body
        assert len(body["entities"]) == 7


# ---------------------------------------------------------------------------
# B. Odoo entity endpoints (all 7)
# ---------------------------------------------------------------------------


class TestOdooEndpoints:
    @pytest.mark.parametrize("entity", ENTITIES)
    def test_odoo_entity_returns_200(self, mock_server, entity):
        status, body, _ = _get(mock_server, f"/odoo/{entity}")
        assert status == 200

    @pytest.mark.parametrize("entity", ENTITIES)
    def test_odoo_entity_has_data(self, mock_server, entity):
        _, body, _ = _get(mock_server, f"/odoo/{entity}")
        assert "data" in body
        assert isinstance(body["data"], list)
        assert len(body["data"]) > 0

    @pytest.mark.parametrize("entity", ENTITIES)
    def test_odoo_entity_has_pagination(self, mock_server, entity):
        _, body, _ = _get(mock_server, f"/odoo/{entity}")
        assert "pagination" in body
        p = body["pagination"]
        assert "total" in p
        assert "has_more" in p
        assert "offset" in p
        assert "limit" in p


# ---------------------------------------------------------------------------
# C. REST entity endpoints (all 7)
# ---------------------------------------------------------------------------


class TestRestEndpoints:
    @pytest.mark.parametrize("entity", ENTITIES)
    def test_rest_entity_returns_200(self, mock_server, entity):
        status, body, _ = _get(mock_server, f"/rest/{entity}")
        assert status == 200

    @pytest.mark.parametrize("entity", ENTITIES)
    def test_rest_entity_has_data(self, mock_server, entity):
        _, body, _ = _get(mock_server, f"/rest/{entity}")
        assert "data" in body
        assert isinstance(body["data"], list)
        assert len(body["data"]) > 0


# ---------------------------------------------------------------------------
# D. Odoo source shape
# ---------------------------------------------------------------------------


class TestOdooShape:
    def test_odoo_customer_has_odoo_fields(self, mock_server):
        _, body, _ = _get(mock_server, "/odoo/customers")
        cust = body["data"][0]
        assert "id" in cust
        assert "name" in cust
        assert "x_studio_segment" in cust
        assert "user_id" in cust
        assert "create_date" in cust
        assert "customer_rank" in cust

    def test_odoo_customer_no_canonical_fields(self, mock_server):
        _, body, _ = _get(mock_server, "/odoo/customers")
        cust = body["data"][0]
        assert "customer_id" not in cust
        assert "customer_name" not in cust
        assert "segment" not in cust
        assert "ownerId" not in cust
        assert "createdAt" not in cust

    def test_odoo_deal_has_odoo_fields(self, mock_server):
        _, body, _ = _get(mock_server, "/odoo/deals")
        deal = body["data"][0]
        assert "partner_id" in deal
        assert "expected_revenue" in deal
        assert "company_currency" in deal
        assert "date_deadline" in deal
        assert "stage_id" in deal

    def test_odoo_employee_has_odoo_fields(self, mock_server):
        _, body, _ = _get(mock_server, "/odoo/employees")
        emp = body["data"][0]
        assert "work_email" in emp
        assert "job_title" in emp
        assert "x_hire_date" in emp
        assert "company_id" in emp


# ---------------------------------------------------------------------------
# E. REST source shape
# ---------------------------------------------------------------------------


class TestRestShape:
    def test_rest_customer_has_camelcase(self, mock_server):
        _, body, _ = _get(mock_server, "/rest/customers")
        cust = body["data"][0]
        assert "id" in cust
        assert "name" in cust
        assert "segment" in cust
        assert "ownerId" in cust
        assert "createdAt" in cust
        assert "isActive" in cust

    def test_rest_customer_no_odoo_fields(self, mock_server):
        _, body, _ = _get(mock_server, "/rest/customers")
        cust = body["data"][0]
        assert "x_studio_segment" not in cust
        assert "user_id" not in cust
        assert "create_date" not in cust
        assert "customer_rank" not in cust

    def test_rest_deal_has_camelcase(self, mock_server):
        _, body, _ = _get(mock_server, "/rest/deals")
        deal = body["data"][0]
        assert "customerId" in deal
        assert "ownerId" in deal
        assert "expectedCloseDate" in deal
        assert "amount" in deal

    def test_rest_employee_has_camelcase(self, mock_server):
        _, body, _ = _get(mock_server, "/rest/employees")
        emp = body["data"][0]
        assert "managerId" in emp
        assert "hireDate" in emp
        assert "isActive" in emp
        assert "organizationId" in emp


# ---------------------------------------------------------------------------
# F. Source ID types
# ---------------------------------------------------------------------------


class TestSourceIdTypes:
    def test_odoo_ids_are_integers(self, mock_server):
        _, body, _ = _get(mock_server, "/odoo/customers")
        for rec in body["data"]:
            assert isinstance(rec["id"], int)

    def test_rest_ids_are_strings(self, mock_server):
        _, body, _ = _get(mock_server, "/rest/customers")
        for rec in body["data"]:
            assert isinstance(rec["id"], str)

    def test_odoo_employee_ids_are_integers(self, mock_server):
        _, body, _ = _get(mock_server, "/odoo/employees")
        for rec in body["data"]:
            assert isinstance(rec["id"], int)

    def test_rest_deal_ids_are_strings(self, mock_server):
        _, body, _ = _get(mock_server, "/rest/deals")
        for rec in body["data"]:
            assert isinstance(rec["id"], str)


# ---------------------------------------------------------------------------
# G. Relationships
# ---------------------------------------------------------------------------


class TestRelationships:
    def test_odoo_deal_partner_id_is_int(self, mock_server):
        _, body, _ = _get(mock_server, "/odoo/deals")
        deal = body["data"][0]
        assert isinstance(deal["partner_id"], int)

    def test_odoo_employee_parent_id_is_int_or_none(self, mock_server):
        _, body, _ = _get(mock_server, "/odoo/employees")
        for emp in body["data"]:
            assert emp["parent_id"] is None or isinstance(emp["parent_id"], int)

    def test_rest_deal_customer_id_is_string(self, mock_server):
        _, body, _ = _get(mock_server, "/rest/deals")
        deal = body["data"][0]
        assert isinstance(deal["customerId"], str)

    def test_rest_employee_manager_id_is_string_or_none(self, mock_server):
        _, body, _ = _get(mock_server, "/rest/employees")
        for emp in body["data"]:
            assert emp["managerId"] is None or isinstance(emp["managerId"], str)


# ---------------------------------------------------------------------------
# H. Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    def test_default_returns_all(self, mock_server):
        _, body, _ = _get(mock_server, "/odoo/customers")
        assert body["pagination"]["total"] == 3
        assert body["pagination"]["has_more"] is False
        assert len(body["data"]) == 3

    def test_limit_one(self, mock_server):
        _, body, _ = _get(mock_server, "/odoo/customers?limit=1")
        assert len(body["data"]) == 1
        assert body["pagination"]["has_more"] is True
        assert body["pagination"]["next_offset"] == 1

    def test_limit_offset(self, mock_server):
        _, body, _ = _get(mock_server, "/odoo/customers?limit=1&offset=1")
        assert len(body["data"]) == 1
        # Second customer from CSV
        assert body["data"][0]["name"] == "Widget Corp"

    def test_last_page(self, mock_server):
        _, body, _ = _get(mock_server, "/odoo/customers?limit=1&offset=2")
        assert len(body["data"]) == 1
        assert body["pagination"]["has_more"] is False

    def test_offset_beyond_data(self, mock_server):
        _, body, _ = _get(mock_server, "/odoo/customers?limit=10&offset=100")
        assert len(body["data"]) == 0
        assert body["pagination"]["has_more"] is False

    def test_rest_pagination(self, mock_server):
        _, body, _ = _get(mock_server, "/rest/customers?limit=2")
        assert len(body["data"]) == 2
        assert body["pagination"]["has_more"] is True


# ---------------------------------------------------------------------------
# I. Individual lookup
# ---------------------------------------------------------------------------


class TestIndividualLookup:
    def test_odoo_customer_by_id(self, mock_server):
        """Odoo customer ID is extracted from CSV: CUST-001 -> int 1."""
        _, body, _ = _get(mock_server, "/odoo/customers")
        first_id = body["data"][0]["id"]
        status, detail, _ = _get(mock_server, f"/odoo/customers/{first_id}")
        assert status == 200
        assert detail["data"]["name"] == "Acme Industries"

    def test_rest_customer_by_id(self, mock_server):
        """REST customer ID is the original CSV string."""
        status, body, _ = _get(mock_server, "/rest/customers/CUST-001")
        assert status == 200
        assert body["data"]["id"] == "CUST-001"
        assert body["data"]["name"] == "Acme Industries"

    def test_odoo_missing_record_404(self, mock_server):
        status, body, _ = _get(mock_server, "/odoo/customers/9999")
        assert status == 404
        assert body["error"] == "not_found"

    def test_rest_missing_record_404(self, mock_server):
        status, body, _ = _get(mock_server, "/rest/customers/NONEXISTENT")
        assert status == 404
        assert body["error"] == "not_found"


# ---------------------------------------------------------------------------
# J. Unknown entity
# ---------------------------------------------------------------------------


class TestUnknownEntity:
    def test_odoo_unknown_entity_404(self, mock_server):
        status, body, _ = _get(mock_server, "/odoo/not_an_entity")
        assert status == 404
        assert body["error"] == "unknown_entity"

    def test_rest_unknown_entity_404(self, mock_server):
        status, body, _ = _get(mock_server, "/rest/not_an_entity")
        assert status == 404
        assert body["error"] == "unknown_entity"


# ---------------------------------------------------------------------------
# K. Unknown route
# ---------------------------------------------------------------------------


class TestUnknownRoute:
    def test_random_path_404(self, mock_server):
        status, body, _ = _get(mock_server, "/something-else")
        assert status == 404
        assert body["error"] == "not_found"

    def test_partial_path_404(self, mock_server):
        status, body, _ = _get(mock_server, "/odoo")
        assert status == 404


# ---------------------------------------------------------------------------
# L. Read-only (405)
# ---------------------------------------------------------------------------


class TestReadOnly:
    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
    def test_write_method_rejected(self, mock_server, method):
        status, body = _request(mock_server, "/odoo/customers", method)
        assert status == 405
        assert body["error"] == "method_not_allowed"


# ---------------------------------------------------------------------------
# M. Malformed pagination
# ---------------------------------------------------------------------------


class TestMalformedPagination:
    def test_limit_zero(self, mock_server):
        status, body, _ = _get(mock_server, "/odoo/customers?limit=0")
        assert status == 400
        assert "invalid_parameter" in body["error"]

    def test_limit_negative(self, mock_server):
        status, body, _ = _get(mock_server, "/odoo/customers?limit=-1")
        assert status == 400

    def test_offset_negative(self, mock_server):
        status, body, _ = _get(mock_server, "/odoo/customers?offset=-5")
        assert status == 400

    def test_limit_non_integer(self, mock_server):
        status, body, _ = _get(mock_server, "/odoo/customers?limit=abc")
        assert status == 400


# ---------------------------------------------------------------------------
# N. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_odoo_customers_deterministic(self, mock_server):
        _, body1, _ = _get(mock_server, "/odoo/customers")
        _, body2, _ = _get(mock_server, "/odoo/customers")
        assert body1 == body2

    def test_rest_customers_deterministic(self, mock_server):
        _, body1, _ = _get(mock_server, "/rest/customers")
        _, body2, _ = _get(mock_server, "/rest/customers")
        assert body1 == body2

    def test_odoo_deals_deterministic(self, mock_server):
        _, body1, _ = _get(mock_server, "/odoo/deals")
        _, body2, _ = _get(mock_server, "/odoo/deals")
        assert body1 == body2


# ---------------------------------------------------------------------------
# O. JSON content type
# ---------------------------------------------------------------------------


class TestJsonContentType:
    def test_health_content_type(self, mock_server):
        _, _, headers = _get(mock_server, "/health")
        assert "application/json" in headers.get("Content-Type", "")

    def test_entity_content_type(self, mock_server):
        _, _, headers = _get(mock_server, "/odoo/customers")
        assert "application/json" in headers.get("Content-Type", "")


# ---------------------------------------------------------------------------
# P. Cross-source difference
# ---------------------------------------------------------------------------


class TestCrossSourceDifference:
    def test_odoo_vs_rest_customer_fields_differ(self, mock_server):
        """Same conceptual customer has different field names."""
        _, odoo_body, _ = _get(mock_server, "/odoo/customers")
        _, rest_body, _ = _get(mock_server, "/rest/customers")

        odoo_cust = odoo_body["data"][0]
        rest_cust = rest_body["data"][0]

        # Odoo-specific fields
        assert "x_studio_segment" in odoo_cust
        assert "user_id" in odoo_cust
        assert "create_date" in odoo_cust

        # REST-specific fields
        assert "segment" in rest_cust
        assert "ownerId" in rest_cust
        assert "createdAt" in rest_cust

        # Cross-check: no field leakage
        assert "segment" not in odoo_cust
        assert "ownerId" not in odoo_cust
        assert "createdAt" not in odoo_cust
        assert "x_studio_segment" not in rest_cust
        assert "user_id" not in rest_cust
        assert "create_date" not in rest_cust

    def test_odoo_vs_rest_id_types_differ(self, mock_server):
        _, odoo_body, _ = _get(mock_server, "/odoo/customers")
        _, rest_body, _ = _get(mock_server, "/rest/customers")
        assert isinstance(odoo_body["data"][0]["id"], int)
        assert isinstance(rest_body["data"][0]["id"], str)

    def test_odoo_vs_rest_deal_fields_differ(self, mock_server):
        _, odoo_body, _ = _get(mock_server, "/odoo/deals")
        _, rest_body, _ = _get(mock_server, "/rest/deals")
        odoo_deal = odoo_body["data"][0]
        rest_deal = rest_body["data"][0]
        assert "partner_id" in odoo_deal
        assert "customerId" in rest_deal
        assert "partner_id" not in rest_deal
        assert "customerId" not in odoo_deal


# ---------------------------------------------------------------------------
# Q. CSV data source verification
# ---------------------------------------------------------------------------


class TestCsvDataSource:
    """Verify mock-source data comes from CSV, not hardcoded fixtures."""

    def test_odoo_customer_name_from_csv(self, mock_server):
        """Customer name must match the CSV fixture data."""
        _, body, _ = _get(mock_server, "/odoo/customers")
        names = [c["name"] for c in body["data"]]
        assert "Acme Industries" in names
        assert "Widget Corp" in names
        assert "DataFlow Systems" in names

    def test_rest_customer_name_from_csv(self, mock_server):
        _, body, _ = _get(mock_server, "/rest/customers")
        names = [c["name"] for c in body["data"]]
        assert "Acme Industries" in names

    def test_same_customers_in_both_sources(self, mock_server):
        """Both /odoo and /rest derive from the same CSV."""
        _, odoo, _ = _get(mock_server, "/odoo/customers")
        _, rest, _ = _get(mock_server, "/rest/customers")
        odoo_names = sorted(c["name"] for c in odoo["data"])
        rest_names = sorted(c["name"] for c in rest["data"])
        assert odoo_names == rest_names

    def test_record_count_matches_csv(self, mock_server):
        """Number of records must match CSV row count."""
        _, body, _ = _get(mock_server, "/odoo/customers")
        assert body["pagination"]["total"] == 3

    def test_load_source_data_returns_both(self, tmp_path):
        """load_source_data() produces both Odoo and REST dicts."""
        _create_fixture_csvs(tmp_path)
        odoo, rest = mock_source.load_source_data(tmp_path)
        assert "customers" in odoo
        assert "customers" in rest
        assert len(odoo["customers"]) == 3
        assert len(rest["customers"]) == 3

    def test_missing_csv_produces_empty_list(self, tmp_path):
        """Missing CSV files result in empty entity lists, not crashes."""
        tmp_path.mkdir(exist_ok=True)
        odoo, rest = mock_source.load_source_data(tmp_path)
        for entity in mock_source.VALID_ENTITIES:
            assert odoo[entity] == []
            assert rest[entity] == []

    def test_odoo_deal_amount_from_csv(self, mock_server):
        """Deal amount must come from CSV, converted to float for typed JSON."""
        _, body, _ = _get(mock_server, "/odoo/deals")
        deal = body["data"][0]
        assert deal["expected_revenue"] == 150000.50
        assert isinstance(deal["expected_revenue"], float)

    def test_rest_deal_amount_from_csv(self, mock_server):
        _, body, _ = _get(mock_server, "/rest/deals")
        deal = body["data"][0]
        assert deal["amount"] == 150000.50
