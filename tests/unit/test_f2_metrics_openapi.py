"""
F2 ingestion metrics route: published contract and failure handling without a database.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.request_id import REQUEST_ID_HEADER
from app.main import create_app
from app.persistence.repositories.canonical import ENTITY_MODELS
from app.persistence.repositories.errors import SEVERITIES
from app.persistence.repositories.runs import RunStatus

METRICS = "/api/v1/metrics/ingestion"
# Synthetic credentials for an unreachable server (nothing listens on port 9).
UNREACHABLE_URL = "postgresql://f2_probe:f2-synthetic-password@127.0.0.1:9/f2_unreachable"
METRIC_FIELDS = {
    "runs_total", "runs_by_status", "records_fetched_total", "records_raw_persisted_total",
    "records_inserted_total", "records_updated_total", "records_unchanged_total",
    "records_rejected_total", "records_failed_total", "warnings_total", "batches_failed_total",
    "errors_by_severity", "connector_request_failures_total", "validation_errors_total",
    "ingestion_duration_seconds_total", "canonical_records",
}
# Spec Section 16 metric names.
SPEC_METRICS = {
    "records_fetched_total", "records_inserted_total", "records_updated_total",
    "records_unchanged_total", "records_rejected_total", "ingestion_duration_seconds_total",
    "connector_request_failures_total", "validation_errors_total",
}


@pytest.fixture(scope="module")
def spec() -> dict:
    return create_app(sessions=sessionmaker()).openapi()


def _ref(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}"}


def test_the_metrics_operation_is_a_parameterless_get(spec):
    path = spec["paths"][METRICS]
    assert set(path) == {"get"}
    operation = path["get"]
    assert "parameters" not in operation and "requestBody" not in operation
    assert set(operation["responses"]) == {"200"}
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == _ref(
        "IngestionMetricsResponse")


def test_the_response_has_totals_and_per_source_metrics(spec):
    schemas = spec["components"]["schemas"]
    response = schemas["IngestionMetricsResponse"]
    # G1 adds the in-process counters (tests/unit/test_g1_process_metrics_openapi.py).
    assert set(response["properties"]) == set(response["required"]) == {
        "totals", "sources", "process"}
    assert response["properties"]["totals"] == _ref("IngestionMetrics")
    assert response["properties"]["sources"]["items"] == _ref("SourceIngestionMetrics")
    assert response["properties"]["process"] == _ref("ProcessIngestionMetrics")


def test_every_metric_is_required_and_includes_the_spec_names(spec):
    schemas = spec["components"]["schemas"]
    metrics = schemas["IngestionMetrics"]
    assert set(metrics["properties"]) == set(metrics["required"]) == METRIC_FIELDS
    assert SPEC_METRICS <= METRIC_FIELDS
    for name in METRIC_FIELDS - {"runs_by_status", "errors_by_severity", "canonical_records",
                                 "ingestion_duration_seconds_total"}:
        assert metrics["properties"][name]["type"] == "integer", name
    assert metrics["properties"]["ingestion_duration_seconds_total"]["type"] == "number"
    source = schemas["SourceIngestionMetrics"]
    extra = {"source_system", "last_run", "last_successful_run"}
    assert set(source["properties"]) == set(source["required"]) == METRIC_FIELDS | extra
    for name in ("last_run", "last_successful_run"):
        assert source["properties"][name]["anyOf"] == [_ref("RunReference"), {"type": "null"}]


@pytest.mark.parametrize(("model", "keys"), [
    ("RunStatusCounts", {status.value for status in RunStatus}),
    ("ErrorSeverityCounts", set(SEVERITIES)),
    ("CanonicalRecordCounts", set(ENTITY_MODELS)),
])
def test_breakdowns_always_list_every_key(spec, model, keys):
    schema = spec["components"]["schemas"][model]
    assert set(schema["properties"]) == set(schema["required"]) == keys
    assert {prop["type"] for prop in schema["properties"].values()} == {"integer"}


def test_run_references_expose_identity_and_timing_only(spec):
    reference = spec["components"]["schemas"]["RunReference"]
    assert set(reference["properties"]) == set(reference["required"]) == {
        "run_id", "status", "started_at", "finished_at"}


def test_an_unreachable_database_is_a_generic_internal_error():
    engine = create_engine(UNREACHABLE_URL, hide_parameters=True,
                           connect_args={"connect_timeout": 2})
    client = TestClient(create_app(sessions=sessionmaker(bind=engine)),
                        raise_server_exceptions=False)
    response = client.get(METRICS, headers={REQUEST_ID_HEADER: "metrics-probe-1"})
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "INTERNAL_ERROR",
                                         "message": "internal server error", "details": None,
                                         "request_id": "metrics-probe-1"}}
    assert response.headers[REQUEST_ID_HEADER] == "metrics-probe-1"
    for private in ("f2-synthetic-password", "f2_probe", "127.0.0.1", "OperationalError"):
        assert private not in response.text
