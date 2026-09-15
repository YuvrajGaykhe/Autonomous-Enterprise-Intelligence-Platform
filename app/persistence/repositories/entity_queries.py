"""
Read-only queries over canonical entities for the API.

Pages of one canonical table and lookups by canonical id. Pages are ordered
by source identity (source_system, source_entity, source_id): the order is
total because the uq_<table>_source_identity constraint makes the identity
unique, and it does not change when E1 updates a record, so re-ingestion
never reshuffles pages.

Like every repository: the caller owns the session and transaction; nothing
here writes, commits, or logs.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.persistence.models.mixins import ProvenanceMixin
from app.persistence.repositories.canonical import ENTITY_MODELS
from app.persistence.repositories.run_queries import QueryPage


def _model(entity_type: str) -> Any:
    model = ENTITY_MODELS.get(entity_type)
    if model is None:
        raise ValueError(f"unknown canonical entity type {entity_type!r}")
    return model


def list_entities(
    session: Session,
    entity_type: str,
    *,
    source_system: str | None,
    limit: int,
    offset: int,
) -> QueryPage[ProvenanceMixin]:
    """Canonical records of one type in source-identity order."""
    model = _model(entity_type)
    conditions = []
    if source_system is not None:
        conditions.append(model.source_system == source_system)
    total = session.execute(
        select(func.count()).select_from(model).where(*conditions)).scalar_one()
    rows = session.scalars(
        select(model).where(*conditions)
        .order_by(model.source_system, model.source_entity, model.source_id)
        .limit(limit).offset(offset)
    ).all()
    return QueryPage(items=list(rows), total=total)


def get_entity(
    session: Session,
    entity_type: str,
    entity_id: uuid.UUID,
) -> ProvenanceMixin | None:
    """One canonical record of the given type, or None."""
    model = _model(entity_type)
    return cast(ProvenanceMixin | None, session.get(model, entity_id))
