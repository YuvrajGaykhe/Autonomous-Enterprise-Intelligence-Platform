"""
Canonical entity persistence keyed by source identity.

Primary identity (spec Section 7): (source_system, source_entity, source_id),
enforced by the uq_<table>_source_identity constraint on every canonical
table. upsert() writes rows with INSERT ... ON CONFLICT ON CONSTRAINT ... DO
UPDATE, so repeated writes of one identity can never create a duplicate and
an existing row keeps its primary key.

This module does not decide WHETHER a record changed; the E1 reconciliation
planner does that from load_states() and passes only rows that must be
written.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import cast

from sqlalchemy import Table, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.database import Base
from app.persistence.models import (
    Customer,
    Deal,
    Document,
    Employee,
    Organization,
    Project,
    SupportTicket,
)
from app.schemas.canonical import CanonicalBase

ENTITY_MODELS: Mapping[str, type[Base]] = MappingProxyType({
    "organizations": Organization,
    "employees": Employee,
    "customers": Customer,
    "deals": Deal,
    "projects": Project,
    "support_tickets": SupportTicket,
    "documents": Document,
})

IDENTITY_COLUMNS = ("source_system", "source_entity", "source_id")

# Upserts are chunked to bound statement size.
_UPSERT_CHUNK = 500


@dataclass(frozen=True)
class PersistedState:
    """The persisted facts reconciliation compares against."""

    id: uuid.UUID
    record_hash: str
    source_updated_at: datetime | None
    references: Mapping[str, uuid.UUID | None]


def _table(entity_type: str) -> Table:
    model = ENTITY_MODELS.get(entity_type)
    if model is None:
        raise ValueError(f"unknown canonical entity type {entity_type!r}")
    return cast(Table, model.__table__)


def reference_fields(entity_type: str) -> tuple[str, ...]:
    """Canonical FK columns of an entity table, sorted by name."""
    table = _table(entity_type)
    return tuple(sorted(column.name for column in table.columns if column.foreign_keys))


def load_states(
    session: Session,
    entity_type: str,
    source_system: str,
    source_ids: Collection[str],
) -> dict[str, PersistedState]:
    """Return persisted state by source_id for one source system and entity."""
    if not source_ids:
        return {}
    table = _table(entity_type)
    references = reference_fields(entity_type)
    statement = (
        select(
            table.c.source_id, table.c.id, table.c.record_hash, table.c.source_updated_at,
            *(table.c[name] for name in references),
        )
        .where(
            table.c.source_system == source_system,
            table.c.source_entity == entity_type,
            table.c.source_id.in_(sorted(set(source_ids))),
        )
    )
    states = {}
    for row in session.execute(statement):
        states[row[0]] = PersistedState(
            id=row[1],
            record_hash=row[2],
            source_updated_at=row[3],
            references=MappingProxyType(dict(zip(references, row[4:], strict=True))),
        )
    return states


def canonical_row(
    entity_type: str,
    record: CanonicalBase,
    references: Mapping[str, uuid.UUID | None],
) -> dict[str, object]:
    """Build a full table row from a canonical record plus E1-resolved references."""
    table = _table(entity_type)
    expected = reference_fields(entity_type)
    if tuple(sorted(references)) != expected:
        raise ValueError(
            f"{entity_type} requires references {list(expected)}, got {sorted(references)}"
        )
    if record.source_entity != entity_type:
        raise ValueError(
            f"record source_entity {record.source_entity!r} does not match {entity_type!r}"
        )
    row: dict[str, object] = {}
    for column in table.columns:
        if column.name in references:
            row[column.name] = references[column.name]
        else:
            row[column.name] = getattr(record, column.name)
    return row


def upsert(session: Session, entity_type: str, rows: Sequence[Mapping[str, object]]) -> None:
    """Insert or update rows by source identity, in deterministic source_id order."""
    table = _table(entity_type)
    columns = {column.name for column in table.columns}
    identities = set()
    for row in rows:
        if set(row) != columns:
            raise ValueError(f"{entity_type} rows must provide exactly the table columns")
        if row["source_entity"] != entity_type:
            raise ValueError(f"row source_entity does not match {entity_type!r}")
        identity = (row["source_system"], row["source_id"])
        if identity in identities:
            raise ValueError("rows contain a duplicate source identity")
        identities.add(identity)
    ordered = sorted(rows, key=lambda row: (str(row["source_system"]), str(row["source_id"])))
    updatable = [name for name in sorted(columns) if name not in ("id", *IDENTITY_COLUMNS)]
    for start in range(0, len(ordered), _UPSERT_CHUNK):
        statement = insert(table).values(list(ordered[start:start + _UPSERT_CHUNK]))
        statement = statement.on_conflict_do_update(
            constraint=f"uq_{table.name}_source_identity",
            set_={name: statement.excluded[name] for name in updatable},
        )
        session.execute(statement)
