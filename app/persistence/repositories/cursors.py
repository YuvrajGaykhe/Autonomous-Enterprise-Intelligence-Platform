"""
ingestion_cursors checkpoint state per (source_system, source_entity).

A checkpoint is written only when an entity completes with every batch
committed, in the same transaction as its last batch, so it can never
advance past a failed batch (spec Section 9).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.persistence.models import IngestionCursor


@dataclass(frozen=True)
class CursorState:
    last_cursor: str | None
    last_successful_run_id: uuid.UUID | None
    updated_at: datetime


def get_cursor(session: Session, source_system: str, source_entity: str) -> CursorState | None:
    row = session.execute(
        select(IngestionCursor.last_cursor, IngestionCursor.last_successful_run_id,
               IngestionCursor.updated_at)
        .where(IngestionCursor.source_system == source_system,
               IngestionCursor.source_entity == source_entity)
    ).one_or_none()
    return None if row is None else CursorState(row[0], row[1], row[2])


def record_entity_success(
    session: Session,
    *,
    source_system: str,
    source_entity: str,
    run_id: uuid.UUID,
    last_cursor: str | None,
    updated_at: datetime,
) -> None:
    """Upsert the checkpoint for an entity whose run completed successfully."""
    if updated_at.utcoffset() is None:
        raise ValueError("updated_at must be timezone-aware")
    statement = insert(IngestionCursor).values(
        id=uuid.uuid4(),
        source_system=source_system,
        source_entity=source_entity,
        last_cursor=last_cursor,
        last_successful_run_id=run_id,
        updated_at=updated_at,
    )
    session.execute(statement.on_conflict_do_update(
        constraint="uq_ingestion_cursors_source_key",
        set_={
            "last_cursor": statement.excluded.last_cursor,
            "last_successful_run_id": statement.excluded.last_successful_run_id,
            "updated_at": statement.excluded.updated_at,
        },
    ))
