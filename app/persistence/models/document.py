"""
Document canonical model.

Spec fields: title, document_type, body_text, source_uri,
             owner_source_id, created_at, updated_at
is_active: NO (per project spec)

body_text stores the full extracted document body in PostgreSQL
for future RAG/institutional memory. It is NOT reduced to metadata.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.persistence.models.mixins import ProvenanceMixin


class Document(ProvenanceMixin, Base):
    __tablename__ = "documents"

    # --- Business fields ---
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    body_text: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Full extracted document body for future RAG",
    )
    source_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    owner_source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Source-system ID of the document owner",
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Document creation timestamp from the source system",
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Document last-updated timestamp from the source system",
    )

    __table_args__ = (
        UniqueConstraint("source_system", "source_entity", "source_id",
                         name="uq_documents_source_identity"),
        Index("ix_documents_ingestion_run_id", "ingestion_run_id"),
        Index("ix_documents_source_updated_at", "source_updated_at"),
    )
