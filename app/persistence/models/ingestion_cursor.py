"""
IngestionCursor operational model.

Tracks incremental ingestion state per (source_system, source_entity).
The cursor key is a unique pair: one cursor per source+entity combination.

Fields:
  - last_cursor: opaque watermark value (timestamp, offset, page token, etc.)
  - last_successful_run_id: references the most recent successful ingestion run
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IngestionCursor(Base):
    __tablename__ = "ingestion_cursors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    source_system: Mapped[str] = mapped_column(String(100), nullable=False)
    source_entity: Mapped[str] = mapped_column(String(100), nullable=False)

    last_cursor: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Opaque watermark: timestamp, offset, page token, etc.",
    )

    last_successful_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("source_system", "source_entity",
                         name="uq_ingestion_cursors_source_key"),
    )
