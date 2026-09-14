"""
D1 Normalization Tests.

Comprehensive test suite for the normalization pipeline covering:
A. Interface / public API
B. Entity coverage (all 7 entities x 3 sources)
C. Field mapping correctness
D. Type conversions (str, int, float, Decimal, bool, date, datetime)
E. Identity (deterministic UUIDs, record_hash)
F. Relationships (source keys, canonical FK = None)
G. Null semantics (None, empty, whitespace, zero, false)
H. Error handling (malformed, missing, unsupported)
I. Boundary (no SQLAlchemy, no database, no HTTP, no connectors)
J. Determinism (repeated normalization = same output)
K. Batch normalization
"""

from __future__ import annotations

import ast
import hashlib
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.normalization import (
    CoercionError,
    FieldMappingError,
    NormalizationError,
    UnsupportedEntityError,
    UnsupportedSourceError,
    canonical_id,
    normalize,
    normalize_batch,
    record_hash,
)
from app.normalization.coercion import (
    coerce_bool,
    coerce_date,
    coerce_datetime,
    coerce_decimal,
    coerce_email,
    coerce_int_id_to_str,
    coerce_str,
)
from app.normalization.mappings import (
    SUPPORTED_ENTITIES,
    SUPPORTED_SOURCES,
    extract_source_id,
    get_mapper,
    has_is_active,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

_RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_INGESTED_AT = datetime(2026, 9, 14, 12, 0, 0)


def _csv_customer() -> dict[str, Any]:
    return {
        "customer_id": "CUST-001",
        "customer_name": "Acme Industries",
        "email_address": " Contact@Acme.Example ",
        "customer_segment": "Enterprise",
        "industry_name": "Manufacturing",
        "account_owner_id": "EMP-002",
        "status": "active",
        "created_date": "2025-01-15",
    }


def _odoo_customer() -> dict[str, Any]:
    return {
        "id": 42,
        "name": "Widget Corp",
        "email": " info@widget.example ",
        "x_studio_segment": "SMB",
        "industry_id": "Retail",
        "user_id": 7,
        "active": True,
        "create_date": "2025-03-20T10:30:00",
        "customer_rank": 1,
    }


def _rest_customer() -> dict[str, Any]:
    return {
        "id": "REST-C-001",
        "name": "RestCo",
        "email": " rest@example.com ",
        "segment": "Enterprise",
        "industry": "Tech",
        "ownerId": "EMP-005",
        "status": "active",
        "createdAt": "2025-06-01",
        "isActive": True,
    }


def _csv_employee() -> dict[str, Any]:
    return {
        "employee_id": "EMP-001",
        "employee_name": "Alice Engineer",
        "email_address": " Alice@Acme.Example ",
        "department": "Engineering",
        "title": "Senior Developer",
        "manager_id": None,
        "status": "active",
        "hire_date": "2024-03-15",
        "is_active": "true",
        "organization_id": "ORG-001",
    }


def _odoo_employee() -> dict[str, Any]:
    return {
        "id": 10,
        "name": "Bob Manager",
        "work_email": " bob@acme.example ",
        "department_id": "Sales",
        "job_title": "Sales Manager",
        "parent_id": None,
        "active": True,
        "x_hire_date": "2023-06-01",
        "company_id": 1,
    }


def _csv_deal() -> dict[str, Any]:
    return {
        "deal_id": "DEAL-001",
        "deal_name": "Acme Platform Deal",
        "customer_id": "CUST-001",
        "owner_id": "EMP-002",
        "stage": "negotiation",
        "amount": "150000.50",
        "currency": "INR",
        "probability": "75.0",
        "expected_close_date": "2026-12-31",
        "is_active": "true",
    }


def _odoo_deal() -> dict[str, Any]:
    return {
        "id": 5,
        "name": "Odoo Deal",
        "partner_id": 42,
        "user_id": 10,
        "stage_id": "qualification",
        "expected_revenue": 45000.0,
        "company_currency": "USD",
        "probability": 40.0,
        "date_deadline": "2026-09-30",
        "active": True,
    }


def _rest_deal() -> dict[str, Any]:
    return {
        "id": "REST-D-001",
        "name": "REST Deal",
        "customerId": "REST-C-001",
        "ownerId": "EMP-005",
        "stage": "closed_won",
        "amount": 99000.0,
        "currency": "EUR",
        "probability": 100.0,
        "expectedCloseDate": "2026-06-30",
        "isActive": False,
    }


def _csv_organization() -> dict[str, Any]:
    return {
        "organization_id": "ORG-001",
        "organization_name": "Acme Corp",
        "industry": "Technology",
        "country": "India",
        "status": "active",
    }


def _csv_project() -> dict[str, Any]:
    return {
        "project_id": "PROJ-001",
        "project_name": "Platform Migration",
        "customer_id": "CUST-001",
        "owner_id": "EMP-001",
        "status": "in_progress",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "budget": "500000.00",
        "is_active": "true",
    }


def _csv_support_ticket() -> dict[str, Any]:
    return {
        "ticket_id": "TKT-001",
        "customer_id": "CUST-001",
        "assignee_id": "EMP-001",
        "priority": "high",
        "status": "open",
        "category": "auth",
        "subject": "Login not working after SSO update",
        "description": "Users cannot log in after the SSO provider migration.",
        "created_date": "2026-09-01",
        "resolved_date": None,
    }


def _csv_document() -> dict[str, Any]:
    return {
        "document_id": "DOC-001",
        "title": "Employee Handbook 2026",
        "document_type": "policy",
        "body_text": "",
        "source_uri": "https://internal.acme.example/docs/handbook.pdf",
        "owner_id": "EMP-001",
        "created_date": "2026-01-01",
        "updated_date": "2026-06-15",
    }


# ---------------------------------------------------------------------------
# A. Interface / Public API
# ---------------------------------------------------------------------------


class TestInterface:
    def test_normalize_exists(self):
        assert callable(normalize)

    def test_normalize_batch_exists(self):
        assert callable(normalize_batch)

    def test_canonical_id_exists(self):
        assert callable(canonical_id)

    def test_record_hash_exists(self):
        assert callable(record_hash)

    def test_normalize_returns_canonical(self):
        result = normalize(
            "csv_demo", "customers", _csv_customer(),
            _RUN_ID, _INGESTED_AT,
        )
        from app.schemas.canonical import CanonicalBase
        assert isinstance(result, CanonicalBase)

    def test_normalize_returns_correct_subclass(self):
        from app.schemas.canonical import CustomerCanonical
        result = normalize(
            "csv_demo", "customers", _csv_customer(),
            _RUN_ID, _INGESTED_AT,
        )
        assert isinstance(result, CustomerCanonical)


# ---------------------------------------------------------------------------
# B. Entity coverage: all 7 entities x 3 sources
# ---------------------------------------------------------------------------


class TestEntityCoverage:
    """Every supported source/entity combination normalizes without error."""

    @pytest.fixture(autouse=True)
    def _records(self):
        self.csv_records = {
            "organizations": _csv_organization(),
            "employees": _csv_employee(),
            "customers": _csv_customer(),
            "deals": _csv_deal(),
            "projects": _csv_project(),
            "support_tickets": _csv_support_ticket(),
            "documents": _csv_document(),
        }
        self.odoo_records = {
            "organizations": {"id": 1, "name": "Acme", "industry_id": "Tech", "country_id": "IN", "active": True},
            "employees": _odoo_employee(),
            "customers": _odoo_customer(),
            "deals": _odoo_deal(),
            "projects": {"id": 3, "name": "Odoo Proj", "partner_id": 42, "user_id": 10, "stage_id": "active", "date_start": "2026-01-01", "date": "2026-12-31", "x_budget": 100000.0, "active": True},
            "support_tickets": {"id": 20, "partner_id": 42, "user_id": 10, "priority": "high", "stage_id": "open", "category_id": "billing", "name": "Invoice issue", "description": "Desc", "create_date": "2026-08-01", "close_date": None},
            "documents": {"id": 50, "name": "Policy Doc", "type": "policy", "datas": "text content", "url": "https://example.com", "owner_id": 10, "create_date": "2026-01-01", "write_date": "2026-06-01"},
        }
        self.rest_records = {
            "organizations": {"id": "REST-O-001", "name": "RestOrg", "industry": "Tech", "country": "US", "status": "active"},
            "employees": {"id": "REST-E-001", "name": "REST Employee", "email": "re@example.com", "department": "Eng", "title": "Dev", "managerId": None, "status": "active", "hireDate": "2025-01-01", "isActive": True, "organizationId": "REST-O-001"},
            "customers": _rest_customer(),
            "deals": _rest_deal(),
            "projects": {"id": "REST-P-001", "name": "REST Project", "customerId": "REST-C-001", "ownerId": "EMP-005", "status": "active", "startDate": "2026-01-01", "endDate": "2026-06-30", "budget": 75000.0, "isActive": True},
            "support_tickets": {"id": "REST-T-001", "customerId": "REST-C-001", "assigneeId": "EMP-005", "priority": "medium", "status": "closed", "category": "billing", "subject": "Invoice", "description": "Desc", "createdAt": "2026-07-01", "resolvedAt": "2026-07-05"},
            "documents": {"id": "REST-DOC-001", "title": "REST Doc", "documentType": "report", "bodyText": "Some text", "sourceUri": "https://example.com/doc", "ownerId": "EMP-005", "createdAt": "2026-01-01", "updatedAt": "2026-06-01"},
        }

    @pytest.mark.parametrize("entity", sorted(SUPPORTED_ENTITIES))
    def test_csv_entity(self, entity):
        result = normalize("csv_demo", entity, self.csv_records[entity], _RUN_ID, _INGESTED_AT)
        assert result.source_system == "csv_demo"
        assert result.source_entity == entity

    @pytest.mark.parametrize("entity", sorted(SUPPORTED_ENTITIES))
    def test_odoo_entity(self, entity):
        result = normalize("odoo_mock", entity, self.odoo_records[entity], _RUN_ID, _INGESTED_AT)
        assert result.source_system == "odoo_mock"
        assert result.source_entity == entity

    @pytest.mark.parametrize("entity", sorted(SUPPORTED_ENTITIES))
    def test_rest_entity(self, entity):
        result = normalize("rest_demo", entity, self.rest_records[entity], _RUN_ID, _INGESTED_AT)
        assert result.source_system == "rest_demo"
        assert result.source_entity == entity


# ---------------------------------------------------------------------------
# C. Field mapping correctness
# ---------------------------------------------------------------------------


class TestFieldMapping:
    def test_csv_customer_fields(self):
        result = normalize("csv_demo", "customers", _csv_customer(), _RUN_ID, _INGESTED_AT)
        assert result.name == "Acme Industries"
        assert result.email == "contact@acme.example"  # lowered, trimmed
        assert result.segment == "Enterprise"
        assert result.industry == "Manufacturing"
        assert result.owner_source_id == "EMP-002"
        assert result.status == "active"

    def test_odoo_customer_fields(self):
        result = normalize("odoo_mock", "customers", _odoo_customer(), _RUN_ID, _INGESTED_AT)
        assert result.name == "Widget Corp"
        assert result.email == "info@widget.example"
        assert result.segment == "SMB"
        assert result.industry == "Retail"
        assert result.owner_source_id == "7"  # Odoo int -> str
        assert result.is_active is True

    def test_rest_customer_fields(self):
        result = normalize("rest_demo", "customers", _rest_customer(), _RUN_ID, _INGESTED_AT)
        assert result.name == "RestCo"
        assert result.email == "rest@example.com"
        assert result.segment == "Enterprise"
        assert result.owner_source_id == "EMP-005"

    def test_csv_employee_fields(self):
        result = normalize("csv_demo", "employees", _csv_employee(), _RUN_ID, _INGESTED_AT)
        assert result.name == "Alice Engineer"
        assert result.email == "alice@acme.example"
        assert result.department == "Engineering"
        assert result.title == "Senior Developer"
        assert result.manager_source_id is None
        assert result.hire_date == date(2024, 3, 15)
        assert result.is_active is True

    def test_odoo_employee_fields(self):
        result = normalize("odoo_mock", "employees", _odoo_employee(), _RUN_ID, _INGESTED_AT)
        assert result.name == "Bob Manager"
        assert result.email == "bob@acme.example"
        assert result.department == "Sales"
        assert result.title == "Sales Manager"
        assert result.manager_source_id is None
        assert result.hire_date == date(2023, 6, 1)

    def test_csv_deal_amount_is_decimal(self):
        result = normalize("csv_demo", "deals", _csv_deal(), _RUN_ID, _INGESTED_AT)
        assert isinstance(result.amount, Decimal)
        assert result.amount == Decimal("150000.50")
        assert result.currency == "INR"

    def test_odoo_deal_amount_is_decimal(self):
        result = normalize("odoo_mock", "deals", _odoo_deal(), _RUN_ID, _INGESTED_AT)
        assert isinstance(result.amount, Decimal)
        assert result.amount == Decimal("45000.0")
        assert result.currency == "USD"

    def test_rest_deal_amount_is_decimal(self):
        result = normalize("rest_demo", "deals", _rest_deal(), _RUN_ID, _INGESTED_AT)
        assert isinstance(result.amount, Decimal)
        assert result.amount == Decimal("99000.0")

    def test_csv_organization_fields(self):
        result = normalize("csv_demo", "organizations", _csv_organization(), _RUN_ID, _INGESTED_AT)
        assert result.name == "Acme Corp"
        assert result.industry == "Technology"
        assert result.country == "India"

    def test_csv_project_budget_is_decimal(self):
        result = normalize("csv_demo", "projects", _csv_project(), _RUN_ID, _INGESTED_AT)
        assert isinstance(result.budget, Decimal)
        assert result.budget == Decimal("500000.00")

    def test_csv_support_ticket_dates(self):
        result = normalize("csv_demo", "support_tickets", _csv_support_ticket(), _RUN_ID, _INGESTED_AT)
        assert result.created_at == datetime(2026, 9, 1)
        assert result.resolved_at is None

    def test_csv_document_fields(self):
        result = normalize("csv_demo", "documents", _csv_document(), _RUN_ID, _INGESTED_AT)
        assert result.title == "Employee Handbook 2026"
        assert result.document_type == "policy"
        assert result.source_uri == "https://internal.acme.example/docs/handbook.pdf"
        assert result.owner_source_id == "EMP-001"


# ---------------------------------------------------------------------------
# D. Type conversions
# ---------------------------------------------------------------------------


class TestCoercion:
    # coerce_str
    def test_str_none(self):
        assert coerce_str(None) is None

    def test_str_normal(self):
        assert coerce_str("hello") == "hello"

    def test_str_whitespace(self):
        assert coerce_str("  hello  ") == "hello"

    def test_str_null_token_na(self):
        assert coerce_str("N/A") is None

    def test_str_null_token_dash(self):
        assert coerce_str("-") is None

    def test_str_null_token_empty(self):
        assert coerce_str("") is None

    def test_str_null_token_whitespace_only(self):
        assert coerce_str("   ") is None

    def test_str_zero_not_null(self):
        assert coerce_str("0") == "0"

    # coerce_email
    def test_email_trim_lowercase(self):
        assert coerce_email("  Alice@EXAMPLE.COM  ") == "alice@example.com"

    def test_email_none(self):
        assert coerce_email(None) is None

    def test_email_null_token(self):
        assert coerce_email("N/A") is None

    # coerce_bool
    def test_bool_true_string(self):
        assert coerce_bool("true") is True

    def test_bool_false_string(self):
        assert coerce_bool("false") is False

    def test_bool_yes(self):
        assert coerce_bool("yes") is True

    def test_bool_no(self):
        assert coerce_bool("no") is False

    def test_bool_one(self):
        assert coerce_bool("1") is True

    def test_bool_zero(self):
        assert coerce_bool("0") is False

    def test_bool_python_true(self):
        assert coerce_bool(True) is True

    def test_bool_python_false(self):
        assert coerce_bool(False) is False

    def test_bool_none(self):
        assert coerce_bool(None) is None

    def test_bool_invalid(self):
        with pytest.raises(CoercionError):
            coerce_bool("maybe")

    # coerce_date
    def test_date_iso(self):
        assert coerce_date("2026-01-15") == date(2026, 1, 15)

    def test_date_none(self):
        assert coerce_date(None) is None

    def test_date_null_token(self):
        assert coerce_date("N/A") is None

    def test_date_invalid(self):
        with pytest.raises(CoercionError):
            coerce_date("15/01/2026")

    def test_date_from_datetime(self):
        dt = datetime(2026, 1, 15, 10, 30)
        assert coerce_date(dt) == date(2026, 1, 15)

    def test_date_object(self):
        d = date(2026, 1, 15)
        assert coerce_date(d) == d

    # coerce_datetime
    def test_datetime_iso(self):
        assert coerce_datetime("2026-01-15T10:30:00") == datetime(2026, 1, 15, 10, 30)

    def test_datetime_date_only(self):
        assert coerce_datetime("2026-01-15") == datetime(2026, 1, 15)

    def test_datetime_none(self):
        assert coerce_datetime(None) is None

    def test_datetime_invalid(self):
        with pytest.raises(CoercionError):
            coerce_datetime("not-a-date")

    def test_datetime_object(self):
        dt = datetime(2026, 1, 15, 10, 30)
        assert coerce_datetime(dt) == dt

    # coerce_decimal
    def test_decimal_string(self):
        assert coerce_decimal("150000.50") == Decimal("150000.50")

    def test_decimal_int(self):
        assert coerce_decimal(42) == Decimal("42")

    def test_decimal_float(self):
        result = coerce_decimal(45000.0)
        assert isinstance(result, Decimal)
        assert result == Decimal("45000.0")

    def test_decimal_none(self):
        assert coerce_decimal(None) is None

    def test_decimal_null_token(self):
        assert coerce_decimal("N/A") is None

    def test_decimal_invalid(self):
        with pytest.raises(CoercionError):
            coerce_decimal("not-a-number")

    def test_decimal_bool_rejected(self):
        with pytest.raises(CoercionError):
            coerce_decimal(True)

    def test_decimal_zero(self):
        assert coerce_decimal(0) == Decimal("0")

    def test_decimal_zero_string(self):
        assert coerce_decimal("0") == Decimal("0")

    # coerce_int_id_to_str
    def test_int_id_to_str(self):
        assert coerce_int_id_to_str(42) == "42"

    def test_int_id_none(self):
        assert coerce_int_id_to_str(None) is None

    def test_int_id_bool_rejected(self):
        with pytest.raises(CoercionError):
            coerce_int_id_to_str(True)


# ---------------------------------------------------------------------------
# E. Identity (deterministic UUIDs, record_hash)
# ---------------------------------------------------------------------------


class TestIdentity:
    def test_canonical_id_deterministic(self):
        id1 = canonical_id("csv_demo", "customers", "CUST-001")
        id2 = canonical_id("csv_demo", "customers", "CUST-001")
        assert id1 == id2

    def test_canonical_id_is_uuid(self):
        cid = canonical_id("csv_demo", "customers", "CUST-001")
        assert isinstance(cid, uuid.UUID)

    def test_canonical_id_different_source_id(self):
        id1 = canonical_id("csv_demo", "customers", "CUST-001")
        id2 = canonical_id("csv_demo", "customers", "CUST-002")
        assert id1 != id2

    def test_canonical_id_different_source_system(self):
        id1 = canonical_id("csv_demo", "customers", "CUST-001")
        id2 = canonical_id("odoo_mock", "customers", "CUST-001")
        assert id1 != id2

    def test_canonical_id_different_entity(self):
        id1 = canonical_id("csv_demo", "customers", "CUST-001")
        id2 = canonical_id("csv_demo", "employees", "CUST-001")
        assert id1 != id2

    def test_record_hash_deterministic(self):
        fields = {"name": "Acme", "status": "active"}
        h1 = record_hash(fields)
        h2 = record_hash(fields)
        assert h1 == h2

    def test_record_hash_different_values(self):
        h1 = record_hash({"name": "Acme"})
        h2 = record_hash({"name": "Widget"})
        assert h1 != h2

    def test_record_hash_excludes_provenance(self):
        fields = {"name": "Acme", "ingested_at": "2026-01-01", "ingestion_run_id": "xyz"}
        fields_clean = {"name": "Acme"}
        assert record_hash(fields) == record_hash(fields_clean)

    def test_record_hash_is_hex_string(self):
        h = record_hash({"x": 1})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_normalize_sets_id_from_source_identity(self):
        result = normalize("csv_demo", "customers", _csv_customer(), _RUN_ID, _INGESTED_AT)
        expected_id = canonical_id("csv_demo", "customers", "CUST-001")
        assert result.id == expected_id

    def test_normalize_sets_record_hash(self):
        result = normalize("csv_demo", "customers", _csv_customer(), _RUN_ID, _INGESTED_AT)
        assert isinstance(result.record_hash, str)
        assert len(result.record_hash) == 64


# ---------------------------------------------------------------------------
# F. Relationships
# ---------------------------------------------------------------------------


class TestRelationships:
    def test_csv_deal_customer_source_id(self):
        result = normalize("csv_demo", "deals", _csv_deal(), _RUN_ID, _INGESTED_AT)
        assert result.customer_source_id == "CUST-001"

    def test_csv_deal_owner_source_id(self):
        result = normalize("csv_demo", "deals", _csv_deal(), _RUN_ID, _INGESTED_AT)
        assert result.owner_source_id == "EMP-002"

    def test_csv_deal_customer_id_is_none(self):
        """canonical FK is None because D1 does not resolve it."""
        result = normalize("csv_demo", "deals", _csv_deal(), _RUN_ID, _INGESTED_AT)
        assert result.customer_id is None

    def test_odoo_deal_customer_source_id_from_partner(self):
        result = normalize("odoo_mock", "deals", _odoo_deal(), _RUN_ID, _INGESTED_AT)
        assert result.customer_source_id == "42"  # partner_id int -> str

    def test_odoo_deal_owner_source_id_from_user(self):
        result = normalize("odoo_mock", "deals", _odoo_deal(), _RUN_ID, _INGESTED_AT)
        assert result.owner_source_id == "10"  # user_id int -> str

    def test_rest_deal_customer_source_id(self):
        result = normalize("rest_demo", "deals", _rest_deal(), _RUN_ID, _INGESTED_AT)
        assert result.customer_source_id == "REST-C-001"

    def test_csv_employee_manager_source_id_none(self):
        result = normalize("csv_demo", "employees", _csv_employee(), _RUN_ID, _INGESTED_AT)
        assert result.manager_source_id is None

    def test_csv_employee_organization_id_none(self):
        """Canonical FK to org is not resolved by D1."""
        result = normalize("csv_demo", "employees", _csv_employee(), _RUN_ID, _INGESTED_AT)
        assert result.organization_id is None

    def test_csv_ticket_customer_source_id(self):
        result = normalize("csv_demo", "support_tickets", _csv_support_ticket(), _RUN_ID, _INGESTED_AT)
        assert result.customer_source_id == "CUST-001"

    def test_csv_ticket_assignee_source_id(self):
        result = normalize("csv_demo", "support_tickets", _csv_support_ticket(), _RUN_ID, _INGESTED_AT)
        assert result.assignee_source_id == "EMP-001"

    def test_cross_entity_identity_consistency(self):
        """Same source_id in same source produces same canonical_id for that entity."""
        deal = normalize("csv_demo", "deals", _csv_deal(), _RUN_ID, _INGESTED_AT)
        # The deal references CUST-001 as customer_source_id
        # If we normalize that customer, its canonical ID should be deterministic
        customer = normalize("csv_demo", "customers", _csv_customer(), _RUN_ID, _INGESTED_AT)
        expected_customer_id = canonical_id("csv_demo", "customers", "CUST-001")
        assert customer.id == expected_customer_id
        assert deal.customer_source_id == customer.source_id


# ---------------------------------------------------------------------------
# G. Null semantics
# ---------------------------------------------------------------------------


class TestNullSemantics:
    def test_none_preserved(self):
        rec = _csv_customer()
        rec["email_address"] = None
        result = normalize("csv_demo", "customers", rec, _RUN_ID, _INGESTED_AT)
        assert result.email is None

    def test_empty_string_becomes_none_for_str(self):
        rec = _csv_customer()
        rec["customer_segment"] = ""
        result = normalize("csv_demo", "customers", rec, _RUN_ID, _INGESTED_AT)
        assert result.segment is None

    def test_whitespace_becomes_none_for_str(self):
        rec = _csv_customer()
        rec["customer_segment"] = "   "
        result = normalize("csv_demo", "customers", rec, _RUN_ID, _INGESTED_AT)
        assert result.segment is None

    def test_zero_preserved_for_decimal(self):
        rec = _csv_deal()
        rec["amount"] = "0"
        result = normalize("csv_demo", "deals", rec, _RUN_ID, _INGESTED_AT)
        assert result.amount == Decimal("0")

    def test_false_preserved_for_bool(self):
        rec = _csv_deal()
        rec["is_active"] = "false"
        result = normalize("csv_demo", "deals", rec, _RUN_ID, _INGESTED_AT)
        assert result.is_active is False

    def test_zero_float_preserved_for_decimal(self):
        rec = _rest_deal()
        rec["amount"] = 0.0
        result = normalize("rest_demo", "deals", rec, _RUN_ID, _INGESTED_AT)
        assert result.amount == Decimal("0.0")

    def test_na_becomes_none(self):
        rec = _csv_customer()
        rec["customer_segment"] = "N/A"
        result = normalize("csv_demo", "customers", rec, _RUN_ID, _INGESTED_AT)
        assert result.segment is None

    def test_dash_becomes_none(self):
        rec = _csv_customer()
        rec["customer_segment"] = "-"
        result = normalize("csv_demo", "customers", rec, _RUN_ID, _INGESTED_AT)
        assert result.segment is None

    def test_missing_optional_field_is_none(self):
        rec = {"customer_id": "CUST-X", "customer_name": "Test"}
        result = normalize("csv_demo", "customers", rec, _RUN_ID, _INGESTED_AT)
        assert result.email is None
        assert result.segment is None


# ---------------------------------------------------------------------------
# H. Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_unsupported_source(self):
        with pytest.raises(UnsupportedSourceError, match="fantasy_source"):
            normalize("fantasy_source", "customers", {}, _RUN_ID, _INGESTED_AT)

    def test_unsupported_entity(self):
        with pytest.raises(UnsupportedEntityError, match="widgets"):
            normalize("csv_demo", "widgets", {}, _RUN_ID, _INGESTED_AT)

    def test_missing_source_id(self):
        with pytest.raises(FieldMappingError, match="customer_id"):
            normalize("csv_demo", "customers", {"customer_name": "Test"}, _RUN_ID, _INGESTED_AT)

    def test_empty_source_id(self):
        rec = _csv_customer()
        rec["customer_id"] = ""
        with pytest.raises(FieldMappingError, match="Empty"):
            normalize("csv_demo", "customers", rec, _RUN_ID, _INGESTED_AT)

    def test_invalid_date(self):
        rec = _csv_customer()
        rec["created_date"] = "not-a-date"
        with pytest.raises((CoercionError, NormalizationError)):
            normalize("csv_demo", "customers", rec, _RUN_ID, _INGESTED_AT)

    def test_invalid_decimal(self):
        rec = _csv_deal()
        rec["amount"] = "not-a-number"
        with pytest.raises((CoercionError, NormalizationError)):
            normalize("csv_demo", "deals", rec, _RUN_ID, _INGESTED_AT)

    def test_invalid_boolean(self):
        rec = _csv_deal()
        rec["is_active"] = "maybe"
        with pytest.raises((CoercionError, NormalizationError)):
            normalize("csv_demo", "deals", rec, _RUN_ID, _INGESTED_AT)

    def test_error_includes_context(self):
        try:
            normalize("csv_demo", "customers", {"customer_name": "Test"}, _RUN_ID, _INGESTED_AT)
        except NormalizationError as exc:
            assert exc.source_system == "csv_demo"
            assert exc.entity_type == "customers"

    def test_normalization_error_hierarchy(self):
        assert issubclass(UnsupportedSourceError, NormalizationError)
        assert issubclass(UnsupportedEntityError, NormalizationError)
        assert issubclass(FieldMappingError, NormalizationError)
        assert issubclass(CoercionError, NormalizationError)

    def test_normalization_error_not_connector_error(self):
        """D1 errors are distinct from connector errors."""
        from app.connectors.types import ConnectorError
        assert not issubclass(NormalizationError, ConnectorError)


# ---------------------------------------------------------------------------
# I. Boundary tests (D1 must NOT import DB/HTTP/connector internals)
# ---------------------------------------------------------------------------


class TestBoundary:
    """Verify D1 does not have infrastructure dependencies."""

    def _module_imports(self, module_path: str) -> set[str]:
        """Parse a Python file's AST and return all imported module names."""
        source = Path(module_path).read_text()
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
        return imports

    def _all_d1_imports(self) -> set[str]:
        """Collect all imports across all D1 modules."""
        d1_dir = Path(__file__).resolve().parent.parent.parent / "app" / "normalization"
        all_imports = set()
        for py_file in d1_dir.glob("*.py"):
            all_imports.update(self._module_imports(str(py_file)))
        return all_imports

    def test_no_sqlalchemy_import(self):
        imports = self._all_d1_imports()
        assert "sqlalchemy" not in imports

    def test_no_httpx_import(self):
        imports = self._all_d1_imports()
        assert "httpx" not in imports

    def test_no_requests_import(self):
        imports = self._all_d1_imports()
        assert "requests" not in imports

    def test_no_database_module_import(self):
        """D1 must not import persistence/database modules."""
        d1_dir = Path(__file__).resolve().parent.parent.parent / "app" / "normalization"
        for py_file in d1_dir.glob("*.py"):
            source = py_file.read_text()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "persistence" not in node.module, (
                        f"{py_file.name} imports persistence module"
                    )
                    assert "models" not in node.module or "schemas" in node.module, (
                        f"{py_file.name} imports models module"
                    )

    def test_no_connector_instantiation(self):
        """D1 must not import connector classes (only types for error checking)."""
        d1_dir = Path(__file__).resolve().parent.parent.parent / "app" / "normalization"
        for py_file in d1_dir.glob("*.py"):
            source = py_file.read_text()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if "app.connectors" in node.module:
                        # Only types.py imports are allowed (for error hierarchy check)
                        for alias in node.names:
                            assert alias.name.startswith("Connector"), (
                                f"{py_file.name} imports non-error connector class: {alias.name}"
                            )


# ---------------------------------------------------------------------------
# J. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_normalize_idempotent(self):
        r1 = normalize("csv_demo", "customers", _csv_customer(), _RUN_ID, _INGESTED_AT)
        r2 = normalize("csv_demo", "customers", _csv_customer(), _RUN_ID, _INGESTED_AT)
        assert r1.id == r2.id
        assert r1.record_hash == r2.record_hash
        assert r1.name == r2.name
        assert r1.email == r2.email

    def test_normalize_stable_across_calls(self):
        """Multiple calls with the same input produce identical canonical objects."""
        results = [
            normalize("csv_demo", "customers", _csv_customer(), _RUN_ID, _INGESTED_AT)
            for _ in range(5)
        ]
        ids = {r.id for r in results}
        hashes = {r.record_hash for r in results}
        assert len(ids) == 1
        assert len(hashes) == 1

    def test_odoo_normalize_idempotent(self):
        r1 = normalize("odoo_mock", "customers", _odoo_customer(), _RUN_ID, _INGESTED_AT)
        r2 = normalize("odoo_mock", "customers", _odoo_customer(), _RUN_ID, _INGESTED_AT)
        assert r1.id == r2.id
        assert r1.record_hash == r2.record_hash

    def test_rest_normalize_idempotent(self):
        r1 = normalize("rest_demo", "deals", _rest_deal(), _RUN_ID, _INGESTED_AT)
        r2 = normalize("rest_demo", "deals", _rest_deal(), _RUN_ID, _INGESTED_AT)
        assert r1.id == r2.id
        assert r1.record_hash == r2.record_hash


# ---------------------------------------------------------------------------
# K. Batch normalization
# ---------------------------------------------------------------------------


class TestBatch:
    def test_batch_all_success(self):
        records = [_csv_customer()]
        ok, errs = normalize_batch("csv_demo", "customers", records, _RUN_ID, _INGESTED_AT)
        assert len(ok) == 1
        assert len(errs) == 0

    def test_batch_mixed(self):
        good = _csv_customer()
        bad = {"customer_name": "No ID"}  # missing customer_id
        ok, errs = normalize_batch("csv_demo", "customers", [good, bad], _RUN_ID, _INGESTED_AT)
        assert len(ok) == 1
        assert len(errs) == 1
        assert isinstance(errs[0][1], NormalizationError)

    def test_batch_all_failures(self):
        bad1 = {"customer_name": "No ID 1"}
        bad2 = {"customer_name": "No ID 2"}
        ok, errs = normalize_batch("csv_demo", "customers", [bad1, bad2], _RUN_ID, _INGESTED_AT)
        assert len(ok) == 0
        assert len(errs) == 2

    def test_batch_empty(self):
        ok, errs = normalize_batch("csv_demo", "customers", [], _RUN_ID, _INGESTED_AT)
        assert len(ok) == 0
        assert len(errs) == 0

    def test_batch_preserves_order(self):
        c1 = _csv_customer()
        c2 = dict(c1)
        c2["customer_id"] = "CUST-002"
        c2["customer_name"] = "Second"
        ok, errs = normalize_batch("csv_demo", "customers", [c1, c2], _RUN_ID, _INGESTED_AT)
        assert len(ok) == 2
        assert ok[0].source_id == "CUST-001"
        assert ok[1].source_id == "CUST-002"


# ---------------------------------------------------------------------------
# L. Provenance fields
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_source_system_set(self):
        result = normalize("csv_demo", "customers", _csv_customer(), _RUN_ID, _INGESTED_AT)
        assert result.source_system == "csv_demo"

    def test_source_entity_set(self):
        result = normalize("csv_demo", "customers", _csv_customer(), _RUN_ID, _INGESTED_AT)
        assert result.source_entity == "customers"

    def test_source_id_set(self):
        result = normalize("csv_demo", "customers", _csv_customer(), _RUN_ID, _INGESTED_AT)
        assert result.source_id == "CUST-001"

    def test_ingestion_run_id_set(self):
        result = normalize("csv_demo", "customers", _csv_customer(), _RUN_ID, _INGESTED_AT)
        assert result.ingestion_run_id == _RUN_ID

    def test_ingested_at_set(self):
        result = normalize("csv_demo", "customers", _csv_customer(), _RUN_ID, _INGESTED_AT)
        assert result.ingested_at == _INGESTED_AT

    def test_source_updated_at_none_default(self):
        result = normalize("csv_demo", "customers", _csv_customer(), _RUN_ID, _INGESTED_AT)
        assert result.source_updated_at is None

    def test_source_updated_at_passed_through(self):
        ts = datetime(2026, 9, 1, 10, 0, 0)
        result = normalize(
            "csv_demo", "customers", _csv_customer(),
            _RUN_ID, _INGESTED_AT, source_updated_at=ts,
        )
        assert result.source_updated_at == ts

    def test_odoo_source_id_is_string(self):
        """Odoo integer IDs must be converted to strings in source_id."""
        result = normalize("odoo_mock", "customers", _odoo_customer(), _RUN_ID, _INGESTED_AT)
        assert result.source_id == "42"
        assert isinstance(result.source_id, str)


# ---------------------------------------------------------------------------
# M. Mappings module API
# ---------------------------------------------------------------------------


class TestMappingsAPI:
    def test_supported_sources(self):
        assert "csv_demo" in SUPPORTED_SOURCES
        assert "odoo_mock" in SUPPORTED_SOURCES
        assert "rest_demo" in SUPPORTED_SOURCES

    def test_supported_entities(self):
        expected = {"organizations", "employees", "customers", "deals",
                    "projects", "support_tickets", "documents"}
        assert SUPPORTED_ENTITIES == expected

    def test_has_is_active(self):
        assert has_is_active("employees") is True
        assert has_is_active("customers") is True
        assert has_is_active("deals") is True
        assert has_is_active("projects") is True
        assert has_is_active("organizations") is False
        assert has_is_active("support_tickets") is False
        assert has_is_active("documents") is False

    def test_get_mapper_returns_callable(self):
        mapper = get_mapper("csv_demo", "customers")
        assert callable(mapper)

    def test_extract_source_id_csv(self):
        sid = extract_source_id("csv_demo", "customers", _csv_customer())
        assert sid == "CUST-001"

    def test_extract_source_id_odoo(self):
        sid = extract_source_id("odoo_mock", "customers", _odoo_customer())
        assert sid == "42"

    def test_extract_source_id_rest(self):
        sid = extract_source_id("rest_demo", "customers", _rest_customer())
        assert sid == "REST-C-001"
