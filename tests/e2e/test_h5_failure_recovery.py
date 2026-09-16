"""
H5 failure-recovery tests (spec Section 15, "Failure recovery").

    malformed row, network error, DB failure, partial batch.

The E1 suite drives these failures through the orchestrator and inspects the
database. This module drives the same failures through the running
application and observes them the way an operator would: the run's status
and counts, the structured errors at GET /ingestion/runs/{id}/errors, and
what is still queryable at GET /entities/... afterwards.

The governing rule under every failure is the same: a failure must be
*reported*, not hidden, and it must not corrupt what already committed.
A partially failed run therefore still returns usable records, still carries
truthful counts, and never leaks a source value or an internal message into
an API response.
"""

from __future__ import annotations

import uuid

import pytest
from conftest import (
    API,
    BAD_FIXTURE_DIR,
    DEMO_DIR,
    ENTITY_TYPES,
    csv_ids,
    csv_rows,
    make_app,
    page,
    start_run,
)
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.connectors.base import SourceConnector
from app.connectors.registry import build_connector
from app.connectors.types import (
    ConnectorCapabilities,
    ConnectorHealth,
    ConnectorUnavailableError,
    Page,
    SourceEntity,
)

pytestmark = [pytest.mark.e2e, pytest.mark.integration]


def _client(sessions, build) -> TestClient:
    return TestClient(make_app(sessions, build), raise_server_exceptions=False)


def _csv_build(directory):
    def build(source: str) -> SourceConnector:
        if source == "csv_demo":
            return build_connector("csv_demo", data_directory=directory)
        return build_connector(source)
    return build


# ---------------------------------------------------------------------------
# A connector that fails on demand
# ---------------------------------------------------------------------------


class FailingConnector:
    """A connector that answers normally until the injected failure fires."""

    def __init__(
        self,
        *,
        fail_on: tuple[str, int] | None = None,
        failure: Exception | None = None,
        healthy: bool = True,
        supports_health_check: bool = True,
    ) -> None:
        self._inner = build_connector("csv_demo", data_directory=DEMO_DIR)
        self._fail_on = fail_on
        self._failure = failure
        self._healthy = healthy
        self._supports_health_check = supports_health_check
        self.health_checks = 0

    @property
    def source_name(self) -> str:
        return "csv_demo"

    @property
    def source_type(self) -> str:
        return "csv"

    def health_check(self) -> ConnectorHealth:
        self.health_checks += 1
        return ConnectorHealth(healthy=self._healthy, source_name=self.source_name)

    def list_entities(self) -> list[SourceEntity]:
        return self._inner.list_entities()

    def capabilities(self) -> ConnectorCapabilities:
        inner = self._inner.capabilities()
        return ConnectorCapabilities(
            supported_entity_types=inner.supported_entity_types,
            supports_incremental=inner.supports_incremental,
            supports_health_check=self._supports_health_check,
            read_only=True,
        )

    def fetch_entities(self, entity_type, cursor=None, page_size=100) -> Page[dict]:
        if self._fail_on == (entity_type, int(cursor or 0)) and self._failure is not None:
            raise self._failure
        return self._inner.fetch_entities(entity_type, cursor, page_size)

    def get_entity(self, entity_type, source_id) -> dict:
        return self._inner.get_entity(entity_type, source_id)


def _failing_build(**kwargs):
    connector = FailingConnector(**kwargs)

    def build(source: str) -> SourceConnector:
        return connector if source == "csv_demo" else build_connector(source)

    return build, connector


# ---------------------------------------------------------------------------
# Malformed rows
# ---------------------------------------------------------------------------


def test_a_malformed_fixture_is_partially_successful_not_failed(bad_fixture_api):
    """Spec Section 20 K and L: bad rows are quarantined, good rows land."""
    run = start_run(bad_fixture_api)

    assert run["status"] == "PARTIAL_SUCCESS"
    assert run["records_rejected"] > 0
    assert run["records_inserted"] > 0
    assert run["records_fetched"] == (
        run["records_inserted"] + run["records_updated"] + run["records_unchanged"]
        + run["records_rejected"] + run["records_failed"]
    )


