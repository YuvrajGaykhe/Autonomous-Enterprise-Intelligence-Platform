"""
Centralized configuration for D1 normalization.

Layout (config/mappings/, spec Section 11):

    normalization.yaml  Source-independent canonical rules: the source-system
                        vocabulary, null tokens, boolean tokens, ISO 4217
                        currency codes, and the canonical kind of every
                        business field (enum values, decimal precision/scale).
    <source>.yaml       One file per source system: identifier type, date and
                        datetime formats, naive-datetime policy, decimal
                        separators, enum aliases, and per-entity mappings.
                        "columns" maps source field -> canonical field(s)
                        (the spec Section 12 shape); "derived" declares
                        explicit derivations between representations.

The loader validates everything against the B2 canonical schemas and raises
NormalizationConfigError on any inconsistency, so an invalid mapping can
never silently produce incomplete canonical records.

Purity: load_config reads only the committed files in the given directory,
never environment variables or the working directory. The resulting
NormalizationConfig is deeply immutable. default_config() memoizes the one
repository configuration; normalize() also accepts an explicit config.
"""

from __future__ import annotations

import functools
import re
import typing
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType

import yaml

from app.normalization.coercion import IDENTIFIER_TYPES, normalize_enum_token
from app.normalization.contract import (
    BUSINESS_FIELDS,
    CANONICAL_SCHEMAS,
    E1_RESOLVED_FIELDS,
    PROVENANCE_FIELDS,
    is_required,
)
from app.normalization.errors import NormalizationConfigError

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config" / "mappings"
GLOBAL_CONFIG_FILE = "normalization.yaml"

_KIND_TYPES: Mapping[str, type] = MappingProxyType({
    "string": str,
    "text": str,
    "email": str,
    "enum": str,
    "currency": str,
    "source_key": str,
    "boolean": bool,
    "decimal": Decimal,
    "date": date,
    "datetime": datetime,
})
FIELD_KINDS = frozenset(_KIND_TYPES)

_SOURCE_NAME = re.compile(r"[a-z][a-z0-9_]*")
_CURRENCY_CODE = re.compile(r"[A-Z]{3}")
_OFFSET = re.compile(r"([+-])(\d{2}):(\d{2})")
_DIRECTIVE = re.compile(r"%.")
_DATETIME_DIRECTIVES = frozenset({"%Y", "%m", "%d", "%H", "%M", "%S", "%f", "%z", "%%"})
_DATE_DIRECTIVES = frozenset({"%Y", "%m", "%d", "%%"})
_DECIMAL_SEPARATORS = frozenset({".", ","})
_THOUSANDS_SEPARATORS = frozenset({",", ".", " ", "'"})
_EMPTY: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True)
class FieldSpec:
    """Canonical normalization rule for one business field."""

    name: str
    kind: str
    required: bool
    enum_values: frozenset[str] = frozenset()
    precision: int | None = None
    scale: int | None = None
    minimum: Decimal | None = None
    maximum: Decimal | None = None


@dataclass(frozen=True)
class EnumMembership:
    """Derive a boolean from the canonical enum value of a source field."""

    enum_field: str
    true_values: frozenset[str]
    false_values: frozenset[str]


@dataclass(frozen=True)
class BooleanToEnum:
    """Derive a canonical enum value from a source boolean."""

    true_value: str
    false_value: str


@dataclass(frozen=True)
class FieldRule:
    """How one canonical field is produced from a source record."""

    target: str
    source_field: str
    derivation: EnumMembership | BooleanToEnum | None = None


@dataclass(frozen=True)
class EntityMapping:
    """Mapping of one source entity to one canonical entity."""

    entity_type: str
    source_id_field: str
    source_updated_at_field: str | None
    rules: Mapping[str, FieldRule]


