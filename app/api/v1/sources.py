"""
Configured sources (spec Section 10).

    GET /api/v1/sources                   configured connectors and capabilities
    GET /api/v1/sources/{source}/health   run one connector's health check

Connector health is separate from application health (spec Section 16) and
is reported with HTTP 200 whatever the outcome: the check itself ran. Only
the outcome, latency and, when the connector raised, the exception class are
returned; connector messages can carry URLs, file paths or source response
bodies and are never exposed or logged.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from http import HTTPStatus

from fastapi import APIRouter, Depends

from app.api.connectors import ConnectorProvider, UnknownSourceError
from app.api.dependencies import get_connectors
from app.api.errors import ApiError, ErrorCode, ErrorResponse
from app.api.v1.schemas import (
    ConnectorHealthStatus,
    SourceCapabilities,
    SourceHealthResponse,
    SourceListResponse,
    SourceSummary,
)
from app.connectors.base import SourceConnector
from app.connectors.types import ConnectorConfigurationError, ConnectorError, ConnectorHealth
from app.ingestion.errors import ConnectorContractError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources", tags=["sources"])

SOURCE_NOT_FOUND_RESPONSE = {"model": ErrorResponse, "description": "The source is not configured"}
SOURCE_MISCONFIGURED_RESPONSE = {
    "model": ErrorResponse, "description": "A source connector configuration is invalid",
}


def resolve_connector(connectors: ConnectorProvider, source: str) -> SourceConnector:
    """The connector for a configured source, or a structured API error."""
    try:
        return connectors.get(source)
    except UnknownSourceError:
        raise ApiError(HTTPStatus.NOT_FOUND, ErrorCode.SOURCE_NOT_FOUND,
                       "source is not configured",
                       {"available_sources": list(connectors.source_names)}) from None
    except ConnectorConfigurationError as exc:
        logger.error("source_misconfigured source=%s failure=%s", source, type(exc).__name__)
        raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, ErrorCode.SOURCE_MISCONFIGURED,
                       "source connector configuration is invalid", {"source": source}) from None


@router.get(
    "",
    response_model=SourceListResponse,
    responses={HTTPStatus.INTERNAL_SERVER_ERROR.value: SOURCE_MISCONFIGURED_RESPONSE},
)
def list_sources(connectors: ConnectorProvider = Depends(get_connectors)) -> SourceListResponse:
    """List configured source connectors and their capabilities."""
    return SourceListResponse(sources=[
        _summary(source, resolve_connector(connectors, source))
        for source in connectors.source_names
    ])


def _summary(source: str, connector: SourceConnector) -> SourceSummary:
    capabilities = connector.capabilities()
    return SourceSummary(
        source=source,
        source_type=connector.source_type,
        capabilities=SourceCapabilities(
            supported_entity_types=list(capabilities.supported_entity_types),
            supports_incremental=capabilities.supports_incremental,
            supports_health_check=capabilities.supports_health_check,
            read_only=capabilities.read_only,
        ),
    )


@router.get(
    "/{source}/health",
    response_model=SourceHealthResponse,
    responses={
        HTTPStatus.NOT_FOUND.value: SOURCE_NOT_FOUND_RESPONSE,
        HTTPStatus.INTERNAL_SERVER_ERROR.value: SOURCE_MISCONFIGURED_RESPONSE,
    },
)
def source_health(
    source: str,
    connectors: ConnectorProvider = Depends(get_connectors),
) -> SourceHealthResponse:
    """Run a connector health check."""
    connector = resolve_connector(connectors, source)
    status, latency_ms, error_type = _check(connector)
    logger.info("connector_health_check source=%s status=%s error_type=%s",
                source, status.value, error_type)
    return SourceHealthResponse(source=source, status=status, latency_ms=latency_ms,
                                error_type=error_type, checked_at=datetime.now(UTC))


def _check(connector: SourceConnector) -> tuple[ConnectorHealthStatus, float | None, str | None]:
    if not connector.capabilities().supports_health_check:
        return ConnectorHealthStatus.UNSUPPORTED, None, None
    try:
        health = connector.health_check()
    except ConnectorError as exc:
        return ConnectorHealthStatus.UNHEALTHY, None, type(exc).__name__
    if not isinstance(health, ConnectorHealth):
        raise ConnectorContractError(
            f"health_check returned {type(health).__name__}, not ConnectorHealth")
    status = ConnectorHealthStatus.HEALTHY if health.healthy is True else \
        ConnectorHealthStatus.UNHEALTHY
    return status, health.latency_ms, None
