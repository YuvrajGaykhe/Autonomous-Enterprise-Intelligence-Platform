"""
D2 quality gate: canonical validation -> valid records OR quarantine.

Architecture position:
    connector records -> D1 normalize -> D2 quality gate -> E1 persistence
                                              |
                                              +-> quarantine records (E1 persists)

Entry points:
    validate_source_batch     D1-normalizes each source-native record, then
                              validates it (the D1 -> D2 boundary).
    validate_canonical_batch  Validates canonical records that were already
                              produced by D1.

Both return a QualityGateResult that partitions the batch, in input order,
into valid canonical records (the exact D1 objects, unmodified) and
quarantine records, plus WARNING findings for valid records.

Failure model:
    DATA failures (classified D1 data errors, D2 contract violations) are
    quarantined and processing continues.
    SYSTEM failures (unsupported batch context, unclassified or unexpected
    D1 errors, broken canonical invariants, configuration errors, and any
    other exception) propagate. No exception is caught broadly.

D2 performs no database, network, connector, or LLM access and resolves no
canonical foreign keys.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from app.normalization import NormalizationConfig, NormalizationError, default_config, normalize
from app.normalization.config import SourceProfile
from app.schemas.canonical import CanonicalBase
from app.validation.config import ValidationConfig, default_validation_config
from app.validation.errors import (
    QualityGateSystemError,
    Severity,
    SystemFailureCode,
    is_data_failure,
)
from app.validation.quarantine import (
    QualityFinding,
    QuarantineRecord,
    quarantine_from_normalization_error,
    quarantine_from_violations,
    safe_message,
)
from app.validation.rules import (
    canonical_values,
    check_canonical_record,
    check_identity,
    check_invariants,
    record_source_id,
    warning_violations,
)


@dataclass(frozen=True)
class QualityGateResult:
    """Deterministic partition of one batch."""

    source_system: str
    entity_type: str
    ingestion_run_id: uuid.UUID
    total_records: int
    valid: tuple[CanonicalBase, ...]
    quarantined: tuple[QuarantineRecord, ...]
    warnings: tuple[QualityFinding, ...]

    def __post_init__(self) -> None:
        if len(self.valid) + len(self.quarantined) != self.total_records:
            raise ValueError("valid and quarantined records must account for every input record")

    @property
    def valid_count(self) -> int:
        return len(self.valid)

    @property
    def quarantined_count(self) -> int:
        return len(self.quarantined)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def summary(self) -> dict[str, object]:
        return {
            "source_system": self.source_system,
            "entity_type": self.entity_type,
            "ingestion_run_id": str(self.ingestion_run_id),
            "total_records": self.total_records,
            "valid": self.valid_count,
            "quarantined": self.quarantined_count,
            "warnings": self.warning_count,
        }


def validate_source_batch(
    source_system: str,
    entity_type: str,
    source_records: Iterable[object],
    ingestion_run_id: uuid.UUID,
    ingested_at: datetime,
    *,
    normalization_config: NormalizationConfig | None = None,
    validation_config: ValidationConfig | None = None,
) -> QualityGateResult:
    """Normalize (D1) and validate (D2) a batch of source-native records."""
    batch = _Batch.open(source_system, entity_type, ingestion_run_id,
                        normalization_config, validation_config)
    _check_ingested_at(ingested_at)
    for index, record in enumerate(source_records):
        batch.total = index + 1
        try:
            # D1 annotates source_record as Mapping[str, object], but normalize() accepts any
            # object at runtime and rejects non-mappings with INVALID_RECORD, a data failure
            # quarantined below. D1 is frozen, so the ignore is limited to this argument.
            canonical = normalize(source_system, entity_type, record,  # type: ignore[arg-type]
                                  ingestion_run_id, ingested_at, config=batch.normalization_config)
        except NormalizationError as exc:
            if not is_data_failure(exc):
                raise QualityGateSystemError(
                    f"normalization reported a non-data failure {exc.code}: "
                    f"{safe_message(exc.reason, batch.validation_config.quarantine)}",
                    code=SystemFailureCode.NORMALIZATION_SYSTEM_FAILURE,
                    source_system=source_system, entity_type=entity_type,
                    source_id=exc.source_id, record_index=index, field_name=exc.field_name,
                ) from exc
            batch.quarantined.append(quarantine_from_normalization_error(
                exc, record=record, record_index=index, ingestion_run_id=ingestion_run_id,
                source_system=source_system, entity_type=entity_type,
                policy=batch.validation_config.quarantine,
            ))
            continue
        batch.gate(index, canonical, raw_record=record)
    return batch.result()


def validate_canonical_batch(
    source_system: str,
    entity_type: str,
    canonical_records: Iterable[CanonicalBase],
    ingestion_run_id: uuid.UUID,
    *,
    normalization_config: NormalizationConfig | None = None,
    validation_config: ValidationConfig | None = None,
) -> QualityGateResult:
    """Validate canonical records already produced by D1 normalization."""
    batch = _Batch.open(source_system, entity_type, ingestion_run_id,
                        normalization_config, validation_config)
    for index, record in enumerate(canonical_records):
        batch.total = index + 1
        batch.gate(index, record, raw_record=None)
    return batch.result()


@dataclass
class _Batch:
    source_system: str
    entity_type: str
    ingestion_run_id: uuid.UUID
    normalization_config: NormalizationConfig
    validation_config: ValidationConfig
    profile: SourceProfile
    accepted: list[tuple[int, CanonicalBase]]
    quarantined: list[QuarantineRecord]
    total: int = 0

    @classmethod
    def open(
        cls,
        source_system: str,
        entity_type: str,
        ingestion_run_id: uuid.UUID,
        normalization_config: NormalizationConfig | None,
        validation_config: ValidationConfig | None,
    ) -> _Batch:
        if not isinstance(ingestion_run_id, uuid.UUID):
            raise TypeError("ingestion_run_id must be a uuid.UUID")
        normalization = default_config() if normalization_config is None else normalization_config
        validation = default_validation_config() if validation_config is None else validation_config
        profile = normalization.sources.get(source_system) if isinstance(source_system, str) else None
        if profile is None:
            raise QualityGateSystemError(
                f"source system {source_system!r} is not configured",
                code=SystemFailureCode.UNSUPPORTED_SOURCE,
            )
        if entity_type not in profile.entities:
            raise QualityGateSystemError(
                f"entity type {entity_type!r} is not mapped for {source_system!r}",
                code=SystemFailureCode.UNSUPPORTED_ENTITY, source_system=source_system,
            )
        return cls(source_system, entity_type, ingestion_run_id, normalization, validation,
                   profile, accepted=[], quarantined=[])

    def gate(self, index: int, record: CanonicalBase, *, raw_record: object) -> None:
        check_invariants(record, source_system=self.source_system, entity_type=self.entity_type,
                         ingestion_run_id=self.ingestion_run_id, record_index=index)
        violations = check_canonical_record(
            record, entity_type=self.entity_type, profile=self.profile,
            config=self.normalization_config, record_index=index,
        )
        if violations:
            self.quarantined.append(quarantine_from_violations(
                violations,
                raw_record=canonical_values(record) if raw_record is None else raw_record,
                record_index=index, source_id=record_source_id(record),
                record_canonical_id=record.id, ingestion_run_id=self.ingestion_run_id,
                source_system=self.source_system, entity_type=self.entity_type,
                policy=self.validation_config.quarantine,
            ))
            return
        check_identity(record, source_system=self.source_system, entity_type=self.entity_type,
                       record_index=index)
        self.accepted.append((index, record))

    def result(self) -> QualityGateResult:
        warnings = tuple(
            QualityFinding(
                severity=Severity.WARNING,
                code=violation.code,
                message=violation.reason,
                record_index=index,
                source_id=record.source_id,
                field_name=violation.field_name,
            )
            for index, record, violation in warning_violations(
                self.accepted, entity_type=self.entity_type,
                policy=self.validation_config.warnings,
            )
        )
        return QualityGateResult(
            source_system=self.source_system,
            entity_type=self.entity_type,
            ingestion_run_id=self.ingestion_run_id,
            total_records=self.total,
            valid=tuple(record for _, record in self.accepted),
            quarantined=tuple(self.quarantined),
            warnings=warnings,
        )


def _check_ingested_at(ingested_at: object) -> None:
    if not isinstance(ingested_at, datetime):
        raise TypeError("ingested_at must be a datetime")
    if ingested_at.utcoffset() is None:
        raise ValueError("ingested_at must be timezone-aware")
