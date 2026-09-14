"""
Canonical validation rules for D2.

Rule groups run on every canonical record in this order:

1. check_invariants (SYSTEM). Facts the pipeline itself generates must hold:
   the schema matches the batch entity; source_system, source_entity and
   ingestion_run_id match the batch; ingested_at is UTC; id and record_hash
   are well formed; E1-resolved FK fields are still unset. A violation raises
   CanonicalInvariantError.

2. check_canonical_record (DATA). Every source-derived value (source_id,
   source_updated_at, business fields) satisfies the canonical contract owned
   by D1 in config/mappings/: strict schema types, required values, enum and
   currency vocabularies, decimal precision/scale/range and canonical scale,
   UTC datetimes, and identifier form. Violations are returned; the record is
   quarantined.

3. check_identity (SYSTEM). For records without data violations, id and
   record_hash must equal the values derived from the record's content.

Warning rules never reject a record.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TypedDict, TypeVar

from pydantic import ValidationError

from app.normalization import ErrorCode, NormalizationConfig, canonical_id, record_hash
from app.normalization.config import FieldSpec, SourceProfile
from app.normalization.contract import (
    BUSINESS_FIELDS,
    CANONICAL_SCHEMAS,
    E1_RESOLVED_FIELDS,
    is_required,
)
from app.schemas.canonical import CanonicalBase
from app.validation.config import WarningPolicy
from app.validation.errors import CanonicalInvariantError, QualityCode, SystemFailureCode
from app.validation.quarantine import Violation

SOURCE_DERIVED_PROVENANCE = ("source_id", "source_updated_at")

_MISSING = object()
_INTEGER_IDENTIFIER = re.compile(r"[1-9][0-9]*")
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
_UTC_OFFSET = timedelta(0)
_T = TypeVar("_T")


class _InvariantContext(TypedDict):
    """Record location carried by every CanonicalInvariantError."""

    source_system: str
    entity_type: str
    record_index: int


class _IdentityContext(_InvariantContext):
    """Record location plus the source identity of a schema-valid record."""

    source_id: str


def canonical_values(record: CanonicalBase) -> dict[str, object]:
    """Return the record's declared field values without triggering validation."""
    fields = type(record).model_fields
    return {name: value for name, value in vars(record).items() if name in fields}


def record_source_id(record: object) -> str | None:
    """Return a usable source_id for diagnostics, or None."""
    value = getattr(record, "__dict__", {}).get("source_id")
    return value if isinstance(value, str) and value.strip() else None


# ---------------------------------------------------------------------------
# 1. Pipeline invariants (SYSTEM)
# ---------------------------------------------------------------------------


def check_invariants(
    record: object,
    *,
    source_system: str,
    entity_type: str,
    ingestion_run_id: uuid.UUID,
    record_index: int,
) -> None:
    """Raise CanonicalInvariantError if a pipeline-generated invariant is broken."""
    schema = CANONICAL_SCHEMAS[entity_type]
    context: _InvariantContext = {"source_system": source_system, "entity_type": entity_type,
                                  "record_index": record_index}
    if type(record) is not schema:
        raise CanonicalInvariantError(
            f"expected a {schema.__name__}, got {type(record).__name__}",
            code=SystemFailureCode.WRONG_ENTITY_SCHEMA, **context,
        )
    values = canonical_values(record)
    source_id = record_source_id(record)

    def violation(code: SystemFailureCode, field: str, reason: str) -> CanonicalInvariantError:
        return CanonicalInvariantError(reason, code=code, source_id=source_id,
                                       field_name=field, **context)

    if values.get("source_system") != source_system:
        raise violation(SystemFailureCode.PROVENANCE_MISMATCH, "source_system",
                        "record source_system does not match the batch source_system")
    if values.get("source_entity") != entity_type:
        raise violation(SystemFailureCode.PROVENANCE_MISMATCH, "source_entity",
                        "record source_entity does not match the batch entity type")
    if values.get("ingestion_run_id") != ingestion_run_id:
        raise violation(SystemFailureCode.PROVENANCE_MISMATCH, "ingestion_run_id",
                        "record does not belong to this ingestion run")
    ingested_at = values.get("ingested_at")
    if not isinstance(ingested_at, datetime) or ingested_at.utcoffset() != _UTC_OFFSET:
        raise violation(SystemFailureCode.INVALID_PROVENANCE, "ingested_at",
                        "ingested_at must be a timezone-aware UTC datetime")
    if not isinstance(values.get("id"), uuid.UUID):
        raise violation(SystemFailureCode.INVALID_PROVENANCE, "id", "id must be a UUID")
    hash_value = values.get("record_hash")
    if not isinstance(hash_value, str) or not _SHA256_HEX.fullmatch(hash_value):
        raise violation(SystemFailureCode.INVALID_PROVENANCE, "record_hash",
                        "record_hash must be a lowercase hex SHA-256 digest")
    for field in sorted(E1_RESOLVED_FIELDS[entity_type]):
        if values.get(field) is not None:
            raise violation(SystemFailureCode.E1_FIELD_POPULATED, field,
                            "canonical FK is resolved by E1 and must be unset before E1")


