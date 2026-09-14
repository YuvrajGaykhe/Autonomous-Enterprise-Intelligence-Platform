"""
Deterministic identity generation for D1 normalization.

Provides:
    canonical_id: Deterministic UUID5 from source identity triple.
    record_hash: SHA-256 of sorted canonical business fields.

Design decisions:
    - UUID5 (name-based, SHA-1) ensures the same (source_system,
      source_entity, source_id) always produces the same canonical UUID.
    - The namespace UUID is a fixed project-specific constant. Changing
      it would change every canonical ID, so it must never be modified
      after initial deployment.
    - record_hash excludes provenance fields (id, ingested_at,
      ingestion_run_id, record_hash itself, source_updated_at) so that
      re-ingestion of an unchanged record produces the same hash. This
      enables idempotent upsert detection in E1.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal
from datetime import date, datetime


# Fixed namespace for AI CEO Layer 1 canonical identity generation.
# This MUST NOT change after initial deployment or all canonical IDs
# will shift, breaking foreign key references.
_NAMESPACE = uuid.UUID("a1c30e00-b1a7-4e5f-9c3d-1a2b3c4d5e6f")

# Fields excluded from record_hash computation.
# These are provenance/system fields that change on re-ingestion
# without the business content changing.
_HASH_EXCLUDED_FIELDS = frozenset({
    "id",
    "ingested_at",
    "ingestion_run_id",
    "record_hash",
    "source_updated_at",
})


def canonical_id(
    source_system: str,
    source_entity: str,
    source_id: str,
) -> uuid.UUID:
    """Generate a deterministic canonical UUID for a source record.

    The same (source_system, source_entity, source_id) triple always
    produces the same UUID5. Different triples produce different UUIDs
    (within the practical collision resistance of SHA-1).

    Args:
        source_system: Logical source name (e.g. "csv_demo").
        source_entity: Entity type (e.g. "customers").
        source_id: Stable identifier from the source system.

    Returns:
        Deterministic UUID5.
    """
    name = f"{source_system}:{source_entity}:{source_id}"
    return uuid.uuid5(_NAMESPACE, name)


def _json_default(obj: object) -> str:
    """JSON serializer for types not natively supported by json.dumps."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Cannot serialize {type(obj).__name__}")


def record_hash(fields: dict) -> str:
    """Compute a deterministic SHA-256 hash of canonical business fields.

    Excludes provenance fields so that re-ingestion of an unchanged
    record produces the same hash, enabling idempotent upsert detection.

    The hash is computed over a JSON-serialized, sorted representation
    of the fields to ensure determinism regardless of dict ordering.

    Args:
        fields: Canonical field name -> value mapping.

    Returns:
        Hex-encoded SHA-256 digest string.
    """
    hashable = {
        k: v for k, v in fields.items()
        if k not in _HASH_EXCLUDED_FIELDS
    }
    # Sort keys for deterministic ordering
    payload = json.dumps(hashable, sort_keys=True, default=_json_default)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
