"""
One persisted position of a risk assessment (VS-01 M7, plan A18, §0.6.5).

Every position both analysts emitted is stored, each once and unmodified, at
its index in the reconciliation's ordered positions (`ordinal`, from 0).
Prevailing, uncontested and overruled positions alike: there is no
disposition, prevailing or dissent flag, because which position prevailed
depends on the conflict policy and lives in the brief's payload instead.

Exactly the nine directed columns. There is no `confidence` column: the
frozen position contract has no confidence field, so none is derived or
manufactured (§0.6.14 OPEN-M7-1).

Identity is `(assessment_id, function, object_ref, proposed_action)`. It
bounds identical positions only, so an assessment may hold several positions
per function.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

#: The database-enforced identity of a position (plan A18, §0.6.5).
IDENTITY_CONSTRAINT = "uq_risk_positions_identity"


class RiskPosition(Base):
    __tablename__ = "risk_positions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("risk_assessments.id", ondelete="CASCADE"),
        nullable=False,
        comment="The assessment that owns this position",
    )

    ordinal: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="The position's index in the ordered positions, from 0",
    )

    function: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="The function that stated the position",
    )

    stance: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="The function's stance toward the contested object",
    )

    proposed_action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="The proposed action-catalogue id",
    )

    object_ref: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="The source id of the object the action applies to",
    )

    rationale: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The position's stated rationale",
    )

    citations: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
        comment="The position's evidence: each item's kind, citation and any rule id",
    )

    __table_args__ = (
        UniqueConstraint(
            "assessment_id", "function", "object_ref", "proposed_action",
            name=IDENTITY_CONSTRAINT,
        ),
        Index("ix_risk_positions_assessment_id", "assessment_id"),
    )
