"""
IngestionRun operational model.

One row per ingestion execution. Tracks source, status, timing,
record counts, and error summary.

Status values: SUCCESS, PARTIAL_SUCCESS, FAILED, NOOP
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    source_system: Mapped[str] = mapped_column(String(100), nullable=False)
    source_entity: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Entity type being ingested; NULL if ingesting all entities",
    )

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="RUNNING",
        comment="SUCCESS, PARTIAL_SUCCESS, FAILED, NOOP, RUNNING",
    )
    mode: Mapped[str] = mapped_column(
        String(50), nullable=False, default="full",
        comment="full or incremental",
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # --- Counts ---
    records_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_warnings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    error_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Human-readable summary of errors if any",
    )

    # --- Relationships ---
    errors = relationship("IngestionError", back_populates="ingestion_run", lazy="select")

    __table_args__ = (
        Index("ix_ingestion_runs_source_system", "source_system"),
        Index("ix_ingestion_runs_status", "status"),
        Index("ix_ingestion_runs_started_at", "started_at"),
    )
