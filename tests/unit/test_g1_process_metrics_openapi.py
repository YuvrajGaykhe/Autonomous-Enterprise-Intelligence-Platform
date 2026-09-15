"""
G1 in-process counters: the published "process" contract of GET /api/v1/metrics/ingestion.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from app.main import create_app

PROCESS_FIELDS = {
    "started_at", "runs_total", "runs_by_status", "records_fetched_total",
    "records_inserted_total", "records_updated_total", "records_unchanged_total",
    "records_rejected_total", "connector_request_failures_total", "validation_errors_total",
    "ingestion_duration_seconds",
}
# Spec Section 16 metrics kept in process memory.
SPEC_METRICS = {
    "records_fetched_total", "records_inserted_total", "records_updated_total",
    "records_unchanged_total", "records_rejected_total", "ingestion_duration_seconds",
    "connector_request_failures_total", "validation_errors_total",
}


@pytest.fixture(scope="module")
def schemas() -> dict:
    return create_app(sessions=sessionmaker()).openapi()["components"]["schemas"]


def test_the_process_block_is_required_next_to_the_database_metrics(schemas):
    response = schemas["IngestionMetricsResponse"]
    assert "process" in response["required"]
    assert response["properties"]["process"] == {
        "$ref": "#/components/schemas/ProcessIngestionMetrics"}


def test_every_process_counter_is_required_and_includes_the_spec_names(schemas):
    process = schemas["ProcessIngestionMetrics"]
    assert set(process["properties"]) == set(process["required"]) == PROCESS_FIELDS
    assert SPEC_METRICS <= PROCESS_FIELDS
    properties = process["properties"]
    assert (properties["started_at"]["type"], properties["started_at"]["format"]) == (
        "string", "date-time")
    for name in PROCESS_FIELDS - {"started_at", "runs_by_status", "ingestion_duration_seconds"}:
        assert properties[name]["type"] == "integer", name
    assert properties["runs_by_status"] == {"$ref": "#/components/schemas/RunStatusCounts"}
    assert properties["ingestion_duration_seconds"] == {
        "$ref": "#/components/schemas/DurationSummary"}


def test_durations_are_a_count_and_a_sum(schemas):
    duration = schemas["DurationSummary"]
    assert set(duration["properties"]) == set(duration["required"]) == {"count", "sum"}
    assert (duration["properties"]["count"]["type"], duration["properties"]["sum"]["type"]) == (
        "integer", "number")


def test_the_process_block_exposes_no_database_only_or_private_fields(schemas):
    properties = set(schemas["ProcessIngestionMetrics"]["properties"])
    assert not properties & {"sources", "source_system", "last_run", "records_raw_persisted_total",
                             "errors_by_severity", "canonical_records", "message",
                             "raw_value", "raw_record", "raw_payload"}
