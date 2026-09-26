"""
Risk assessments, briefs and the human decision on a brief (VS-01 M8, §0.7.8).

    POST /api/v1/risk/assessments                     run an assessment
    GET  /api/v1/risk/assessments                     list assessments (filters, limit/offset)
    GET  /api/v1/risk/assessments/{assessment_id}     one assessment, its positions, every brief
    GET  /api/v1/risk/briefs/{brief_id}               one stored brief and its decision status
    POST /api/v1/risk/briefs/{brief_id}/decision      record a decision on a brief
    GET  /api/v1/risk/briefs/{brief_id}/decisions     the brief's decisions, first to head

Assessing answers 201 when any result was created and 200 when every result
already existed; creation is read from each result's own flag, never
inferred. The results keep M7's ranking order.

The list is ordered by the repository (§0.7.8): newest as_of first, then by
scope and versions, then by the stored ranking key, then by id. A brief is
read back exactly as stored: its payload is an opaque object, and nothing is
re-hashed, re-rendered or re-resolved during a GET. Its status is the stored
column, which is never updated; decision_status is derived from the decision
history.

Each POST owns one transaction, opened by `with sessions() as session,
session.begin()` inside a try whose except clauses sit outside the with, so a
failure is rolled back before it is mapped to an error and nothing a failed
request wrote is durable. Each GET reads one read-only snapshot. The decision
time comes from the overridable clock dependency, read once per decision
before its transaction; this module is the only place M8 reads a clock.

A value a POST body names that cannot be resolved is 422; 404 is reserved for
a missing path resource. Every other failure is the generic 500.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from http import HTTPStatus

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import get_sessions, read_snapshot
from app.api.errors import ApiError, ErrorCode, ErrorResponse
from app.api.v1.schemas import (
    AssessmentBrief,
    AssessmentDetailResponse,
    AssessmentListItem,
    AssessmentListResponse,
    AssessmentPosition,
    AssessmentRunItem,
    AssessmentRunRequest,
    AssessmentRunResponse,
    BriefResponse,
    DecisionHistoryResponse,
    DecisionRequest,
    DecisionResponse,
    RiskDecision,
    RiskDecisionStatus,
)
from app.decisions.approval import (
    Decision,
    DecisionConflictError,
    DecisionRecord,
    PayloadHashConflictError,
    UnknownBriefError,
    decision_history,
    decision_status,
    record_decision,
)
from app.decisions.assessment import run_assessment
from app.decisions.payload import payload_citations
from app.intelligence import RiskBand, ScopeResolutionError
from app.persistence.repositories import risk_queries
from app.relationships import UnknownCustomerError

router = APIRouter(prefix="/risk", tags=["risk"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
MAX_OFFSET = 2_147_483_647

INVALID_REQUEST_RESPONSE = {"model": ErrorResponse, "description": "Invalid request parameters"}
ASSESSMENT_NOT_FOUND_RESPONSE = {
    "model": ErrorResponse, "description": "The risk assessment does not exist",
}
BRIEF_NOT_FOUND_RESPONSE = {"model": ErrorResponse, "description": "The risk brief does not exist"}
ASSESSMENT_REPEATED_RESPONSE = {
    "model": AssessmentRunResponse,
    "description": "Every result already existed; nothing was created",
}
ASSESSMENT_REJECTED_RESPONSE = {
    "model": ErrorResponse,
    "description": "Invalid request, a customer outside the assessment scope, or a null as_of "
                   "the scope cannot resolve; nothing is written",
}
DECISION_CONFLICT_RESPONSE = {
    "model": ErrorResponse,
    "description": "payload_hash does not match the brief's decision payload "
                   "(PAYLOAD_HASH_CONFLICT), or the decision does not extend the brief's "
                   "decision history (DECISION_CONFLICT); nothing is written",
}
SYSTEM_FAILURE_RESPONSE = {
    "model": ErrorResponse, "description": "A system failure; nothing is written",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def get_clock() -> Callable[[], datetime]:
    """The clock a decision's time is read from. Tests replace it through dependency_overrides."""
    return _utc_now


