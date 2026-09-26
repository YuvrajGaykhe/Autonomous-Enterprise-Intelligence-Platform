"""
Pydantic request and response models for API v1.

Routes never return ORM objects; every response is one of these models.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

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


class RunStatusCounts(BaseModel):
    """Runs per status; every status is always present."""

    RUNNING: int
    SUCCESS: int
    PARTIAL_SUCCESS: int
    FAILED: int
    NOOP: int


class ErrorSeverityCounts(BaseModel):
    """ingestion_errors rows per severity; every severity is always present."""

    ERROR: int
    WARNING: int
    INFO: int


class CanonicalRecordCounts(BaseModel):
    """Canonical records per entity type; every type is always present."""

    organizations: int
    employees: int
    customers: int
    deals: int
    projects: int
    support_tickets: int
    documents: int


class RunReference(BaseModel):
    run_id: uuid.UUID
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None


class IngestionMetrics(BaseModel):
    """Operational ingestion metrics derived from persisted runs, errors and records.

    records_failed_total = records_fetched_total - (records_inserted_total
    + records_updated_total + records_unchanged_total + records_rejected_total).
    batches_failed_total counts BATCH_FAILED errors; connector_request_failures_total
    counts CONNECTOR_UNHEALTHY and CONNECTOR_FAILED errors; validation_errors_total
    counts ERROR findings other than those E1 system codes.
    ingestion_duration_seconds_total sums finished_at - started_at over finished runs.
    """

    runs_total: int
    runs_by_status: RunStatusCounts
    records_fetched_total: int
    records_raw_persisted_total: int
    records_inserted_total: int
    records_updated_total: int
    records_unchanged_total: int
    records_rejected_total: int
    records_failed_total: int
    warnings_total: int
    batches_failed_total: int
    errors_by_severity: ErrorSeverityCounts
    connector_request_failures_total: int
    validation_errors_total: int
    ingestion_duration_seconds_total: float
    canonical_records: CanonicalRecordCounts


class SourceIngestionMetrics(IngestionMetrics):
    """One source system's metrics. last_successful_run is the newest SUCCESS,
    PARTIAL_SUCCESS or NOOP run."""

    source_system: str
    last_run: RunReference | None
    last_successful_run: RunReference | None


class DurationSummary(BaseModel):
    """Finished runs (count) and their summed duration in seconds (sum)."""

    count: int
    sum: float


class ProcessIngestionMetrics(BaseModel):
    """Counters for ingestion runs executed by this API process since started_at.

    They start at zero when the process starts and are not persisted; runs of
    other processes (other API workers, the ingest-demo command) are not
    included. runs_by_status RUNNING counts runs still in progress. Record
    counts come from committed batches (a failed batch's records count as
    fetched); every rejected record is one validation error;
    connector_request_failures_total counts failed health checks and failed
    page fetches; ingestion_duration_seconds covers finished runs.
    """

    started_at: datetime
    runs_total: int
    runs_by_status: RunStatusCounts
    records_fetched_total: int
    records_inserted_total: int
    records_updated_total: int
    records_unchanged_total: int
    records_rejected_total: int
    connector_request_failures_total: int
    validation_errors_total: int
    ingestion_duration_seconds: DurationSummary


class IngestionMetricsResponse(BaseModel):
    """Database-derived metrics for every source system combined and per source system
    (sorted by name), plus the in-process counters of the API process answering."""

    totals: IngestionMetrics
    sources: list[SourceIngestionMetrics]
    process: ProcessIngestionMetrics


# ---------------------------------------------------------------------------
# Risk assessments, briefs and decisions (VS-01 M8, §0.7.8)
#
# This module imports no Layer 2 package. Where a model needs M8's decision
# vocabulary it declares a mirrored enum, which a test pins equal to
# app.decisions.approval's. `band` is the stored band name, a plain string.
# ---------------------------------------------------------------------------


class RiskDecision(StrEnum):
    """What a decision says about a brief. Mirrors app.decisions.approval.Decision."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RiskDecisionStatus(StrEnum):
    """A brief's derived decision state. Mirrors app.decisions.approval.DecisionStatus."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AssessmentRunRequest(BaseModel):
    """Assess every customer in scope, or the one named, and persist the results.

    as_of is required and may be null, which asks for the scope's fallback
    date explicitly. The run is unpinned: no expected fingerprint is taken,
    and no rules, linker or policy override is accepted.
    """

    model_config = ConfigDict(extra="forbid")

    as_of: date | None
    source_system: str = Field(default="csv_demo", min_length=1, max_length=100)
    customer_source_id: str | None = Field(default=None, min_length=1, max_length=255)


class AssessmentRunItem(BaseModel):
    """One customer's result: its assessment, whether this run created it, and its brief."""

    assessment_id: uuid.UUID
    created: bool
    brief_id: uuid.UUID | None
    payload_hash: str | None


