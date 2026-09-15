"""
Read-only aggregates for the ingestion metrics API.

Aggregates over ingestion_runs, ingestion_errors, source_records and the
canonical tables. Each function answers with one grouped query (canonical
counts: one per canonical table), so the cost does not grow with the number
of runs. Runs, errors and raw records are attributed to the source_system of
their run.

Like every repository: the caller owns the session and transaction; nothing
here writes, commits, or logs.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.persistence.models import IngestionError, IngestionRun, SourceRecord
from app.persistence.repositories.canonical import ENTITY_MODELS


@dataclass(frozen=True)
class RunAggregate:
    """Runs of one source system and status, with their summed counts.

    duration_seconds sums finished_at - started_at over the finished runs.
    """

    source_system: str
    status: str
    runs: int
    records_fetched: int
    records_inserted: int
    records_updated: int
    records_unchanged: int
    records_rejected: int
    warnings: int
    duration_seconds: float


@dataclass(frozen=True)
class RunReference:
    """Identity and timing of one run."""

    run_id: uuid.UUID
    status: str
    started_at: datetime
    finished_at: datetime | None


def run_aggregates(session: Session) -> list[RunAggregate]:
    """Run counts and summed record counts per (source_system, status)."""
    duration = func.extract("epoch", IngestionRun.finished_at - IngestionRun.started_at)
    rows = session.execute(
        select(
            IngestionRun.source_system, IngestionRun.status, func.count(),
            func.sum(IngestionRun.records_fetched), func.sum(IngestionRun.records_inserted),
            func.sum(IngestionRun.records_updated), func.sum(IngestionRun.records_unchanged),
            func.sum(IngestionRun.records_rejected), func.sum(IngestionRun.records_warnings),
            func.coalesce(func.sum(duration), 0),
        )
        .group_by(IngestionRun.source_system, IngestionRun.status)
    ).tuples().all()
    return [
        RunAggregate(
            source_system=source_system, status=status, runs=runs,
            records_fetched=int(fetched), records_inserted=int(inserted),
            records_updated=int(updated), records_unchanged=int(unchanged),
            records_rejected=int(rejected), warnings=int(warnings),
            duration_seconds=float(seconds),
        )
        for (source_system, status, runs, fetched, inserted, updated, unchanged, rejected,
             warnings, seconds) in rows
    ]


def raw_record_counts(session: Session) -> dict[str, int]:
    """source_records rows per run source_system (systems without rows are absent)."""
    rows = session.execute(
        select(IngestionRun.source_system, func.count())
        .select_from(SourceRecord)
        .join(IngestionRun, SourceRecord.ingestion_run_id == IngestionRun.id)
        .group_by(IngestionRun.source_system)
    )
    return dict(rows.tuples().all())


def error_counts(session: Session) -> dict[tuple[str, str, str | None], int]:
    """ingestion_errors rows per (run source_system, severity, error_code)."""
    rows = session.execute(
        select(IngestionRun.source_system, IngestionError.severity, IngestionError.error_code,
               func.count())
        .select_from(IngestionError)
        .join(IngestionRun, IngestionError.ingestion_run_id == IngestionRun.id)
        .group_by(IngestionRun.source_system, IngestionError.severity, IngestionError.error_code)
    )
    return {(source_system, severity, code): count
            for source_system, severity, code, count in rows.tuples().all()}


def latest_runs(
    session: Session,
    *,
    statuses: Collection[str] | None = None,
) -> dict[str, RunReference]:
    """The newest run per source system (started_at, then id, descending).

    With statuses, only runs in one of those statuses are considered.
    """
    statement = (
        select(IngestionRun.source_system, IngestionRun.id, IngestionRun.status,
               IngestionRun.started_at, IngestionRun.finished_at)
        .distinct(IngestionRun.source_system)
        .order_by(IngestionRun.source_system, IngestionRun.started_at.desc(),
                  IngestionRun.id.desc())
    )
    if statuses is not None:
        statement = statement.where(IngestionRun.status.in_(list(statuses)))
    return {
        source_system: RunReference(run_id=run_id, status=status, started_at=started_at,
                                    finished_at=finished_at)
        for source_system, run_id, status, started_at, finished_at
        in session.execute(statement).tuples().all()
    }


def canonical_record_counts(session: Session) -> dict[str, dict[str, int]]:
    """Canonical rows per entity type, then per source_system (systems without rows are absent)."""
    counts: dict[str, dict[str, int]] = {}
    for entity_type, model in ENTITY_MODELS.items():
        table: Any = model
        rows = session.execute(
            select(table.source_system, func.count()).group_by(table.source_system))
        counts[entity_type] = dict(rows.tuples().all())
    return counts
