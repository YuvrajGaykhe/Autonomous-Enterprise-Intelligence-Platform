"""
Pydantic request and response models for API v1.

Routes never return ORM objects; every response is one of these models.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class DependencyStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"


class HealthChecks(BaseModel):
    database: DependencyStatus


class HealthResponse(BaseModel):
    """Liveness (the process answered) and readiness (its dependencies are reachable)."""

    status: HealthStatus
    service: str
    version: str
    checks: HealthChecks


class SourceCapabilities(BaseModel):
    supported_entity_types: list[str]
    supports_incremental: bool
    supports_health_check: bool
    read_only: bool


class SourceSummary(BaseModel):
    """A configured source. Connection details (URLs, paths, credentials) are never exposed."""

    source: str
    source_type: str
    capabilities: SourceCapabilities


class SourceListResponse(BaseModel):
    sources: list[SourceSummary]


class ConnectorHealthStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNSUPPORTED = "unsupported"


class SourceHealthResponse(BaseModel):
    """Connector health. Connector diagnostic messages are never exposed.

    error_type is the connector exception class when the check raised.
    """

    source: str
    status: ConnectorHealthStatus
    latency_ms: float | None
    error_type: str | None
    checked_at: datetime
