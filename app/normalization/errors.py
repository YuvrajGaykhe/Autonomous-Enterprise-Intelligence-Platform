"""
Normalization exception hierarchy for Layer 1 (D1).

Every per-record failure raised by the D1 pipeline is a NormalizationError
carrying structured context, so D2/E1 can record a quarantine or ingestion
error without parsing message text (spec Section 13):

    code           stable machine-readable ErrorCode
    reason         human-readable explanation (without context)
    source_system  logical source name (e.g. csv_demo)
    entity_type    canonical entity type (e.g. customers)
    source_id      normalized source record identifier, when known
    field_name     canonical field involved, when applicable
    raw_value      offending source value, when applicable

Hierarchy:
    NormalizationError
        UnsupportedSourceError   source_system is not configured
        UnsupportedEntityError   entity is not mapped for the source
        InvalidRecordError       record is not a mapping
        IdentifierError          invalid or missing source ID / relationship key
        FieldMappingError        required canonical field is missing
        CoercionError            value cannot be normalized to its canonical type
        SchemaValidationError    canonical Pydantic schema rejected the record

NormalizationConfigError is deliberately NOT a NormalizationError: a broken
mapping configuration is a system fault, not a bad record, and must never be
quarantined as one.
"""

from __future__ import annotations

from enum import StrEnum

_MAX_VALUE_REPR = 80


class ErrorCode(StrEnum):
    """Stable machine-readable normalization error codes."""

    UNSUPPORTED_SOURCE = "UNSUPPORTED_SOURCE"
    UNSUPPORTED_ENTITY = "UNSUPPORTED_ENTITY"
    INVALID_RECORD = "INVALID_RECORD"
    SOURCE_ID_MISSING = "SOURCE_ID_MISSING"
    SOURCE_ID_INVALID = "SOURCE_ID_INVALID"
    RELATIONSHIP_KEY_INVALID = "RELATIONSHIP_KEY_INVALID"
    REQUIRED_FIELD_MISSING = "REQUIRED_FIELD_MISSING"
    INVALID_TYPE = "INVALID_TYPE"
    INVALID_BOOLEAN = "INVALID_BOOLEAN"
    INVALID_DATE = "INVALID_DATE"
    AMBIGUOUS_DATE = "AMBIGUOUS_DATE"
    INVALID_DATETIME = "INVALID_DATETIME"
    AMBIGUOUS_DATETIME = "AMBIGUOUS_DATETIME"
    NAIVE_DATETIME_REJECTED = "NAIVE_DATETIME_REJECTED"
    INVALID_DECIMAL = "INVALID_DECIMAL"
    DECIMAL_SCALE_EXCEEDED = "DECIMAL_SCALE_EXCEEDED"
    DECIMAL_PRECISION_EXCEEDED = "DECIMAL_PRECISION_EXCEEDED"
    DECIMAL_OUT_OF_RANGE = "DECIMAL_OUT_OF_RANGE"
    UNKNOWN_ENUM_VALUE = "UNKNOWN_ENUM_VALUE"
    INVALID_CURRENCY = "INVALID_CURRENCY"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


def describe_value(value: object) -> str:
    """Return a bounded repr of a source value for error messages."""
    text = repr(value)
    if len(text) <= _MAX_VALUE_REPR:
        return text
    return text[: _MAX_VALUE_REPR - 3] + "..."


class NormalizationError(Exception):
    """Base exception for all per-record normalization failures."""

    default_code: ErrorCode = ErrorCode.UNEXPECTED_ERROR

    def __init__(
        self,
        reason: str,
        *,
        code: ErrorCode | None = None,
        source_system: str | None = None,
        entity_type: str | None = None,
        source_id: str | None = None,
        field_name: str | None = None,
        raw_value: object = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code if code is not None else self.default_code
        self.source_system = source_system
        self.entity_type = entity_type
        self.source_id = source_id
        self.field_name = field_name
        self.raw_value = raw_value

    def with_context(
        self,
        *,
        source_system: str | None = None,
        entity_type: str | None = None,
        source_id: str | None = None,
        field_name: str | None = None,
    ) -> NormalizationError:
        """Fill context attributes that are still unknown. Never overwrites."""
        if self.source_system is None:
            self.source_system = source_system
        if self.entity_type is None:
            self.entity_type = entity_type
        if self.source_id is None:
            self.source_id = source_id
        if self.field_name is None:
            self.field_name = field_name
        return self

    @property
    def message(self) -> str:
        """Human-readable message including code and record context."""
        location = "/".join(
            str(part)
            for part in (self.source_system, self.entity_type, self.source_id)
            if part is not None
        )
        header = f"[{self.code}]"
        if location:
            header = f"{header} {location}"
        if self.field_name:
            header = f"{header} field '{self.field_name}'"
        return f"{header}: {self.reason}"

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, str | None]:
        """Structured representation for quarantine / ingestion_errors."""
        return {
            "code": str(self.code),
            "message": self.message,
            "source_system": self.source_system,
            "entity_type": self.entity_type,
            "source_id": self.source_id,
            "field_name": self.field_name,
        }


class UnsupportedSourceError(NormalizationError):
    """Raised when the source_system is not configured for normalization."""

    default_code = ErrorCode.UNSUPPORTED_SOURCE


class UnsupportedEntityError(NormalizationError):
    """Raised when the entity type is not mapped for the given source."""

    default_code = ErrorCode.UNSUPPORTED_ENTITY


class InvalidRecordError(NormalizationError):
    """Raised when a source record is not a mapping."""

    default_code = ErrorCode.INVALID_RECORD


class IdentifierError(NormalizationError):
    """Raised for a missing/invalid source ID or an invalid relationship key."""

    default_code = ErrorCode.SOURCE_ID_INVALID


class FieldMappingError(NormalizationError):
    """Raised when a required canonical field has no value."""

    default_code = ErrorCode.REQUIRED_FIELD_MISSING


class CoercionError(NormalizationError):
    """Raised when a value cannot be converted to its canonical type."""

    default_code = ErrorCode.INVALID_TYPE


class SchemaValidationError(NormalizationError):
    """Raised when the canonical Pydantic schema rejects the mapped record."""

    default_code = ErrorCode.SCHEMA_VALIDATION_FAILED


class NormalizationConfigError(Exception):
    """Raised when the normalization configuration is missing or inconsistent."""