@router.post(
    "/assessments",
    status_code=HTTPStatus.CREATED,
    response_model=AssessmentRunResponse,
    responses={HTTPStatus.OK.value: ASSESSMENT_REPEATED_RESPONSE,
               HTTPStatus.UNPROCESSABLE_ENTITY.value: ASSESSMENT_REJECTED_RESPONSE,
               HTTPStatus.INTERNAL_SERVER_ERROR.value: SYSTEM_FAILURE_RESPONSE},
)
def run_assessments(
    body: AssessmentRunRequest,
    response: Response,
    sessions: sessionmaker[Session] = Depends(get_sessions),
) -> AssessmentRunResponse:
    """Assess every customer in scope, or the one named; 201 if anything was created."""
    try:
        with sessions() as session, session.begin():
            results = run_assessment(session, as_of=body.as_of,
                                     source_system=body.source_system,
                                     customer_source_id=body.customer_source_id)
    except UnknownCustomerError:
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, ErrorCode.CUSTOMER_NOT_FOUND,
                       "customer is not in the assessment scope") from None
    except ScopeResolutionError:
        raise ApiError(HTTPStatus.UNPROCESSABLE_ENTITY, ErrorCode.SCOPE_UNRESOLVED,
                       "as_of is null and the scope has no support ticket to resolve it "
                       "from") from None
    if not any(result.created for result in results):
        response.status_code = HTTPStatus.OK
    return AssessmentRunResponse(items=[
        AssessmentRunItem(assessment_id=result.assessment_id, created=result.created,
                          brief_id=result.brief_id, payload_hash=result.payload_hash)
        for result in results
    ])


@router.get(
    "/assessments",
    response_model=AssessmentListResponse,
    responses={HTTPStatus.UNPROCESSABLE_ENTITY.value: INVALID_REQUEST_RESPONSE},
)
def list_assessments(
    as_of: date | None = None,
    band: RiskBand | None = None,
    executive_worthy: bool | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Page size"),
    offset: int = Query(0, ge=0, le=MAX_OFFSET, description="Rows to skip"),
    sessions: sessionmaker[Session] = Depends(get_sessions),
) -> AssessmentListResponse:
    """Assessments matching every given filter, each with the ids of its briefs."""
    with read_snapshot(sessions) as session:
        page = risk_queries.list_assessments(
            session, as_of=as_of, band=None if band is None else band.value,
            executive_worthy=executive_worthy, limit=limit, offset=offset)
        brief_ids = risk_queries.brief_ids_for(session, [item.id for item in page.items])
    return AssessmentListResponse(
        items=[AssessmentListItem(**item._asdict(), brief_ids=brief_ids.get(item.id, []))
               for item in page.items],
        total=page.total, limit=limit, offset=offset,
    )


@router.get(
    "/assessments/{assessment_id}",
    response_model=AssessmentDetailResponse,
    responses={HTTPStatus.NOT_FOUND.value: ASSESSMENT_NOT_FOUND_RESPONSE,
               HTTPStatus.UNPROCESSABLE_ENTITY.value: INVALID_REQUEST_RESPONSE},
)
def get_assessment(
    assessment_id: uuid.UUID,
    sessions: sessionmaker[Session] = Depends(get_sessions),
) -> AssessmentDetailResponse:
    """One assessment, its positions by ordinal and every one of its briefs."""
    with read_snapshot(sessions) as session:
        assessment = risk_queries.get_assessment(session, assessment_id)
        if assessment is None:
            raise ApiError(HTTPStatus.NOT_FOUND, ErrorCode.ASSESSMENT_NOT_FOUND,
                           "risk assessment does not exist")
        positions = risk_queries.positions_for(session, assessment_id)
        briefs = risk_queries.briefs_for(session, assessment_id)
    return AssessmentDetailResponse(
        **assessment._asdict(),
        positions=[AssessmentPosition(**position._asdict()) for position in positions],
        briefs=[AssessmentBrief(**brief._asdict()) for brief in briefs],
    )


