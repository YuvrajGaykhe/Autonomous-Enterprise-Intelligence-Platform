"""
Shared fixtures and helpers for the D1 normalization test modules.

FULL_CASES holds one fully populated source-native record for each of the
21 source x entity combinations, together with the exact canonical output
expected from it. Every business field is populated with a value distinct
from the other fields of the same type, so swapped, dropped, or mis-wired
mappings cannot pass the field-level assertions.
"""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.normalization.contract import BUSINESS_FIELDS
from app.normalization.errors import ErrorCode, NormalizationError

RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
INGESTED_AT = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)
SOURCES = ("csv_demo", "odoo_mock", "rest_mock")
ENTITIES = tuple(BUSINESS_FIELDS)

# Sentinel: remove the field from the record instead of setting a value.
ABSENT = object()


def utc(*args: int) -> datetime:
    """Build a timezone-aware UTC datetime."""
    return datetime(*args, tzinfo=UTC)


def business(obj: Any) -> dict[str, Any]:
    """Return the canonical business fields of a canonical object."""
    return {name: getattr(obj, name) for name in BUSINESS_FIELDS[obj.source_entity]}


def with_value(record: dict[str, Any], field: str, value: object) -> dict[str, Any]:
    """Return a copy of record with field set to value (or removed if ABSENT)."""
    updated = copy.deepcopy(record)
    if value is ABSENT:
        updated.pop(field, None)
    else:
        updated[field] = value
    return updated


def assert_error(
    exc: BaseException,
    error_type: type[NormalizationError],
    code: ErrorCode,
    *,
    source_system: str | None,
    entity_type: str | None,
    source_id: str | None,
    field_name: str | None,
) -> None:
    """Assert the exact exception type, stable code, and full record context."""
    assert type(exc) is error_type, f"expected {error_type.__name__}, got {type(exc).__name__}: {exc}"
    assert exc.code == code, exc
    assert exc.source_system == source_system
    assert exc.entity_type == entity_type
    assert exc.source_id == source_id
    assert exc.field_name == field_name
    assert exc.reason
    assert exc.message.startswith(f"[{code}]")
    assert str(exc) == exc.message
    assert exc.to_dict() == {
        "code": str(code),
        "message": exc.message,
        "source_system": source_system,
        "entity_type": entity_type,
        "source_id": source_id,
        "field_name": field_name,
    }


