"""
Source-to-canonical field mapping tables for D1 normalization.

Provides explicit, per-entity, per-source mappings from source-native
field names to canonical field names, along with the coercion function
to apply to each field.

Design decisions:
    - Explicit mapping dicts rather than reflection. Every field
      transformation is visible and auditable.
    - Source ID extraction is per-source/entity because sources use
      different field names and types for their primary identifier.
    - Odoo integer IDs are converted to strings (canonical source_id
      is always a string).
    - is_active derivation differs per entity and per source:
      * CSV: parse string boolean from 'is_active' column
      * Odoo: map 'active' boolean field
      * REST: map 'isActive' boolean field
      * For entities without is_active (Organization, SupportTicket,
        Document), the canonical schema does not include is_active.
    - Relationship source keys (owner_source_id, customer_source_id,
      etc.) are mapped to canonical names. Integer references (Odoo)
      are converted to strings.
    - Canonical FK fields like customer_id and organization_id are NOT
      set by D1. They require persisted-state lookups and belong to
      E1/persistence. D1 sets them to None.

Source systems:
    csv_demo  -> CSV source schemas
    odoo_mock -> Odoo source schemas
    rest_demo -> REST source schemas
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.normalization.coercion import (
    coerce_bool,
    coerce_date,
    coerce_datetime,
    coerce_decimal,
    coerce_email,
    coerce_int_id_to_str,
    coerce_str,
)
from app.normalization.errors import (
    FieldMappingError,
    UnsupportedEntityError,
    UnsupportedSourceError,
)


# ---------------------------------------------------------------------------
# Supported sources and entities
# ---------------------------------------------------------------------------

SUPPORTED_SOURCES = frozenset({"csv_demo", "odoo_mock", "rest_demo"})

SUPPORTED_ENTITIES = frozenset({
    "organizations",
    "employees",
    "customers",
    "deals",
    "projects",
    "support_tickets",
    "documents",
})

# Entities that have an is_active field in the canonical schema.
_ACTIVE_ENTITIES = frozenset({
    "employees",
    "customers",
    "deals",
    "projects",
})


# ---------------------------------------------------------------------------
# Source ID extraction
# ---------------------------------------------------------------------------

# Maps (source_system, entity_type) to the source field name that
# contains the primary identifier, plus whether it needs int-to-str
# conversion.

_SOURCE_ID_FIELD: dict[tuple[str, str], tuple[str, bool]] = {
    # CSV: string IDs
    ("csv_demo", "organizations"): ("organization_id", False),
    ("csv_demo", "employees"): ("employee_id", False),
    ("csv_demo", "customers"): ("customer_id", False),
    ("csv_demo", "deals"): ("deal_id", False),
    ("csv_demo", "projects"): ("project_id", False),
    ("csv_demo", "support_tickets"): ("ticket_id", False),
    ("csv_demo", "documents"): ("document_id", False),
    # Odoo: integer IDs
    ("odoo_mock", "organizations"): ("id", True),
    ("odoo_mock", "employees"): ("id", True),
    ("odoo_mock", "customers"): ("id", True),
    ("odoo_mock", "deals"): ("id", True),
    ("odoo_mock", "projects"): ("id", True),
    ("odoo_mock", "support_tickets"): ("id", True),
    ("odoo_mock", "documents"): ("id", True),
    # REST: string IDs
    ("rest_demo", "organizations"): ("id", False),
    ("rest_demo", "employees"): ("id", False),
    ("rest_demo", "customers"): ("id", False),
    ("rest_demo", "deals"): ("id", False),
    ("rest_demo", "projects"): ("id", False),
    ("rest_demo", "support_tickets"): ("id", False),
    ("rest_demo", "documents"): ("id", False),
}


def extract_source_id(
    source_system: str,
    entity_type: str,
    record: dict[str, Any],
) -> str:
    """Extract and return the source record's primary identifier as a string.

    Args:
        source_system: Logical source name.
        entity_type: Canonical entity type.
        record: Source-native record dict.

    Returns:
        Source ID as a string.

    Raises:
        FieldMappingError: If the ID field is missing or empty.
    """
    key = (source_system, entity_type)
    if key not in _SOURCE_ID_FIELD:
        raise UnsupportedEntityError(
            f"No source ID mapping for {source_system}/{entity_type}",
            source_system=source_system,
            entity_type=entity_type,
        )
    field_name, needs_int_conv = _SOURCE_ID_FIELD[key]
    raw = record.get(field_name)
    if raw is None:
        raise FieldMappingError(
            f"Missing required source ID field '{field_name}' "
            f"in {source_system}/{entity_type}",
            field_name=field_name,
            source_system=source_system,
            entity_type=entity_type,
        )
    if needs_int_conv:
        return coerce_int_id_to_str(raw)
    sid = str(raw).strip()
    if not sid:
        raise FieldMappingError(
            f"Empty source ID field '{field_name}' "
            f"in {source_system}/{entity_type}",
            field_name=field_name,
            source_system=source_system,
            entity_type=entity_type,
        )
    return sid


# ---------------------------------------------------------------------------
# Field mapping functions
#
# Each function takes a source record dict and returns a dict of
# canonical business fields (excluding provenance fields which are
# added by the pipeline).
# ---------------------------------------------------------------------------


def _map_csv_organization(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("organization_name")) or "",
        "industry": coerce_str(rec.get("industry")),
        "country": coerce_str(rec.get("country")),
        "status": coerce_str(rec.get("status")),
    }


def _map_csv_employee(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("employee_name")) or "",
        "email": coerce_email(rec.get("email_address")),
        "department": coerce_str(rec.get("department")),
        "title": coerce_str(rec.get("title")),
        "manager_source_id": coerce_str(rec.get("manager_id")),
        "status": coerce_str(rec.get("status")),
        "hire_date": coerce_date(rec.get("hire_date")),
        "is_active": coerce_bool(rec.get("is_active")) if rec.get("is_active") is not None else True,
        "organization_id": None,  # Canonical FK resolved by E1
    }


def _map_csv_customer(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("customer_name")) or "",
        "email": coerce_email(rec.get("email_address")),
        "segment": coerce_str(rec.get("customer_segment")),
        "industry": coerce_str(rec.get("industry_name")),
        "status": coerce_str(rec.get("status")),
        "owner_source_id": coerce_str(rec.get("account_owner_id")),
        "created_at": coerce_datetime(rec.get("created_date")),
        "is_active": True,  # CSV customers default to active (status-based)
    }


def _map_csv_deal(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("deal_name")) or "",
        "stage": coerce_str(rec.get("stage")),
        "amount": coerce_decimal(rec.get("amount")),
        "currency": coerce_str(rec.get("currency")),
        "probability": coerce_decimal(rec.get("probability")),
        "expected_close_date": coerce_date(rec.get("expected_close_date")),
        "is_active": coerce_bool(rec.get("is_active")) if rec.get("is_active") is not None else True,
        "customer_source_id": coerce_str(rec.get("customer_id")),
        "owner_source_id": coerce_str(rec.get("owner_id")),
        "customer_id": None,  # Canonical FK resolved by E1
    }


def _map_csv_project(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("project_name")) or "",
        "status": coerce_str(rec.get("status")),
        "start_date": coerce_date(rec.get("start_date")),
        "end_date": coerce_date(rec.get("end_date")),
        "budget": coerce_decimal(rec.get("budget")),
        "is_active": coerce_bool(rec.get("is_active")) if rec.get("is_active") is not None else True,
        "customer_source_id": coerce_str(rec.get("customer_id")),
        "owner_source_id": coerce_str(rec.get("owner_id")),
        "customer_id": None,  # Canonical FK resolved by E1
    }


def _map_csv_support_ticket(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject": coerce_str(rec.get("subject")),
        "description": coerce_str(rec.get("description")),
        "priority": coerce_str(rec.get("priority")),
        "status": coerce_str(rec.get("status")),
        "category": coerce_str(rec.get("category")),
        "created_at": coerce_datetime(rec.get("created_date")),
        "resolved_at": coerce_datetime(rec.get("resolved_date")),
        "customer_source_id": coerce_str(rec.get("customer_id")),
        "assignee_source_id": coerce_str(rec.get("assignee_id")),
        "customer_id": None,  # Canonical FK resolved by E1
    }


def _map_csv_document(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": coerce_str(rec.get("title")),
        "document_type": coerce_str(rec.get("document_type")),
        "body_text": rec.get("body_text"),  # Preserve as-is, no null token mapping
        "source_uri": coerce_str(rec.get("source_uri")),
        "owner_source_id": coerce_str(rec.get("owner_id")),
        "created_at": coerce_datetime(rec.get("created_date")),
        "updated_at": coerce_datetime(rec.get("updated_date")),
    }


# ---------------------------------------------------------------------------
# Odoo mappers
# ---------------------------------------------------------------------------


def _map_odoo_organization(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("name")) or "",
        "industry": coerce_str(rec.get("industry_id")),
        "country": coerce_str(rec.get("country_id")),
        "status": "active" if rec.get("active", True) else "inactive",
    }


def _map_odoo_employee(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("name")) or "",
        "email": coerce_email(rec.get("work_email")),
        "department": coerce_str(rec.get("department_id")),
        "title": coerce_str(rec.get("job_title")),
        "manager_source_id": coerce_int_id_to_str(rec.get("parent_id")),
        "status": "active" if rec.get("active", True) else "inactive",
        "hire_date": coerce_date(rec.get("x_hire_date")),
        "is_active": rec.get("active", True),
        "organization_id": None,  # Canonical FK resolved by E1
    }


def _map_odoo_customer(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("name")) or "",
        "email": coerce_email(rec.get("email")),
        "segment": coerce_str(rec.get("x_studio_segment")),
        "industry": coerce_str(rec.get("industry_id")),
        "status": "active" if rec.get("active", True) else "inactive",
        "owner_source_id": coerce_int_id_to_str(rec.get("user_id")),
        "created_at": coerce_datetime(rec.get("create_date")),
        "is_active": rec.get("active", True),
    }


def _map_odoo_deal(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("name")) or "",
        "stage": coerce_str(rec.get("stage_id")),
        "amount": coerce_decimal(rec.get("expected_revenue")),
        "currency": coerce_str(rec.get("company_currency")),
        "probability": coerce_decimal(rec.get("probability")),
        "expected_close_date": coerce_date(rec.get("date_deadline")),
        "is_active": rec.get("active", True),
        "customer_source_id": coerce_int_id_to_str(rec.get("partner_id")),
        "owner_source_id": coerce_int_id_to_str(rec.get("user_id")),
        "customer_id": None,  # Canonical FK resolved by E1
    }


def _map_odoo_project(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("name")) or "",
        "status": coerce_str(rec.get("stage_id")),
        "start_date": coerce_date(rec.get("date_start")),
        "end_date": coerce_date(rec.get("date")),
        "budget": coerce_decimal(rec.get("x_budget")),
        "is_active": rec.get("active", True),
        "customer_source_id": coerce_int_id_to_str(rec.get("partner_id")),
        "owner_source_id": coerce_int_id_to_str(rec.get("user_id")),
        "customer_id": None,  # Canonical FK resolved by E1
    }


def _map_odoo_support_ticket(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject": coerce_str(rec.get("name")),
        "description": rec.get("description"),
        "priority": coerce_str(rec.get("priority")),
        "status": coerce_str(rec.get("stage_id")),
        "category": coerce_str(rec.get("category_id")),
        "created_at": coerce_datetime(rec.get("create_date")),
        "resolved_at": coerce_datetime(rec.get("close_date")),
        "customer_source_id": coerce_int_id_to_str(rec.get("partner_id")),
        "assignee_source_id": coerce_int_id_to_str(rec.get("user_id")),
        "customer_id": None,  # Canonical FK resolved by E1
    }


def _map_odoo_document(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": coerce_str(rec.get("name")),
        "document_type": coerce_str(rec.get("type")),
        "body_text": rec.get("datas"),
        "source_uri": coerce_str(rec.get("url")),
        "owner_source_id": coerce_int_id_to_str(rec.get("owner_id")),
        "created_at": coerce_datetime(rec.get("create_date")),
        "updated_at": coerce_datetime(rec.get("write_date")),
    }


# ---------------------------------------------------------------------------
# REST mappers
# ---------------------------------------------------------------------------


def _map_rest_organization(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("name")) or "",
        "industry": coerce_str(rec.get("industry")),
        "country": coerce_str(rec.get("country")),
        "status": coerce_str(rec.get("status")),
    }


def _map_rest_employee(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("name")) or "",
        "email": coerce_email(rec.get("email")),
        "department": coerce_str(rec.get("department")),
        "title": coerce_str(rec.get("title")),
        "manager_source_id": coerce_str(rec.get("managerId")),
        "status": coerce_str(rec.get("status")),
        "hire_date": coerce_date(rec.get("hireDate")),
        "is_active": coerce_bool(rec.get("isActive")) if rec.get("isActive") is not None else True,
        "organization_id": None,  # Canonical FK resolved by E1
    }


def _map_rest_customer(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("name")) or "",
        "email": coerce_email(rec.get("email")),
        "segment": coerce_str(rec.get("segment")),
        "industry": coerce_str(rec.get("industry")),
        "status": coerce_str(rec.get("status")),
        "owner_source_id": coerce_str(rec.get("ownerId")),
        "created_at": coerce_datetime(rec.get("createdAt")),
        "is_active": coerce_bool(rec.get("isActive")) if rec.get("isActive") is not None else True,
    }


def _map_rest_deal(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("name")) or "",
        "stage": coerce_str(rec.get("stage")),
        "amount": coerce_decimal(rec.get("amount")),
        "currency": coerce_str(rec.get("currency")),
        "probability": coerce_decimal(rec.get("probability")),
        "expected_close_date": coerce_date(rec.get("expectedCloseDate")),
        "is_active": coerce_bool(rec.get("isActive")) if rec.get("isActive") is not None else True,
        "customer_source_id": coerce_str(rec.get("customerId")),
        "owner_source_id": coerce_str(rec.get("ownerId")),
        "customer_id": None,  # Canonical FK resolved by E1
    }


def _map_rest_project(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("name")) or "",
        "status": coerce_str(rec.get("status")),
        "start_date": coerce_date(rec.get("startDate")),
        "end_date": coerce_date(rec.get("endDate")),
        "budget": coerce_decimal(rec.get("budget")),
        "is_active": coerce_bool(rec.get("isActive")) if rec.get("isActive") is not None else True,
        "customer_source_id": coerce_str(rec.get("customerId")),
        "owner_source_id": coerce_str(rec.get("ownerId")),
        "customer_id": None,  # Canonical FK resolved by E1
    }


def _map_rest_support_ticket(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": coerce_str(rec.get("name")) if "name" in rec else None,
        "subject": coerce_str(rec.get("subject")),
        "description": rec.get("description"),
        "priority": coerce_str(rec.get("priority")),
        "status": coerce_str(rec.get("status")),
        "category": coerce_str(rec.get("category")),
        "created_at": coerce_datetime(rec.get("createdAt")),
        "resolved_at": coerce_datetime(rec.get("resolvedAt")),
        "customer_source_id": coerce_str(rec.get("customerId")),
        "assignee_source_id": coerce_str(rec.get("assigneeId")),
        "customer_id": None,  # Canonical FK resolved by E1
    }


def _map_rest_document(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": coerce_str(rec.get("title")),
        "document_type": coerce_str(rec.get("documentType")),
        "body_text": rec.get("bodyText"),
        "source_uri": coerce_str(rec.get("sourceUri")),
        "owner_source_id": coerce_str(rec.get("ownerId")),
        "created_at": coerce_datetime(rec.get("createdAt")),
        "updated_at": coerce_datetime(rec.get("updatedAt")),
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

# Registry of (source_system, entity_type) -> mapper function
_MAPPER_REGISTRY: dict[
    tuple[str, str],
    type[Any],  # Actually Callable[[dict], dict], but Any for simplicity
] = {
    # CSV
    ("csv_demo", "organizations"): _map_csv_organization,
    ("csv_demo", "employees"): _map_csv_employee,
    ("csv_demo", "customers"): _map_csv_customer,
    ("csv_demo", "deals"): _map_csv_deal,
    ("csv_demo", "projects"): _map_csv_project,
    ("csv_demo", "support_tickets"): _map_csv_support_ticket,
    ("csv_demo", "documents"): _map_csv_document,
    # Odoo
    ("odoo_mock", "organizations"): _map_odoo_organization,
    ("odoo_mock", "employees"): _map_odoo_employee,
    ("odoo_mock", "customers"): _map_odoo_customer,
    ("odoo_mock", "deals"): _map_odoo_deal,
    ("odoo_mock", "projects"): _map_odoo_project,
    ("odoo_mock", "support_tickets"): _map_odoo_support_ticket,
    ("odoo_mock", "documents"): _map_odoo_document,
    # REST
    ("rest_demo", "organizations"): _map_rest_organization,
    ("rest_demo", "employees"): _map_rest_employee,
    ("rest_demo", "customers"): _map_rest_customer,
    ("rest_demo", "deals"): _map_rest_deal,
    ("rest_demo", "projects"): _map_rest_project,
    ("rest_demo", "support_tickets"): _map_rest_support_ticket,
    ("rest_demo", "documents"): _map_rest_document,
}

# Maps entity_type to the canonical schema class name (for pipeline.py)
_CANONICAL_SCHEMA_MAP: dict[str, str] = {
    "organizations": "OrganizationCanonical",
    "employees": "EmployeeCanonical",
    "customers": "CustomerCanonical",
    "deals": "DealCanonical",
    "projects": "ProjectCanonical",
    "support_tickets": "SupportTicketCanonical",
    "documents": "DocumentCanonical",
}


def get_mapper(
    source_system: str,
    entity_type: str,
):
    """Return the field mapping function for the given source/entity.

    Args:
        source_system: Logical source name.
        entity_type: Canonical entity type.

    Returns:
        Callable that takes a source record dict and returns a
        canonical business field dict.

    Raises:
        UnsupportedSourceError: If source_system is not recognized.
        UnsupportedEntityError: If entity_type is not supported.
    """
    if source_system not in SUPPORTED_SOURCES:
        raise UnsupportedSourceError(
            f"Unsupported source system: '{source_system}'",
            source_system=source_system,
        )
    if entity_type not in SUPPORTED_ENTITIES:
        raise UnsupportedEntityError(
            f"Unsupported entity type: '{entity_type}'",
            entity_type=entity_type,
        )
    key = (source_system, entity_type)
    mapper = _MAPPER_REGISTRY.get(key)
    if mapper is None:
        raise UnsupportedEntityError(
            f"No mapper for {source_system}/{entity_type}",
            source_system=source_system,
            entity_type=entity_type,
        )
    return mapper


def has_is_active(entity_type: str) -> bool:
    """Check if an entity type has an is_active field in its canonical schema."""
    return entity_type in _ACTIVE_ENTITIES
