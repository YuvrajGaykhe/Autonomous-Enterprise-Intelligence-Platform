"""
Ingestion runs (spec Section 10).

    POST /api/v1/ingestion/runs                   start a run (synchronous)
    GET  /api/v1/ingestion/runs                   list runs (filters, limit/offset)
    GET  /api/v1/ingestion/runs/{run_id}          run detail and counts
    GET  /api/v1/ingestion/runs/{run_id}/errors   structured errors (safe findings)

POST executes the run through E1 before responding and returns 201 with the
completed run, whatever its status (a FAILED run is still a created run).
Requests that are invalid, ask for dry_run, name an unknown source, or that
E1 rejects create no run (422). A system failure during the run leaves the
run FAILED in the database and returns a generic 500; the request ID is
logged beside the run ID when the run finishes.

Pagination is explicit and stable: runs are ordered newest first
(started_at, id descending) and errors by (created_at, id); every page
reports total, limit and offset. Each request reads one read-only snapshot.

Errors never expose raw records, raw values or stored D1/D2 messages; see
app.api.ingestion_errors.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from http import HTTPStatus

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session, sessionmaker

from app.api.connectors import ConnectorProvider
from app.api.dependencies import (
    get_connectors,
    get_process_metrics,
    get_sessions,
    read_snapshot,
)
from app.api.errors import ApiError, ErrorCode, ErrorResponse
from app.api.ingestion_errors import safe_findings, safe_message
from app.api.request_id import request_id_of
from app.api.v1.schemas import (
    EntityRunResult,
    ErrorFinding,
    ErrorListResponse,
    ErrorSeverity,
    IngestionErrorResponse,
    IngestionRunCreatedResponse,
    IngestionRunRequest,
    IngestionRunResponse,
    RunListResponse,
)
from app.api.v1.sources import resolve_connector
from app.core.logging import log_event
from app.ingestion.errors import IngestionCode, IngestionRequestError
from app.ingestion.orchestrator import IngestionRequest, RunSummary, run_ingestion
from app.observability.metrics import ProcessMetrics
from app.persistence.models import IngestionError, IngestionRun
from app.persistence.repositories import run_queries
from app.persistence.repositories.runs import RunStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion/runs", tags=["ingestion"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
MAX_OFFSET = 2_147_483_647

INVALID_REQUEST_RESPONSE = {"model": ErrorResponse, "description": "Invalid request parameters"}
RUN_NOT_FOUND_RESPONSE = {"model": ErrorResponse, "description": "The ingestion run does not exist"}
START_REJECTED_RESPONSE = {
    "model": ErrorResponse,
    "description": "Invalid or unsupported request, unknown source, or a request the source "
                   "cannot serve; no run is created",
}
START_FAILED_RESPONSE = {
    "model": ErrorResponse,
    "description": "Source misconfigured (no run is created) or a system failure during the run "
                   "(the run is marked FAILED)",
}


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    response_model=IngestionRunCreatedResponse,
    responses={HTTPStatus.UNPROCESSABLE_ENTITY.value: START_REJECTED_RESPONSE,
               HTTPStatus.INTERNAL_SERVER_ERROR.value: START_FAILED_RESPONSE},
)
def start_run(
    body: IngestionRunRequest,
    request: Request,
    response: Response,
    sessions: sessionmaker[Session] = Depends(get_sessions),
    connectors: ConnectorProvider = Depends(get_connectors),
    process_metrics: ProcessMetrics = Depends(get_process_metrics),
) -> IngestionRunCreatedResponse:
    """Run one ingestion to completion and return the run."""
    if body.dry_run:
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, ErrorCode.UNSUPPORTED_OPTION,
                       "dry_run is not supported: every Layer 1 ingestion run persists its "
                       "results", {"option": "dry_run"})
    if body.source not in connectors.source_names:
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, ErrorCode.SOURCE_NOT_FOUND,
                       "source is not configured",
                       {"available_sources": list(connectors.source_names)})
    connector = resolve_connector(connectors, body.source)
    entities = None if body.entities is None else [entity.value for entity in body.entities]
    request_id = request_id_of(request)
    log_event(logger, logging.INFO, "ingestion_run_requested", request_id=request_id,
              source=body.source, entities="all" if entities is None else ",".join(entities))
    try:
        summary = run_ingestion(connector, sessions, IngestionRequest(
            entities=entities, mode=body.mode, page_size=body.page_size),
            observer=process_metrics)
    except IngestionRequestError as exc:
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, ErrorCode.INVALID_INGESTION_REQUEST,
                       "ingestion request is not valid for this source",
                       {"source": body.source, "reason": str(exc)}) from None
    log_event(logger, logging.INFO, "ingestion_run_finished", request_id=request_id,
              run_id=summary.run_id, status=summary.status.value)

    with read_snapshot(sessions) as session:
        run = run_responses(session, [_existing_run(session, summary.run_id)])[0]
    response.headers["Location"] = str(request.app.url_path_for(
        "get_run", run_id=str(summary.run_id)))
    return IngestionRunCreatedResponse(
        **run.model_dump(),
        batches_committed=summary.batches_committed,
        entities=_entity_results(summary),
    )


def _entity_results(summary: RunSummary) -> list[EntityRunResult]:
    return [
        EntityRunResult(
            entity_type=entity.entity_type,
            status=entity.status,
            records_fetched=entity.counts.fetched,
            records_inserted=entity.counts.inserted,
            records_updated=entity.counts.updated,
            records_unchanged=entity.counts.unchanged,
            records_rejected=entity.counts.rejected,
            records_failed=entity.records_failed,
            warnings=entity.counts.warnings,
            batches_committed=entity.batches_committed,
            batches_failed=entity.batches_failed,
            failure=entity.failure,
        )
        for entity in summary.entities
    ]


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