# ---------------------------------------------------------------------------
# 2. Canonical data contract (DATA)
# ---------------------------------------------------------------------------


def check_canonical_record(
    record: CanonicalBase,
    *,
    entity_type: str,
    profile: SourceProfile,
    config: NormalizationConfig,
    record_index: int,
) -> list[Violation]:
    """Return data-contract violations in canonical field order (empty if valid)."""
    schema = CANONICAL_SCHEMAS[entity_type]
    values = canonical_values(record)
    checked = (*SOURCE_DERIVED_PROVENANCE, *BUSINESS_FIELDS[entity_type])

    # First pydantic error type per field; the type is all the classification uses.
    schema_errors: dict[str, str] = {}
    try:
        schema.model_validate(values, strict=True)
    except ValidationError as exc:
        for error in exc.errors(include_url=False):
            field = str(error["loc"][0]) if error["loc"] else ""
            schema_errors.setdefault(field, error["type"])
    unexpected = sorted(set(schema_errors) - set(checked))
    if unexpected:
        raise CanonicalInvariantError(
            f"canonical schema rejected pipeline-generated fields {unexpected}",
            code=SystemFailureCode.INVALID_PROVENANCE, source_system=profile.name,
            entity_type=entity_type, source_id=record_source_id(record),
            record_index=record_index,
        )

    violations = []
    for field in checked:
        value = values.get(field, _MISSING)
        if field in schema_errors:
            code, reason = _schema_violation(entity_type, field, value, schema_errors[field],
                                             config)
        else:
            found = _contract_violation(entity_type, field, value, profile, config)
            if found is None:
                continue
            code, reason = found
        violations.append(Violation(field, str(code), reason,
                                    None if value is _MISSING else value))
    return violations


def _kind(entity_type: str, field: str, config: NormalizationConfig) -> str:
    if field == "source_id":
        return "source_id"
    if field == "source_updated_at":
        return "datetime"
    return config.fields[entity_type][field].kind


def _schema_violation(
    entity_type: str,
    field: str,
    value: object,
    error_type: str,
    config: NormalizationConfig,
) -> tuple[str, str]:
    kind = _kind(entity_type, field, config)
    if value is _MISSING or value is None:
        if kind == "source_id":
            return ErrorCode.SOURCE_ID_MISSING, "source_id has no value"
        if is_required(entity_type, field):
            return ErrorCode.REQUIRED_FIELD_MISSING, "required canonical field has no value"
    if error_type == "finite_number":
        return ErrorCode.INVALID_DECIMAL, "decimal value must be finite"
    if error_type == "is_instance_of" or error_type.endswith("_type"):
        if kind == "source_id":
            return ErrorCode.SOURCE_ID_INVALID, "source_id must be a string"
        if kind == "source_key":
            return ErrorCode.RELATIONSHIP_KEY_INVALID, "relationship key must be a string"
        return ErrorCode.INVALID_TYPE, (
            f"value of type {type(value).__name__} is not the canonical type for this field"
        )
    return ErrorCode.SCHEMA_VALIDATION_FAILED, f"canonical schema rejected the value ({error_type})"


