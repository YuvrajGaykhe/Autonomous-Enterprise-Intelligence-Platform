"""
One recorded decision on a risk brief (VS-01 M8, plan A18, §0.7.5).

A decision binds an asserted actor's APPROVED or REJECTED to one stored brief
and to the payload hash that brief was generated with. Rows are append-only:
the database rejects every UPDATE and DELETE through a trigger the M8
migration creates, and the repository only inserts (OPEN-M8-4).

A brief's decisions form one linear chain. Its first decision supersedes
nothing (`supersedes_id` NULL); every later one supersedes the current head.
The two partial unique indexes below are what the database can enforce of
that: at most one first decision per brief, and at most one successor per
decision, so no fork can be written, even concurrently. That a predecessor
belongs to the same brief and is the current head is the application's to
check (§0.7.7); the self-FK stays plain (§0.7.18 Q-M8-2).

Both foreign keys RESTRICT, so a decided brief cannot disappear through a
cascade, and neither can a decision another one supersedes (OPEN-M8-5).

No ProvenanceMixin and no `source_system`: a decision is not an ingested
record. `decided_at` is the one timestamp column in any VS-01 table (X7). It
is always supplied by the caller and has no ORM default and no server
default; the supersession chain, not `decided_at`, orders a brief's history.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

#: At most one first decision per brief (§0.7.5).
FIRST_DECISION_INDEX = "uq_brief_decisions_first_decision"

#: At most one successor per decision, so no fork (§0.7.5).
ONE_SUCCESSOR_INDEX = "uq_brief_decisions_one_successor"


class BriefDecision(Base):
    __tablename__ = "brief_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("risk_briefs.id", ondelete="RESTRICT"),
        nullable=False,
        comment="The brief the decision was made on",
    )

    payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="The brief's payload hash the decision is bound to",
    )

    actor: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Who recorded the decision, as supplied; asserted, never verified",
    )

    decision: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="APPROVED or REJECTED",
    )

    note: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
        comment="The actor's optional note",
    )

    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the decision was recorded; always supplied by the caller",
    )

    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brief_decisions.id", ondelete="RESTRICT"),
        nullable=True,
        comment="The decision this one supersedes; NULL for a brief's first decision",
    )

    __table_args__ = (
        Index("ix_brief_decisions_brief_id", "brief_id"),
    )


# The two partial indexes name their predicates through the mapped columns,
# because textual SQL is not used under app/ (G2), so they are declared once
# the columns exist rather than inside __table_args__.
Index(
    FIRST_DECISION_INDEX,
    BriefDecision.brief_id,
    unique=True,
    postgresql_where=BriefDecision.supersedes_id.is_(None),
)
Index(
    ONE_SUCCESSOR_INDEX,
    BriefDecision.supersedes_id,
    unique=True,
    postgresql_where=BriefDecision.supersedes_id.is_not(None),
)