FULL_CASES: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {
    # ------------------------------------------------------------------ CSV
    ("csv_demo", "organizations"): (
        {"organization_id": " ORG-001 ", "organization_name": "  Acme Corp ",
         "industry": "Technology", "country": "India", "status": "Active"},
        {"source_id": "ORG-001", "source_updated_at": None, "fields": {
            "name": "Acme Corp", "industry": "Technology", "country": "India",
            "status": "active"}},
    ),
    ("csv_demo", "employees"): (
        {"employee_id": "EMP-003", "employee_name": "Carol Analyst",
         "email_address": " Carol@GlobalTech.Example ", "department": "Analytics",
         "title": "Data Analyst", "manager_id": "EMP-002", "status": "active",
         "hire_date": "2025-01-10", "is_active": "true", "organization_id": "ORG-002"},
        {"source_id": "EMP-003", "source_updated_at": None, "fields": {
            "name": "Carol Analyst", "email": "carol@globaltech.example",
            "department": "Analytics", "title": "Data Analyst",
            "manager_source_id": "EMP-002", "status": "active",
            "hire_date": date(2025, 1, 10), "is_active": True}},
    ),
    ("csv_demo", "customers"): (
        {"customer_id": "CUST-001", "customer_name": "Acme Industries",
         "email_address": "contact@acme-ind.example", "customer_segment": "Enterprise",
         "industry_name": "Manufacturing", "account_owner_id": "EMP-002",
         "status": "inactive", "created_date": "2025-01-15 09:45:00"},
        {"source_id": "CUST-001", "source_updated_at": None, "fields": {
            "name": "Acme Industries", "email": "contact@acme-ind.example",
            "segment": "Enterprise", "industry": "Manufacturing", "status": "inactive",
            "owner_source_id": "EMP-002", "created_at": utc(2025, 1, 15, 9, 45),
            "is_active": False}},
    ),
    ("csv_demo", "deals"): (
        {"deal_id": "DEAL-001", "deal_name": "Acme Platform Deal", "customer_id": "CUST-001",
         "owner_id": "EMP-002", "stage": "Negotiation", "amount": "150000.5",
         "currency": " inr ", "probability": "75", "expected_close_date": "2026-12-31",
         "is_active": "No"},
        {"source_id": "DEAL-001", "source_updated_at": None, "fields": {
            "name": "Acme Platform Deal", "stage": "negotiation",
            "amount": Decimal("150000.50"), "currency": "INR",
            "probability": Decimal("75.00"), "expected_close_date": date(2026, 12, 31),
            "is_active": False, "customer_source_id": "CUST-001",
            "owner_source_id": "EMP-002"}},
    ),
    ("csv_demo", "projects"): (
        {"project_id": "PROJ-001", "project_name": "Platform Migration",
         "customer_id": "CUST-001", "owner_id": "EMP-001", "status": "in progress",
         "start_date": "2026-01-01", "end_date": "2026-12-31", "budget": "500000.00",
         "is_active": "1"},
        {"source_id": "PROJ-001", "source_updated_at": None, "fields": {
            "name": "Platform Migration", "status": "in_progress",
            "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31),
            "budget": Decimal("500000.00"), "is_active": True,
            "customer_source_id": "CUST-001", "owner_source_id": "EMP-001"}},
    ),
    ("csv_demo", "support_tickets"): (
        {"ticket_id": "TKT-002", "customer_id": "CUST-002", "assignee_id": "EMP-003",
         "priority": "medium", "status": "resolved", "category": "billing",
         "subject": "Invoice discrepancy Q3",
         "description": "  Invoice totals do not match the agreed contract.\n",
         "created_date": "2026-08-15", "resolved_date": "2026-08-20T16:05:00"},
        {"source_id": "TKT-002", "source_updated_at": None, "fields": {
            "subject": "Invoice discrepancy Q3",
            "description": "  Invoice totals do not match the agreed contract.\n",
            "priority": "medium", "status": "resolved", "category": "billing",
            "created_at": utc(2026, 8, 15), "resolved_at": utc(2026, 8, 20, 16, 5),
            "customer_source_id": "CUST-002", "assignee_source_id": "EMP-003"}},
    ),
    ("csv_demo", "documents"): (
        {"document_id": "DOC-002", "title": "Q3 Sales Report", "document_type": "report",
         "body_text": "Quarterly revenue grew 12%.\nPipeline is healthy.",
         "source_uri": "https://internal.acme.example/reports/q3-sales.pdf",
         "owner_id": "EMP-002", "created_date": "2026-07-01",
         "updated_date": "2026-09-05 14:30:00"},
        {"source_id": "DOC-002", "source_updated_at": utc(2026, 9, 5, 14, 30), "fields": {
            "title": "Q3 Sales Report", "document_type": "report",
            "body_text": "Quarterly revenue grew 12%.\nPipeline is healthy.",
            "source_uri": "https://internal.acme.example/reports/q3-sales.pdf",
            "owner_source_id": "EMP-002", "created_at": utc(2026, 7, 1),
            "updated_at": utc(2026, 9, 5, 14, 30)}},
    ),
    # ----------------------------------------------------------------- Odoo
    ("odoo_mock", "organizations"): (
        {"id": 2, "name": "GlobalTech Solutions", "industry_id": "Technology",
         "country_id": "United States", "active": False},
        {"source_id": "2", "source_updated_at": None, "fields": {
            "name": "GlobalTech Solutions", "industry": "Technology",
            "country": "United States", "status": "inactive"}},
    ),
    ("odoo_mock", "employees"): (
        {"id": 3, "name": "Carol Analyst", "work_email": "Carol@GlobalTech.example",
         "department_id": "Analytics", "job_title": "Data Analyst", "parent_id": 2,
         "active": False, "x_hire_date": "2025-01-10", "company_id": 2},
        {"source_id": "3", "source_updated_at": None, "fields": {
            "name": "Carol Analyst", "email": "carol@globaltech.example",
            "department": "Analytics", "title": "Data Analyst", "manager_source_id": "2",
            "status": "inactive", "hire_date": date(2025, 1, 10), "is_active": False}},
    ),
    ("odoo_mock", "customers"): (
        {"id": 1, "name": "Acme Industries", "email": "contact@acme-ind.example",
         "x_studio_segment": "Enterprise", "industry_id": "Manufacturing", "user_id": 2,
         "active": True, "create_date": "2025-01-15 09:45:00", "customer_rank": 1},
        {"source_id": "1", "source_updated_at": None, "fields": {
            "name": "Acme Industries", "email": "contact@acme-ind.example",
            "segment": "Enterprise", "industry": "Manufacturing", "status": "active",
            "owner_source_id": "2", "created_at": utc(2025, 1, 15, 9, 45),
            "is_active": True}},
    ),
    ("odoo_mock", "deals"): (
        {"id": 1, "name": "Acme Platform Deal", "partner_id": 1, "user_id": 2,
         "stage_id": "negotiation", "expected_revenue": 150000.5,
         "company_currency": "INR", "probability": 75.0, "date_deadline": "2026-12-31",
         "active": True},
        {"source_id": "1", "source_updated_at": None, "fields": {
            "name": "Acme Platform Deal", "stage": "negotiation",
            "amount": Decimal("150000.50"), "currency": "INR",
            "probability": Decimal("75.00"), "expected_close_date": date(2026, 12, 31),
            "is_active": True, "customer_source_id": "1", "owner_source_id": "2"}},
    ),
    ("odoo_mock", "projects"): (
        {"id": 2, "name": "CRM Integration", "partner_id": 2, "user_id": 1,
         "stage_id": "planning", "date_start": "2026-04-01", "date": "2026-10-31",
         "x_budget": 120000.0, "active": False},
        {"source_id": "2", "source_updated_at": None, "fields": {
            "name": "CRM Integration", "status": "planning",
            "start_date": date(2026, 4, 1), "end_date": date(2026, 10, 31),
            "budget": Decimal("120000.00"), "is_active": False,
            "customer_source_id": "2", "owner_source_id": "1"}},
    ),
    ("odoo_mock", "support_tickets"): (
        {"id": 1, "partner_id": 1, "user_id": 3, "priority": "high", "stage_id": "open",
         "category_id": "auth", "name": "Login not working after SSO update",
         "description": "Users cannot log in after the SSO provider migration.",
         "create_date": "2026-09-01 08:00:00", "close_date": "2026-09-02 17:15:30"},
        {"source_id": "1", "source_updated_at": None, "fields": {
            "subject": "Login not working after SSO update",
            "description": "Users cannot log in after the SSO provider migration.",
            "priority": "high", "status": "open", "category": "auth",
            "created_at": utc(2026, 9, 1, 8), "resolved_at": utc(2026, 9, 2, 17, 15, 30),
            "customer_source_id": "1", "assignee_source_id": "3"}},
    ),
    ("odoo_mock", "documents"): (
        {"id": 1, "name": "Employee Handbook 2026", "type": "policy",
         "datas": "Section 1: Code of conduct.",
         "url": "https://internal.acme.example/docs/handbook.pdf", "owner_id": 4,
         "create_date": "2026-01-01 00:00:00", "write_date": "2026-06-15 10:20:30"},
        {"source_id": "1", "source_updated_at": utc(2026, 6, 15, 10, 20, 30), "fields": {
            "title": "Employee Handbook 2026", "document_type": "policy",
            "body_text": "Section 1: Code of conduct.",
            "source_uri": "https://internal.acme.example/docs/handbook.pdf",
            "owner_source_id": "4", "created_at": utc(2026, 1, 1),
            "updated_at": utc(2026, 6, 15, 10, 20, 30)}},
    ),
    # ----------------------------------------------------------------- REST
    ("rest_mock", "organizations"): (
        {"id": "ORG-003", "name": "Pinnacle Industries", "industry": "Manufacturing",
         "country": "Germany", "status": "inactive"},
        {"source_id": "ORG-003", "source_updated_at": None, "fields": {
            "name": "Pinnacle Industries", "industry": "Manufacturing",
            "country": "Germany", "status": "inactive"}},
    ),
    ("rest_mock", "employees"): (
        {"id": "EMP-002", "name": "Bob Manager", "email": "bob@acme.example",
         "department": "Sales", "title": "Sales Manager", "managerId": "EMP-009",
         "status": "active", "hireDate": "2023-06-01", "isActive": True,
         "organizationId": "ORG-001"},
        {"source_id": "EMP-002", "source_updated_at": None, "fields": {
            "name": "Bob Manager", "email": "bob@acme.example", "department": "Sales",
            "title": "Sales Manager", "manager_source_id": "EMP-009", "status": "active",
            "hire_date": date(2023, 6, 1), "is_active": True}},
    ),
    ("rest_mock", "customers"): (
        {"id": "CUST-003", "name": "DataFlow Systems", "email": "hello@dataflow.example",
         "segment": "Enterprise", "industry": "Technology", "ownerId": "EMP-001",
         "status": "inactive", "createdAt": "2025-06-10T18:30:00+05:30", "isActive": False},
        {"source_id": "CUST-003", "source_updated_at": None, "fields": {
            "name": "DataFlow Systems", "email": "hello@dataflow.example",
            "segment": "Enterprise", "industry": "Technology", "status": "inactive",
            "owner_source_id": "EMP-001", "created_at": utc(2025, 6, 10, 13, 0),
            "is_active": False}},
    ),
    ("rest_mock", "deals"): (
        {"id": "DEAL-003", "name": "DataFlow Analytics Suite", "customerId": "CUST-003",
         "ownerId": "EMP-001", "stage": "won", "amount": 280000.0, "currency": "EUR",
         "probability": 100.0, "expectedCloseDate": "2026-06-15", "isActive": False},
        {"source_id": "DEAL-003", "source_updated_at": None, "fields": {
            "name": "DataFlow Analytics Suite", "stage": "won",
            "amount": Decimal("280000.00"), "currency": "EUR",
            "probability": Decimal("100.00"), "expected_close_date": date(2026, 6, 15),
            "is_active": False, "customer_source_id": "CUST-003",
            "owner_source_id": "EMP-001"}},
    ),
    ("rest_mock", "projects"): (
        {"id": "PROJ-002", "name": "CRM Integration", "customerId": "CUST-002",
         "ownerId": "EMP-002", "status": "planning", "startDate": "2026-04-01",
         "endDate": "2026-10-31", "budget": 120000.0, "isActive": True},
        {"source_id": "PROJ-002", "source_updated_at": None, "fields": {
            "name": "CRM Integration", "status": "planning",
            "start_date": date(2026, 4, 1), "end_date": date(2026, 10, 31),
            "budget": Decimal("120000.00"), "is_active": True,
            "customer_source_id": "CUST-002", "owner_source_id": "EMP-002"}},
    ),
    ("rest_mock", "support_tickets"): (
        {"id": "TKT-001", "customerId": "CUST-001", "assigneeId": "EMP-001",
         "priority": "high", "status": "open", "category": "auth",
         "subject": "Login not working", "description": "SSO failure after migration.",
         "createdAt": "2026-09-01T09:00:00Z", "resolvedAt": "2026-09-01T21:30:00-04:00"},
        {"source_id": "TKT-001", "source_updated_at": None, "fields": {
            "subject": "Login not working", "description": "SSO failure after migration.",
            "priority": "high", "status": "open", "category": "auth",
            "created_at": utc(2026, 9, 1, 9), "resolved_at": utc(2026, 9, 2, 1, 30),
            "customer_source_id": "CUST-001", "assignee_source_id": "EMP-001"}},
    ),
    ("rest_mock", "documents"): (
        {"id": "DOC-001", "title": "Employee Handbook 2026", "documentType": "policy",
         "bodyText": "Section 1: Code of conduct.",
         "sourceUri": "https://internal.acme.example/docs/handbook.pdf",
         "ownerId": "EMP-001", "createdAt": "2026-01-01T00:00:00Z",
         "updatedAt": "2026-06-15T10:20:30.250000Z"},
        {"source_id": "DOC-001",
         "source_updated_at": utc(2026, 6, 15, 10, 20, 30, 250000), "fields": {
            "title": "Employee Handbook 2026", "document_type": "policy",
            "body_text": "Section 1: Code of conduct.",
            "source_uri": "https://internal.acme.example/docs/handbook.pdf",
            "owner_source_id": "EMP-001", "created_at": utc(2026, 1, 1),
            "updated_at": utc(2026, 6, 15, 10, 20, 30, 250000)}},
    ),
}

CASE_KEYS = sorted(FULL_CASES)


def case_id(key: tuple[str, str]) -> str:
    return f"{key[0]}-{key[1]}"


def full_case(source: str, entity: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return deep copies of (source record, expected canonical output)."""
    record, expected = FULL_CASES[(source, entity)]
    return copy.deepcopy(record), copy.deepcopy(expected)