@dataclass(frozen=True)
class SourceProfile:
    """Normalization rules for one source system."""

    name: str
    identifier_type: str
    naive_timezone: tzinfo | None
    date_formats: tuple[str, ...]
    datetime_formats: tuple[str, ...]
    decimal_separator: str
    thousands_separator: str | None
    null_tokens: frozenset[str]
    enum_aliases: Mapping[str, Mapping[str, str]]
    entities: Mapping[str, EntityMapping]

    def aliases_for(self, entity_type: str, field_name: str) -> Mapping[str, str]:
        """Return enum aliases configured for a canonical field."""
        return self.enum_aliases.get(f"{entity_type}.{field_name}", _EMPTY)


@dataclass(frozen=True)
class NormalizationConfig:
    """Complete, validated, immutable D1 normalization configuration."""

    source_systems: tuple[str, ...]
    fields: Mapping[str, Mapping[str, FieldSpec]]
    true_tokens: frozenset[str]
    false_tokens: frozenset[str]
    currency_codes: frozenset[str]
    currency_aliases: Mapping[str, str]
    sources: Mapping[str, SourceProfile]


@functools.lru_cache(maxsize=1)
def default_config() -> NormalizationConfig:
    """Load (once) the repository configuration from config/mappings/."""
    return load_config(DEFAULT_CONFIG_DIR)


def load_config(directory: str | Path) -> NormalizationConfig:
    """Load and validate the normalization configuration from a directory."""
    directory = Path(directory)
    path = directory / GLOBAL_CONFIG_FILE
    data = _read_yaml(path)
    where = str(path)
    _check_keys(
        data,
        where,
        required={"version", "source_systems", "null_tokens", "boolean_tokens", "currency",
                  "canonical_fields"},
    )
    if data["version"] != 1:
        raise NormalizationConfigError(f"{where}: unsupported version {data['version']!r}")

    source_systems = tuple(_string_list(data["source_systems"], f"{where}: source_systems"))
    for name in source_systems:
        if not _SOURCE_NAME.fullmatch(name):
            raise NormalizationConfigError(f"{where}: invalid source system name {name!r}")

    null_tokens = _token_set(data["null_tokens"], f"{where}: null_tokens", allow_empty=True)

    booleans = data["boolean_tokens"]
    _check_keys(booleans, f"{where}: boolean_tokens", required={"true_values", "false_values"})
    true_tokens = _token_set(booleans["true_values"], f"{where}: boolean_tokens.true_values")
    false_tokens = _token_set(booleans["false_values"], f"{where}: boolean_tokens.false_values")
    if true_tokens & false_tokens:
        raise NormalizationConfigError(
            f"{where}: boolean tokens are both true and false: {sorted(true_tokens & false_tokens)}"
        )
    _check_disjoint_from_booleans(null_tokens, true_tokens, false_tokens, f"{where}: null_tokens")

    currency = data["currency"]
    _check_keys(currency, f"{where}: currency", required={"codes"}, optional={"aliases"})
    codes = _string_list(currency["codes"], f"{where}: currency.codes")
    for code in codes:
        if not _CURRENCY_CODE.fullmatch(code):
            raise NormalizationConfigError(f"{where}: invalid ISO 4217 code {code!r}")
    currency_codes = frozenset(codes)
    currency_aliases = {}
    for alias, code in _mapping(currency.get("aliases") or {}, f"{where}: currency.aliases").items():
        if not isinstance(alias, str) or not alias.strip() or code not in currency_codes:
            raise NormalizationConfigError(
                f"{where}: currency alias {alias!r} must map to a configured code, got {code!r}"
            )
        currency_aliases[alias.strip()] = code

    fields = _parse_canonical_fields(data["canonical_fields"], where)
    sources = {
        name: _load_source(directory, name, fields, null_tokens, true_tokens, false_tokens)
        for name in source_systems
    }
    return NormalizationConfig(
        source_systems=source_systems,
        fields=fields,
        true_tokens=true_tokens,
        false_tokens=false_tokens,
        currency_codes=currency_codes,
        currency_aliases=MappingProxyType(currency_aliases),
        sources=MappingProxyType(sources),
    )


