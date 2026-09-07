"""
Organization canonical model.

Represents the enterprise boundary / tenant. The demo system has one
organization row (e.g. "Acme Corp"). is_active is NOT included per
the project specification.

Spec fields: name, industry, country, status
"""

from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.persistence.models.mixins import ProvenanceMixin


class Organization(ProvenanceMixin, Base):
    __tablename__ = "organizations"

    # --- Business fields ---
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Relationships ---
    employees = relationship("Employee", back_populates="organization", lazy="select")

    __table_args__ = (
        UniqueConstraint("source_system", "source_entity", "source_id",
                         name="uq_organizations_source_identity"),
        Index("ix_organizations_ingestion_run_id", "ingestion_run_id"),
        Index("ix_organizations_source_updated_at", "source_updated_at"),
    )
