"""
Safe API presentation of persisted ingestion errors.

ingestion_errors keeps full diagnostics for internal debugging: D1/D2
messages quote the rejected source value (e.g. "unknown value 'suspended'"),
and detail holds a redacted copy of the raw record and per-field raw values.
None of that is returned by the API.

Messages:
    E1-owned codes (IngestionCode) keep their stored message: E1 writes it
    from entity names, field names, counts and exception class names only.
    Every other code gets a fixed description from SAFE_MESSAGES, and a code
    missing from the catalogue gets FALLBACK_MESSAGE, so a new D1/D2 code can
    never expose stored diagnostic text.

Findings:
    Parsed from detail: each finding's code, field_name and severity, with
    the message chosen by the same rule. raw_record, raw_value, source keys
    and stored D1/D2 messages are never read into the response. A detail that
    is absent, not JSON, or not in an E1 format yields no findings; the row's
    own code and safe message are still returned.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType

from app.ingestion.errors import IngestionCode
from app.persistence.repositories.errors import SEVERITIES

TRUSTED_MESSAGE_CODES = frozenset(code.value for code in IngestionCode)

FALLBACK_MESSAGE = "record failed data quality checks"

SAFE_MESSAGES = MappingProxyType({
    # D1 normalization (app.normalization.ErrorCode)
    "UNSUPPORTED_SOURCE": "source system is not supported by the normalization configuration",
    "UNSUPPORTED_ENTITY": "entity type is not supported for this source",
    "INVALID_RECORD": "record is not a valid source record",
    "SOURCE_ID_MISSING": "record has no source identifier",
    "SOURCE_ID_INVALID": "source identifier is not valid for this source",
    "RELATIONSHIP_KEY_INVALID": "relationship key is not a valid source identifier",
    "REQUIRED_FIELD_MISSING": "required field has no value",
    "INVALID_TYPE": "value has the wrong type for this field",
    "INVALID_BOOLEAN": "value is not a recognised boolean",
    "INVALID_DATE": "value is not a date in the configured formats",
    "AMBIGUOUS_DATE": "date value is ambiguous under the configured formats",
    "INVALID_DATETIME": "value is not a datetime in the configured formats",
    "AMBIGUOUS_DATETIME": "datetime value is ambiguous under the configured formats",
    "NAIVE_DATETIME_REJECTED": "datetime value has no UTC offset and this source requires one",
    "INVALID_DECIMAL": "value is not a decimal number in the configured source format",
    "DECIMAL_SCALE_EXCEEDED": "decimal value has more fractional digits than the canonical scale",
    "DECIMAL_PRECISION_EXCEEDED": "decimal value exceeds the canonical precision",
    "DECIMAL_OUT_OF_RANGE": "decimal value is outside the canonical range",
    "UNKNOWN_ENUM_VALUE": "value is not in the canonical vocabulary for this field",
    "INVALID_CURRENCY": "value is not a configured ISO 4217 currency code",
    "SCHEMA_VALIDATION_FAILED": "record does not satisfy the canonical schema",
    "UNEXPECTED_ERROR": "record could not be normalized",
    # D2 validation (app.validation.QualityCode)
    "NON_CANONICAL_VALUE": "value is not in canonical form",
    "DUPLICATE_SOURCE_RECORD": "duplicate of an earlier record in the batch with identical content",
    "DUPLICATE_SOURCE_IDENTITY_CONFLICT":
        "an earlier record in the batch has the same source identity with different content",
    "MISSING_RECOMMENDED_FIELD": "recommended field has no value; the record remains usable",
})


@dataclass(frozen=True)
class SafeFinding:
    code: str
    field_name: str | None
    severity: str | None
    message: str


def safe_message(code: str | None, stored_message: str) -> str:
    """The message the API may show for an error or finding with this code."""
    if code in TRUSTED_MESSAGE_CODES:
        return stored_message
    if code is None:
        return FALLBACK_MESSAGE
    return SAFE_MESSAGES.get(code, FALLBACK_MESSAGE)


def safe_findings(detail: str | None, stored_message: str) -> list[SafeFinding]:
    """Field-level findings parsed from a stored detail, without source values."""
    payload = _json_object(detail)
    if payload is None:
        return []
    entries = payload.get("findings")
    candidates = entries if isinstance(entries, list) else [payload]
    findings = []
    for entry in candidates:
        finding = _finding(entry, stored_message)
        if finding is not None:
            findings.append(finding)
    return findings


def _json_object(detail: str | None) -> dict[str, object] | None:
    if detail is None:
        return None
    try:
        value = json.loads(detail)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _finding(entry: object, stored_message: str) -> SafeFinding | None:
    if not isinstance(entry, dict):
        return None
    code = entry.get("code")
    if not isinstance(code, str):
        return None
    field_name = entry.get("field_name")
    severity = entry.get("severity")
    return SafeFinding(
        code=code,
        field_name=field_name if isinstance(field_name, str) else None,
        severity=severity if isinstance(severity, str) and severity in SEVERITIES else None,
        message=safe_message(code, stored_message),
    )
