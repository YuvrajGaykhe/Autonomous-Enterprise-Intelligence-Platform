"""
One customer's persisted risk assessment (VS-01 M7, plan A18, §0.6.5).

A row records what the run decided for one customer at one scope: the band,
the satisfied rule ids, the signal values, M6's executive-worthiness verdict
and M6's ranking key, each stored verbatim and never recomputed here.

No ProvenanceMixin. An assessment is not an ingested record: it has no source
record, no ingestion run and no record_hash. Its provenance is the identity
key itself, which holds exactly the inputs an assessment row depends on
(§0.6.6): the customer, `as_of`, `source_system`, `layer1_fingerprint`,
`rules_version` and `linker_version`. `policy_version` is deliberately absent,
because neither this row nor its positions depend on the conflict policy;
the brief does, and a policy change appends a brief under the same
assessment.

`customer_id` is the one nullable column. It follows the non-destructive FK
philosophy of Layer 1's customer-linked rows (`ondelete="SET NULL"`, as in
deal.py), and SET NULL needs a nullable column. Layer 1 never deletes a
canonical row, so the NULL case is unreachable on the pipeline.

No timestamp column: an assessment is a pure function of its key (§A24).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

#: The database-enforced identity of an assessment (plan A18, §0.6.5).
IDENTITY_CONSTRAINT = "uq_risk_assessments_identity"


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        comment="The assessed customer",
    )

    as_of: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="The evaluation date",
    )

    source_system: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="The one source system the assessment was computed over",
    )

    layer1_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="The Layer 1 snapshot the assessment was computed from",
    )

    rules_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="The risk-rule configuration version",
    )

    linker_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="The document-linker version",
    )

    band: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="The assigned risk band",
    )

    executive_worthy: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="The reconciliation's executive-worthiness verdict, verbatim",
    )

    signals: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
        comment="The signal values the band was assigned from",
    )

    satisfied_rules: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
        comment="The satisfied band-rule ids, in band-table order",
    )

    ranking_key: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
        comment="The reconciliation's ranking key, verbatim",
    )

    __table_args__ = (
        UniqueConstraint(
            "customer_id", "as_of", "source_system", "layer1_fingerprint",
            "rules_version", "linker_version",
            name=IDENTITY_CONSTRAINT,
        ),
        Index("ix_risk_assessments_customer_id", "customer_id"),
    )
