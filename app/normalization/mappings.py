"""
Source-record field mapping for D1 normalization.

Applies a source's EntityMapping (from the centralized configuration in
config/mappings/) to one source-native record:

    - extracts and normalizes the source identity
    - extracts the per-record source_updated_at, where the source has one
    - produces every canonical business field, including enum, currency,
      decimal, date/time, boolean, and relationship-key normalization

No source field names or source-specific rules live in this module; they
come from configuration. Canonical FK fields resolved by E1 (customer_id,
organization_id) are never produced here.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from app.normalization.coercion import (
    coerce_boolean,
    coerce_currency,
    coerce_date,
    coerce_datetime,
    coerce_decimal,
    coerce_email,
    coerce_enum,
    coerce_string,
    coerce_text,
    normalize_identifier,
)
from app.normalization.config import (
    BooleanToEnum,
    EntityMapping,
    EnumMembership,
    FieldRule,
    FieldSpec,
    NormalizationConfig,
    SourceProfile,
)
from app.normalization.errors import (
    ErrorCode,
    FieldMappingError,
    IdentifierError,
    NormalizationError,
)


def extract_source_id(
    profile: SourceProfile,
    mapping: EntityMapping,
    record: Mapping[str, object],
) -> str:
    """Return the normalized source identifier of a record."""
    field = mapping.source_id_field
    try:
        source_id = normalize_identifier(
            record.get(field),
            identifier_type=profile.identifier_type,
            invalid_code=ErrorCode.SOURCE_ID_INVALID,
        )
    except NormalizationError as exc:
        raise exc.with_context(field_name="source_id") from None
    if source_id is None:
        state = "absent" if field not in record else "empty"
        raise IdentifierError(
            f"source ID field '{field}' is {state}",
            code=ErrorCode.SOURCE_ID_MISSING,
            field_name="source_id",
            raw_value=record.get(field),
        )
    return source_id


def map_record(
    config: NormalizationConfig,
    profile: SourceProfile,
    mapping: EntityMapping,
    record: Mapping[str, object],
) -> tuple[datetime | None, dict[str, object]]:
    """Produce (source_updated_at, canonical business fields) for a record."""
    specs = config.fields[mapping.entity_type]
    values: dict[str, object] = {}
    for name, rule in mapping.rules.items():
        spec = specs[name]
        try:
            value = _apply_rule(config, profile, mapping.entity_type, spec, rule, record)
        except NormalizationError as exc:
            raise exc.with_context(field_name=name) from None
        if value is None and spec.required:
            state = ("absent from the source record" if rule.source_field not in record
                     else "empty or a null token")
            raise FieldMappingError(
                f"required field has no value: source field '{rule.source_field}' is {state}",
                code=ErrorCode.REQUIRED_FIELD_MISSING,
                field_name=name,
                raw_value=record.get(rule.source_field),
            )
        values[name] = value

    source_updated_at = None
    if mapping.source_updated_at_field is not None:
        try:
            source_updated_at = coerce_datetime(
                record.get(mapping.source_updated_at_field),
                null_tokens=profile.null_tokens,
                formats=profile.datetime_formats,
                naive_timezone=profile.naive_timezone,
            )
        except NormalizationError as exc:
            raise exc.with_context(field_name="source_updated_at") from None
    return source_updated_at, values


def _apply_rule(
    config: NormalizationConfig,
    profile: SourceProfile,
    entity_type: str,
    spec: FieldSpec,
    rule: FieldRule,
    record: Mapping[str, object],
) -> object:
    raw = record.get(rule.source_field)
    derivation = rule.derivation
    if isinstance(derivation, EnumMembership):
        enum_spec = config.fields[entity_type][derivation.enum_field]
        token = coerce_enum(
            raw,
            null_tokens=profile.null_tokens,
            allowed=enum_spec.enum_values,
            aliases=profile.aliases_for(entity_type, derivation.enum_field),
        )
        return None if token is None else token in derivation.true_values
    if isinstance(derivation, BooleanToEnum):
        flag = coerce_boolean(
            raw,
            null_tokens=profile.null_tokens,
            true_tokens=config.true_tokens,
            false_tokens=config.false_tokens,
        )
        if flag is None:
            return None
        return derivation.true_value if flag else derivation.false_value
    return _coerce(config, profile, entity_type, spec, raw)


def _coerce(
    config: NormalizationConfig,
    profile: SourceProfile,
    entity_type: str,
    spec: FieldSpec,
    raw: object,
) -> object:
    kind = spec.kind
    if kind == "string":
        return coerce_string(raw, null_tokens=profile.null_tokens)
    if kind == "text":
        return coerce_text(raw)
    if kind == "email":
        return coerce_email(raw, null_tokens=profile.null_tokens)
    if kind == "enum":
        return coerce_enum(
            raw,
            null_tokens=profile.null_tokens,
            allowed=spec.enum_values,
            aliases=profile.aliases_for(entity_type, spec.name),
        )
    if kind == "boolean":
        return coerce_boolean(
            raw,
            null_tokens=profile.null_tokens,
            true_tokens=config.true_tokens,
            false_tokens=config.false_tokens,
        )
    if kind == "decimal":
        return coerce_decimal(
            raw,
            null_tokens=profile.null_tokens,
            precision=spec.precision,
            scale=spec.scale,
            minimum=spec.minimum,
            maximum=spec.maximum,
            decimal_separator=profile.decimal_separator,
            thousands_separator=profile.thousands_separator,
        )
    if kind == "currency":
        return coerce_currency(
            raw,
            null_tokens=profile.null_tokens,
            codes=config.currency_codes,
            aliases=config.currency_aliases,
        )
    if kind == "date":
        return coerce_date(raw, null_tokens=profile.null_tokens, formats=profile.date_formats)
    if kind == "datetime":
        return coerce_datetime(
            raw,
            null_tokens=profile.null_tokens,
            formats=profile.datetime_formats,
            naive_timezone=profile.naive_timezone,
        )
    if kind == "source_key":
        return normalize_identifier(
            raw,
            identifier_type=profile.identifier_type,
            invalid_code=ErrorCode.RELATIONSHIP_KEY_INVALID,
        )
    raise AssertionError(f"unhandled field kind {kind!r}")
