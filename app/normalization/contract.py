"""
Canonical contract facts that D1 relies on.

Derived from the B2 canonical schemas rather than duplicated by hand, so
normalization, hashing, and configuration validation all agree on:

    - which schema belongs to each canonical entity
    - which fields are provenance metadata (spec Section 6)
    - which canonical FK fields are resolved later by E1
    - which fields are canonical business content
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from app.schemas.canonical import (
    CanonicalBase,
    CustomerCanonical,
    DealCanonical,
    DocumentCanonical,
    EmployeeCanonical,
    OrganizationCanonical,
    ProjectCanonical,
    SupportTicketCanonical,
)

CANONICAL_SCHEMAS: Mapping[str, type[CanonicalBase]] = MappingProxyType({
    "organizations": OrganizationCanonical,
    "employees": EmployeeCanonical,
    "customers": CustomerCanonical,
    "deals": DealCanonical,
    "projects": ProjectCanonical,
    "support_tickets": SupportTicketCanonical,
    "documents": DocumentCanonical,
})

# Universal provenance fields shared by every canonical entity.
PROVENANCE_FIELDS: frozenset[str] = frozenset(CanonicalBase.model_fields)

# Canonical FK fields that require persisted state and are resolved by E1.
# D1 never populates them and they are excluded from record_hash.
E1_RESOLVED_FIELDS: Mapping[str, frozenset[str]] = MappingProxyType({
    "organizations": frozenset(),
    "employees": frozenset({"organization_id"}),
    "customers": frozenset(),
    "deals": frozenset({"customer_id"}),
    "projects": frozenset({"customer_id"}),
    "support_tickets": frozenset({"customer_id"}),
    "documents": frozenset(),
})

# Canonical business fields per entity, in schema declaration order.
BUSINESS_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    entity_type: tuple(
        name
        for name in schema.model_fields
        if name not in PROVENANCE_FIELDS and name not in E1_RESOLVED_FIELDS[entity_type]
    )
    for entity_type, schema in CANONICAL_SCHEMAS.items()
})


def is_required(entity_type: str, field_name: str) -> bool:
    """Return whether the canonical schema requires a non-null value."""
    return CANONICAL_SCHEMAS[entity_type].model_fields[field_name].is_required()