class AssessmentRunResponse(BaseModel):
    """One item per customer assessed, in ranking order."""

    items: list[AssessmentRunItem]


class AssessmentFields(BaseModel):
    """An assessment's stored columns. customer_source_id is null once its customer is gone."""

    id: uuid.UUID
    customer_source_id: str | None
    as_of: date
    source_system: str
    layer1_fingerprint: str
    rules_version: int
    linker_version: str
    band: str
    executive_worthy: bool
    ranking_key: tuple[int, int, int, str]


class AssessmentListItem(AssessmentFields):
    """An assessment and the ids of every brief generated for it."""

    brief_ids: list[uuid.UUID]


class AssessmentListResponse(BaseModel):
    """One limit/offset page: newest as_of first, then by scope and versions, then by
    ranking key, then by id."""

    items: list[AssessmentListItem]
    total: int
    limit: int
    offset: int


class AssessmentPosition(BaseModel):
    """One position a function stated, as stored, with its evidence."""

    ordinal: int
    function: str
    stance: str
    proposed_action: str
    object_ref: str
    rationale: str
    citations: list[dict[str, Any]]


class AssessmentBrief(BaseModel):
    """One brief of an assessment. None is current: every brief is listed."""

    id: uuid.UUID
    policy_version: int
    template_version: str
    payload_hash: str


class AssessmentDetailResponse(AssessmentFields):
    """An assessment with its satisfied rules, signals, positions by ordinal and every brief."""

    satisfied_rules: list[str]
    signals: dict[str, Any]
    positions: list[AssessmentPosition]
    briefs: list[AssessmentBrief]


class BriefResponse(BaseModel):
    """A stored brief, read back as written: nothing is re-rendered or re-resolved.

    status is the stored column and is never updated; decision_status is
    derived from the brief's decision history. payload is the stored decision
    payload as an opaque object, and citations are the payload's own distinct
    citations in ascending wire order.
    """

    id: uuid.UUID
    assessment_id: uuid.UUID
    status: str
    decision_status: RiskDecisionStatus
    policy_version: int
    template_version: str
    payload_hash: str
    payload: dict[str, Any]
    narrative: str
    citations: list[dict[str, Any]]


class DecisionRequest(BaseModel):
    """Record a human decision on a stored brief.

    actor is recorded exactly as supplied; it is asserted, never
    authenticated, and never validated as an email address. supersedes_id is
    null only for the brief's first decision, and otherwise names its current
    head.
    """

    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1, max_length=255)
    decision: RiskDecision
    note: str | None = Field(default=None, max_length=2000)
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    supersedes_id: uuid.UUID | None = None


class DecisionResponse(BaseModel):
    """One recorded decision."""

    id: uuid.UUID
    brief_id: uuid.UUID
    payload_hash: str
    actor: str
    decision: RiskDecision
    note: str | None
    decided_at: datetime
    supersedes_id: uuid.UUID | None


class DecisionHistoryResponse(BaseModel):
    """A brief's decisions in chain order, first to head."""

    items: list[DecisionResponse]
