"""
Quarantine contract and safe diagnostic payloads for D2.

A QuarantineRecord describes one rejected source record (spec Section 13):
source context, record identity, stable error codes, human-readable
reasons, and a safe representation of the raw record. It is an in-memory,
JSON-serializable value; persisting it (ingestion_errors, data/quarantine)
belongs to E1.

Safe payloads are deterministic and bounded:
    - values under sensitive keys (password, token, authorization, ...)
      are replaced by the redaction marker
    - strings matching sensitive value patterns (e.g. "Bearer ...") are
      redacted wherever they appear
    - long strings are truncated and nesting is depth-limited
    - non-JSON types become stable strings (never object memory addresses)
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.normalization import NormalizationError, canonical_id
from app.normalization.errors import describe_value
from app.validation.config import QuarantinePolicy, normalize_key
from app.validation.errors import Severity, Stage

MAX_DEPTH_MARKER = "[MAX_DEPTH]"


@dataclass(frozen=True)
class Violation:
    """A data-contract violation found by a D2 rule (before sanitization)."""

    field_name: str
    code: str
    reason: str
    value: object = None


@dataclass(frozen=True)
class QualityFinding:
    """One ERROR (quarantine) or WARNING (valid record) quality finding."""

    severity: Severity
    code: str
    message: str
    record_index: int
    source_id: str | None = None
    field_name: str | None = None
    raw_value: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "severity": str(self.severity),
            "code": self.code,
            "message": self.message,
            "record_index": self.record_index,
            "source_id": self.source_id,
            "field_name": self.field_name,
            "raw_value": self.raw_value,
        }


@dataclass(frozen=True)
class QuarantineRecord:
    """A rejected source record with its findings and safe raw payload."""

    ingestion_run_id: uuid.UUID
    source_system: str
    entity_type: str
    record_index: int
    stage: Stage
    source_id: str | None
    canonical_id: uuid.UUID | None
    findings: tuple[QualityFinding, ...]
    raw_record: object

    def __post_init__(self) -> None:
        if not self.findings or any(f.severity is not Severity.ERROR for f in self.findings):
            raise ValueError("a quarantine record requires one or more ERROR findings")

    @property
    def code(self) -> str:
        """Code of the primary (first) finding."""
        return self.findings[0].code

    @property
    def field_name(self) -> str | None:
        return self.findings[0].field_name

    @property
    def message(self) -> str:
        return self.findings[0].message

    def to_dict(self) -> dict[str, object]:
        return {
            "ingestion_run_id": str(self.ingestion_run_id),
            "source_system": self.source_system,
            "entity_type": self.entity_type,
            "record_index": self.record_index,
            "stage": str(self.stage),
            "source_id": self.source_id,
            "canonical_id": None if self.canonical_id is None else str(self.canonical_id),
            "severity": str(Severity.ERROR),
            "code": self.code,
            "field_name": self.field_name,
            "message": self.message,
            "findings": [finding.to_dict() for finding in self.findings],
            "raw_record": self.raw_record,
        }


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def quarantine_from_normalization_error(
    error: NormalizationError,
    *,
    record: object,
    record_index: int,
    ingestion_run_id: uuid.UUID,
    source_system: str,
    entity_type: str,
    policy: QuarantinePolicy,
) -> QuarantineRecord:
    """Quarantine a record that D1 rejected with a data-failure error."""
    finding = QualityFinding(
        severity=Severity.ERROR,
        code=str(error.code),
        message=safe_message(error.reason, policy),
        record_index=record_index,
        source_id=error.source_id,
        field_name=error.field_name,
        raw_value=safe_repr(error.raw_value, policy),
    )
    return QuarantineRecord(
        ingestion_run_id=ingestion_run_id,
        source_system=source_system,
        entity_type=entity_type,
        record_index=record_index,
        stage=Stage.NORMALIZATION,
        source_id=error.source_id,
        canonical_id=(None if error.source_id is None
                      else canonical_id(source_system, entity_type, error.source_id)),
        findings=(finding,),
        raw_record=safe_payload(record, policy),
    )


def quarantine_from_violations(
    violations: list[Violation],
    *,
    raw_record: object,
    record_index: int,
    source_id: str | None,
    record_canonical_id: uuid.UUID | None,
    ingestion_run_id: uuid.UUID,
    source_system: str,
    entity_type: str,
    policy: QuarantinePolicy,
) -> QuarantineRecord:
    """Quarantine a canonical record that failed D2 data rules."""
    findings = tuple(
        QualityFinding(
            severity=Severity.ERROR,
            code=violation.code,
            message=safe_message(violation.reason, policy),
            record_index=record_index,
            source_id=source_id,
            field_name=violation.field_name,
            raw_value=safe_repr(violation.value, policy),
        )
        for violation in violations
    )
    return QuarantineRecord(
        ingestion_run_id=ingestion_run_id,
        source_system=source_system,
        entity_type=entity_type,
        record_index=record_index,
        stage=Stage.VALIDATION,
        source_id=source_id,
        canonical_id=record_canonical_id,
        findings=findings,
        raw_record=safe_payload(raw_record, policy),
    )


# ---------------------------------------------------------------------------
# Safe representations
# ---------------------------------------------------------------------------


def is_sensitive_key(key: str, policy: QuarantinePolicy) -> bool:
    """True if a mapping key names a credential-like value."""
    normalized = normalize_key(key)
    return any(part in normalized for part in policy.sensitive_keys)


def safe_payload(value: object, policy: QuarantinePolicy) -> object:
    """Return a bounded, redacted, JSON-serializable copy of a value."""
    return _safe(value, policy, depth=0)


def safe_repr(value: object, policy: QuarantinePolicy) -> str | None:
    """Return a bounded, redacted repr of a single offending value."""
    if value is None:
        return None
    return describe_value(safe_payload(value, policy))


def safe_message(text: str, policy: QuarantinePolicy) -> str:
    """Redact sensitive value patterns inside a human-readable message."""
    for pattern in policy.sensitive_value_patterns:
        text = pattern.sub(policy.redaction, text)
    return _truncate(text, policy)


def _safe(value: object, policy: QuarantinePolicy, depth: int) -> object:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, str):
        return _safe_string(value, policy)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if depth >= policy.max_depth:
        return MAX_DEPTH_MARKER
    if isinstance(value, Mapping):
        return {
            str(key): (policy.redaction if is_sensitive_key(str(key), policy)
                       else _safe(item, policy, depth + 1))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe(item, policy, depth + 1) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_safe(item, policy, depth + 1) for item in value), key=repr)
    return f"<{type(value).__name__}>"


def _safe_string(text: str, policy: QuarantinePolicy) -> str:
    if any(pattern.search(text) for pattern in policy.sensitive_value_patterns):
        return policy.redaction
    return _truncate(text, policy)


def _truncate(text: str, policy: QuarantinePolicy) -> str:
    limit = policy.max_string_length
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...[truncated {len(text) - limit} chars]"
