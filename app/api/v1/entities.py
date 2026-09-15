"""
Canonical entities (spec Sections 10 and 19).

    GET /api/v1/entities/{entity_type}         canonical records (filter, limit/offset)
    GET /api/v1/entities/{entity_type}/{id}    one canonical record by canonical id

One typed pair of routes is registered per canonical entity type, so the
published URLs are exactly the spec's /entities/{entity_type} paths while
OpenAPI documents each type's own record model. An unknown entity type is
an unknown route (404 NOT_FOUND).

Records are the B2 canonical schemas: business fields plus provenance
(source_system, source_entity, source_id, source_updated_at, ingested_at,
ingestion_run_id, record_hash). Raw source payloads live in source_records
and are never read here. Decimal amounts are JSON strings, never floats.

Pagination is explicit and stable: records are ordered by their unique
source identity (source_system, source_entity, source_id) and every page
reports total, limit and offset. Each request reads one read-only snapshot.
"""

from __future__ import annotations

import uuid
from http import HTTPStatus

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import get_sessions, read_snapshot
from app.api.errors import ApiError, ErrorCode, ErrorResponse
from app.api.v1.schemas import ENTITY_PAGES, ENTITY_RECORDS, EntityPage, EntityType
from app.persistence.repositories import entity_queries
from app.schemas.canonical import CanonicalBase

router = APIRouter(prefix="/entities", tags=["entities"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
MAX_OFFSET = 2_147_483_647

INVALID_REQUEST_RESPONSE = {"model": ErrorResponse, "description": "Invalid request parameters"}
ENTITY_NOT_FOUND_RESPONSE = {
    "model": ErrorResponse, "description": "No record of this entity type has this id",
}


def _register(
    entity_type: EntityType,
    record_model: type[CanonicalBase],
    page_model: type[EntityPage],
) -> None:
    label = entity_type.value.replace("_", " ")

    def list_records(
        source_system: str | None = Query(None, min_length=1, max_length=100),
        limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Page size"),
        offset: int = Query(0, ge=0, le=MAX_OFFSET, description="Rows to skip"),
        sessions: sessionmaker[Session] = Depends(get_sessions),
    ) -> EntityPage:
        with read_snapshot(sessions) as session:
            page = entity_queries.list_entities(session, entity_type.value,
                                                source_system=source_system,
                                                limit=limit, offset=offset)
            items = [record_model.model_validate(row) for row in page.items]
        return page_model(items=items, total=page.total, limit=limit, offset=offset)

    def get_record(
        entity_id: uuid.UUID,
        sessions: sessionmaker[Session] = Depends(get_sessions),
    ) -> CanonicalBase:
        with read_snapshot(sessions) as session:
            row = entity_queries.get_entity(session, entity_type.value, entity_id)
            if row is None:
                raise ApiError(HTTPStatus.NOT_FOUND, ErrorCode.ENTITY_NOT_FOUND,
                               "entity does not exist", {"entity_type": entity_type.value})
            return record_model.model_validate(row)

    router.add_api_route(
        f"/{entity_type.value}", list_records, methods=["GET"], response_model=page_model,
        name=f"list_{entity_type.value}", summary=f"List canonical {label}",
        description=f"Canonical {label} in source-identity order.",
        responses={HTTPStatus.UNPROCESSABLE_ENTITY.value: INVALID_REQUEST_RESPONSE},
    )
    router.add_api_route(
        f"/{entity_type.value}/{{entity_id}}", get_record, methods=["GET"],
        response_model=record_model, name=f"get_{entity_type.value}",
        summary=f"Fetch one canonical {label} record",
        description="Look up a record by its canonical id.",
        responses={HTTPStatus.NOT_FOUND.value: ENTITY_NOT_FOUND_RESPONSE,
                   HTTPStatus.UNPROCESSABLE_ENTITY.value: INVALID_REQUEST_RESPONSE},
    )


for _entity_type in EntityType:
    _register(_entity_type, ENTITY_RECORDS[_entity_type], ENTITY_PAGES[_entity_type])
