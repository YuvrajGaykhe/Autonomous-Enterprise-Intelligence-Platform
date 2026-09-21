"""
Derived Document to Customer link (VS-01 M4, plan A18, §0.3.10.3).

The only mechanism in VS-01 by which a Document and a Customer are ever
related. Layer 1 is untouched: `documents` gains no customer reference and
`customers` gains no document reference, so the association lives here or
it does not exist at all.

No ProvenanceMixin. A derived link has no source system, no ingestion run
and no record_hash — it is not an ingested record. Its provenance is the
pair of stamps the plan requires instead: the Layer 1 snapshot it was
derived from (`layer1_fingerprint`) and the matching rules that derived it
(`linker_version`). Both sit in the unique key, so a link produced under a
superseded snapshot or linker is identifiable rather than silently stale.

Identity is `(document_id, customer_id, basis, linker_version,
layer1_fingerprint)`. `basis` is in the key because the grain is one row per
(document, customer, basis): a pair matching on both ID_TOKEN and EXACT_NAME
yields two rows carrying two different matched tokens, and collapsing them
would destroy one. `as_of`, `rules_version` and `policy_version` are
deliberately absent: no link depends on the evaluation date, the band table
or the conflict policy, so including them would mint duplicate rows for
identical content.

Re-derivation therefore appends or does nothing; it never updates and never
deletes. There is no computed_at, no superseded_by, no validity interval and
no history table (§0.3.4).

No source_system column: both foreign keys point at rows that already carry
one and a link may never cross source systems, so the pair determines it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

#: The database-enforced identity of a derived link (plan A18, §0.3.4).
IDENTITY_CONSTRAINT = "uq_document_customer_links_identity"


class DocumentCustomerLink(Base):
    __tablename__ = "document_customer_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        comment="The document whose text asserts the relationship",
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        comment="The customer the document's text names",
    )

    basis: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="LinkBasis: how the match was made (ID_TOKEN or EXACT_NAME)",
    )

    matched_token: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="The matched text exactly as the document writes it",
    )

    match_start: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Half-open span start in the document's citable text",
    )

    match_end: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Half-open span end in the document's citable text",
    )

    linker_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="The matching rules that derived this link",
    )

    layer1_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="The Layer 1 snapshot this link was derived from",
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id", "customer_id", "basis", "linker_version", "layer1_fingerprint",
            name=IDENTITY_CONSTRAINT,
        ),
        # documents_for() looks a customer up; the unique index leads with
        # document_id, which does not serve that access path.
        Index("ix_document_customer_links_customer_id", "customer_id"),
        Index("ix_document_customer_links_document_id", "document_id"),
    )