# ---------------------------------------------------------------------------
# Canonical field specifications
# ---------------------------------------------------------------------------


def _parse_canonical_fields(
    raw: object, where: str
) -> Mapping[str, Mapping[str, FieldSpec]]:
    entities = _mapping(raw, f"{where}: canonical_fields")
    _check_exact(set(entities), set(CANONICAL_SCHEMAS), f"{where}: canonical_fields entities")
    result = {}
    for entity_type in CANONICAL_SCHEMAS:
        loc = f"{where}: canonical_fields.{entity_type}"
        entity_raw = _mapping(entities[entity_type], loc)
        _check_exact(set(entity_raw), set(BUSINESS_FIELDS[entity_type]), f"{loc} fields")
        result[entity_type] = MappingProxyType({
            name: _parse_field_spec(entity_type, name, entity_raw[name], f"{loc}.{name}")
            for name in BUSINESS_FIELDS[entity_type]
        })
    return MappingProxyType(result)


def _parse_field_spec(entity_type: str, name: str, raw: object, loc: str) -> FieldSpec:
    spec = _mapping(raw, loc)
    kind = spec.get("kind")
    if kind not in FIELD_KINDS:
        raise NormalizationConfigError(f"{loc}: unknown kind {kind!r}")
    optional = {"values"} if kind == "enum" else set()
    if kind == "decimal":
        optional = {"precision", "scale", "min", "max"}
    _check_keys(spec, loc, required={"kind"}, optional=optional)

    annotation = CANONICAL_SCHEMAS[entity_type].model_fields[name].annotation
    declared = {arg for arg in typing.get_args(annotation) if arg is not type(None)}
    if (declared or {annotation}) != {_KIND_TYPES[kind]}:
        raise NormalizationConfigError(
            f"{loc}: kind {kind!r} does not match canonical annotation {annotation}"
        )

    required = is_required(entity_type, name)
    if kind == "enum":
        values = _string_list(spec.get("values"), f"{loc}.values")
        for value in values:
            if normalize_enum_token(value) != value:
                raise NormalizationConfigError(
                    f"{loc}: enum value {value!r} is not in canonical form "
                    f"{normalize_enum_token(value)!r}"
                )
        return FieldSpec(name, kind, required, enum_values=frozenset(values))
    if kind == "decimal":
        precision = spec.get("precision")
        scale = spec.get("scale")
        if (
            not isinstance(precision, int) or isinstance(precision, bool)
            or not isinstance(scale, int) or isinstance(scale, bool)
            or not 0 <= scale < precision <= 28
        ):
            raise NormalizationConfigError(
                f"{loc}: decimal requires integer precision/scale with 0 <= scale < precision <= 28"
            )
        minimum = _optional_decimal(spec.get("min"), f"{loc}.min")
        maximum = _optional_decimal(spec.get("max"), f"{loc}.max")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise NormalizationConfigError(f"{loc}: min is greater than max")
        return FieldSpec(name, kind, required, precision=precision, scale=scale,
                         minimum=minimum, maximum=maximum)
    return FieldSpec(name, kind, required)


# ---------------------------------------------------------------------------
# Source profiles
# ---------------------------------------------------------------------------


