"""
One persisted risk brief (VS-01 M7, plan A17, A18, §0.6.5).

A brief holds the hashed decision payload, its digest, the narrative
rendered from it, and the two versions the payload itself does not carry as
a column: `policy_version`, which selects the brief rather than the
assessment, and `template_version`, which is stored and never hashed.

Identity is `(assessment_id, payload_hash)`. Several briefs per assessment
are normal, one per distinct payload; none is marked current and none
supersedes another (§0.6.6). A template-only change leaves the hash
unchanged, so the existing brief is read back and its narrative and
template_version are never updated.

`status` defaults to DRAFT in the ORM and in the database. Every other value
belongs to the approval flow (M8).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

#: The database-enforced identity of a brief (plan A18, §0.6.5).
IDENTITY_CONSTRAINT = "uq_risk_briefs_identity"

#: The status every brief is written with.
DRAFT_STATUS = "DRAFT"


class RiskBrief(Base):
    __tablename__ = "risk_briefs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("risk_assessments.id", ondelete="CASCADE"),
        nullable=False,
        comment="The assessment the brief was generated for",
    )

    policy_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="The conflict-policy version the brief was reconciled under",
    )

    template_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="The narrative template version; stored, never hashed",
    )

    decision_payload: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
        comment="The hashed decision payload",
    )

    payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 of the canonical decision payload",
    )

    narrative: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The narrative rendered from the payload; a view, not hashed",
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DRAFT_STATUS,
        server_default=DRAFT_STATUS,
        comment="The brief's approval status",
    )

    __table_args__ = (
        UniqueConstraint("assessment_id", "payload_hash", name=IDENTITY_CONSTRAINT),
        Index("ix_risk_briefs_assessment_id", "assessment_id"),
    )
