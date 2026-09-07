"""
IngestionError operational model.

Stores structured connector/validation/rejected-record errors.
Severity levels: ERROR, WARNING, INFO.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class IngestionError(Base):
    __tablename__ = "ingestion_errors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    source_system: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_entity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Source record identifier, if known",
    )

    severity: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="ERROR, WARNING, or INFO",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Machine-readable error classification",
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Extended detail, raw record excerpt, or stack trace",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # --- Relationships ---
    ingestion_run = relationship("IngestionRun", back_populates="errors", lazy="select")

    __table_args__ = (
        Index("ix_ingestion_errors_ingestion_run_id", "ingestion_run_id"),
        Index("ix_ingestion_errors_severity", "severity"),
    )