def _load_source(
    directory: Path,
    name: str,
    fields: Mapping[str, Mapping[str, FieldSpec]],
    default_null_tokens: frozenset[str],
    true_tokens: frozenset[str],
    false_tokens: frozenset[str],
) -> SourceProfile:
    path = directory / f"{name}.yaml"
    data = _read_yaml(path)
    where = str(path)
    _check_keys(
        data,
        where,
        required={"source", "identifier_type", "naive_datetime_timezone", "date_formats",
                  "datetime_formats", "decimal", "entities"},
        optional={"null_tokens", "enum_aliases"},
    )
    if data["source"] != name:
        raise NormalizationConfigError(f"{where}: 'source' must be {name!r}, got {data['source']!r}")
    identifier_type = data["identifier_type"]
    if identifier_type not in IDENTIFIER_TYPES:
        raise NormalizationConfigError(
            f"{where}: identifier_type must be one of {sorted(IDENTIFIER_TYPES)}"
        )

    decimal_cfg = _mapping(data["decimal"], f"{where}: decimal")
    _check_keys(decimal_cfg, f"{where}: decimal",
                required={"decimal_separator", "thousands_separator"})
    decimal_separator = decimal_cfg["decimal_separator"]
    thousands_separator = decimal_cfg["thousands_separator"]
    if decimal_separator not in _DECIMAL_SEPARATORS or (
        thousands_separator is not None
        and (thousands_separator not in _THOUSANDS_SEPARATORS
             or thousands_separator == decimal_separator)
    ):
        raise NormalizationConfigError(f"{where}: invalid decimal/thousands separators")

    null_tokens = default_null_tokens
    if "null_tokens" in data:
        null_tokens = _token_set(data["null_tokens"], f"{where}: null_tokens", allow_empty=True)
        _check_disjoint_from_booleans(null_tokens, true_tokens, false_tokens,
                                      f"{where}: null_tokens")

    entities_raw = _mapping(data["entities"], f"{where}: entities")
    unknown = set(entities_raw) - set(CANONICAL_SCHEMAS)
    if unknown or not entities_raw:
        raise NormalizationConfigError(
            f"{where}: entities must be a non-empty subset of canonical entities; "
            f"unknown: {sorted(unknown)}"
        )
    entities = {
        entity_type: _parse_entity(entity_type, entities_raw[entity_type],
                                   fields[entity_type], f"{where}: entities.{entity_type}")
        for entity_type in CANONICAL_SCHEMAS
        if entity_type in entities_raw
    }

    return SourceProfile(
        name=name,
        identifier_type=identifier_type,
        naive_timezone=_parse_timezone(data["naive_datetime_timezone"], where),
        date_formats=_formats(data["date_formats"], _DATE_DIRECTIVES, f"{where}: date_formats"),
        datetime_formats=_formats(data["datetime_formats"], _DATETIME_DIRECTIVES,
                                  f"{where}: datetime_formats"),
        decimal_separator=decimal_separator,
        thousands_separator=thousands_separator,
        null_tokens=null_tokens,
        enum_aliases=_parse_enum_aliases(data.get("enum_aliases") or {}, fields,
                                         f"{where}: enum_aliases"),
        entities=MappingProxyType(entities),
    )


def _parse_entity(
    entity_type: str,
    raw: object,
    specs: Mapping[str, FieldSpec],
    loc: str,
) -> EntityMapping:
    entity = _mapping(raw, loc)
    _check_keys(entity, loc, required={"columns"}, optional={"derived"})
    seen: set[str] = set()
    source_id_field: str | None = None
    updated_field: str | None = None
    rules: dict[str, FieldRule] = {}

    def claim(target: str) -> None:
        if target in seen:
            raise NormalizationConfigError(f"{loc}: canonical target {target!r} is mapped twice")
        seen.add(target)
        if target in E1_RESOLVED_FIELDS[entity_type]:
            raise NormalizationConfigError(
                f"{loc}: {target!r} is a canonical FK resolved by E1 and cannot be mapped by D1"
            )
        if target in PROVENANCE_FIELDS and target not in {"source_id", "source_updated_at"}:
            raise NormalizationConfigError(
                f"{loc}: provenance field {target!r} is generated by the pipeline"
            )
        if target not in specs and target not in {"source_id", "source_updated_at"}:
            raise NormalizationConfigError(f"{loc}: unknown canonical field {target!r}")

    for source_field, targets in _mapping(entity["columns"], f"{loc}.columns").items():
        if not isinstance(source_field, str) or not source_field:
            raise NormalizationConfigError(f"{loc}.columns: invalid source field {source_field!r}")
        target_list = [targets] if isinstance(targets, str) else targets
        for target in _string_list(target_list, f"{loc}.columns.{source_field}"):
            claim(target)
            if target == "source_id":
                source_id_field = source_field
            elif target == "source_updated_at":
                updated_field = source_field
            else:
                rules[target] = FieldRule(target, source_field)

    for target, rule_raw in _mapping(entity.get("derived") or {}, f"{loc}.derived").items():
        rule_loc = f"{loc}.derived.{target}"
        claim(target)
        if target not in specs:
            raise NormalizationConfigError(f"{rule_loc}: only business fields can be derived")
        rules[target] = _parse_derivation(target, rule_raw, specs, rule_loc)

    if source_id_field is None:
        raise NormalizationConfigError(f"{loc}: no column is mapped to source_id")
    missing = [name for name in specs if name not in rules]
    if missing:
        raise NormalizationConfigError(f"{loc}: canonical business fields not mapped: {missing}")
    return EntityMapping(
        entity_type=entity_type,
        source_id_field=source_id_field,
        source_updated_at_field=updated_field,
        rules=MappingProxyType({name: rules[name] for name in specs}),
    )


