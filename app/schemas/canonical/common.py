"""
Common canonical schema definitions.

Provides the shared provenance base that all canonical entity schemas
inherit from. Uses Pydantic v2 with from_attributes=True for ORM
compatibility.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CanonicalBase(BaseModel):
    """
    Universal provenance contract for all canonical entities.

    Every canonical record carries these fields to identify its
    source system, ingestion provenance, and content identity.

    Fields:
        id: Internal canonical primary key (UUID).
        source_system: Logical source name (e.g. csv_demo, odoo_mock).
        source_entity: Original entity/table/resource type in the source.
        source_id: Stable source-system identifier for this record.
        source_updated_at: Timestamp from the source, when available.
        ingested_at: When this version entered Layer 1.
        ingestion_run_id: Run that produced/updated the record.
        record_hash: Deterministic hash of normalized business fields
                     (excludes provenance metadata like ingested_at).
    """

    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
    )

    id: uuid.UUID
    source_system: str
    source_entity: str
    source_id: str
    source_updated_at: datetime | None = None
    ingested_at: datetime
    ingestion_run_id: uuid.UUID
    record_hash: str
