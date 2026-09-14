"""
Failure model for D2 validation and quarantine.

Every failure belongs to exactly one category:

    DATA failure    A source record, or a canonical value derived from it,
                    violates the canonical contract. The record is
                    quarantined with structured findings and the remaining
                    records continue.

    SYSTEM failure  A configuration fault, programming bug, unsupported batch
                    context, or broken pipeline invariant. Nothing is
                    quarantined: the operation raises, so a fault can never
                    hide inside quarantine data.

D1 NormalizationError codes are classified explicitly below. Any code that is
not listed in DATA_FAILURE_CODES fails closed as a system failure.
"""

from __future__ import annotations

from enum import StrEnum

from app.normalization import ErrorCode, NormalizationError


class Severity(StrEnum):
    """Spec Section 13 severity model."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class Stage(StrEnum):
    """Pipeline stage that rejected a record."""

    NORMALIZATION = "normalization"
    VALIDATION = "validation"


class QualityCode(StrEnum):
    """D2-specific finding codes. D1 ErrorCode values are reused verbatim."""

    NON_CANONICAL_VALUE = "NON_CANONICAL_VALUE"
    DUPLICATE_SOURCE_RECORD = "DUPLICATE_SOURCE_RECORD"
    DUPLICATE_SOURCE_IDENTITY_CONFLICT = "DUPLICATE_SOURCE_IDENTITY_CONFLICT"
    MISSING_RECOMMENDED_FIELD = "MISSING_RECOMMENDED_FIELD"


class SystemFailureCode(StrEnum):
    """Stable codes carried by QualityGateSystemError."""

    UNSUPPORTED_SOURCE = "UNSUPPORTED_SOURCE"
    UNSUPPORTED_ENTITY = "UNSUPPORTED_ENTITY"
    NORMALIZATION_SYSTEM_FAILURE = "NORMALIZATION_SYSTEM_FAILURE"
    WRONG_ENTITY_SCHEMA = "WRONG_ENTITY_SCHEMA"
    PROVENANCE_MISMATCH = "PROVENANCE_MISMATCH"
    INVALID_PROVENANCE = "INVALID_PROVENANCE"
    E1_FIELD_POPULATED = "E1_FIELD_POPULATED"
    CANONICAL_ID_MISMATCH = "CANONICAL_ID_MISMATCH"
    RECORD_HASH_MISMATCH = "RECORD_HASH_MISMATCH"


# D1 codes describing bad source data: the record is quarantined.
DATA_FAILURE_CODES: frozenset[ErrorCode] = frozenset({
    ErrorCode.INVALID_RECORD,
    ErrorCode.SOURCE_ID_MISSING,
    ErrorCode.SOURCE_ID_INVALID,
    ErrorCode.RELATIONSHIP_KEY_INVALID,
    ErrorCode.REQUIRED_FIELD_MISSING,
    ErrorCode.INVALID_TYPE,
    ErrorCode.INVALID_BOOLEAN,
    ErrorCode.INVALID_DATE,
    ErrorCode.AMBIGUOUS_DATE,
    ErrorCode.INVALID_DATETIME,
    ErrorCode.AMBIGUOUS_DATETIME,
    ErrorCode.NAIVE_DATETIME_REJECTED,
    ErrorCode.INVALID_DECIMAL,
    ErrorCode.DECIMAL_SCALE_EXCEEDED,
    ErrorCode.DECIMAL_PRECISION_EXCEEDED,
    ErrorCode.DECIMAL_OUT_OF_RANGE,
    ErrorCode.UNKNOWN_ENUM_VALUE,
    ErrorCode.INVALID_CURRENCY,
    ErrorCode.SCHEMA_VALIDATION_FAILED,
})

# D1 codes describing caller, configuration, or programming faults: raise.
SYSTEM_FAILURE_CODES: frozenset[ErrorCode] = frozenset({
    ErrorCode.UNSUPPORTED_SOURCE,
    ErrorCode.UNSUPPORTED_ENTITY,
    ErrorCode.UNEXPECTED_ERROR,
})


def is_data_failure(error: NormalizationError) -> bool:
    """Return True only for D1 errors explicitly classified as bad data."""
    return isinstance(error, NormalizationError) and error.code in DATA_FAILURE_CODES


class QualityGateSystemError(Exception):
    """A system failure that must stop the quality gate operation."""

    def __init__(
        self,
        reason: str,
        *,
        code: SystemFailureCode,
        source_system: str | None = None,
        entity_type: str | None = None,
        source_id: str | None = None,
        record_index: int | None = None,
        field_name: str | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code
        self.source_system = source_system
        self.entity_type = entity_type
        self.source_id = source_id
        self.record_index = record_index
        self.field_name = field_name

    @property
    def message(self) -> str:
        location = "/".join(
            str(part)
            for part in (self.source_system, self.entity_type, self.source_id)
            if part is not None
        )
        header = f"[{self.code}]"
        if location:
            header = f"{header} {location}"
        if self.record_index is not None:
            header = f"{header} record #{self.record_index}"
        if self.field_name:
            header = f"{header} field '{self.field_name}'"
        return f"{header}: {self.reason}"

    def __str__(self) -> str:
        return self.message


class CanonicalInvariantError(QualityGateSystemError):
    """A pipeline-generated canonical invariant does not hold."""


class ValidationConfigError(Exception):
    """Raised when the quality gate configuration is missing or inconsistent."""
