"""
Configuration for the D2 quality gate (config/validation/quality_gate.yaml).

The canonical contract itself (field kinds, enum values, decimal limits,
source vocabulary) is owned by D1 in config/mappings/ and reused by D2.
This file configures only D2 policy:

    quarantine  safe diagnostic payload limits and secret redaction
    warnings    WARNING-severity rules that never reject a record

load_validation_config reads only the given file. The resulting
ValidationConfig is immutable; default_validation_config() memoizes the
repository configuration.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import yaml

from app.normalization.contract import BUSINESS_FIELDS, CANONICAL_SCHEMAS, is_required
from app.validation.errors import ValidationConfigError

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "validation" / "quality_gate.yaml"
)

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]")


def normalize_key(key: str) -> str:
    """Casefold and drop non-alphanumerics: 'API-Key' and 'api_key' -> 'apikey'."""
    return _NON_ALPHANUMERIC.sub("", key.casefold())


@dataclass(frozen=True)
class QuarantinePolicy:
    """Limits and redaction rules for quarantine diagnostic payloads."""

    max_string_length: int
    max_depth: int
    redaction: str
    sensitive_keys: frozenset[str]
    sensitive_value_patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class WarningPolicy:
    """WARNING-severity rules; they never quarantine a record."""

    duplicate_source_identity: bool
    recommended_fields: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class ValidationConfig:
    """Complete, validated, immutable D2 configuration."""

    quarantine: QuarantinePolicy
    warnings: WarningPolicy


@functools.lru_cache(maxsize=1)
def default_validation_config() -> ValidationConfig:
    """Load (once) the repository quality gate configuration."""
    return load_validation_config(DEFAULT_CONFIG_PATH)


def load_validation_config(path: str | Path) -> ValidationConfig:
    """Load and validate a quality gate configuration file."""
    path = Path(path)
    where = str(path)
    if not path.is_file():
        raise ValidationConfigError(f"Validation configuration file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValidationConfigError(f"{where}: invalid YAML: {exc}") from exc
    data = _section(data, where, {"version", "quarantine", "warnings"})
    if data["version"] != 1:
        raise ValidationConfigError(f"{where}: unsupported version {data['version']!r}")
    return ValidationConfig(
        quarantine=_parse_quarantine(data["quarantine"], f"{where}: quarantine"),
        warnings=_parse_warnings(data["warnings"], f"{where}: warnings"),
    )


def _parse_quarantine(raw: object, loc: str) -> QuarantinePolicy:
    raw = _section(raw, loc, {"max_string_length", "max_depth", "redaction", "sensitive_keys",
                              "sensitive_value_patterns"})
    redaction = raw["redaction"]
    if not isinstance(redaction, str) or not redaction.strip():
        raise ValidationConfigError(f"{loc}.redaction: expected a non-empty string")

    keys = frozenset(normalize_key(key) for key in _strings(raw["sensitive_keys"],
                                                            f"{loc}.sensitive_keys"))
    if "" in keys:
        raise ValidationConfigError(f"{loc}.sensitive_keys: keys must contain letters or digits")

    patterns = []
    for pattern in _strings(raw["sensitive_value_patterns"], f"{loc}.sensitive_value_patterns"):
        try:
            patterns.append(re.compile(pattern))
        except re.error as exc:
            raise ValidationConfigError(
                f"{loc}.sensitive_value_patterns: invalid pattern {pattern!r}: {exc}"
            ) from exc

    return QuarantinePolicy(
        max_string_length=_bounded_int(raw["max_string_length"], 16, 100_000,
                                       f"{loc}.max_string_length"),
        max_depth=_bounded_int(raw["max_depth"], 1, 32, f"{loc}.max_depth"),
        redaction=redaction,
        sensitive_keys=keys,
        sensitive_value_patterns=tuple(patterns),
    )


def _parse_warnings(raw: object, loc: str) -> WarningPolicy:
    raw = _section(raw, loc, {"duplicate_source_identity", "recommended_fields"})
    duplicates = raw["duplicate_source_identity"]
    if not isinstance(duplicates, bool):
        raise ValidationConfigError(f"{loc}.duplicate_source_identity: expected true or false")

    recommended_raw = raw["recommended_fields"]
    if not isinstance(recommended_raw, dict):
        raise ValidationConfigError(f"{loc}.recommended_fields: expected a mapping")
    unknown = set(map(str, recommended_raw)) - set(CANONICAL_SCHEMAS)
    if unknown:
        raise ValidationConfigError(f"{loc}.recommended_fields: unknown entities {sorted(unknown)}")
    recommended = {}
    for entity_type in CANONICAL_SCHEMAS:
        if entity_type not in recommended_raw:
            continue
        fields = _strings(recommended_raw[entity_type], f"{loc}.recommended_fields.{entity_type}")
        for field in fields:
            if field not in BUSINESS_FIELDS[entity_type]:
                raise ValidationConfigError(
                    f"{loc}.recommended_fields.{entity_type}: {field!r} is not a business field"
                )
            if is_required(entity_type, field):
                raise ValidationConfigError(
                    f"{loc}.recommended_fields.{entity_type}: {field!r} is already required"
                )
        recommended[entity_type] = tuple(fields)
    return WarningPolicy(
        duplicate_source_identity=duplicates,
        recommended_fields=MappingProxyType(recommended),
    )


def _section(data: object, loc: str, expected: set[str]) -> dict[str, object]:
    """Return a configuration mapping after checking it has exactly the expected keys."""
    if not isinstance(data, dict):
        raise ValidationConfigError(f"{loc}: expected a mapping")
    missing = expected - set(data)
    unknown = set(map(str, data)) - expected
    if missing or unknown:
        raise ValidationConfigError(
            f"{loc}: missing keys {sorted(missing)}, unknown keys {sorted(unknown)}"
        )
    return data


def _strings(value: object, loc: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValidationConfigError(f"{loc}: expected a non-empty list of unique strings")
    return value


def _bounded_int(value: object, minimum: int, maximum: int, loc: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValidationConfigError(f"{loc}: expected an integer in [{minimum}, {maximum}]")
    return value
