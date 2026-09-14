"""
ingestion_runs lifecycle.

A run is created RUNNING, accumulates counts batch by batch (inside each
batch transaction, so persisted counts always match committed data), and is
finished exactly once with a terminal status. State transitions are guarded
in SQL (WHERE status = 'RUNNING'), so a finished run can never be modified.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, fields
from datetime import datetime
from enum import StrEnum
from typing import cast

from sqlalchemy import CursorResult, update
from sqlalchemy.orm import Session

from app.persistence.models import IngestionRun


class RunStatus(StrEnum):
    """ingestion_runs.status vocabulary (spec Section 8)."""

    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    NOOP = "NOOP"


class RunMode(StrEnum):
    """ingestion_runs.mode vocabulary. No Layer 1 connector supports incremental sync."""

    FULL = "full"


class RunStateError(Exception):
    """The run does not exist or is not RUNNING."""


@dataclass(frozen=True)
class RunCounts:
    """Record counts persisted on ingestion_runs."""

    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0
    warnings: int = 0

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int or value < 0:
                raise ValueError(f"count {field.name!r} must be a non-negative int")

    def __add__(self, other: RunCounts) -> RunCounts:
        return RunCounts(**{
            field.name: getattr(self, field.name) + getattr(other, field.name)
            for field in fields(self)
        })


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value


def create_run(
    session: Session,
    *,
    run_id: uuid.UUID,
    source_system: str,
    source_entity: str | None,
    mode: RunMode,
    started_at: datetime,
) -> None:
    """Insert a RUNNING run with zero counts."""
    session.add(IngestionRun(
        id=run_id,
        source_system=source_system,
        source_entity=source_entity,
        status=RunStatus.RUNNING.value,
        mode=RunMode(mode).value,
        started_at=_aware(started_at, "started_at"),
        records_fetched=0,
        records_inserted=0,
        records_updated=0,
        records_unchanged=0,
        records_rejected=0,
        records_warnings=0,
    ))
    session.flush()


def _update_running(session: Session, run_id: uuid.UUID, values: dict[str, object]) -> None:
    statement = (
        update(IngestionRun)
        .where(IngestionRun.id == run_id, IngestionRun.status == RunStatus.RUNNING.value)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    result = cast(CursorResult[object], session.execute(statement))
    if result.rowcount != 1:
        raise RunStateError(f"ingestion run {run_id} does not exist or is not RUNNING")


def add_run_counts(session: Session, run_id: uuid.UUID, counts: RunCounts) -> None:
    """Atomically add counts to a RUNNING run."""
    _update_running(session, run_id, {
        "records_fetched": IngestionRun.records_fetched + counts.fetched,
        "records_inserted": IngestionRun.records_inserted + counts.inserted,
        "records_updated": IngestionRun.records_updated + counts.updated,
        "records_unchanged": IngestionRun.records_unchanged + counts.unchanged,
        "records_rejected": IngestionRun.records_rejected + counts.rejected,
        "records_warnings": IngestionRun.records_warnings + counts.warnings,
    })


def finish_run(
    session: Session,
    run_id: uuid.UUID,
    *,
    status: RunStatus,
    finished_at: datetime,
    error_summary: str | None,
) -> None:
    """Move a RUNNING run to a terminal status. A run can finish only once."""
    terminal = RunStatus(status)
    if terminal is RunStatus.RUNNING:
        raise ValueError("finish_run requires a terminal status")
    _update_running(session, run_id, {
        "status": terminal.value,
        "finished_at": _aware(finished_at, "finished_at"),
        "error_summary": error_summary,
    })
