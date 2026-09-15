"""
In-process ingestion counters (spec Section 16).

ProcessMetrics counts the ingestion work E1 performs in this process, from
the moment it is created (API application startup) until the process ends:
a restart starts again from zero. It is the RunObserver E1 notifies at the
same points where it commits to the database, so it never reads, estimates
or copies database rows, and runs executed elsewhere (another API process,
the ingest-demo command) are not included. The database-derived metrics in
GET /api/v1/metrics/ingestion remain the durable totals.

    run_started        runs_total and runs_by_status RUNNING (in progress)
    batch_committed    records fetched/inserted/updated/unchanged/rejected;
                       every rejected record is one validation error
    batch_failed       the failed batch's records count as fetched
    connector_failed   connector_request_failures_total (failed health
                       check or failed page fetch)
    run_finished       RUNNING -> final status; duration count and sum

These are the same definitions as the database-derived metrics, so for a
process that ran every ingestion against an empty database the two agree.
Updates are serialised by a lock: API ingestion runs execute in a thread pool.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.persistence.repositories.runs import RunCounts, RunStatus


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ProcessMetricsSnapshot:
    """A consistent copy of the counters."""

    started_at: datetime
    runs_by_status: dict[str, int]
    records_fetched_total: int
    records_inserted_total: int
    records_updated_total: int
    records_unchanged_total: int
    records_rejected_total: int
    connector_request_failures_total: int
    validation_errors_total: int
    ingestion_duration_seconds_count: int
    ingestion_duration_seconds_sum: float

    @property
    def runs_total(self) -> int:
        return sum(self.runs_by_status.values())


class ProcessMetrics:
    """Thread-safe ingestion counters for one process; a RunObserver for E1."""

    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        started_at = clock()
        if started_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        self._started_at = started_at.astimezone(UTC)
        self._lock = threading.Lock()
        self._runs = dict.fromkeys((status.value for status in RunStatus), 0)
        self._fetched = self._inserted = self._updated = self._unchanged = self._rejected = 0
        self._connector_failures = self._validation_errors = 0
        self._duration_count = 0
        self._duration_sum = 0.0

    def run_started(self) -> None:
        with self._lock:
            self._runs[RunStatus.RUNNING.value] += 1

    def batch_committed(self, counts: RunCounts) -> None:
        with self._lock:
            self._fetched += counts.fetched
            self._inserted += counts.inserted
            self._updated += counts.updated
            self._unchanged += counts.unchanged
            self._rejected += counts.rejected
            self._validation_errors += counts.rejected

    def batch_failed(self, records: int) -> None:
        with self._lock:
            self._fetched += records

    def connector_failed(self) -> None:
        with self._lock:
            self._connector_failures += 1

    def run_finished(self, status: RunStatus, duration_seconds: float) -> None:
        final = RunStatus(status)
        if final is RunStatus.RUNNING:
            raise ValueError("a finished run cannot be RUNNING")
        with self._lock:
            self._runs[RunStatus.RUNNING.value] -= 1
            self._runs[final.value] += 1
            self._duration_count += 1
            self._duration_sum += duration_seconds

    def snapshot(self) -> ProcessMetricsSnapshot:
        with self._lock:
            return ProcessMetricsSnapshot(
                started_at=self._started_at,
                runs_by_status=dict(self._runs),
                records_fetched_total=self._fetched,
                records_inserted_total=self._inserted,
                records_updated_total=self._updated,
                records_unchanged_total=self._unchanged,
                records_rejected_total=self._rejected,
                connector_request_failures_total=self._connector_failures,
                validation_errors_total=self._validation_errors,
                ingestion_duration_seconds_count=self._duration_count,
                ingestion_duration_seconds_sum=self._duration_sum,
            )
