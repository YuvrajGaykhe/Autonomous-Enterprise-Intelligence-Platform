"""
Persistence for derived Document to Customer links (VS-01 M4, §0.3.10.3).

This module is **persistence only**, and that is an architectural boundary
rather than a stylistic preference (§0.3.11 D-M4-B1, D-M4-B2).

    It writes link rows, and it reads them back joined to `documents`.

    It constructs no DerivedLink and no LinkedDocument, and it imports
    neither app.intelligence nor app.evidence. Reconstructing a DerivedLink
    needs EntityRef, LinkBasis, Evidence and DocumentCitation, all of which
    are M1's; importing them here would make app/persistence depend on
    app.intelligence, which plan §0.3.9 T2 forbids and
    tests/unit/test_m1_boundary.py enforces over app/, scripts/, migrations/
    and docker/. Domain reconstruction is app/evidence/documents.py's, and
    only its.

The two row types below are **row projections, not domain types**: every
field is a str or an int, none carries M1 vocabulary, and neither validates
anything. They name the columns a caller reads and writes so the seam is
typed rather than a bare tuple. The repository does not return a competing
abstraction over LinkedDocument, because it returns no abstraction at all.

It performs **no derivation** — it never matches text — and **no rendering**.

Session and transaction are the caller's, matching every Layer 1 repository:
nothing here calls commit, rollback or begin, and nothing flushes, because
no caller needs the generated primary keys inside the same call.

Conflict behaviour is DO NOTHING, never DO UPDATE. §0.3.4 states that a link
is never updated in place, so the canonical upsert pattern would contradict
it. The conflict is resolved by the database against the named constraint,
not by an application-level pre-existence check, which is what makes a
concurrent duplicate insert a read rather than a race.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, NamedTuple, cast

from sqlalchemy import CursorResult, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.persistence.models import Customer, Document
from app.persistence.models.document_customer_link import (
    IDENTITY_CONSTRAINT,
    DocumentCustomerLink,
)

#: Layer 1 source_entity values this repository joins against.
DOCUMENTS = "documents"
CUSTOMERS = "customers"


class LinkRow(NamedTuple):
    """
    One link to write, keyed by source identity rather than by surrogate key.

    The caller derives links over source ids; resolving those to the
    `documents.id` and `customers.id` surrogate keys is a persistence
    concern, so it happens here and the evidence layer never handles a UUID.
    Ordering is tuple ordering, which is what makes the insert byte-stable.
    """

    document_source_id: str
    customer_source_id: str
    basis: str
    matched_token: str
    match_start: int
    match_end: int
    linker_version: str
    layer1_fingerprint: str


class PersistedLink(NamedTuple):
    """
    One persisted link row, joined to the Layer 1 document it cites.

    `document_type` is read from `documents` at join time and is **never**
    stored on the link row, so a Layer 1 correction is reflected without
    re-deriving anything. `source_system` likewise comes from the joined
    rows: the link table carries no such column, because both foreign keys
    point at rows that already have one.
    """

    document_source_id: str
    customer_source_id: str
    basis: str
    matched_token: str
    match_start: int
    match_end: int
    linker_version: str
    layer1_fingerprint: str
    source_system: str
    document_type: str | None


def insert_links(session: Session, source_system: str, rows: Sequence[LinkRow]) -> int:
    """
    Write link rows, returning how many were actually inserted.

    The return value is how a caller observes plan A27.8's "re-run inserts
    nothing": a repeated derivation over an unchanged snapshot conflicts on
    every row and returns 0, while a changed `layer1_fingerprint` or
    `linker_version` inserts a fresh set and leaves the earlier rows intact.

    A row naming a document or customer outside `source_system` is dropped
    rather than written, which is the structural half of source-system
    isolation: the identity maps below are built per source system, so a
    cross-source link has no surrogate key to point at.
    """
    if not rows:
        return 0
    documents = _identity_map(session, Document, source_system, DOCUMENTS)
    customers = _identity_map(session, Customer, source_system, CUSTOMERS)
    values = [
        {
            "id": uuid.uuid4(),
            "document_id": documents[row.document_source_id],
            "customer_id": customers[row.customer_source_id],
            "basis": row.basis,
            "matched_token": row.matched_token,
            "match_start": row.match_start,
            "match_end": row.match_end,
            "linker_version": row.linker_version,
            "layer1_fingerprint": row.layer1_fingerprint,
        }
        for row in sorted(rows)
        if row.document_source_id in documents and row.customer_source_id in customers
    ]
    if not values:
        return 0
    statement = insert(DocumentCustomerLink).values(values).on_conflict_do_nothing(
        constraint=IDENTITY_CONSTRAINT
    )
    # A DML execute returns a CursorResult, whose rowcount is the number of
    # rows the database actually inserted - the ones ON CONFLICT DO NOTHING
    # did not skip. Session.execute is typed as returning the wider Result.
    result = cast("CursorResult[Any]", session.execute(statement))
    return int(result.rowcount)


def read_links(
    session: Session, source_system: str, customer_source_id: str
) -> tuple[PersistedLink, ...]:
    """
    Every persisted link for one customer, joined to its document.

    Both joins are constrained to `source_system`, so a link can never be
    read across source systems even if one were somehow written.
    """
    rows = session.execute(
        select(
            Document.source_id,
            Customer.source_id,
            DocumentCustomerLink.basis,
            DocumentCustomerLink.matched_token,
            DocumentCustomerLink.match_start,
            DocumentCustomerLink.match_end,
            DocumentCustomerLink.linker_version,
            DocumentCustomerLink.layer1_fingerprint,
            Document.source_system,
            Document.document_type,
        )
        .join(Document, DocumentCustomerLink.document_id == Document.id)
        .join(Customer, DocumentCustomerLink.customer_id == Customer.id)
        .where(
            Document.source_system == source_system,
            Document.source_entity == DOCUMENTS,
            Customer.source_system == source_system,
            Customer.source_entity == CUSTOMERS,
            Customer.source_id == customer_source_id,
        )
        .order_by(
            Document.source_id,
            DocumentCustomerLink.basis,
            DocumentCustomerLink.match_start,
        )
    ).all()
    return tuple(PersistedLink(*row) for row in rows)


def _identity_map(
    session: Session, model: type[Document] | type[Customer], source_system: str, entity: str
) -> dict[str, uuid.UUID]:
    """Source id to surrogate key, for one entity type within one source system."""
    rows = session.execute(
        select(model.source_id, model.id).where(
            model.source_system == source_system,
            model.source_entity == entity,
        )
    ).all()
    return dict(rows)  # type: ignore[arg-type]
