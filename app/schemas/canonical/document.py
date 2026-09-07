"""
Document canonical schema.

Spec fields: title, document_type, body_text, source_uri,
             owner_source_id, created_at, updated_at
is_active: No (not meaningful for Document per spec)

body_text stores full document content (Text type, not limited).
No embeddings/vectors/RAG metadata in B2; those belong to
future intelligence layers.
"""

from datetime import datetime

from app.schemas.canonical.common import CanonicalBase


class DocumentCanonical(CanonicalBase):
    """
    Source-neutral canonical representation of a Document.

    Supports future RAG and institutional memory. body_text
    accepts full textual content with no artificial length limit.
    """

    title: str | None = None
    document_type: str | None = None
    body_text: str | None = None
    source_uri: str | None = None
    owner_source_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
