"""
The Layer 1 acceptance scenario (scripts/verify_layer1.py) driven end to end.

Spec Section 20 requires the scenario to be executed and its observed results
reported; Task I1 turns it into a command. These tests run that command's
scenario against the real application over the real migrated database, so a
check that silently stops proving its step fails here.

The API is built over a connector provider limited to csv_demo: the odoo_mock
and rest_mock sources answer over HTTP to the compose mock-source, which this
suite does not start (the H2 contract suite covers all three connectors). The
connector_health check is exercised against that provider and, separately,
against a source whose health check fails.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.connectors import ConnectorProvider
from app.connectors.base import SourceConnector
from app.connectors.registry import build_connector
from app.connectors.types import ConnectorError
from app.main import create_app

pytestmark = pytest.mark.e2e

REPO = Path(__file__).resolve().parents[2]


def _load_script() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "verify_layer1", REPO / "scripts" / "verify_layer1.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # The script defines dataclasses, which resolve their own module by name.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify_layer1 = _load_script()
Outcome = verify_layer1.Outcome

#: The checks the scenario publishes, in order (spec Section 20 steps A-O).
EXPECTED_CHECKS = (
    ("A-C", "stack_ready"),
    ("D", "demo_dataset"),
    ("E-F", "ingestion"),
    ("G-H", "api_query"),
    ("I-J", "idempotency"),
    ("K-L", "validation"),
    ("M", "connector_health"),
    ("A-M", "read_only"),
    ("N", "test_suite"),
    ("O", "clean_rebuild"),
)


def _csv_only(build=build_connector) -> ConnectorProvider:
    return ConnectorProvider(build=build, sources=("csv_demo",))


def _client(sessions, connectors: ConnectorProvider) -> TestClient:
    return TestClient(create_app(sessions=sessions, connectors=connectors),
                      raise_server_exceptions=False)


@pytest.fixture
def api(e1_sessions) -> Iterator[TestClient]:
    """The real application over the migrated test database and csv_demo."""
    with _client(e1_sessions, _csv_only()) as client:
        yield client


def _report(client, sessions, **kwargs):
    return verify_layer1.run_scenario(client, sessions, **kwargs)


def _outcomes(report) -> dict[str, Outcome]:
    return {check.name: check.outcome for check in report.checks}


def _failures(report) -> str:
    return "; ".join(f"{check.name}: {check.detail}" for check in report.failures)


# ---------------------------------------------------------------------------
# The scenario on a clean database
# ---------------------------------------------------------------------------


def test_the_acceptance_scenario_passes_on_a_clean_database(api, e1_sessions):
    report = _report(api, e1_sessions)

    assert report.failures == (), _failures(report)
    assert report.exit_code == 0
    assert report.count(Outcome.PASS) == 8
    assert report.count(Outcome.SKIPPED) == 1
    assert report.count(Outcome.OPERATOR) == 1


def test_the_report_publishes_every_step_in_spec_order(api, e1_sessions):
    report = _report(api, e1_sessions)

    assert tuple((check.steps, check.name) for check in report.checks) == EXPECTED_CHECKS


def test_a_clean_database_is_reported_as_empty_before_the_scenario(api, e1_sessions):
    report = _report(api, e1_sessions)

    stack = next(check for check in report.checks if check.name == "stack_ready")
    assert "database empty" in stack.detail
    assert "all 7 canonical tables queryable" in stack.detail


def test_every_check_line_names_its_steps_outcome_and_evidence(api, e1_sessions):
    report = _report(api, e1_sessions)

    for check in report.checks:
        line = str(check)
        assert line.startswith("verify-layer1: ")
        assert check.steps in line and check.name in line
        assert check.outcome.value in line and check.detail in line
    assert report.summary() == "verify-layer1: 8 passed, 0 failed, 1 skipped, 1 operator"


def test_each_check_is_reported_as_it_completes(api, e1_sessions):
    streamed: list[object] = []

    report = _report(api, e1_sessions, report_line=streamed.append)

    assert streamed == list(report.checks)


# ---------------------------------------------------------------------------
# Repeating the scenario
# ---------------------------------------------------------------------------


def test_the_scenario_is_safe_to_run_repeatedly(api, e1_sessions):
    first = _report(api, e1_sessions)
    second = _report(api, e1_sessions)

    assert second.failures == (), _failures(second)
    assert _outcomes(second) == _outcomes(first)


def test_a_repeated_scenario_reports_the_database_as_already_populated(api, e1_sessions):
    _report(api, e1_sessions)

    stack = next(check for check in _report(api, e1_sessions).checks
                 if check.name == "stack_ready")
    assert "database already holding" in stack.detail
    assert "database empty" not in stack.detail


def test_evidence_independent_of_run_history_is_reproduced_exactly(api, e1_sessions):
    """Checks that describe the committed system, not this run, must not drift."""
    stable = {"demo_dataset", "connector_health", "read_only", "clean_rebuild"}

    def details(report) -> dict[str, str]:
        return {check.name: check.detail for check in report.checks if check.name in stable}

    first = _report(api, e1_sessions)
    second = _report(api, e1_sessions)

    assert details(second) == details(first)
    assert set(details(first)) == stable


def test_no_source_file_is_written_by_the_scenario(api, e1_sessions):
    before = verify_layer1.source_fingerprints()

    report = _report(api, e1_sessions)

    assert verify_layer1.source_fingerprints() == before
    read_only = next(check for check in report.checks if check.name == "read_only")
    assert read_only.outcome is Outcome.PASS
    assert "14 source files byte-identical" in read_only.detail


# ---------------------------------------------------------------------------
# What the individual checks prove
# ---------------------------------------------------------------------------


def test_the_ingestion_check_reports_truthful_counts_for_the_committed_dataset(api, e1_sessions):
    report = _report(api, e1_sessions)

    ingestion = next(check for check in report.checks if check.name == "ingestion")
    assert "SUCCESS" in ingestion.detail
    assert "over 5 entity types" in ingestion.detail
    runs = api.get("/api/v1/ingestion/runs", params={"limit": 500}).json()
    started = [run for run in runs["items"] if run["status"] != "PARTIAL_SUCCESS"]
    assert {run["status"] for run in started} == {"SUCCESS", "NOOP"}


def test_the_api_query_check_sees_provenance_on_every_queried_record(api, e1_sessions):
    _report(api, e1_sessions)

    page = api.get("/api/v1/entities/customers", params={"limit": 500}).json()
    # 50 from the demo dataset plus the two the malformed fixture got past the gate.
    assert page["total"] == 52
    for item in page["items"]:
        for field in verify_layer1.PROVENANCE_FIELDS:
            assert item[field], f"{item['source_id']} is missing {field}"


def test_the_validation_check_leaves_valid_fixture_rows_queryable(api, e1_sessions):
    report = _report(api, e1_sessions)

    validation = next(check for check in report.checks if check.name == "validation")
    assert validation.outcome is Outcome.PASS, validation.detail
    assert "no source values disclosed" in validation.detail
    customers = {item["source_id"] for item in
                 api.get("/api/v1/entities/customers", params={"limit": 500}).json()["items"]}
    # CUST-902 is missing its email, which is a warning; CUST-903 carries an unknown
    # status value, which the quality gate rejects.
    assert {"CUST-901", "CUST-902"} <= customers
    assert "CUST-903" not in customers
    deals = {item["source_id"] for item in
             api.get("/api/v1/entities/deals", params={"limit": 500}).json()["items"]}
    assert {"DEAL-901", "DEAL-902"} <= deals
    assert {"DEAL-903", "DEAL-904"}.isdisjoint(deals)


def test_the_validation_check_reads_structured_errors_through_the_api(api, e1_sessions):
    _report(api, e1_sessions)

    runs = api.get("/api/v1/ingestion/runs",
                   params={"status": "PARTIAL_SUCCESS", "limit": 50}).json()
    assert runs["total"] == 1
    run_id = runs["items"][0]["run_id"]
    errors = api.get(f"/api/v1/ingestion/runs/{run_id}/errors", params={"limit": 500}).json()
    assert errors["total"] > 0
    for item in errors["items"]:
        assert item["code"] and item["message"] and item["findings"]


def test_the_idempotency_check_leaves_one_record_per_source_identity(api, e1_sessions):
    _report(api, e1_sessions)
    _report(api, e1_sessions)

    for entity in verify_layer1.ENTITY_TYPES:
        page = api.get(f"/api/v1/entities/{entity}", params={"limit": 500}).json()
        identities = [(item["source_system"], item["source_entity"], item["source_id"])
                      for item in page["items"]]
        assert len(set(identities)) == len(identities) == page["total"]


def test_the_connector_health_check_covers_every_configured_source(api, e1_sessions):
    report = _report(api, e1_sessions)

    health = next(check for check in report.checks if check.name == "connector_health")
    assert health.outcome is Outcome.PASS, health.detail
    assert health.detail == "1 configured sources healthy and read-only: csv_demo"


# ---------------------------------------------------------------------------
# Failure behaviour
# ---------------------------------------------------------------------------


class _UnhealthySource:
    """A configured connector whose source cannot be reached."""

    source_name = "csv_demo"
    source_type = "csv"

    def __init__(self, healthy: SourceConnector) -> None:
        self._healthy = healthy

    def capabilities(self):
        return self._healthy.capabilities()

    def list_entities(self, entity_type, cursor=None, page_size=100):
        return self._healthy.list_entities(entity_type, cursor=cursor, page_size=page_size)

    def get_entity(self, entity_type, entity_id):
        return self._healthy.get_entity(entity_type, entity_id)

    def health_check(self) -> bool:
        raise ConnectorError("source unreachable", source_name=self.source_name)


def test_an_unreachable_source_fails_the_connector_health_check(e1_sessions):
    unhealthy = _UnhealthySource(build_connector("csv_demo"))
    with _client(e1_sessions, _csv_only(build=lambda source: unhealthy)) as client:
        report = _report(client, e1_sessions)

    health = next(check for check in report.checks if check.name == "connector_health")
    assert health.outcome is Outcome.FAIL
    assert "source csv_demo reports health unhealthy" in health.detail
    assert report.exit_code == 1


def test_an_unreachable_database_fails_the_stack_check(e1_sessions):
    broken = sessionmaker(bind=create_engine(
        "postgresql://nobody:nobody@127.0.0.1:1/absent", connect_args={"connect_timeout": 1}))
    with _client(broken, _csv_only()) as client:
        report = _report(client, e1_sessions)

    stack = next(check for check in report.checks if check.name == "stack_ready")
    assert stack.outcome is Outcome.FAIL
    assert "not 200" in stack.detail or "not 'healthy'" in stack.detail
    assert report.exit_code == 1


def test_a_failing_check_does_not_hide_the_checks_after_it(e1_sessions):
    unhealthy = _UnhealthySource(build_connector("csv_demo"))
    with _client(e1_sessions, _csv_only(build=lambda source: unhealthy)) as client:
        report = _report(client, e1_sessions)

    assert _outcomes(report)["read_only"] is Outcome.PASS
    assert _outcomes(report)["demo_dataset"] is Outcome.PASS
    assert len(report.checks) == len(EXPECTED_CHECKS)


def test_the_test_suite_step_runs_only_when_requested(api, e1_sessions):
    calls: list[int] = []

    skipped = _report(api, e1_sessions)
    requested = _report(api, e1_sessions, with_tests=True,
                        test_runner=lambda: (calls.append(1), (0, "3973 passed"))[1])

    assert _outcomes(skipped)["test_suite"] is Outcome.SKIPPED
    assert _outcomes(requested)["test_suite"] is Outcome.PASS
    assert next(c for c in requested.checks if c.name == "test_suite").detail == "3973 passed"
    assert calls == [1]


def test_a_failing_test_suite_fails_the_scenario(api, e1_sessions):
    report = _report(api, e1_sessions, with_tests=True,
                     test_runner=lambda: (1, "2 failed, 3971 passed"))

    assert _outcomes(report)["test_suite"] is Outcome.FAIL
    assert report.exit_code == 1
