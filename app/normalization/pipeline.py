"""
D1 normalization pipeline: source-native record -> canonical entity.

Architecture position:
    Source connector -> source-native dict -> normalize() -> CanonicalBase
    subclass -> D2 validation / E1 persistence

For each record the pipeline:
    1. Resolves the source profile and entity mapping from configuration.
    2. Rejects non-mapping records.
    3. Extracts and normalizes the source identifier.
    4. Maps and normalizes every canonical business field and the
       per-record source_updated_at.
    5. Generates the deterministic canonical UUID.
    6. Validates the canonical Pydantic schema.
    7. Computes record_hash from the validated canonical object.

D1 does NOT access the database, call HTTP APIs, instantiate connectors,
persist or quarantine records, or resolve canonical foreign keys
(customer_id, organization_id); those belong to D2/E1.

Every per-record failure is raised as a NormalizationError subclass with a
stable code and full record context. Invalid invocation arguments
(ingestion_run_id, ingested_at) are programming errors and raise
TypeError/ValueError before any record is processed.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from pydantic import ValidationError

from app.normalization.config import NormalizationConfig, default_config
from app.normalization.contract import CANONICAL_SCHEMAS
from app.normalization.errors import (
    ErrorCode,
    InvalidRecordError,
    NormalizationError,
    SchemaValidationError,
    UnsupportedEntityError,
    UnsupportedSourceError,
)
from app.normalization.identifiers import canonical_id, record_hash
from app.normalization.mappings import extract_source_id, map_record
from app.schemas.canonical import CanonicalBase

_PENDING_HASH = ""


def normalize(
    source_system: str,
    entity_type: str,
    source_record: Mapping[str, object],
    ingestion_run_id: uuid.UUID,
    ingested_at: datetime,
    *,
    config: NormalizationConfig | None = None,
) -> CanonicalBase:
    """Normalize one source-native record into a canonical Pydantic object.

    Args:
        source_system: Logical source name (csv_demo, odoo_mock, rest_mock).
        entity_type: Canonical entity type (e.g. "customers").
        source_record: Source-native record as returned by a connector.
        ingestion_run_id: UUID of the current ingestion run (from E1).
        ingested_at: Timezone-aware time the record entered Layer 1 (from E1).
        config: Explicit configuration; defaults to config/mappings/.

    Raises:
        NormalizationError: (subclass) for any per-record failure.
        TypeError, ValueError: for invalid ingestion_run_id / ingested_at.
    """
    ingested_at_utc = _validate_run_context(ingestion_run_id, ingested_at)
    resolved = default_config() if config is None else config
    return _normalize_record(
        resolved, source_system, entity_type, source_record, ingestion_run_id, ingested_at_utc
    )


def normalize_batch(
    source_system: str,
    entity_type: str,
    source_records: Iterable[object],
    ingestion_run_id: uuid.UUID,
    ingested_at: datetime,
    *,
    config: NormalizationConfig | None = None,
) -> tuple[list[CanonicalBase], list[tuple[object, NormalizationError]]]:
    """Normalize a batch; failures are collected per record, never aborting the batch.

    Returns:
        (successful canonical objects in input order,
         (original record, NormalizationError) pairs in input order)
    """
    ingested_at_utc = _validate_run_context(ingestion_run_id, ingested_at)
    resolved = default_config() if config is None else config
    successes: list[CanonicalBase] = []
    failures: list[tuple[object, NormalizationError]] = []
    for record in source_records:
        try:
            successes.append(
                _normalize_record(
                    resolved, source_system, entity_type, record, ingestion_run_id,
                    ingested_at_utc,
                )
            )
        except NormalizationError as exc:
            failures.append((record, exc))
    return successes, failures


def _validate_run_context(ingestion_run_id: object, ingested_at: object) -> datetime:
    if not isinstance(ingestion_run_id, uuid.UUID):
        raise TypeError("ingestion_run_id must be a uuid.UUID")
    if not isinstance(ingested_at, datetime):
        raise TypeError("ingested_at must be a datetime")
    if ingested_at.utcoffset() is None:
        raise ValueError("ingested_at must be timezone-aware")
    return ingested_at.astimezone(UTC)


def _normalize_record(
    config: NormalizationConfig,
    source_system: str,
    entity_type: str,
    record: object,
    ingestion_run_id: uuid.UUID,
    ingested_at: datetime,
) -> CanonicalBase:
    source_id: str | None = None
    try:
        profile = config.sources.get(source_system)
        if profile is None:
            raise UnsupportedSourceError(
                f"unsupported source system {source_system!r}; "
                f"configured: {list(config.source_systems)}"
            )
        mapping = profile.entities.get(entity_type)
        if mapping is None:
            raise UnsupportedEntityError(
                f"entity type {entity_type!r} is not mapped for source {source_system!r}; "
                f"mapped: {list(profile.entities)}"
            )
        if not isinstance(record, Mapping):
            raise InvalidRecordError(
                f"source record must be a mapping, got {type(record).__name__}"
            )
        source_id = extract_source_id(profile, mapping, record)
        source_updated_at, fields = map_record(config, profile, mapping, record)
        return _build_canonical(
            source_system, entity_type, source_id, source_updated_at,
            ingestion_run_id, ingested_at, fields,
        )
    except NormalizationError as exc:
        raise exc.with_context(
            source_system=source_system, entity_type=entity_type, source_id=source_id
        ) from exc.__cause__
    except Exception as exc:
        raise NormalizationError(
            f"unexpected {type(exc).__name__} during normalization: {exc}",
            code=ErrorCode.UNEXPECTED_ERROR,
            source_system=source_system,
            entity_type=entity_type,
            source_id=source_id,
        ) from exc


def _build_canonical(
    source_system: str,
    entity_type: str,
    source_id: str,
    source_updated_at: datetime | None,
    ingestion_run_id: uuid.UUID,
    ingested_at: datetime,
    fields: dict[str, object],
) -> CanonicalBase:
    schema = CANONICAL_SCHEMAS[entity_type]
    payload = {
        "id": canonical_id(source_system, entity_type, source_id),
        "source_system": source_system,
        "source_entity": entity_type,
        "source_id": source_id,
        "source_updated_at": source_updated_at,
        "ingested_at": ingested_at,
        "ingestion_run_id": ingestion_run_id,
        "record_hash": _PENDING_HASH,
        **fields,
    }
    try:
        draft = schema.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or None
        raise SchemaValidationError(
            f"{schema.__name__} rejected the record: {first['msg']}",
            field_name=location,
        ) from exc
    return draft.model_copy(update={"record_hash": record_hash(draft)})
