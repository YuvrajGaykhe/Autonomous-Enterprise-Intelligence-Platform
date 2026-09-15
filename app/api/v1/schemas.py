"""
Pydantic request and response models for API v1.

Routes never return ORM objects; every response is one of these models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from app.ingestion.orchestrator import ENTITY_ORDER, MAX_PAGE_SIZE, EntityStatus
from app.persistence.repositories.runs import RunStatus
from app.schemas.canonical import (
    CanonicalBase,
    CustomerCanonical,
    DealCanonical,
    DocumentCanonical,
    EmployeeCanonical,
    OrganizationCanonical,
    ProjectCanonical,
    SupportTicketCanonical,
)


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


class EntityType(StrEnum):
    """Canonical entity types, in dependency order."""

    ORGANIZATIONS = "organizations"
    EMPLOYEES = "employees"
    CUSTOMERS = "customers"
    DEALS = "deals"
    PROJECTS = "projects"
    SUPPORT_TICKETS = "support_tickets"
    DOCUMENTS = "documents"


class IngestionRunRequest(BaseModel):
    """Start a synchronous ingestion run.

    Connection details (URLs, directories, credentials) cannot be supplied:
    the source is built from its committed configuration. entities omitted
    means every entity the source provides; parents always run first.
    dry_run is accepted for contract compatibility, but only false is
    supported.
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=100)
    entities: list[EntityType] | None = Field(default=None, min_length=1,
                                              max_length=len(ENTITY_ORDER))
    mode: Literal["full"] = "full"
    dry_run: StrictBool = False
    page_size: StrictInt = Field(default=100, ge=1, le=MAX_PAGE_SIZE)


class EntityRunResult(BaseModel):
    """One entity's outcome. failure is an exception class name or error code."""

    entity_type: str
    status: EntityStatus
    records_fetched: int
    records_inserted: int
    records_updated: int
    records_unchanged: int
    records_rejected: int
    records_failed: int
    warnings: int
    batches_committed: int
    batches_failed: int
    failure: str | None


class IngestionRunCreatedResponse(IngestionRunResponse):
    """The completed run, plus the per-entity results known only at execution time."""

    batches_committed: int
    entities: list[EntityRunResult]


class EntityPage(BaseModel):
    """One limit/offset page of canonical records in source-identity order."""

    total: int
    limit: int
    offset: int


class OrganizationListResponse(EntityPage):
    items: list[OrganizationCanonical]


class EmployeeListResponse(EntityPage):
    items: list[EmployeeCanonical]


class CustomerListResponse(EntityPage):
    items: list[CustomerCanonical]


class DealListResponse(EntityPage):
    items: list[DealCanonical]


class ProjectListResponse(EntityPage):
    items: list[ProjectCanonical]


class SupportTicketListResponse(EntityPage):
    items: list[SupportTicketCanonical]


class DocumentListResponse(EntityPage):
    items: list[DocumentCanonical]


# Record and page models for each canonical entity type.
ENTITY_RECORDS: dict[EntityType, type[CanonicalBase]] = {
    EntityType.ORGANIZATIONS: OrganizationCanonical,
    EntityType.EMPLOYEES: EmployeeCanonical,
    EntityType.CUSTOMERS: CustomerCanonical,
    EntityType.DEALS: DealCanonical,
    EntityType.PROJECTS: ProjectCanonical,
    EntityType.SUPPORT_TICKETS: SupportTicketCanonical,
    EntityType.DOCUMENTS: DocumentCanonical,
}
ENTITY_PAGES: dict[EntityType, type[EntityPage]] = {
    EntityType.ORGANIZATIONS: OrganizationListResponse,
    EntityType.EMPLOYEES: EmployeeListResponse,
    EntityType.CUSTOMERS: CustomerListResponse,
    EntityType.DEALS: DealListResponse,
    EntityType.PROJECTS: ProjectListResponse,
    EntityType.SUPPORT_TICKETS: SupportTicketListResponse,
    EntityType.DOCUMENTS: DocumentListResponse,
}
