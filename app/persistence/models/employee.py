"""
Employee canonical model.

Spec fields: name, email, department, title, manager_source_id,
             status, hire_date
is_active: Yes (per project spec)
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.persistence.models.mixins import ProvenanceMixin


class Employee(ProvenanceMixin, Base):
    __tablename__ = "employees"

    # --- Business fields ---
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manager_source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Source-system ID of the manager; may not resolve to a canonical employee",
    )
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # --- Canonical FK: organization ---
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    organization = relationship("Organization", back_populates="employees", lazy="select")

    __table_args__ = (
        UniqueConstraint("source_system", "source_entity", "source_id",
                         name="uq_employees_source_identity"),
        Index("ix_employees_ingestion_run_id", "ingestion_run_id"),
        Index("ix_employees_source_updated_at", "source_updated_at"),
        Index("ix_employees_email", "email"),
        Index("ix_employees_organization_id", "organization_id"),
    )
