"""
Persistence for brief decisions: insert only (VS-01 M8, §0.7.6).

This module is **persistence only**, on the boundary M4 drew (§0.3.11 D-M4-B1,
D-M4-B2) and M7 kept (§0.6.5): it imports no app.intelligence, app.evidence,
app.analysts or app.decisions module, names no domain type, and decides
nothing. The row type below is a row projection whose fields are plain data.

It inserts and does nothing else: no update, no delete and no read. The table
is append-only twice over (OPEN-M8-4), here and in the database trigger the
M8 migration creates. Every read of a decision is risk_queries.py's
(OPEN-M8-16).

The insert runs ON CONFLICT DO NOTHING with **no conflict target**, so
PostgreSQL skips a row that would violate any unique index, including the two
partial ones that allow one first decision per brief and one successor per
decision. A lost race is therefore a `None`, not an aborted transaction, and
nothing catches an IntegrityError (§0.7.6). A foreign-key violation is not a
conflict and still raises.

Session and transaction are the caller's, matching every Layer 1 repository:
nothing here commits, rolls back, begins, closes or flushes, and nothing logs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import NamedTuple

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.persistence.models import BriefDecision


class NewDecision(NamedTuple):
    """One decision to write. `supersedes_id` is None only for a brief's first decision."""

    brief_id: uuid.UUID
    payload_hash: str
    actor: str
    decision: str
    note: str | None
    decided_at: datetime
    supersedes_id: uuid.UUID | None


def insert_decision(session: Session, row: NewDecision) -> uuid.UUID | None:
    """
    Write a decision, returning its new id, or None when a unique index skipped it.

    None means another first decision of the same brief, or another successor
    of the same decision, is already stored or was committed first by a
    concurrent transaction. The row is never compared, updated or read back.
    """
    statement = (
        insert(BriefDecision)
        .values(
            id=uuid.uuid4(),
            brief_id=row.brief_id,
            payload_hash=row.payload_hash,
            actor=row.actor,
            decision=row.decision,
            note=row.note,
            decided_at=row.decided_at,
            supersedes_id=row.supersedes_id,
        )
        .on_conflict_do_nothing()
        .returning(BriefDecision.id)
    )
    return session.execute(statement).scalar_one_or_none()