def _parse_derivation(
    target: str,
    raw: object,
    specs: Mapping[str, FieldSpec],
    loc: str,
) -> FieldRule:
    rule = _mapping(raw, loc)
    kind = rule.get("rule")
    source_field = rule.get("from")
    if not isinstance(source_field, str) or not source_field:
        raise NormalizationConfigError(f"{loc}: 'from' must name a source field")

    if kind == "enum_membership":
        _check_keys(rule, loc, required={"rule", "from", "enum_of", "true_values", "false_values"})
        enum_spec = specs.get(rule["enum_of"])
        if specs[target].kind != "boolean" or enum_spec is None or enum_spec.kind != "enum":
            raise NormalizationConfigError(
                f"{loc}: enum_membership derives a boolean from a canonical enum field"
            )
        true_values = frozenset(_string_list(rule["true_values"], f"{loc}.true_values"))
        false_values = frozenset(_string_list(rule["false_values"], f"{loc}.false_values"))
        if true_values & false_values or (true_values | false_values) != enum_spec.enum_values:
            raise NormalizationConfigError(
                f"{loc}: true_values and false_values must partition the enum values "
                f"{sorted(enum_spec.enum_values)}"
            )
        return FieldRule(target, source_field,
                         EnumMembership(rule["enum_of"], true_values, false_values))

    if kind == "boolean_to_enum":
        _check_keys(rule, loc, required={"rule", "from", "true_value", "false_value"})
        spec = specs[target]
        true_value, false_value = rule["true_value"], rule["false_value"]
        if (
            spec.kind != "enum"
            or true_value not in spec.enum_values
            or false_value not in spec.enum_values
            or true_value == false_value
        ):
            raise NormalizationConfigError(
                f"{loc}: boolean_to_enum needs two distinct values of the target enum"
            )
        return FieldRule(target, source_field, BooleanToEnum(true_value, false_value))

    raise NormalizationConfigError(f"{loc}: unknown derivation rule {kind!r}")


def _parse_enum_aliases(
    raw: object,
    fields: Mapping[str, Mapping[str, FieldSpec]],
    loc: str,
) -> Mapping[str, Mapping[str, str]]:
    result = {}
    for key, aliases in _mapping(raw, loc).items():
        entity_type, _, field_name = str(key).partition(".")
        spec = fields.get(entity_type, {}).get(field_name)
        if spec is None or spec.kind != "enum":
            raise NormalizationConfigError(f"{loc}: {key!r} is not a canonical enum field")
        normalized = {}
        for alias, value in _mapping(aliases, f"{loc}.{key}").items():
            token = normalize_enum_token(str(alias))
            if value not in spec.enum_values or token in spec.enum_values:
                raise NormalizationConfigError(
                    f"{loc}.{key}: alias {alias!r} must map a non-canonical label to one of "
                    f"{sorted(spec.enum_values)}"
                )
            normalized[token] = value
        result[str(key)] = MappingProxyType(normalized)
    return MappingProxyType(result)


