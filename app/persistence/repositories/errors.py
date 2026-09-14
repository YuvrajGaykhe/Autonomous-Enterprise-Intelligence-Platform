"""
ingestion_errors rows: quarantined records, warnings, and run/batch failures.

Callers supply already-safe text: quarantine messages and detail come from
D2's redacted payloads, and E1 failure entries never include source values.
Identifier columns are diagnostic, so over-long identifiers are truncated to
the column width instead of failing the transaction that records them; the
full (D2-bounded) value remains in detail.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import String, insert
from sqlalchemy.orm import Session

from app.persistence.models import IngestionError

SEVERITIES = frozenset({"ERROR", "WARNING", "INFO"})


@dataclass(frozen=True)
class ErrorEntry:
    """One structured ingestion error."""

    severity: str
    error_code: str
    message: str
    source_system: str | None = None
    source_entity: str | None = None
    source_id: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {sorted(SEVERITIES)}")
        if not self.error_code or not self.message:
            raise ValueError("error_code and message are required")


def _fit(value: str | None, column: str) -> str | None:
    column_type = IngestionError.__table__.c[column].type
    if value is None or not isinstance(column_type, String) or column_type.length is None:
        return value
    return value[:column_type.length]


def add_errors(
    session: Session,
    run_id: uuid.UUID,
    entries: Sequence[ErrorEntry],
    *,
    created_at: datetime,
) -> int:
    """Append error rows for a run, preserving entry order; return rows written."""
    if created_at.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    rows = [
        {
            "id": uuid.uuid4(),
            "ingestion_run_id": run_id,
            "source_system": _fit(entry.source_system, "source_system"),
            "source_entity": _fit(entry.source_entity, "source_entity"),
            "source_id": _fit(entry.source_id, "source_id"),
            "severity": entry.severity,
            "error_code": _fit(entry.error_code, "error_code"),
            "message": entry.message,
            "detail": entry.detail,
            "created_at": created_at,
        }
        for entry in entries
    ]
    if rows:
        session.execute(insert(IngestionError), rows)
    return len(rows)
