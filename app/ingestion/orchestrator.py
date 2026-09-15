"""
E1 ingestion run orchestrator (spec Section 9 end-to-end workflow).

    create run -> health-check source -> for each entity in dependency order:
        fetch page -> D1 + D2 quality gate -> commit batch (one transaction)
        -> next page until the source is exhausted
    -> finalize run status and counts

Entities are processed in ENTITY_ORDER so every parent entity is committed
before the children that reference it, whatever order the request lists.

Failure model:
    DATA failure     D2 quarantines the record; the batch continues.
    SOURCE failure   ConnectorError while fetching a page. Authentication and
                     configuration errors stop the run ("fail fast"); any
                     other connector error fails the current entity and the
                     run continues with the next entity.
    BATCH failure    IntegrityError or DataError while committing a batch.
                     The batch is rolled back and recorded as BATCH_FAILED
                     with the SQLSTATE only; its entity stops, so the
                     entity's checkpoint never passes the failed batch.
    SYSTEM failure   Everything else: database connectivity, a broken
                     connector contract, non-JSON payloads, quality gate
                     system errors, programming errors. The run is marked
                     FAILED and the exception propagates unchanged.

Run status: FAILED if the health check failed or nothing committed while an
entity failed; PARTIAL_SUCCESS if an entity failed or any record was
rejected; NOOP if nothing was inserted or updated; SUCCESS otherwise.

Retries: C4/C5 connectors retry transient network errors themselves; E1
does not add a second retry layer. A failed or partial run is recovered by
running again, which is safe because persistence is idempotent.

Logs and persisted failure text carry identifiers, counts and exception
class names only: never source values, connector messages, or payloads.

Log events (app.core.logging), each with the run ID:
    run_started, run_finished (with duration_seconds), run_failed
    connector_health_check_failed, entity_failed
    batch_fetched       per fetched page, before the quality gate
    record_normalized   DEBUG, per record the quality gate accepted
    record_rejected     WARNING, per record the quality gate quarantined
                        (stage and finding codes, never values)
    batch_committed, batch_failed
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.base import SourceConnector
from app.connectors.types import (
    ConnectorAuthenticationError,
    ConnectorCapabilities,
    ConnectorConfigurationError,
    ConnectorError,
    ConnectorHealth,
    Page,
)
from app.core.logging import log_event
from app.ingestion.batch import Checkpoint, commit_batch
from app.ingestion.errors import ConnectorContractError, IngestionCode, IngestionRequestError
from app.normalization import NormalizationConfig, default_config
from app.persistence.repositories import errors, runs
from app.validation import (
    QualityGateResult,
    ValidationConfig,
    default_validation_config,
    validate_source_batch,
)

logger = logging.getLogger(__name__)

# Parents before children (reconciliation.REFERENCE_RULES).
ENTITY_ORDER: tuple[str, ...] = (
    "organizations", "employees", "customers", "deals", "projects", "support_tickets", "documents",
)

MAX_PAGE_SIZE = 10_000


@dataclass(frozen=True)
class IngestionRequest:
    """What to ingest. entities=None selects every entity the source provides."""

    entities: Sequence[str] | None = None
    mode: str = runs.RunMode.FULL.value
    page_size: int = 100


class EntityStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class EntitySummary:
    entity_type: str
    status: EntityStatus
    counts: runs.RunCounts
    batches_committed: int = 0
    batches_failed: int = 0
    raw_persisted: int = 0
    records_failed: int = 0
    failure: str | None = None


@dataclass(frozen=True)
class RunSummary:
    """Run outcome. counts.fetched = inserted + updated + unchanged + rejected + records_failed."""

    run_id: uuid.UUID
    source_system: str
    status: runs.RunStatus
    started_at: datetime
    finished_at: datetime
    entities: tuple[EntitySummary, ...]
    error_summary: str | None

    @property
    def counts(self) -> runs.RunCounts:
        total = runs.RunCounts()
        for entity in self.entities:
            total = total + entity.counts
        return total

    @property
    def batches_committed(self) -> int:
        return sum(entity.batches_committed for entity in self.entities)

    @property
    def batches_failed(self) -> int:
        return sum(entity.batches_failed for entity in self.entities)

    @property
    def raw_persisted(self) -> int:
        return sum(entity.raw_persisted for entity in self.entities)

    @property
    def records_failed(self) -> int:
        return sum(entity.records_failed for entity in self.entities)

    def to_dict(self) -> dict[str, object]:
        counts = self.counts
        return {
            "run_id": str(self.run_id),
            "source_system": self.source_system,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "records_fetched": counts.fetched,
            "records_raw_persisted": self.raw_persisted,
            "records_inserted": counts.inserted,
            "records_updated": counts.updated,
            "records_unchanged": counts.unchanged,
            "records_rejected": counts.rejected,
            "records_failed": self.records_failed,
            "warnings": counts.warnings,
            "batches_committed": self.batches_committed,
            "batches_failed": self.batches_failed,
            "error_summary": self.error_summary,
            "entities": [
                {
                    "entity_type": entity.entity_type,
                    "status": entity.status.value,
                    "records_fetched": entity.counts.fetched,
                    "records_inserted": entity.counts.inserted,
                    "records_updated": entity.counts.updated,
                    "records_unchanged": entity.counts.unchanged,
                    "records_rejected": entity.counts.rejected,
                    "records_failed": entity.records_failed,
                    "warnings": entity.counts.warnings,
                    "batches_committed": entity.batches_committed,
                    "batches_failed": entity.batches_failed,
                    "failure": entity.failure,
                }
                for entity in self.entities
            ],
        }


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _Context:
    connector: SourceConnector
    sessions: sessionmaker[Session]
    run_id: uuid.UUID
    source_system: str
    page_size: int
    clock: Callable[[], datetime]
    normalization: NormalizationConfig
    validation: ValidationConfig

    def now(self) -> datetime:
        return _aware_utc(self.clock())

    def record(self, entry: errors.ErrorEntry) -> None:
        with self.sessions.begin() as session:
            errors.add_errors(session, self.run_id, [entry], created_at=self.now())


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


def _detail(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def run_ingestion(
    connector: SourceConnector,
    sessions: sessionmaker[Session],
    request: IngestionRequest | None = None,
    *,
    clock: Callable[[], datetime] = _utc_now,
    normalization_config: NormalizationConfig | None = None,
    validation_config: ValidationConfig | None = None,
) -> RunSummary:
    """Execute one ingestion run and return its summary.

    Raises:
        IngestionRequestError: the request is invalid; no run is created.
        Any system failure, unchanged, after the run is marked FAILED.
    """
    request = IngestionRequest() if request is None else request
    normalization = default_config() if normalization_config is None else normalization_config
    validation = default_validation_config() if validation_config is None else validation_config
    capabilities = connector.capabilities()
    entities = _select_entities(connector.source_name, capabilities, request, normalization)

    context = _Context(connector, sessions, uuid.uuid4(), connector.source_name,
                       request.page_size, clock, normalization, validation)
    started_at = context.now()
    with sessions.begin() as session:
        runs.create_run(session, run_id=context.run_id, source_system=context.source_system,
                        source_entity=entities[0] if len(entities) == 1 else None,
                        mode=runs.RunMode.FULL, started_at=started_at)
    log_event(logger, logging.INFO, "run_started", run_id=context.run_id,
              source_system=context.source_system, entities=",".join(entities))

    finished = False
    try:
        summary = _execute(context, capabilities, entities, started_at)
        finished = True
        return summary
    finally:
        if not finished:
            _abort(context)


def _select_entities(
    source_system: str,
    capabilities: ConnectorCapabilities,
    request: IngestionRequest,
    normalization: NormalizationConfig,
) -> tuple[str, ...]:
    try:
        runs.RunMode(request.mode)
    except ValueError:
        raise IngestionRequestError(
            f"unsupported mode {request.mode!r}; Layer 1 connectors support full sync only"
        ) from None
    if type(request.page_size) is not int or not 1 <= request.page_size <= MAX_PAGE_SIZE:
        raise IngestionRequestError(f"page_size must be an int between 1 and {MAX_PAGE_SIZE}")
    profile = normalization.sources.get(source_system)
    if profile is None:
        raise IngestionRequestError(f"source system {source_system!r} has no normalization mapping")
    available = set(capabilities.supported_entity_types) & set(profile.entities)

    if request.entities is None:
        selected = tuple(entity for entity in ENTITY_ORDER if entity in available)
    else:
        requested = set(request.entities)
        unknown = sorted(requested - set(ENTITY_ORDER), key=str)
        if unknown:
            raise IngestionRequestError(f"unknown entity types {unknown}")
        unavailable = sorted(requested - available)
        if unavailable:
            raise IngestionRequestError(
                f"entity types {unavailable} are not available from {source_system!r}")
        selected = tuple(entity for entity in ENTITY_ORDER if entity in requested)
    if not selected:
        raise IngestionRequestError("no entity types selected")
    return selected


def _execute(
    context: _Context,
    capabilities: ConnectorCapabilities,
    entities: tuple[str, ...],
    started_at: datetime,
) -> RunSummary:
    healthy = _check_health(context, capabilities)
    summaries: list[EntitySummary] = []
    stop = not healthy
    for entity in entities:
        if stop:
            summaries.append(EntitySummary(entity, EntityStatus.SKIPPED, runs.RunCounts()))
            continue
        entity_summary, stop = _ingest_entity(context, entity)
        summaries.append(entity_summary)

    status = _run_status(summaries)
    error_summary = _error_summary(healthy, summaries)
    finished_at = context.now()
    with context.sessions.begin() as session:
        runs.finish_run(session, context.run_id, status=status, finished_at=finished_at,
                        error_summary=error_summary)
    summary = RunSummary(context.run_id, context.source_system, status, started_at, finished_at,
                         tuple(summaries), error_summary)
    counts = summary.counts
    log_event(logger, logging.INFO, "run_finished", run_id=context.run_id, status=status.value,
              fetched=counts.fetched, inserted=counts.inserted, updated=counts.updated,
              unchanged=counts.unchanged, rejected=counts.rejected,
              failed=summary.records_failed, warnings=counts.warnings,
              duration_seconds=(finished_at - started_at).total_seconds())
    return summary


def _check_health(context: _Context, capabilities: ConnectorCapabilities) -> bool:
    if not capabilities.supports_health_check:
        return True
    try:
        health = context.connector.health_check()
    except ConnectorError as exc:
        failure = type(exc).__name__
    else:
        if not isinstance(health, ConnectorHealth):
            raise ConnectorContractError(
                f"health_check returned {type(health).__name__}, not ConnectorHealth")
        if health.healthy is True:
            return True
        failure = "unhealthy"
    context.record(errors.ErrorEntry(
        severity="ERROR", error_code=IngestionCode.CONNECTOR_UNHEALTHY.value,
        message=f"connector health check failed ({failure}); no entities were fetched",
        source_system=context.source_system,
        detail=_detail({"failure": failure}),
    ))
    log_event(logger, logging.WARNING, "connector_health_check_failed", run_id=context.run_id,
              source_system=context.source_system, failure=failure)
    return False


def _ingest_entity(context: _Context, entity: str) -> tuple[EntitySummary, bool]:
    """Ingest every page of one entity. Returns (summary, stop the run)."""
    counts = runs.RunCounts()
    batches = raw_persisted = 0
    cursor: str | None = None
    page_index = 0
    while True:
        try:
            page = context.connector.fetch_entities(entity, cursor, context.page_size)
        except ConnectorError as exc:
            fatal = isinstance(exc, (ConnectorAuthenticationError, ConnectorConfigurationError))
            failure = type(exc).__name__
            context.record(errors.ErrorEntry(
                severity="ERROR", error_code=IngestionCode.CONNECTOR_FAILED.value,
                message=(f"connector raised {failure} fetching page {page_index}"
                         + ("; run stopped" if fatal else "; entity stopped")),
                source_system=context.source_system, source_entity=entity,
                detail=_detail({"exception": failure, "page_index": page_index,
                                "run_stopped": fatal}),
            ))
            log_event(logger, logging.WARNING, "entity_failed", run_id=context.run_id,
                      entity=entity, page=page_index, failure=failure, run_stopped=fatal)
            return EntitySummary(entity, EntityStatus.FAILED, counts, batches, 0, raw_persisted,
                                 0, failure), fatal

        items = _page_items(page, cursor, context.page_size)
        log_event(logger, logging.INFO, "batch_fetched", run_id=context.run_id, entity=entity,
                  page=page_index, records=len(items), has_more=page.has_more)
        ingested_at = context.now()
        gate = validate_source_batch(
            context.source_system, entity, items, context.run_id, ingested_at,
            normalization_config=context.normalization, validation_config=context.validation,
        )
        _log_quality_gate(context, entity, page_index, gate)
        try:
            result = commit_batch(
                context.sessions, run_id=context.run_id, gate=gate, raw_records=items,
                ingested_at=ingested_at, checkpoint=None if page.has_more else Checkpoint(),
            )
        except (IntegrityError, DataError) as exc:
            failed = runs.RunCounts(fetched=len(items))
            _record_failed_batch(context, entity, page_index, len(items), exc, ingested_at, failed)
            return EntitySummary(entity, EntityStatus.FAILED, counts + failed, batches, 1,
                                 raw_persisted, len(items), IngestionCode.BATCH_FAILED.value), False

        counts = counts + result.counts
        batches += 1
        raw_persisted += result.raw_persisted
        log_event(logger, logging.INFO, "batch_committed", run_id=context.run_id, entity=entity,
                  page=page_index, fetched=result.counts.fetched, inserted=result.counts.inserted,
                  updated=result.counts.updated, unchanged=result.counts.unchanged,
                  rejected=result.counts.rejected, warnings=result.counts.warnings)
        if not page.has_more:
            return EntitySummary(entity, EntityStatus.COMPLETED, counts, batches, 0,
                                 raw_persisted), False
        cursor = page.next_cursor
        page_index += 1


def _log_quality_gate(
    context: _Context,
    entity: str,
    page_index: int,
    gate: QualityGateResult,
) -> None:
    """record_normalized per accepted record (DEBUG only), then record_rejected per rejection."""
    if logger.isEnabledFor(logging.DEBUG):
        rejected = {record.record_index for record in gate.quarantined}
        accepted = (index for index in range(gate.total_records) if index not in rejected)
        for record_index, record in zip(accepted, gate.valid, strict=False):
            log_event(logger, logging.DEBUG, "record_normalized", run_id=context.run_id,
                      entity=entity, page=page_index, record_index=record_index,
                      source_id=record.source_id)
    for quarantined in gate.quarantined:
        log_event(logger, logging.WARNING, "record_rejected", run_id=context.run_id,
                  entity=entity, page=page_index, record_index=quarantined.record_index,
                  source_id=quarantined.source_id, stage=quarantined.stage.value,
                  codes=",".join(dict.fromkeys(f.code for f in quarantined.findings)))


def _page_items(page: object, cursor: str | None, page_size: int) -> list[object]:
    if not isinstance(page, Page):
        raise ConnectorContractError(f"fetch_entities returned {type(page).__name__}, not Page")
    if not isinstance(page.items, list):
        raise ConnectorContractError("Page.items must be a list")
    if len(page.items) > page_size:
        raise ConnectorContractError("Page holds more records than the requested page_size")
    if page.has_more is not True and page.has_more is not False:
        raise ConnectorContractError("Page.has_more must be a bool")
    if page.has_more and (not isinstance(page.next_cursor, str) or page.next_cursor == cursor):
        raise ConnectorContractError("Page reports more records without advancing the cursor")
    return page.items


def _record_failed_batch(
    context: _Context,
    entity: str,
    page_index: int,
    records: int,
    exc: IntegrityError | DataError,
    created_at: datetime,
    counts: runs.RunCounts,
) -> None:
    database_error = type(exc.orig).__name__ if exc.orig is not None else type(exc).__name__
    sqlstate = getattr(exc.orig, "pgcode", None)
    with context.sessions.begin() as session:
        errors.add_errors(session, context.run_id, [errors.ErrorEntry(
            severity="ERROR", error_code=IngestionCode.BATCH_FAILED.value,
            message=(f"batch {page_index} rolled back by {database_error} (SQLSTATE {sqlstate}); "
                     f"{records} records not persisted; entity stopped"),
            source_system=context.source_system, source_entity=entity,
            detail=_detail({"page_index": page_index, "records": records,
                            "database_error": database_error, "sqlstate": sqlstate}),
        )], created_at=created_at)
        runs.add_run_counts(session, context.run_id, counts)
    log_event(logger, logging.WARNING, "batch_failed", run_id=context.run_id, entity=entity,
              page=page_index, records=records, database_error=database_error, sqlstate=sqlstate)


def _run_status(entities: Sequence[EntitySummary]) -> runs.RunStatus:
    # A failed health check skips every entity, so it is FAILED by the first rule.
    committed = sum(entity.batches_committed for entity in entities)
    if any(entity.status is not EntityStatus.COMPLETED for entity in entities):
        return runs.RunStatus.PARTIAL_SUCCESS if committed else runs.RunStatus.FAILED
    total = runs.RunCounts()
    for entity in entities:
        total = total + entity.counts
    if total.rejected:
        return runs.RunStatus.PARTIAL_SUCCESS
    if total.inserted == 0 and total.updated == 0:
        return runs.RunStatus.NOOP
    return runs.RunStatus.SUCCESS


def _error_summary(healthy: bool, entities: Sequence[EntitySummary]) -> str | None:
    parts = []
    if not healthy:
        parts.append("connector health check failed")
    rejected = sum(entity.counts.rejected for entity in entities)
    if rejected:
        parts.append(f"{rejected} records rejected")
    parts += [f"{entity.entity_type} failed: {entity.failure}" for entity in entities
              if entity.status is EntityStatus.FAILED]
    skipped = sum(1 for entity in entities if entity.status is EntityStatus.SKIPPED)
    if skipped:
        parts.append(f"{skipped} entities skipped")
    return "; ".join(parts) or None


def _abort(context: _Context) -> None:
    """Mark the run FAILED while a system failure propagates."""
    failure = sys.exc_info()[1]
    label = "interrupted" if failure is None else type(failure).__name__
    with context.sessions.begin() as session:
        runs.finish_run(session, context.run_id, status=runs.RunStatus.FAILED,
                        finished_at=context.now(),
                        error_summary=f"run aborted by system failure: {label}")
    log_event(logger, logging.ERROR, "run_failed", run_id=context.run_id, failure=label)
