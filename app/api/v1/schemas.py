"""
Pydantic request and response models for API v1.

Routes never return ORM objects; every response is one of these models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from app.persistence.repositories.runs import RunStatus


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


class IngestionRunResponse(BaseModel):
    """A run's state and quality counts.

    records_fetched = records_inserted + records_updated + records_unchanged
    + records_rejected + records_failed. records_raw_persisted counts captured
    source_records rows; batches_failed counts rolled-back batches.
    """

    run_id: uuid.UUID
    source_system: str
    source_entity: str | None
    mode: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None
    records_fetched: int
    records_raw_persisted: int
    records_inserted: int
    records_updated: int
    records_unchanged: int
    records_rejected: int
    records_failed: int
    warnings: int
    batches_failed: int
    error_summary: str | None


class RunListResponse(BaseModel):
    items: list[IngestionRunResponse]
    total: int
    limit: int
    offset: int


class ErrorSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ErrorFinding(BaseModel):
    """A field-level finding. Source values are never included."""

    code: str
    field_name: str | None
    severity: ErrorSeverity | None
    message: str


class IngestionErrorResponse(BaseModel):
    """A structured ingestion error with a safe message (no raw records or values)."""

    id: uuid.UUID
    severity: ErrorSeverity
    code: str | None
    message: str
    source_system: str | None
    source_entity: str | None
    source_id: str | None
    created_at: datetime
    findings: list[ErrorFinding]


class ErrorListResponse(BaseModel):
    items: list[IngestionErrorResponse]
    total: int
    limit: int
    offset: int
