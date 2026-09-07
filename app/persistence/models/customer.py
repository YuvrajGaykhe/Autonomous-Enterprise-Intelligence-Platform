"""
Customer canonical model.

Spec fields: name, email, segment, industry, status,
             owner_source_id, created_at
is_active: Yes (per project spec)
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.persistence.models.mixins import ProvenanceMixin


class Customer(ProvenanceMixin, Base):
    __tablename__ = "customers"

    # --- Business fields ---
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    segment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    owner_source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Source-system ID of the account owner (employee)",
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Creation timestamp from the source system",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # --- Relationships ---
    deals = relationship("Deal", back_populates="customer", lazy="select")
    support_tickets = relationship("SupportTicket", back_populates="customer", lazy="select")

    __table_args__ = (
        UniqueConstraint("source_system", "source_entity", "source_id",
                         name="uq_customers_source_identity"),
        Index("ix_customers_ingestion_run_id", "ingestion_run_id"),
        Index("ix_customers_source_updated_at", "source_updated_at"),
        Index("ix_customers_email", "email"),
    )