# ---------------------------------------------------------------------------
# Primitive validators
# ---------------------------------------------------------------------------


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise NormalizationConfigError(f"Normalization configuration file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise NormalizationConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise NormalizationConfigError(f"{path}: top level must be a mapping")
    return data


def _mapping(value: object, loc: str) -> dict:
    if not isinstance(value, dict):
        raise NormalizationConfigError(f"{loc}: expected a mapping")
    return value


def _check_keys(data: object, loc: str, *, required: set[str],
                optional: set[str] | None = None) -> None:
    data = _mapping(data, loc)
    missing = required - set(data)
    unknown = set(data) - required - (optional or set())
    if missing or unknown:
        raise NormalizationConfigError(
            f"{loc}: missing keys {sorted(missing)}, unknown keys {sorted(map(str, unknown))}"
        )


def _check_exact(actual: set[str], expected: set[str], loc: str) -> None:
    if actual != expected:
        raise NormalizationConfigError(
            f"{loc}: missing {sorted(expected - actual)}, unknown {sorted(map(str, actual - expected))}"
        )


def _string_list(value: object, loc: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
        or len(set(value)) != len(value)
    ):
        raise NormalizationConfigError(f"{loc}: expected a non-empty list of unique strings")
    return value


def _token_set(value: object, loc: str, *, allow_empty: bool = False) -> frozenset[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise NormalizationConfigError(f"{loc}: expected a list of tokens")
    if not all(isinstance(item, str) for item in value):
        raise NormalizationConfigError(f"{loc}: tokens must be strings")
    return frozenset(item.strip().casefold() for item in value)


def _check_disjoint_from_booleans(null_tokens: frozenset[str], true_tokens: frozenset[str],
                                  false_tokens: frozenset[str], loc: str) -> None:
    overlap = null_tokens & (true_tokens | false_tokens)
    if overlap:
        raise NormalizationConfigError(f"{loc}: tokens are also boolean tokens: {sorted(overlap)}")


def _optional_decimal(value: object, loc: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise NormalizationConfigError(f"{loc}: expected a number")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise NormalizationConfigError(f"{loc}: expected a number") from exc
    if not number.is_finite():
        raise NormalizationConfigError(f"{loc}: expected a finite number")
    return number


def _formats(value: object, allowed: frozenset[str], loc: str) -> tuple[str, ...]:
    formats = _string_list(value, loc)
    for fmt in formats:
        unsupported = set(_DIRECTIVE.findall(fmt)) - allowed
        if unsupported or "%" not in fmt:
            raise NormalizationConfigError(
                f"{loc}: format {fmt!r} uses unsupported directives {sorted(unsupported)}"
            )
    return tuple(formats)


def _parse_timezone(value: object, loc: str) -> tzinfo | None:
    """'reject' -> None, 'UTC' -> UTC, '+HH:MM'/'-HH:MM' -> fixed offset.

    Named regional zones are intentionally unsupported: a fixed policy
    avoids daylight-saving ambiguity for naive source timestamps.
    """
    if value == "reject":
        return None
    if value == "UTC":
        return UTC
    match = _OFFSET.fullmatch(str(value))
    if match:
        sign, hours, minutes = match.groups()
        offset = timedelta(hours=int(hours), minutes=int(minutes))
        if offset < timedelta(hours=24) and int(minutes) < 60:
            return timezone(-offset if sign == "-" else offset)
    raise NormalizationConfigError(
        f"{loc}: naive_datetime_timezone must be 'reject', 'UTC', or '+HH:MM', got {value!r}"
    )