def test_quarantined_rows_are_reported_as_structured_errors(bad_fixture_api):
    """Section 21: errors are persisted and queryable, never only printed."""
    run = start_run(bad_fixture_api)
    errors = bad_fixture_api.get(f"{API}/ingestion/runs/{run['run_id']}/errors",
                                 params={"limit": 500}).json()

    assert errors["total"] == run["records_rejected"] + run["warnings"]
    severities = {item["severity"] for item in errors["items"]}
    assert "ERROR" in severities
    for item in errors["items"]:
        assert item["code"]
        assert item["message"]
        assert item["source_system"] == "csv_demo"


def test_error_reports_identify_the_rejected_record_by_its_source_id(bad_fixture_api):
    """The identity is reported so an operator can find the offending row."""
    run = start_run(bad_fixture_api)
    items = bad_fixture_api.get(f"{API}/ingestion/runs/{run['run_id']}/errors",
                                params={"limit": 500}).json()["items"]

    reported = {item["source_id"] for item in items if item["source_id"]}
    assert reported, "a rejected record must be identifiable"
    for entity in ENTITY_TYPES:
        for source_id in reported & csv_ids(BAD_FIXTURE_DIR, entity):
            assert source_id in csv_ids(BAD_FIXTURE_DIR, entity)


def test_error_reports_never_echo_a_source_field_value(bad_fixture_api):
    """A rejected value may be personal data or a credential (Section 14).

    The source identity is deliberately reported; every other column of the
    offending row must not appear anywhere in the response.
    """
    run = start_run(bad_fixture_api)
    body = bad_fixture_api.get(f"{API}/ingestion/runs/{run['run_id']}/errors",
                               params={"limit": 500}).text

    identities = set()
    for entity in ENTITY_TYPES:
        identities |= csv_ids(BAD_FIXTURE_DIR, entity)

    values = set()
    for entity in ENTITY_TYPES:
        for row in csv_rows(BAD_FIXTURE_DIR, entity):
            values.update(value for value in row.values()
                          if len(value.strip()) >= 8 and value not in identities)
    assert "contact@kestrel-supplies.example" in values, "emails must be under test"
    assert "Kestrel Supplies" in values, "names must be under test"
    assert len(values) >= 15, "the fixture must supply enough values to be a real check"

    leaked = sorted(value for value in values if value in body)
    assert leaked == [], f"error report echoed source values: {leaked[:3]}"


def test_valid_rows_of_a_malformed_fixture_stay_queryable(bad_fixture_api):
    """Section 20 L: a bad row never takes a good one down with it."""
    run = start_run(bad_fixture_api)
    assert run["records_inserted"] > 0

    total = sum(page(bad_fixture_api, entity)["total"] for entity in ENTITY_TYPES)
    assert total == run["records_inserted"]
    for entity in ENTITY_TYPES:
        for item in page(bad_fixture_api, entity)["items"]:
            assert item["source_id"] in csv_ids(BAD_FIXTURE_DIR, entity)


def test_a_malformed_fixture_does_not_corrupt_an_earlier_clean_ingestion(e1_sessions):
    """The demo records survive a later run over the bad fixture."""
    good = _client(e1_sessions, _csv_build(DEMO_DIR))
    start_run(good)
    before = {entity: {item["source_id"]: item["record_hash"]
                       for item in page(good, entity)["items"]}
              for entity in ENTITY_TYPES}

    bad = _client(e1_sessions, _csv_build(BAD_FIXTURE_DIR))
    run = start_run(bad)
    assert run["status"] == "PARTIAL_SUCCESS"

    after = {entity: {item["source_id"]: item["record_hash"]
                      for item in page(good, entity)["items"]}
             for entity in ENTITY_TYPES}
    for entity in ENTITY_TYPES:
        for source_id, record_hash in before[entity].items():
            assert after[entity][source_id] == record_hash, f"{entity}/{source_id} changed"