def _validated(value: object, expected: type[_T]) -> _T:
    """Narrow a value that strict schema validation has already accepted.

    _contract_violation only sees fields the strict schema accepted, and the
    canonical schemas declare exactly this Python type for each contract kind,
    so a mismatch is a programming fault and fails loudly.
    """
    if not isinstance(value, expected):
        raise TypeError(
            f"strict schema accepted {type(value).__name__}; expected {expected.__name__}"
        )
    return value


def _contract_violation(
    entity_type: str,
    field: str,
    value: object,
    profile: SourceProfile,
    config: NormalizationConfig,
) -> tuple[str, str] | None:
    if value is _MISSING or value is None:
        return None
    if field == "source_id":
        return _identifier_violation(_validated(value, str), profile.identifier_type,
                                     ErrorCode.SOURCE_ID_MISSING, ErrorCode.SOURCE_ID_INVALID)
    if field == "source_updated_at":
        return _datetime_violation(_validated(value, datetime))

    spec = config.fields[entity_type][field]
    kind = spec.kind
    if kind in ("string", "email"):
        value = _validated(value, str)
        if not value.strip():
            code = ErrorCode.REQUIRED_FIELD_MISSING if spec.required else QualityCode.NON_CANONICAL_VALUE
            return code, "blank string; canonical missing values are null"
        if value != value.strip():
            return QualityCode.NON_CANONICAL_VALUE, "string has surrounding whitespace"
        if kind == "email" and value != value.lower():
            return QualityCode.NON_CANONICAL_VALUE, "email is not lowercase"
        return None
    if kind == "text":
        value = _validated(value, str)
        if value.strip():
            return None
        return QualityCode.NON_CANONICAL_VALUE, "blank text; canonical missing values are null"
    if kind == "enum":
        if value in spec.enum_values:
            return None
        return ErrorCode.UNKNOWN_ENUM_VALUE, (
            f"not a canonical value; expected one of {sorted(spec.enum_values)}"
        )
    if kind == "currency":
        if value in config.currency_codes:
            return None
        return ErrorCode.INVALID_CURRENCY, "not a configured ISO 4217 currency code"
    if kind == "source_key":
        return _identifier_violation(_validated(value, str), profile.identifier_type,
                                     ErrorCode.RELATIONSHIP_KEY_INVALID,
                                     ErrorCode.RELATIONSHIP_KEY_INVALID)
    if kind == "decimal":
        return _decimal_violation(_validated(value, Decimal), spec)
    if kind == "datetime":
        return _datetime_violation(_validated(value, datetime))
    # boolean and date are fully enforced by the strict schema.
    return None


def _identifier_violation(value: str, identifier_type: str, blank_code: ErrorCode,
                          invalid_code: ErrorCode) -> tuple[str, str] | None:
    if not value.strip():
        return blank_code, "identifier is blank"
    if value != value.strip():
        return invalid_code, "identifier has surrounding whitespace"
    if identifier_type == "integer" and not _INTEGER_IDENTIFIER.fullmatch(value):
        return invalid_code, "identifier is not a canonical positive integer"
    return None


