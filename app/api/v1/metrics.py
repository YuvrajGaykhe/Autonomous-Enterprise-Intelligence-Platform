"""
Operational ingestion metrics (spec Sections 10 and 16).

    GET /api/v1/metrics/ingestion

totals and sources are derived from what E1 persisted (ingestion_runs,
ingestion_errors, source_records and the canonical tables) in one read-only
snapshot, so they survive restarts, agree across API processes and are never
estimated. process holds the in-process counters (G1) of the API process
answering the request, which start at zero with that process.

    totals    every source system combined
    sources   each configured source and each source system with persisted
              data, sorted by name; sources without data report zeros
    process   runs executed by this process since it started
              (app.observability.metrics.ProcessMetrics)

Counts reconcile with the run report: the totals are sums over runs, and a
RUNNING run contributes the counts it has committed so far but no duration.
Error messages, raw records and source values are never read.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, sessionmaker

from app.api.connectors import ConnectorProvider
from app.api.dependencies import get_connectors, get_process_metrics, get_sessions, read_snapshot
from app.api.v1.schemas import (
    CanonicalRecordCounts,
    DurationSummary,
    ErrorSeverity,
    ErrorSeverityCounts,
    IngestionMetrics,
    IngestionMetricsResponse,
    ProcessIngestionMetrics,
    RunReference,
    RunStatusCounts,
    SourceIngestionMetrics,
)
from app.ingestion.errors import IngestionCode
from app.observability.metrics import ProcessMetrics
from app.persistence.repositories import metrics_queries
from app.persistence.repositories.runs import RunStatus

router = APIRouter(prefix="/metrics", tags=["metrics"])

CONNECTOR_FAILURE_CODES = frozenset({IngestionCode.CONNECTOR_UNHEALTHY.value,
                                     IngestionCode.CONNECTOR_FAILED.value})
SYSTEM_ERROR_CODES = CONNECTOR_FAILURE_CODES | {IngestionCode.BATCH_FAILED.value}
SUCCESSFUL_STATUSES = (RunStatus.SUCCESS.value, RunStatus.PARTIAL_SUCCESS.value,
                       RunStatus.NOOP.value)

ErrorKey = tuple[str, str | None]


@router.get("/ingestion", response_model=IngestionMetricsResponse)
def ingestion_metrics(
    sessions: sessionmaker[Session] = Depends(get_sessions),
    connectors: ConnectorProvider = Depends(get_connectors),
    process_metrics: ProcessMetrics = Depends(get_process_metrics),
) -> IngestionMetricsResponse:
    """Database-derived ingestion metrics, plus this process's in-process counters."""
    with read_snapshot(sessions) as session:
        runs = metrics_queries.run_aggregates(session)
        raw = metrics_queries.raw_record_counts(session)
        errors = metrics_queries.error_counts(session)
        canonical = metrics_queries.canonical_record_counts(session)
        latest = metrics_queries.latest_runs(session)
        successful = metrics_queries.latest_runs(session, statuses=SUCCESSFUL_STATUSES)

    # Raw records and errors belong to runs, so their source systems are run source systems.
    names = sorted({
        *connectors.source_names,
        *(aggregate.source_system for aggregate in runs),
        *(source_system for per_source in canonical.values() for source_system in per_source),
    })
    sources = [
        SourceIngestionMetrics(
            source_system=name,
            last_run=_reference(latest.get(name)),
            last_successful_run=_reference(successful.get(name)),
            **_metrics(
                [aggregate for aggregate in runs if aggregate.source_system == name],
                raw.get(name, 0),
                {(severity, code): count
                 for (source_system, severity, code), count in errors.items()
                 if source_system == name},
                {entity: per_source.get(name, 0) for entity, per_source in canonical.items()},
            ),
        )
        for name in names
    ]
    all_errors: Counter[ErrorKey] = Counter()
    for (_, severity, code), count in errors.items():
        all_errors[(severity, code)] += count
    totals = IngestionMetrics(**_metrics(
        runs, sum(raw.values()), all_errors,
        {entity: sum(per_source.values()) for entity, per_source in canonical.items()},
    ))
    return IngestionMetricsResponse(totals=totals, sources=sources,
                                    process=_process(process_metrics))


def _process(process_metrics: ProcessMetrics) -> ProcessIngestionMetrics:
    snapshot = process_metrics.snapshot()
    return ProcessIngestionMetrics(
        started_at=snapshot.started_at,
        runs_total=snapshot.runs_total,
        runs_by_status=RunStatusCounts(**snapshot.runs_by_status),
        records_fetched_total=snapshot.records_fetched_total,
        records_inserted_total=snapshot.records_inserted_total,
        records_updated_total=snapshot.records_updated_total,
        records_unchanged_total=snapshot.records_unchanged_total,
        records_rejected_total=snapshot.records_rejected_total,
        connector_request_failures_total=snapshot.connector_request_failures_total,
        validation_errors_total=snapshot.validation_errors_total,
        ingestion_duration_seconds=DurationSummary(
            count=snapshot.ingestion_duration_seconds_count,
            sum=round(snapshot.ingestion_duration_seconds_sum, 6)),
    )


def _metrics(
    runs: Iterable[metrics_queries.RunAggregate],
    raw_records: int,
    errors: Mapping[ErrorKey, int],
    canonical: Mapping[str, int],
) -> dict[str, Any]:
    runs = list(runs)
    by_status = {status.value: 0 for status in RunStatus}
    for aggregate in runs:
        by_status[RunStatus(aggregate.status).value] += aggregate.runs
    by_severity = {severity.value: 0 for severity in ErrorSeverity}
    for (severity, _), count in errors.items():
        by_severity[ErrorSeverity(severity).value] += count
    fetched = sum(aggregate.records_fetched for aggregate in runs)
    inserted = sum(aggregate.records_inserted for aggregate in runs)
    updated = sum(aggregate.records_updated for aggregate in runs)
    unchanged = sum(aggregate.records_unchanged for aggregate in runs)
    rejected = sum(aggregate.records_rejected for aggregate in runs)
    return {
        "runs_total": sum(aggregate.runs for aggregate in runs),
        "runs_by_status": RunStatusCounts(**by_status),
        "records_fetched_total": fetched,
        "records_raw_persisted_total": raw_records,
        "records_inserted_total": inserted,
        "records_updated_total": updated,
        "records_unchanged_total": unchanged,
        "records_rejected_total": rejected,
        "records_failed_total": fetched - (inserted + updated + unchanged + rejected),
        "warnings_total": sum(aggregate.warnings for aggregate in runs),
        "batches_failed_total": sum(count for (_, code), count in errors.items()
                                    if code == IngestionCode.BATCH_FAILED.value),
        "errors_by_severity": ErrorSeverityCounts(**by_severity),
        "connector_request_failures_total": sum(count for (_, code), count in errors.items()
                                                if code in CONNECTOR_FAILURE_CODES),
        "validation_errors_total": sum(count for (severity, code), count in errors.items()
                                       if severity == ErrorSeverity.ERROR.value
                                       and code not in SYSTEM_ERROR_CODES),
        "ingestion_duration_seconds_total": round(
            sum(aggregate.duration_seconds for aggregate in runs), 6),
        "canonical_records": CanonicalRecordCounts(**canonical),
    }


def _reference(run: metrics_queries.RunReference | None) -> RunReference | None:
    if run is None:
        return None
    return RunReference(run_id=run.run_id, status=RunStatus(run.status),
                        started_at=run.started_at, finished_at=run.finished_at)