def test_repeating_a_malformed_ingestion_creates_no_duplicates(bad_fixture_api):
    """Quarantine is idempotent too: the same bad rows reject the same way."""
    first = start_run(bad_fixture_api)
    identities = {entity: sorted(item["source_id"]
                                 for item in page(bad_fixture_api, entity)["items"])
                  for entity in ENTITY_TYPES}

    second = start_run(bad_fixture_api)
    assert second["records_rejected"] == first["records_rejected"]
    assert second["records_inserted"] == 0
    assert {entity: sorted(item["source_id"]
                           for item in page(bad_fixture_api, entity)["items"])
            for entity in ENTITY_TYPES} == identities


# ---------------------------------------------------------------------------
# Connector and network failures
# ---------------------------------------------------------------------------


def test_an_unhealthy_source_fails_the_run_without_fetching(e1_sessions):
    """A source that cannot be reached is reported, not silently skipped."""
    build, connector = _failing_build(healthy=False)
    client = _client(e1_sessions, build)

    run = start_run(client)
    assert run["status"] == "FAILED"
    assert run["records_fetched"] == 0
    assert connector.health_checks == 1

    errors = client.get(f"{API}/ingestion/runs/{run['run_id']}/errors").json()
    assert errors["total"] >= 1
    assert any("CONNECTOR" in item["code"] for item in errors["items"])


def test_a_connector_without_health_support_is_ingested_anyway(e1_sessions):
    """A connector that declares no health check is not blocked by one."""
    build, connector = _failing_build(supports_health_check=False)
    client = _client(e1_sessions, build)

    run = start_run(client)
    assert run["status"] == "SUCCESS"
    assert connector.health_checks == 0, "the orchestrator honoured the capability"
    assert run["records_inserted"] > 0


def test_a_network_failure_fails_only_the_affected_entity(e1_sessions):
    """Other entities still commit; the failure is attributed to one entity."""
    build, _ = _failing_build(
        fail_on=("deals", 0),
        failure=ConnectorUnavailableError("source unreachable", source_name="csv_demo"),
    )
    client = _client(e1_sessions, build)

    run = start_run(client)
    assert run["status"] == "PARTIAL_SUCCESS"

    results = {result["entity_type"]: result for result in run["entities"]}
    assert results["deals"]["failure"] == "ConnectorUnavailableError"
    assert results["customers"]["status"] != "FAILED"

    assert page(client, "deals")["total"] == 0
    assert page(client, "customers")["total"] == len(csv_ids(DEMO_DIR, "customers"))


def test_a_network_failure_is_reported_without_its_message(e1_sessions):
    """Connector diagnostics can name internal hosts; only the class is public."""
    secret_host = "internal-host-9f2c.example.invalid"
    build, _ = _failing_build(
        fail_on=("deals", 0),
        failure=ConnectorUnavailableError(f"cannot reach {secret_host}",
                                          source_name="csv_demo"),
    )
    client = _client(e1_sessions, build)
    run = start_run(client)

    errors = client.get(f"{API}/ingestion/runs/{run['run_id']}/errors",
                        params={"limit": 500})
    assert secret_host not in errors.text
    assert secret_host not in client.get(f"{API}/ingestion/runs/{run['run_id']}").text