def _decimal_violation(value: Decimal, spec: FieldSpec) -> tuple[str, str] | None:
    if spec.precision is None or spec.scale is None:
        # D1 configuration loading requires integer precision and scale for decimal fields.
        raise TypeError(f"decimal field {spec.name!r} has no configured precision/scale")
    if _significant_fractional_digits(value) > spec.scale:
        return ErrorCode.DECIMAL_SCALE_EXCEEDED, (
            f"more than {spec.scale} significant fractional digits"
        )
    if abs(value) >= Decimal(1).scaleb(spec.precision - spec.scale):
        return ErrorCode.DECIMAL_PRECISION_EXCEEDED, (
            f"exceeds canonical precision ({spec.precision}, {spec.scale})"
        )
    if (spec.minimum is not None and value < spec.minimum) or (
        spec.maximum is not None and value > spec.maximum
    ):
        return ErrorCode.DECIMAL_OUT_OF_RANGE, (
            f"outside the canonical range [{spec.minimum}, {spec.maximum}]"
        )
    if value.as_tuple().exponent != -spec.scale or (value.is_zero() and value.is_signed()):
        return QualityCode.NON_CANONICAL_VALUE, (
            f"decimal is not quantized to {spec.scale} fractional digits"
        )
    return None


def _significant_fractional_digits(number: Decimal) -> int:
    if number.is_zero():
        return 0
    _, digits, exponent = number.as_tuple()
    if not isinstance(exponent, int):
        # NaN/Infinity have a string exponent; the strict schema rejects them earlier.
        raise TypeError("non-finite decimal has no fractional digits")
    coefficient = "".join(str(digit) for digit in digits)
    trailing_zeros = len(coefficient) - len(coefficient.rstrip("0"))
    return max(0, -(exponent + trailing_zeros))


def _datetime_violation(value: datetime) -> tuple[str, str] | None:
    offset = value.utcoffset()
    if offset is None:
        return ErrorCode.NAIVE_DATETIME_REJECTED, "datetime has no UTC offset"
    if offset != _UTC_OFFSET:
        return QualityCode.NON_CANONICAL_VALUE, "datetime is not normalized to UTC"
    return None


# ---------------------------------------------------------------------------
# 3. Content-derived identity (SYSTEM)
# ---------------------------------------------------------------------------


def check_identity(
    record: CanonicalBase,
    *,
    source_system: str,
    entity_type: str,
    record_index: int,
) -> None:
    """Raise if id or record_hash does not match the record's own content."""
    context: _IdentityContext = {"source_system": source_system, "entity_type": entity_type,
                                 "source_id": record.source_id, "record_index": record_index}
    if record.id != canonical_id(source_system, entity_type, record.source_id):
        raise CanonicalInvariantError(
            "id is not the canonical UUID of the record's source identity",
            code=SystemFailureCode.CANONICAL_ID_MISMATCH, field_name="id", **context,
        )
    if record.record_hash != record_hash(record):
        raise CanonicalInvariantError(
            "record_hash does not match the record's canonical business content",
            code=SystemFailureCode.RECORD_HASH_MISMATCH, field_name="record_hash", **context,
        )


# ---------------------------------------------------------------------------
# Warning rules
# ---------------------------------------------------------------------------


def warning_violations(
    accepted: list[tuple[int, CanonicalBase]],
    *,
    entity_type: str,
    policy: WarningPolicy,
) -> list[tuple[int, CanonicalBase, Violation]]:
    """Return WARNING violations for accepted records, in record order."""
    warnings = []
    first_seen: dict[str, tuple[int, str]] = {}
    recommended = policy.recommended_fields.get(entity_type, ())
    for index, record in accepted:
        for field in recommended:
            if getattr(record, field) is None:
                warnings.append((index, record, Violation(
                    field, QualityCode.MISSING_RECOMMENDED_FIELD,
                    "recommended field has no value; the record remains usable",
                )))
        if not policy.duplicate_source_identity:
            continue
        previous = first_seen.get(record.source_id)
        if previous is None:
            first_seen[record.source_id] = (index, record.record_hash)
            continue
        if previous[1] == record.record_hash:
            code = QualityCode.DUPLICATE_SOURCE_RECORD
            reason = f"duplicate of record #{previous[0]} with identical business content"
        else:
            code = QualityCode.DUPLICATE_SOURCE_IDENTITY_CONFLICT
            reason = f"same source identity as record #{previous[0]} with different business content"
        warnings.append((index, record, Violation("source_id", code, reason)))
    return warnings
