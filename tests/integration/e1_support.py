"""Shared fixtures for the E1 integration test modules (synthetic demo-shaped data)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.normalization import normalize
from app.persistence.repositories import runs
from app.schemas.canonical import CanonicalBase

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)

# csv_demo source rows, one fully valid row per entity.
CSV_ROWS: dict[str, dict[str, str]] = {
    "organizations": {
        "organization_id": "ORG-001", "organization_name": "Acme Corp", "industry": "Technology",
        "country": "India", "status": "active",
    },
    "employees": {
        "employee_id": "EMP-001", "employee_name": "Alice Engineer",
        "email_address": "alice@acme.example", "department": "Engineering",
        "title": "Senior Developer", "manager_id": "", "status": "active",
        "hire_date": "2024-03-15", "is_active": "true", "organization_id": "ORG-001",
    },
    "customers": {
        "customer_id": "CUST-001", "customer_name": "Acme Industries",
        "email_address": "contact@acme-ind.example", "customer_segment": "Enterprise",
        "industry_name": "Manufacturing", "account_owner_id": "EMP-002", "status": "active",
        "created_date": "2025-01-15",
    },
    "deals": {
        "deal_id": "DEAL-001", "deal_name": "Acme Platform Deal", "customer_id": "CUST-001",
        "owner_id": "EMP-002", "stage": "negotiation", "amount": "150000.50", "currency": "INR",
        "probability": "75.0", "expected_close_date": "2026-12-31", "is_active": "true",
    },
    "projects": {
        "project_id": "PROJ-001", "project_name": "Platform Migration", "customer_id": "CUST-001",
        "owner_id": "EMP-001", "status": "in_progress", "start_date": "2026-01-01",
        "end_date": "2026-12-31", "budget": "500000.00", "is_active": "true",
    },
    "support_tickets": {
        "ticket_id": "TKT-001", "customer_id": "CUST-001", "assignee_id": "EMP-001",
        "priority": "high", "status": "open", "category": "auth",
        "subject": "Login not working after SSO update",
        "description": "Users cannot log in after the SSO provider migration.",
        "created_date": "2026-09-01", "resolved_date": "",
    },
    "documents": {
        "document_id": "DOC-001", "title": "Employee Handbook 2026", "document_type": "policy",
        "body_text": "", "source_uri": "https://internal.acme.example/docs/handbook.pdf",
        "owner_id": "EMP-001", "created_date": "2026-01-01", "updated_date": "2026-06-15",
    },
}

ID_COLUMNS = {
    "organizations": "organization_id", "employees": "employee_id", "customers": "customer_id",
    "deals": "deal_id", "projects": "project_id", "support_tickets": "ticket_id",
    "documents": "document_id",
}


def csv_row(entity: str, **overrides: str) -> dict[str, str]:
    return {**CSV_ROWS[entity], **overrides}


def csv_canonical(
    entity: str,
    run_id: uuid.UUID,
    *,
    ingested_at: datetime = NOW,
    **overrides: str,
) -> CanonicalBase:
    """Real D1 output for a csv_demo row."""
    return normalize("csv_demo", entity, csv_row(entity, **overrides), run_id, ingested_at)


def make_run(sessions: sessionmaker[Session], *, source_system: str = "csv_demo") -> uuid.UUID:
    """Create and commit a RUNNING run."""
    run_id = uuid.uuid4()
    with sessions.begin() as session:
        runs.create_run(session, run_id=run_id, source_system=source_system, source_entity=None,
                        mode=runs.RunMode.FULL, started_at=NOW)
    return run_id
