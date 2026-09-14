"""
Deterministic identity generation for D1 normalization.

Provides:
    canonical_id: Deterministic UUID5 from the source identity triple.
    record_hash:  SHA-256 over the canonical business content of a
                  validated canonical record.

Design decisions:
    - UUID5 with a fixed project namespace: the same (source_system,
      source_entity, source_id) always yields the same canonical UUID.
      The namespace MUST NOT change once records are persisted.
    - record_hash is computed from the validated canonical object, never
      from raw mapper output, over the business fields only. It excludes
      all provenance fields (id, source_system, source_entity, source_id,
      source_updated_at, ingested_at, ingestion_run_id, record_hash) and
      the canonical FK fields resolved later by E1. Identical business
      content therefore always yields the identical hash, which is the
      secondary content identity of spec Section 7.
    - Serialization is canonical: sorted keys, compact separators,
      Decimals without insignificant trailing zeros, datetimes as UTC
      ISO 8601. Naive datetimes and unsupported types are rejected.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.normalization.contract import BUSINESS_FIELDS, CANONICAL_SCHEMAS
from app.schemas.canonical import CanonicalBase

# Fixed namespace for AI CEO Layer 1 canonical identity generation.
_NAMESPACE = uuid.UUID("a1c30e00-b1a7-4e5f-9c3d-1a2b3c4d5e6f")

_ENTITY_BY_SCHEMA = {schema: entity for entity, schema in CANONICAL_SCHEMAS.items()}


def canonical_id(source_system: str, source_entity: str, source_id: str) -> uuid.UUID:
    """Generate the deterministic canonical UUID for a source record."""
    return uuid.uuid5(_NAMESPACE, f"{source_system}:{source_entity}:{source_id}")


def hash_payload(canonical: CanonicalBase) -> dict[str, object]:
    """Return the canonical business-content payload that record_hash covers."""
    entity_type = _ENTITY_BY_SCHEMA.get(type(canonical))
    if entity_type is None:
        raise TypeError(f"Not a canonical entity schema: {type(canonical).__name__}")
    return {
        name: _canonical_value(name, getattr(canonical, name))
        for name in BUSINESS_FIELDS[entity_type]
    }


def record_hash(canonical: CanonicalBase) -> str:
    """Compute the hex SHA-256 record hash of a canonical record."""
    payload = json.dumps(
        hash_payload(canonical),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_value(field_name: str, value: object) -> object:
    """Convert a canonical field value to its deterministic JSON form."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"Non-finite Decimal in field '{field_name}' cannot be hashed")
        if value.is_zero():
            return "0"
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError(f"Naive datetime in field '{field_name}' cannot be hashed")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(
        f"Unsupported value type {type(value).__name__} in field '{field_name}'"
    )
