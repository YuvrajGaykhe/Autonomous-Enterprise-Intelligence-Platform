"""
Read-only queries over ingestion runs for the API.

Lists and lookups over ingestion_runs and ingestion_errors, plus the per-run
aggregates the stored counts do not carry (raw records captured, errors of a
given code). Aggregates take a whole page of run IDs and answer in one
grouped query, so listing runs never issues a query per run.

Like every repository: the caller owns the session and transaction; nothing
here writes, commits, or logs.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.persistence.models import IngestionError, IngestionRun, SourceRecord

T = TypeVar("T")


@dataclass(frozen=True)
class QueryPage(Generic[T]):
    """One limit/offset page and the total number of matching rows."""

    items: list[T]
    total: int


def list_runs(
    session: Session,
    *,
    source_system: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> QueryPage[IngestionRun]:
    """Runs matching the filters, newest first (started_at, then id, descending)."""
    conditions = []
    if source_system is not None:
        conditions.append(IngestionRun.source_system == source_system)
    if status is not None:
        conditions.append(IngestionRun.status == status)
    total = session.execute(
        select(func.count()).select_from(IngestionRun).where(*conditions)).scalar_one()
    rows = session.scalars(
        select(IngestionRun).where(*conditions)
        .order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc())
        .limit(limit).offset(offset)
    ).all()
    return QueryPage(items=list(rows), total=total)


def get_run(session: Session, run_id: uuid.UUID) -> IngestionRun | None:
    return session.get(IngestionRun, run_id)


def records_failed(run: IngestionRun) -> int:
    """Records of failed batches.

    E1 persists records_fetched = inserted + updated + unchanged + rejected +
    failed, so the failed count is the remainder.
    """
    return run.records_fetched - (run.records_inserted + run.records_updated
                                  + run.records_unchanged + run.records_rejected)


def count_raw_records(session: Session, run_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    """source_records rows captured per run (runs without rows are absent)."""
    if not run_ids:
        return {}
    rows = session.execute(
        select(SourceRecord.ingestion_run_id, func.count())
        .where(SourceRecord.ingestion_run_id.in_(run_ids))
        .group_by(SourceRecord.ingestion_run_id)
    )
    return dict(rows.tuples().all())


def count_errors(
    session: Session,
    run_ids: Sequence[uuid.UUID],
    *,
    error_code: str,
) -> dict[uuid.UUID, int]:
    """ingestion_errors rows with one error code per run (runs without rows are absent)."""
    if not run_ids:
        return {}
    rows = session.execute(
        select(IngestionError.ingestion_run_id, func.count())
        .where(IngestionError.ingestion_run_id.in_(run_ids),
               IngestionError.error_code == error_code)
        .group_by(IngestionError.ingestion_run_id)
    )
    return dict(rows.tuples().all())


def list_errors(
    session: Session,
    run_id: uuid.UUID,
    *,
    severity: str | None,
    limit: int,
    offset: int,
) -> QueryPage[IngestionError]:
    """A run's errors in a stable order (created_at, then id, ascending)."""
    conditions = [IngestionError.ingestion_run_id == run_id]
    if severity is not None:
        conditions.append(IngestionError.severity == severity)
    total = session.execute(
        select(func.count()).select_from(IngestionError).where(*conditions)).scalar_one()
    rows = session.scalars(
        select(IngestionError).where(*conditions)
        .order_by(IngestionError.created_at, IngestionError.id)
        .limit(limit).offset(offset)
    ).all()
    return QueryPage(items=list(rows), total=total)
