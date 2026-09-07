"""
SourceRecord operational model.

Represents the raw/source payload boundary. Preserves the original
source data for audit, debugging, and reprocessing. Uses JSONB for
native PostgreSQL JSON storage of source payloads.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SourceRecord(Base):
    __tablename__ = "source_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    source_system: Mapped[str] = mapped_column(String(100), nullable=False)
    source_entity: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)

    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    raw_payload: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Original source payload preserved for audit and debugging",
    )

    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="Hash of the raw payload for change detection",
    )

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_source_records_source_identity",
              "source_system", "source_entity", "source_id"),
        Index("ix_source_records_ingestion_run_id", "ingestion_run_id"),
    )
