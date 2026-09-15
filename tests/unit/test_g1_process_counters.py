"""
G1 in-process ingestion counters: lifecycle, counting semantics and thread safety.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.observability.metrics import ProcessMetrics
from app.persistence.repositories.runs import RunCounts, RunStatus

T0 = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
STATUSES = [status.value for status in RunStatus]


def _metrics() -> ProcessMetrics:
    return ProcessMetrics(clock=lambda: T0)


def test_a_new_process_starts_at_zero_with_its_start_time():
    snapshot = _metrics().snapshot()
    assert snapshot.started_at == T0
    assert snapshot.runs_by_status == dict.fromkeys(STATUSES, 0)
    assert snapshot.runs_total == 0
    assert (snapshot.records_fetched_total, snapshot.records_inserted_total,
            snapshot.records_updated_total, snapshot.records_unchanged_total,
            snapshot.records_rejected_total, snapshot.connector_request_failures_total,
            snapshot.validation_errors_total, snapshot.ingestion_duration_seconds_count,
            snapshot.ingestion_duration_seconds_sum) == (0, 0, 0, 0, 0, 0, 0, 0, 0.0)


def test_the_start_time_is_normalised_to_utc_and_must_be_aware():
    india = timezone(timedelta(hours=5, minutes=30))
    started = ProcessMetrics(clock=lambda: datetime(2026, 9, 15, 14, 30, tzinfo=india))
    assert started.snapshot().started_at == T0
    assert started.snapshot().started_at.tzinfo is UTC
    with pytest.raises(ValueError, match="timezone-aware"):
        ProcessMetrics(clock=lambda: datetime(2026, 9, 15, 9, 0))


def test_the_default_clock_is_the_current_utc_time():
    before = datetime.now(UTC)
    started_at = ProcessMetrics().snapshot().started_at
    assert before <= started_at <= datetime.now(UTC)


def test_a_run_is_running_until_it_finishes():
    metrics = _metrics()
    metrics.run_started()
    running = metrics.snapshot()
    assert running.runs_by_status == {**dict.fromkeys(STATUSES, 0), "RUNNING": 1}
    assert (running.runs_total, running.ingestion_duration_seconds_count) == (1, 0)
    metrics.run_finished(RunStatus.SUCCESS, 2.5)
    finished = metrics.snapshot()
    assert finished.runs_by_status == {**dict.fromkeys(STATUSES, 0), "SUCCESS": 1}
    assert (finished.runs_total, finished.ingestion_duration_seconds_count,
            finished.ingestion_duration_seconds_sum) == (1, 1, 2.5)


def test_committed_batches_add_their_counts_and_rejections_are_validation_errors():
    metrics = _metrics()
    metrics.batch_committed(RunCounts(fetched=10, inserted=4, updated=3, unchanged=1, rejected=2,
                                      warnings=5))
    metrics.batch_committed(RunCounts(fetched=3, inserted=1, updated=0, unchanged=1, rejected=1))
    snapshot = metrics.snapshot()
    assert (snapshot.records_fetched_total, snapshot.records_inserted_total,
            snapshot.records_updated_total, snapshot.records_unchanged_total,
            snapshot.records_rejected_total, snapshot.validation_errors_total) == (
        13, 5, 3, 2, 3, 3)
    assert snapshot.connector_request_failures_total == 0
    assert snapshot.runs_total == 0


def test_failed_batches_count_only_as_fetched_records():
    metrics = _metrics()
    metrics.batch_failed(7)
    snapshot = metrics.snapshot()
    assert (snapshot.records_fetched_total, snapshot.records_inserted_total,
            snapshot.records_rejected_total, snapshot.validation_errors_total) == (7, 0, 0, 0)


def test_connector_failures_are_counted_one_by_one():
    metrics = _metrics()
    metrics.connector_failed()
    metrics.connector_failed()
    snapshot = metrics.snapshot()
    assert snapshot.connector_request_failures_total == 2
    assert snapshot.records_fetched_total == 0


@pytest.mark.parametrize("status", [RunStatus.SUCCESS, RunStatus.PARTIAL_SUCCESS, RunStatus.NOOP,
                                    RunStatus.FAILED, "FAILED"])
def test_every_final_status_is_counted_under_its_own_name(status):
    metrics = _metrics()
    metrics.run_started()
    metrics.run_finished(status, 1.0)
    assert metrics.snapshot().runs_by_status == {**dict.fromkeys(STATUSES, 0),
                                                 RunStatus(status).value: 1}


def test_a_run_cannot_finish_as_running():
    metrics = _metrics()
    metrics.run_started()
    with pytest.raises(ValueError, match="RUNNING"):
        metrics.run_finished(RunStatus.RUNNING, 1.0)
    assert metrics.snapshot().runs_by_status["RUNNING"] == 1


def test_durations_accumulate_over_finished_runs():
    metrics = _metrics()
    for status, seconds in ((RunStatus.SUCCESS, 1.25), (RunStatus.NOOP, 0.5),
                            (RunStatus.FAILED, 3.0)):
        metrics.run_started()
        metrics.run_finished(status, seconds)
    snapshot = metrics.snapshot()
    assert (snapshot.ingestion_duration_seconds_count,
            snapshot.ingestion_duration_seconds_sum) == (3, 4.75)
    assert snapshot.runs_by_status == {**dict.fromkeys(STATUSES, 0), "SUCCESS": 1, "NOOP": 1,
                                       "FAILED": 1}


def test_snapshots_are_copies():
    metrics = _metrics()
    first = metrics.snapshot()
    first.runs_by_status["SUCCESS"] = 99
    metrics.run_started()
    assert metrics.snapshot().runs_by_status["SUCCESS"] == 0
    assert first.runs_by_status["RUNNING"] == 0


def test_separate_instances_do_not_share_counters():
    first, second = _metrics(), _metrics()
    first.run_started()
    first.batch_committed(RunCounts(fetched=1, inserted=1))
    assert second.snapshot().runs_total == 0
    assert second.snapshot().records_fetched_total == 0


def test_concurrent_updates_are_never_lost():
    metrics = _metrics()
    threads_count, iterations = 8, 2_000

    def work() -> None:
        for _ in range(iterations):
            metrics.run_started()
            metrics.batch_committed(RunCounts(fetched=2, inserted=1, rejected=1))
            metrics.batch_failed(1)
            metrics.connector_failed()
            metrics.run_finished(RunStatus.SUCCESS, 0.5)

    threads = [threading.Thread(target=work) for _ in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    total = threads_count * iterations
    snapshot = metrics.snapshot()
    assert snapshot.runs_by_status == {**dict.fromkeys(STATUSES, 0), "SUCCESS": total}
    assert (snapshot.records_fetched_total, snapshot.records_inserted_total,
            snapshot.records_rejected_total, snapshot.validation_errors_total,
            snapshot.connector_request_failures_total,
            snapshot.ingestion_duration_seconds_count,
            snapshot.ingestion_duration_seconds_sum) == (
        3 * total, total, total, total, total, total, 0.5 * total)
