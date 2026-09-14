"""
GET /api/v1/health — application liveness and readiness (spec Section 16).

Any response proves the API process is alive. Readiness additionally
requires PostgreSQL: the endpoint answers 200 "healthy" when a trivial query
succeeds and 503 "unhealthy" when the database cannot be reached. Connector
health is deliberately separate (GET /api/v1/sources/{source}/health): a
healthy application does not imply every source is reachable.
"""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import get_sessions
from app.api.v1.schemas import DependencyStatus, HealthChecks, HealthResponse, HealthStatus
from app.core.config import SERVICE_NAME, SERVICE_VERSION

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={HTTPStatus.SERVICE_UNAVAILABLE.value: {
        "model": HealthResponse, "description": "PostgreSQL is not reachable",
    }},
)
def health_check(
    response: Response,
    sessions: sessionmaker[Session] = Depends(get_sessions),
) -> HealthResponse:
    """Liveness and readiness probe."""
    database = _database_status(sessions)
    ready = database is DependencyStatus.OK
    if not ready:
        response.status_code = HTTPStatus.SERVICE_UNAVAILABLE
    return HealthResponse(
        status=HealthStatus.HEALTHY if ready else HealthStatus.UNHEALTHY,
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        checks=HealthChecks(database=database),
    )


def _database_status(sessions: sessionmaker[Session]) -> DependencyStatus:
    try:
        with sessions() as session:
            session.execute(select(1))
    except (DBAPIError, PoolTimeoutError) as exc:
        logger.warning("readiness_check_failed dependency=database failure=%s",
                       type(exc).__name__)
        return DependencyStatus.UNAVAILABLE
    return DependencyStatus.OK
