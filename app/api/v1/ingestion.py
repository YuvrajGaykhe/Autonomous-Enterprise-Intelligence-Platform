"""
Ingestion runs (spec Section 10).

    GET /api/v1/ingestion/runs                    list runs (filters, limit/offset)
    GET /api/v1/ingestion/runs/{run_id}           run detail and counts
    GET /api/v1/ingestion/runs/{run_id}/errors    structured errors (safe findings)

Pagination is explicit and stable: runs are ordered newest first
(started_at, id descending) and errors by (created_at, id); every page
reports total, limit and offset. Each request reads one read-only snapshot.

Errors never expose raw records, raw values or stored D1/D2 messages; see
app.api.ingestion_errors.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from http import HTTPStatus

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import get_sessions, read_snapshot
from app.api.errors import ApiError, ErrorCode, ErrorResponse
from app.api.ingestion_errors import safe_findings, safe_message
from app.api.v1.schemas import (
    ErrorFinding,
    ErrorListResponse,
    ErrorSeverity,
    IngestionErrorResponse,
    IngestionRunResponse,
    RunListResponse,
)
from app.ingestion.errors import IngestionCode
from app.persistence.models import IngestionError, IngestionRun
from app.persistence.repositories import run_queries
from app.persistence.repositories.runs import RunStatus

router = APIRouter(prefix="/ingestion/runs", tags=["ingestion"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
MAX_OFFSET = 2_147_483_647

INVALID_REQUEST_RESPONSE = {"model": ErrorResponse, "description": "Invalid request parameters"}
RUN_NOT_FOUND_RESPONSE = {"model": ErrorResponse, "description": "The ingestion run does not exist"}


@router.get(
    "",
    response_model=RunListResponse,
    responses={HTTPStatus.UNPROCESSABLE_ENTITY.value: INVALID_REQUEST_RESPONSE},
)
def list_runs(
    source_system: str | None = Query(None, min_length=1, max_length=100),
    status: RunStatus | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Page size"),
    offset: int = Query(0, ge=0, le=MAX_OFFSET, description="Rows to skip"),
    sessions: sessionmaker[Session] = Depends(get_sessions),
) -> RunListResponse:
    """List ingestion runs, newest first."""
    with read_snapshot(sessions) as session:
        page = run_queries.list_runs(session, source_system=source_system,
                                     status=None if status is None else status.value,
                                     limit=limit, offset=offset)
        items = run_responses(session, page.items)
    return RunListResponse(items=items, total=page.total, limit=limit, offset=offset)


@router.get(
    "/{run_id}",
    response_model=IngestionRunResponse,
    responses={HTTPStatus.NOT_FOUND.value: RUN_NOT_FOUND_RESPONSE,
               HTTPStatus.UNPROCESSABLE_ENTITY.value: INVALID_REQUEST_RESPONSE},
)
def get_run(
    run_id: uuid.UUID,
    sessions: sessionmaker[Session] = Depends(get_sessions),
) -> IngestionRunResponse:
    """Run detail and counts."""
    with read_snapshot(sessions) as session:
        return run_responses(session, [_existing_run(session, run_id)])[0]


@router.get(
    "/{run_id}/errors",
    response_model=ErrorListResponse,
    responses={HTTPStatus.NOT_FOUND.value: RUN_NOT_FOUND_RESPONSE,
               HTTPStatus.UNPROCESSABLE_ENTITY.value: INVALID_REQUEST_RESPONSE},
)
def list_run_errors(
    run_id: uuid.UUID,
    severity: ErrorSeverity | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Page size"),
    offset: int = Query(0, ge=0, le=MAX_OFFSET, description="Rows to skip"),
    sessions: sessionmaker[Session] = Depends(get_sessions),
) -> ErrorListResponse:
    """A run's structured errors with safe messages and field-level findings."""
    with read_snapshot(sessions) as session:
        _existing_run(session, run_id)
        page = run_queries.list_errors(session, run_id,
                                       severity=None if severity is None else severity.value,
                                       limit=limit, offset=offset)
        items = [_error_response(row) for row in page.items]
    return ErrorListResponse(items=items, total=page.total, limit=limit, offset=offset)


def _existing_run(session: Session, run_id: uuid.UUID) -> IngestionRun:
    run = run_queries.get_run(session, run_id)
    if run is None:
        raise ApiError(HTTPStatus.NOT_FOUND, ErrorCode.RUN_NOT_FOUND,
                       "ingestion run does not exist")
    return run


def run_responses(session: Session, runs: Sequence[IngestionRun]) -> list[IngestionRunResponse]:
    """Response models for runs, with per-run aggregates fetched in two grouped queries."""
    run_ids = [run.id for run in runs]
    raw = run_queries.count_raw_records(session, run_ids)
    failed_batches = run_queries.count_errors(session, run_ids,
                                              error_code=IngestionCode.BATCH_FAILED.value)
    return [
        IngestionRunResponse(
            run_id=run.id,
            source_system=run.source_system,
            source_entity=run.source_entity,
            mode=run.mode,
            status=RunStatus(run.status),
            started_at=run.started_at,
            finished_at=run.finished_at,
            records_fetched=run.records_fetched,
            records_raw_persisted=raw.get(run.id, 0),
            records_inserted=run.records_inserted,
            records_updated=run.records_updated,
            records_unchanged=run.records_unchanged,
            records_rejected=run.records_rejected,
            records_failed=run_queries.records_failed(run),
            warnings=run.records_warnings,
            batches_failed=failed_batches.get(run.id, 0),
            error_summary=run.error_summary,
        )
        for run in runs
    ]


def _error_response(row: IngestionError) -> IngestionErrorResponse:
    return IngestionErrorResponse(
        id=row.id,
        severity=ErrorSeverity(row.severity),
        code=row.error_code,
        message=safe_message(row.error_code, row.message),
        source_system=row.source_system,
        source_entity=row.source_entity,
        source_id=row.source_id,
        created_at=row.created_at,
        findings=[
            ErrorFinding(code=finding.code, field_name=finding.field_name,
                         severity=None if finding.severity is None
                         else ErrorSeverity(finding.severity),
                         message=finding.message)
            for finding in safe_findings(row.detail, row.message)
        ],
    )
