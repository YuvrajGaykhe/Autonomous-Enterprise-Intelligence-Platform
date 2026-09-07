"""
Provenance mixin shared by all canonical entities.

Every canonical record must retain enough metadata to identify its
source system, source record, ingestion run, and timestamps.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class ProvenanceMixin:
    """
    Columns shared by every canonical entity table.

    Provides: id, source_system, source_entity, source_id,
    source_updated_at, ingested_at, ingestion_run_id, record_hash.

    is_active is NOT included here because it applies only to
    employees, customers, deals, and projects.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    source_system: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Logical source name, e.g. csv_demo, odoo_mock",
    )

    source_entity: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Original entity/table/resource type in the source system",
    )

    source_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Stable source-system identifier for this record",
    )

    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp from the source when available",
    )

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When this version entered Layer 1",
    )

    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Run that produced/updated this record",
    )

    record_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Deterministic hash of normalized business fields (excludes provenance)",
    )
