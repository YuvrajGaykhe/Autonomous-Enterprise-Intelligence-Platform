"""
SupportTicket canonical model.

Spec fields: customer_source_id, priority, status, category,
             subject, description, created_at, resolved_at,
             assignee_source_id
is_active: NO (per project spec)
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.persistence.models.mixins import ProvenanceMixin


class SupportTicket(ProvenanceMixin, Base):
    __tablename__ = "support_tickets"

    # --- Business fields ---
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Ticket creation timestamp from the source system",
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # --- Source keys ---
    customer_source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Source-system customer key for this ticket",
    )
    assignee_source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Source-system ID of the assigned employee",
    )

    # --- Canonical FK: customer (nullable) ---
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    customer = relationship("Customer", back_populates="support_tickets", lazy="select")

    __table_args__ = (
        UniqueConstraint("source_system", "source_entity", "source_id",
                         name="uq_support_tickets_source_identity"),
        Index("ix_support_tickets_ingestion_run_id", "ingestion_run_id"),
        Index("ix_support_tickets_source_updated_at", "source_updated_at"),
        Index("ix_support_tickets_customer_id", "customer_id"),
        Index("ix_support_tickets_created_at", "created_at"),
    )