@router.get(
    "/briefs/{brief_id}",
    response_model=BriefResponse,
    responses={HTTPStatus.NOT_FOUND.value: BRIEF_NOT_FOUND_RESPONSE,
               HTTPStatus.UNPROCESSABLE_ENTITY.value: INVALID_REQUEST_RESPONSE},
)
def get_brief(
    brief_id: uuid.UUID,
    sessions: sessionmaker[Session] = Depends(get_sessions),
) -> BriefResponse:
    """A stored brief as written, its citations, and its derived decision status."""
    with read_snapshot(sessions) as session:
        brief = risk_queries.get_brief(session, brief_id)
        if brief is None:
            raise ApiError(HTTPStatus.NOT_FOUND, ErrorCode.BRIEF_NOT_FOUND,
                           "risk brief does not exist")
        status = decision_status(decision_history(session, brief_id))
    return BriefResponse(
        id=brief.id,
        assessment_id=brief.assessment_id,
        status=brief.status,
        decision_status=RiskDecisionStatus(status.value),
        policy_version=brief.policy_version,
        template_version=brief.template_version,
        payload_hash=brief.payload_hash,
        payload=brief.decision_payload,
        narrative=brief.narrative,
        citations=[citation.to_payload() for citation in payload_citations(brief.decision_payload)],
    )


@router.post(
    "/briefs/{brief_id}/decision",
    status_code=HTTPStatus.CREATED,
    response_model=DecisionResponse,
    responses={HTTPStatus.NOT_FOUND.value: BRIEF_NOT_FOUND_RESPONSE,
               HTTPStatus.CONFLICT.value: DECISION_CONFLICT_RESPONSE,
               HTTPStatus.UNPROCESSABLE_ENTITY.value: INVALID_REQUEST_RESPONSE,
               HTTPStatus.INTERNAL_SERVER_ERROR.value: SYSTEM_FAILURE_RESPONSE},
)
def record_brief_decision(
    brief_id: uuid.UUID,
    body: DecisionRequest,
    sessions: sessionmaker[Session] = Depends(get_sessions),
    clock: Callable[[], datetime] = Depends(get_clock),
) -> DecisionResponse:
    """Record one decision on the stored brief, extending its history."""
    decided_at = clock()
    try:
        with sessions() as session, session.begin():
            record = record_decision(
                session, brief_id=brief_id, payload_hash=body.payload_hash, actor=body.actor,
                decision=Decision(body.decision.value), note=body.note,
                supersedes_id=body.supersedes_id, decided_at=decided_at)
    except UnknownBriefError:
        raise ApiError(HTTPStatus.NOT_FOUND, ErrorCode.BRIEF_NOT_FOUND,
                       "risk brief does not exist") from None
    except PayloadHashConflictError as conflict:
        raise ApiError(HTTPStatus.CONFLICT, ErrorCode.PAYLOAD_HASH_CONFLICT,
                       "payload_hash does not match the brief's decision payload",
                       {"reason": conflict.reason.value}) from None
    except DecisionConflictError as conflict:
        raise ApiError(HTTPStatus.CONFLICT, ErrorCode.DECISION_CONFLICT,
                       "the decision does not extend the brief's decision history",
                       {"reason": conflict.reason.value}) from None
    return _decision_response(record)


@router.get(
    "/briefs/{brief_id}/decisions",
    response_model=DecisionHistoryResponse,
    responses={HTTPStatus.NOT_FOUND.value: BRIEF_NOT_FOUND_RESPONSE,
               HTTPStatus.UNPROCESSABLE_ENTITY.value: INVALID_REQUEST_RESPONSE},
)
def list_brief_decisions(
    brief_id: uuid.UUID,
    sessions: sessionmaker[Session] = Depends(get_sessions),
) -> DecisionHistoryResponse:
    """The brief's decisions in chain order, from its first decision to its head."""
    try:
        with read_snapshot(sessions) as session:
            history = decision_history(session, brief_id)
    except UnknownBriefError:
        raise ApiError(HTTPStatus.NOT_FOUND, ErrorCode.BRIEF_NOT_FOUND,
                       "risk brief does not exist") from None
    return DecisionHistoryResponse(items=[_decision_response(record) for record in history])


def _decision_response(record: DecisionRecord) -> DecisionResponse:
    return DecisionResponse(
        id=record.id,
        brief_id=record.brief_id,
        payload_hash=record.payload_hash,
        actor=record.actor,
        decision=RiskDecision(record.decision.value),
        note=record.note,
        decided_at=record.decided_at,
        supersedes_id=record.supersedes_id,
    )
