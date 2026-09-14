"""
D1 Normalization pipeline — main entry point.

Provides the ``normalize`` function that converts a source-native
record dict into a fully populated canonical Pydantic object.

Architecture position:
    Source Connector
          |
    source-native dict
          |
          v
    normalize()          <-- THIS MODULE
          |
    CanonicalBase subclass
          |
          v
    D2 validation / E1 persistence

The pipeline:
    1. Validates source_system and entity_type are supported.
    2. Extracts the source_id from the source record.
    3. Generates a deterministic canonical UUID.
    4. Applies the source/entity-specific field mapper.
    5. Computes the record_hash over canonical business fields.
    6. Constructs and returns the canonical Pydantic object.

D1 does NOT:
    - Access the database
    - Call HTTP APIs
    - Instantiate connectors
    - Perform quarantine or persistence
    - Resolve canonical foreign keys (customer_id, organization_id)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.normalization.errors import (
    FieldMappingError,
    NormalizationError,
)
from app.normalization.identifiers import canonical_id, record_hash
from app.normalization.mappings import (
    SUPPORTED_ENTITIES,
    SUPPORTED_SOURCES,
    extract_source_id,
    get_mapper,
)
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


# Maps entity_type to the canonical Pydantic class.
_CANONICAL_CLASSES: dict[str, type[CanonicalBase]] = {
    "organizations": OrganizationCanonical,
    "employees": EmployeeCanonical,
    "customers": CustomerCanonical,
    "deals": DealCanonical,
    "projects": ProjectCanonical,
    "support_tickets": SupportTicketCanonical,
    "documents": DocumentCanonical,
}


def normalize(
    source_system: str,
    entity_type: str,
    source_record: dict[str, Any],
    ingestion_run_id: uuid.UUID,
    ingested_at: datetime,
    source_updated_at: datetime | None = None,
) -> CanonicalBase:
    """Normalize a source-native record into a canonical Pydantic object.

    This is the main D1 entry point. It performs field mapping, type
    coercion, deterministic identity generation, and record hashing.

    Args:
        source_system: Logical source name (e.g. "csv_demo").
        entity_type: Canonical entity type (e.g. "customers").
        source_record: Source-native record dict as returned by a connector.
        ingestion_run_id: UUID of the current ingestion run (from E1).
        ingested_at: Timestamp when this record entered Layer 1 (from E1).
        source_updated_at: Timestamp from the source system (if available).

    Returns:
        A fully populated canonical Pydantic object (subclass of CanonicalBase).

    Raises:
        UnsupportedSourceError: If source_system is not recognized.
        UnsupportedEntityError: If entity_type is not supported.
        FieldMappingError: If a required field is missing.
        CoercionError: If a value cannot be converted to canonical type.
        NormalizationError: Base class for any normalization failure.
    """
    # 1. Get the mapper function (validates source/entity)
    mapper = get_mapper(source_system, entity_type)

    # 2. Extract source ID
    source_id = extract_source_id(source_system, entity_type, source_record)

    # 3. Generate deterministic canonical UUID
    cid = canonical_id(source_system, entity_type, source_id)

    # 4. Apply field mapping and type coercion
    try:
        business_fields = mapper(source_record)
    except NormalizationError:
        raise
    except Exception as exc:
        raise FieldMappingError(
            f"Field mapping failed for {source_system}/{entity_type}/{source_id}: {exc}",
            source_system=source_system,
            entity_type=entity_type,
            source_id=source_id,
        ) from exc

    # 5. Compute record hash over business fields
    hash_input = dict(business_fields)
    hash_input["source_system"] = source_system
    hash_input["source_entity"] = entity_type
    hash_input["source_id"] = source_id
    rhash = record_hash(hash_input)

    # 6. Assemble provenance + business fields
    canonical_fields = {
        "id": cid,
        "source_system": source_system,
        "source_entity": entity_type,
        "source_id": source_id,
        "source_updated_at": source_updated_at,
        "ingested_at": ingested_at,
        "ingestion_run_id": ingestion_run_id,
        "record_hash": rhash,
        **business_fields,
    }

    # 7. Construct the canonical Pydantic object
    canonical_class = _CANONICAL_CLASSES[entity_type]
    try:
        return canonical_class(**canonical_fields)
    except Exception as exc:
        raise FieldMappingError(
            f"Failed to construct {canonical_class.__name__} for "
            f"{source_system}/{entity_type}/{source_id}: {exc}",
            source_system=source_system,
            entity_type=entity_type,
            source_id=source_id,
        ) from exc


def normalize_batch(
    source_system: str,
    entity_type: str,
    source_records: list[dict[str, Any]],
    ingestion_run_id: uuid.UUID,
    ingested_at: datetime,
    source_updated_at: datetime | None = None,
) -> tuple[list[CanonicalBase], list[tuple[dict[str, Any], NormalizationError]]]:
    """Normalize a batch of source records, collecting errors separately.

    Records that fail normalization are collected as (record, error) pairs
    rather than aborting the entire batch. This supports the spec's
    requirement that "a malformed individual record should not corrupt
    an entire successful batch."

    Args:
        source_system: Logical source name.
        entity_type: Canonical entity type.
        source_records: List of source-native record dicts.
        ingestion_run_id: UUID of the current ingestion run.
        ingested_at: Timestamp for ingested_at.
        source_updated_at: Timestamp from source (if available).

    Returns:
        Tuple of (successful canonical objects, failed (record, error) pairs).
    """
    successes: list[CanonicalBase] = []
    failures: list[tuple[dict[str, Any], NormalizationError]] = []

    for record in source_records:
        try:
            canonical = normalize(
                source_system=source_system,
                entity_type=entity_type,
                source_record=record,
                ingestion_run_id=ingestion_run_id,
                ingested_at=ingested_at,
                source_updated_at=source_updated_at,
            )
            successes.append(canonical)
        except NormalizationError as exc:
            failures.append((record, exc))

    return successes, failures
