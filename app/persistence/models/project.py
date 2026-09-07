"""
Project canonical model.

Spec fields: name, customer_source_id, owner_source_id, status,
             start_date, end_date, budget
is_active: Yes (per project spec)
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


class Project(ProvenanceMixin, Base):
    __tablename__ = "projects"

    # --- Business fields ---
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    budget: Mapped[float | None] = mapped_column(
        Numeric(precision=15, scale=2), nullable=True,
        comment="Project budget in fixed-precision decimal",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # --- Source keys ---
    customer_source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Source-system customer key for this project",
    )
    owner_source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Source-system ID of the project owner (employee)",
    )

    # --- Canonical FK: customer (nullable) ---
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("source_system", "source_entity", "source_id",
                         name="uq_projects_source_identity"),
        Index("ix_projects_ingestion_run_id", "ingestion_run_id"),
        Index("ix_projects_source_updated_at", "source_updated_at"),
        Index("ix_projects_customer_id", "customer_id"),
    )
