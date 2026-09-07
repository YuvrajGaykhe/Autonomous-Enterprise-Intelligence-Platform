"""
Deal canonical model.

Spec fields: name, customer_source_id, owner_source_id, stage,
             amount, currency, probability, expected_close_date
is_active: Yes (per project spec)

CRITICAL: customer_id (canonical FK) MUST be nullable. If the source
customer key cannot be resolved, the deal is kept with customer_id=NULL
and the original customer_source_id preserved for later resolution.
"""

import uuid
from datetime import date

from sqlalchemy import (
    Boolean, Date, ForeignKey, Index, Numeric, String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.persistence.models.mixins import ProvenanceMixin


class Deal(ProvenanceMixin, Base):
    __tablename__ = "deals"

    # --- Business fields ---
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    amount: Mapped[float | None] = mapped_column(
        Numeric(precision=15, scale=2), nullable=True,
        comment="Deal value in fixed-precision decimal (never float)",
    )
    currency: Mapped[str | None] = mapped_column(
        String(10), nullable=True,
        comment="ISO currency code, e.g. USD, INR",
    )
    probability: Mapped[float | None] = mapped_column(
        Numeric(precision=5, scale=2), nullable=True,
        comment="Win probability as percentage (0.00-100.00)",
    )
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # --- Source keys (preserved even when canonical FK is NULL) ---
    customer_source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Original source customer key; preserved for unresolved FK tracking",
    )
    owner_source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Source-system ID of the deal owner (employee)",
    )

    # --- Canonical FK: customer (nullable per unresolved-FK requirement) ---
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    customer = relationship("Customer", back_populates="deals", lazy="select")

    __table_args__ = (
        UniqueConstraint("source_system", "source_entity", "source_id",
                         name="uq_deals_source_identity"),
        Index("ix_deals_ingestion_run_id", "ingestion_run_id"),
        Index("ix_deals_source_updated_at", "source_updated_at"),
        Index("ix_deals_customer_id", "customer_id"),
    )