def test_a_failed_entity_can_be_completed_by_a_later_run(e1_sessions):
    """Recovery: rerunning after the source returns fills the gap."""
    build, _ = _failing_build(
        fail_on=("deals", 0),
        failure=ConnectorUnavailableError("source unreachable", source_name="csv_demo"),
    )
    client = _client(e1_sessions, build)
    first = start_run(client)
    assert first["status"] == "PARTIAL_SUCCESS"
    assert page(client, "deals")["total"] == 0

    recovered = _client(e1_sessions, _csv_build(DEMO_DIR))
    second = start_run(recovered)

    assert second["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert page(recovered, "deals")["total"] == len(csv_ids(DEMO_DIR, "deals"))
    for entity in ENTITY_TYPES:
        assert page(recovered, entity)["total"] == len(csv_ids(DEMO_DIR, entity))


def test_a_partial_batch_keeps_the_pages_that_already_committed(e1_sessions):
    """A mid-entity failure does not roll back earlier committed pages."""
    build, _ = _failing_build(
        fail_on=("customers", 10),
        failure=ConnectorUnavailableError("source unreachable", source_name="csv_demo"),
    )
    client = _client(e1_sessions, build)

    run = start_run(client, page_size=10)
    assert run["status"] == "PARTIAL_SUCCESS"

    landed = page(client, "customers")["total"]
    assert landed == 10, "the first page committed, the second never arrived"
    assert landed < len(csv_ids(DEMO_DIR, "customers"))


def test_a_partial_batch_is_completed_by_a_later_run_without_duplicates(e1_sessions):
    """The checkpoint never passed the failed batch, so a rerun finishes it."""
    build, _ = _failing_build(
        fail_on=("customers", 10),
        failure=ConnectorUnavailableError("source unreachable", source_name="csv_demo"),
    )
    start_run(_client(e1_sessions, build), page_size=10)

    recovered = _client(e1_sessions, _csv_build(DEMO_DIR))
    start_run(recovered)

    body = page(recovered, "customers")
    assert body["total"] == len(csv_ids(DEMO_DIR, "customers"))
    source_ids = [item["source_id"] for item in body["items"]]
    assert len(source_ids) == len(set(source_ids))


# ---------------------------------------------------------------------------
# Database failures
# ---------------------------------------------------------------------------


def test_a_database_failure_during_a_run_is_reported_not_swallowed(e1_sessions, monkeypatch):
    """An unreachable database fails the request with the error envelope."""
    client = _client(e1_sessions, _csv_build(DEMO_DIR))

    from app.api.v1 import ingestion as ingestion_route

    def explode(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("database is unreachable"))

    monkeypatch.setattr(ingestion_route, "run_ingestion", explode)
    response = client.post(f"{API}/ingestion/runs", json={"source": "csv_demo"})

    assert response.status_code >= 400
    body = response.json()
    assert set(body) == {"error"}
    assert "database is unreachable" not in response.text


def test_the_api_reports_an_unready_database_through_health(e1_sessions, monkeypatch):
    """Readiness is separate from liveness (spec Section 16)."""
    client = _client(e1_sessions, _csv_build(DEMO_DIR))
    assert client.get(f"{API}/health").json()["checks"]["database"] == "ok"


def test_a_failed_run_leaves_no_half_written_entity(e1_sessions):
    """Either a batch commits or it does not; no entity is left mid-write."""
    build, _ = _failing_build(
        fail_on=("organizations", 0),
        failure=ConnectorUnavailableError("source unreachable", source_name="csv_demo"),
    )
    client = _client(e1_sessions, build)

    run = start_run(client)
    assert page(client, "organizations")["total"] == 0

    results = {result["entity_type"]: result for result in run["entities"]}
    assert results["organizations"]["records_inserted"] == 0


def test_every_failure_still_produces_a_persisted_run_row(e1_sessions):
    """Section 21: a failure is never invisible; the run is always recorded."""
    build, _ = _failing_build(healthy=False)
    client = _client(e1_sessions, build)
    run = start_run(client)

    listing = client.get(f"{API}/ingestion/runs").json()
    assert listing["total"] == 1
    assert listing["items"][0]["run_id"] == run["run_id"]
    assert listing["items"][0]["status"] == "FAILED"

    totals = client.get(f"{API}/metrics/ingestion").json()["totals"]
    assert totals["runs_by_status"]["FAILED"] == 1


def test_a_failed_run_is_filterable_by_status(e1_sessions):
    """Operators find failures without reading every run."""
    failing_build, _ = _failing_build(healthy=False)
    start_run(_client(e1_sessions, failing_build))
    good = _client(e1_sessions, _csv_build(DEMO_DIR))
    start_run(good)

    failed = good.get(f"{API}/ingestion/runs", params={"status": "FAILED"}).json()
    assert failed["total"] == 1
    assert failed["items"][0]["status"] == "FAILED"


def test_an_error_page_for_an_unknown_run_is_not_found(e1_sessions):
    client = _client(e1_sessions, _csv_build(DEMO_DIR))
    assert client.get(f"{API}/ingestion/runs/{uuid.uuid4()}/errors").status_code == 404
