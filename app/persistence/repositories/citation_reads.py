"""
The three plain Layer 1 reads the assessment run needs (VS-01 M7, §0.6.5).

    document_texts          the (title, body_text) of named documents, from
                            which the run builds citable text and locates its
                            cited-span phrases (§0.6.8)
    field_nullness          whether a record exists, and whether one named
                            field on it is NULL, for record-citation
                            resolution (§0.6.9)
    ticket_created_at       the created_at of named support tickets: the
                            authorised read path of §0.6.14 OPEN-M7-3, from
                            which the brief's ticket dates and ticket span
                            are derived

Each read goes through Layer 1's ENTITY_MODELS, is constrained to one source
system and to the entity's own `source_entity`, takes strings, and returns
plain values. None of them decides membership: the ids it is given are the
caller's, and the ticket ids in particular are the customer's visible
tickets, which M2 and M5 already decided (§0.2.3). Nothing here names a
domain type or imports a Layer 2 package, so app/persistence stays below
app.intelligence (§0.3.11 D-M4-B2).

The session is the caller's; nothing here writes, commits or logs. Every read
is explicitly ordered, because PostgreSQL guarantees no row order without it.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime
from typing import cast

from sqlalchemy import Table, select
from sqlalchemy.orm import Session

from app.persistence.repositories.canonical import ENTITY_MODELS

#: Layer 1 entity types the two typed reads address.
DOCUMENTS = "documents"
SUPPORT_TICKETS = "support_tickets"


def document_texts(
    session: Session, source_system: str, document_ids: Collection[str]
) -> dict[str, tuple[str | None, str | None]]:
    """
    The `(title, body_text)` of each named document found in `source_system`.

    A document with no row in the source system is absent from the result
    rather than mapped to a placeholder, so the caller can refuse it by name.
    """
    if not document_ids:
        return {}
    table = _table(DOCUMENTS)
    rows = session.execute(
        select(table.c.source_id, table.c.title, table.c.body_text)
        .where(
            table.c.source_system == source_system,
            table.c.source_entity == DOCUMENTS,
            table.c.source_id.in_(sorted(set(document_ids))),
        )
        .order_by(table.c.source_id)
    ).all()
    return {source_id: (title, body_text) for source_id, title, body_text in rows}


def field_nullness(
    session: Session, source_system: str, entity_type: str, source_id: str, field_name: str
) -> bool | None:
    """
    Whether a record's named field is NULL, or None when no such record exists.

    The entity type and field name are a citation's, and both were validated
    against Layer 1's canonical contract when the citation was built.
    """
    table = _table(entity_type)
    row = session.execute(
        select(table.c[field_name].is_(None))
        .where(
            table.c.source_system == source_system,
            table.c.source_entity == entity_type,
            table.c.source_id == source_id,
        )
        .order_by(table.c.source_id)
    ).one_or_none()
    return None if row is None else bool(row[0])


def ticket_created_at(
    session: Session, source_system: str, ticket_ids: Collection[str]
) -> dict[str, datetime | None]:
    """
    The `created_at` of each named support ticket found in `source_system`.

    A NULL `created_at` is returned as None and a ticket with no row is
    absent, so the caller can tell the two apart and refuse either by name.
    """
    if not ticket_ids:
        return {}
    table = _table(SUPPORT_TICKETS)
    rows = session.execute(
        select(table.c.source_id, table.c.created_at)
        .where(
            table.c.source_system == source_system,
            table.c.source_entity == SUPPORT_TICKETS,
            table.c.source_id.in_(sorted(set(ticket_ids))),
        )
        .order_by(table.c.source_id)
    ).tuples().all()
    return dict(rows)


def _table(entity_type: str) -> Table:
    return cast(Table, ENTITY_MODELS[entity_type].__table__)
