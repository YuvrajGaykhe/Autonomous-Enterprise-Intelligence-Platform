"""
scripts/verify_layer1.py unit tests: the command surface and every failure branch.

The E2E suite (tests/e2e/test_i1_acceptance.py) proves the scenario passes
against a real stack. These tests cover what a passing stack cannot show: the
argument contract, the report model, the committed-file helpers, and the
message each check produces when its acceptance requirement is violated. The
API is a stub here, so a check can be driven into exactly one failure at a
time without a database.
"""

from __future__ import annotations

import contextlib
import importlib.util
import itertools
import re
import subprocess
import sys
import types
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]


def _load_script() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "verify_layer1", REPO / "scripts" / "verify_layer1.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify_layer1 = _load_script()
Check = verify_layer1.Check
CheckFailed = verify_layer1.CheckFailed
Outcome = verify_layer1.Outcome
Report = verify_layer1.Report
Scenario = verify_layer1.Scenario
ScenarioAborted = verify_layer1.ScenarioAborted
API = verify_layer1.API
ENTITY_TYPES = verify_layer1.ENTITY_TYPES
BAD_FIXTURE_DIR = verify_layer1.BAD_FIXTURE_DIR


# ---------------------------------------------------------------------------
# A stub API
# ---------------------------------------------------------------------------


class StubResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class StubClient:
    """Answers each (method, path) from a routing table and records every call."""

    base_url = "http://stub"

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Any] = {}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def route(self, method: str, path: str, payload: Any, status_code: int = 200) -> StubClient:
        self.routes[(method, path)] = StubResponse(payload, status_code)
        return self

    def dynamic(self, method: str, path: str, answer) -> StubClient:
        self.routes[(method, path)] = answer
        return self

    def request(self, method: str, path: str, **kwargs: Any) -> StubResponse:
        self.calls.append((method, path, kwargs))
        entry = self.routes.get((method, path))
        if entry is None:
            raise AssertionError(f"the scenario made an unrouted request: {method} {path}")
        return entry(kwargs) if callable(entry) else entry

    def get(self, path: str, **kwargs: Any) -> StubResponse:
        return self.request("GET", path, **kwargs)


def health_payload(status: str = "healthy", database: str = "ok") -> dict[str, Any]:
    return {"status": status, "service": "ai-ceo-layer1", "version": "0.1.0",
            "checks": {"database": database}}


def metrics_payload(counts: dict[str, int] | None = None) -> dict[str, Any]:
    return {"totals": {"canonical_records": dict.fromkeys(ENTITY_TYPES, 0)
                       if counts is None else counts}}


def run_payload(**overrides: Any) -> dict[str, Any]:
    run = {"run_id": str(uuid.uuid4()), "status": "SUCCESS", "finished_at": "2026-09-16T10:00:00Z",
           "records_fetched": 10, "records_raw_persisted": 10, "records_inserted": 10,
           "records_updated": 0, "records_unchanged": 0, "records_rejected": 0,
           "records_failed": 0, "batches_failed": 0,
           "entities": [{"entity_type": entity, "status": "completed", "records_fetched": 2,
                         "failure": None} for entity in verify_layer1.SCENARIO_ENTITIES]}
    run.update(overrides)
    return run


def record(source_id: str, **overrides: Any) -> dict[str, Any]:
    item = {"id": str(uuid.uuid4()), "source_system": "csv_demo", "source_entity": "customers",
            "source_id": source_id, "ingested_at": "2026-09-16T10:00:00Z",
            "ingestion_run_id": str(uuid.uuid4()), "record_hash": "9a1e"}
    item.update(overrides)
    return item


def page_payload(items: list[dict[str, Any]], total: int | None = None,
                 limit: int = 2, offset: int = 0) -> dict[str, Any]:
    return {"items": items, "total": len(items) if total is None else total,
            "limit": limit, "offset": offset}


def scenario(client: StubClient, **kwargs: Any) -> Scenario:
    return Scenario(client, sessions=None, **kwargs)


def fails(check, message: str) -> None:
    with pytest.raises(CheckFailed) as failure:
        check()
    assert message in str(failure.value)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def test_the_defaults_target_the_compose_stack():
    args = verify_layer1.parse_args([])

    assert args.base_url == "http://localhost:8000"
    assert args.page_size == verify_layer1.DEFAULT_PAGE_SIZE
    assert args.timeout == verify_layer1.DEFAULT_TIMEOUT
    assert args.with_tests is False


def test_every_option_can_be_overridden():
    args = verify_layer1.parse_args(
        ["--base-url", "http://api:9000", "--timeout", "5", "--page-size", "7", "--with-tests"])

    assert (args.base_url, args.timeout, args.page_size, args.with_tests) == (
        "http://api:9000", 5.0, 7, True)


@pytest.mark.parametrize("argv, message", [
    (["--page-size", "0"], "--page-size must be between 1"),
    (["--page-size", "-1"], "--page-size must be between 1"),
    ([f"--page-size={verify_layer1.MAX_PAGE_SIZE + 1}"], "--page-size must be between 1"),
    (["--timeout", "0"], "--timeout must be greater than zero"),
    (["--timeout", "-0.5"], "--timeout must be greater than zero"),
])
def test_invalid_arguments_exit_two_without_touching_the_stack(argv, message, capsys, monkeypatch):
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the scenario must not connect when arguments are invalid")

    monkeypatch.setattr(verify_layer1, "create_engine", refuse)

    assert verify_layer1.main(argv) == 2
    assert message in capsys.readouterr().err


def test_an_unknown_option_is_refused_by_argparse():
    with pytest.raises(SystemExit):
        verify_layer1.parse_args(["--drop-database"])


# ---------------------------------------------------------------------------
# The report model
# ---------------------------------------------------------------------------


def test_a_check_line_names_its_steps_name_outcome_and_evidence():
    line = str(Check("E-F", "ingestion", Outcome.PASS, "94 records"))

    assert line.startswith("verify-layer1: ")
    assert "E-F" in line and "ingestion" in line and "PASS" in line and "94 records" in line


def test_a_report_counts_each_outcome_and_lists_only_failures():
    report = Report((Check("A", "one", Outcome.PASS, ""), Check("B", "two", Outcome.FAIL, "why"),
                     Check("C", "three", Outcome.SKIPPED, ""),
                     Check("D", "four", Outcome.OPERATOR, "")))

    assert report.count(Outcome.PASS) == 1
    assert [check.name for check in report.failures] == ["two"]
    assert report.summary() == "verify-layer1: 1 passed, 1 failed, 1 skipped, 1 operator"


def test_only_a_failed_check_makes_the_command_fail():
    passing = Report((Check("A", "one", Outcome.PASS, ""),
                      Check("N", "test_suite", Outcome.SKIPPED, ""),
                      Check("O", "clean_rebuild", Outcome.OPERATOR, "")))

    assert passing.exit_code == 0
    assert Report(passing.checks + (Check("B", "two", Outcome.FAIL, ""),)).exit_code == 1


def test_an_empty_report_is_not_a_failure():
    assert Report(()).exit_code == 0


# ---------------------------------------------------------------------------
# The committed source files
# ---------------------------------------------------------------------------


def test_the_entity_mapping_comes_from_the_committed_connector_configuration():
    entities = verify_layer1.csv_entities()

    assert set(entities) == set(ENTITY_TYPES)
    assert entities["customers"].file == "customers.csv"
    assert entities["support_tickets"].id_column == "ticket_id"


def test_the_malformed_fixture_source_ids_are_read_from_its_own_files():
    ids = verify_layer1.fixture_source_ids(BAD_FIXTURE_DIR)

    assert ids["customers"] == {"CUST-901", "CUST-902", "CUST-903"}
    assert ids["deals"] == {"DEAL-901", "DEAL-902", "DEAL-903", "DEAL-904"}
    assert ids["organizations"] == set()


def test_a_directory_without_source_files_yields_no_source_ids(tmp_path):
    assert verify_layer1.fixture_source_ids(tmp_path) == dict.fromkeys(ENTITY_TYPES, set())


def test_only_disclosable_source_values_are_watched_for(tmp_path):
    (tmp_path / "customers.csv").write_text(
        "customer_id,customer_name,email_address,status\n"
        "CUST-901,Kestrel Supplies,contact@kestrel.example,active\n",
        encoding="utf-8")

    values = verify_layer1.sensitive_values(tmp_path)

    assert values == {"Kestrel Supplies", "contact@kestrel.example"}
    assert "CUST-901" not in values, "the identifier is published in errors by design"
    assert "active" not in values, "single tokens are canonical vocabulary, not disclosure"


def test_an_identifier_is_never_treated_as_a_disclosable_value(tmp_path):
    """Structured errors name the rejected row's source id on purpose, whatever it looks like."""
    (tmp_path / "customers.csv").write_text(
        "customer_id,customer_name\nCUST 901 A,Kestrel Supplies\n", encoding="utf-8")

    values = verify_layer1.sensitive_values(tmp_path)

    assert values == {"Kestrel Supplies"}
    assert "CUST 901 A" not in values


def test_every_committed_source_file_is_fingerprinted():
    fingerprints = verify_layer1.source_fingerprints()

    assert len(fingerprints) == 14
    assert "demo/customers.csv" in fingerprints
    assert "csv_demo_bad/deals.csv" in fingerprints
    assert all(len(digest) == 64 for digest in fingerprints.values())


def test_a_changed_source_file_changes_its_fingerprint(tmp_path, monkeypatch):
    demo = tmp_path / "demo"
    demo.mkdir()
    (demo / "customers.csv").write_text("customer_id\nCUST-001\n", encoding="utf-8")
    monkeypatch.setattr(verify_layer1, "DEMO_DIR", demo)
    monkeypatch.setattr(verify_layer1, "BAD_FIXTURE_DIR", tmp_path / "absent")
    before = verify_layer1.source_fingerprints()

    (demo / "customers.csv").write_text("customer_id\nCUST-002\n", encoding="utf-8")

    assert verify_layer1.source_fingerprints() != before


# ---------------------------------------------------------------------------
# Safety: the read-only check
# ---------------------------------------------------------------------------


def test_untouched_source_files_pass_the_read_only_check():
    detail = scenario(StubClient()).read_only()

    assert detail == "14 source files byte-identical (sha256) after the scenario"


def test_a_rewritten_source_file_fails_the_read_only_check():
    check = scenario(StubClient())
    check.fingerprints = dict(check.fingerprints, **{"demo/customers.csv": "0" * 64})

    fails(check.read_only, "source files changed during the scenario: demo/customers.csv")


def test_a_source_file_that_appears_during_the_scenario_fails_the_read_only_check():
    check = scenario(StubClient())
    check.fingerprints.pop("demo/deals.csv")

    fails(check.read_only, "demo/deals.csv")


# ---------------------------------------------------------------------------
# Reaching the stack at all
# ---------------------------------------------------------------------------


def test_an_unreachable_api_aborts_the_scenario():
    class Unreachable(StubClient):
        def get(self, path: str, **kwargs: Any) -> StubResponse:
            raise httpx.ConnectError("refused")

    with pytest.raises(ScenarioAborted) as aborted:
        verify_layer1.probe(Unreachable())
    assert "could not be reached (ConnectError)" in str(aborted.value)
    assert "make docker-up" in str(aborted.value)


def test_a_reachable_api_does_not_abort():
    assert verify_layer1.probe(StubClient().route("GET", f"{API}/health", health_payload())) is None


def test_a_transport_failure_mid_scenario_fails_only_that_check():
    class Flaky(StubClient):
        def request(self, method: str, path: str, **kwargs: Any) -> StubResponse:
            raise httpx.ReadTimeout("slow")

    fails(scenario(Flaky()).stack_ready, f"GET {API}/health could not be reached (ReadTimeout)")


# ---------------------------------------------------------------------------
# Steps A-C — the stack is ready
# ---------------------------------------------------------------------------


def _ready_client(counts: dict[str, int] | None = None) -> StubClient:
    return (StubClient()
            .route("GET", f"{API}/health", health_payload())
            .route("GET", f"{API}/metrics/ingestion", metrics_payload(counts)))


def test_a_ready_stack_reports_its_service_and_starting_state():
    detail = scenario(_ready_client()).stack_ready()

    assert "ai-ceo-layer1 0.1.0 ready" in detail
    assert "all 7 canonical tables queryable" in detail
    assert detail.endswith("database empty")


def test_a_populated_database_is_reported_as_such():
    counts = dict.fromkeys(ENTITY_TYPES, 0) | {"customers": 50}

    assert scenario(_ready_client(counts)).stack_ready().endswith(
        "database already holding 50 canonical records")


def test_a_health_endpoint_that_is_not_200_fails_the_stack_check():
    client = _ready_client()
    client.route("GET", f"{API}/health", health_payload("unhealthy", "unavailable"), 503)

    fails(scenario(client).stack_ready, f"GET {API}/health answered 503, not 200")


def test_an_unhealthy_api_fails_the_stack_check():
    client = _ready_client().route("GET", f"{API}/health", health_payload("degraded"))

    fails(scenario(client).stack_ready, "the API reports status 'degraded', not 'healthy'")


def test_an_unreachable_database_fails_the_stack_check():
    client = _ready_client().route("GET", f"{API}/health", health_payload(database="unavailable"))

    fails(scenario(client).stack_ready, "the API reports database 'unavailable', not 'ok'")


def test_a_missing_canonical_table_fails_the_stack_check():
    client = _ready_client({"customers": 1})

    fails(scenario(client).stack_ready, "not the seven canonical entity types")


# ---------------------------------------------------------------------------
# Step D — the committed demo dataset
# ---------------------------------------------------------------------------


def test_the_committed_dataset_regenerates_byte_identically():
    detail = scenario(StubClient()).demo_dataset()

    assert detail.startswith("14 committed CSV files regenerate byte-identically")
    assert "customers 50" in detail and "support_tickets 80" in detail


def test_a_stale_committed_file_fails_the_dataset_check(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_layer1, "DEMO_DIR", tmp_path)

    fails(scenario(StubClient()).demo_dataset,
          "the committed demo files differ from the generator: customers.csv")


def test_a_stale_malformed_fixture_fails_the_dataset_check(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_layer1, "BAD_FIXTURE_DIR", tmp_path)

    fails(scenario(StubClient()).demo_dataset,
          "the committed malformed fixture files differ from the generator")


# ---------------------------------------------------------------------------
# Steps E-F — ingestion and truthful counts
# ---------------------------------------------------------------------------


def _ingest_client(run: dict[str, Any], counts: dict[str, int] | None = None) -> StubClient:
    return (_ready_client(counts)
            .route("POST", f"{API}/ingestion/runs", run, 201))


def test_a_rejected_ingestion_request_fails_the_ingestion_check():
    client = _ingest_client(run_payload())
    client.route("POST", f"{API}/ingestion/runs", {"error": {}}, 422)

    fails(scenario(client).ingestion, f"POST {API}/ingestion/runs answered 422, not 201")


@pytest.mark.parametrize("status", ["FAILED", "RUNNING", "", "success"])
def test_a_run_outside_the_accepted_statuses_fails_the_ingestion_check(status):
    client = _ingest_client(run_payload(status=status))

    fails(scenario(client).ingestion, f"the run finished {status}, not one of")


@pytest.mark.parametrize("overrides, message", [
    ({"records_fetched": 11}, "fetched 11 records but accounts for 10"),
    ({"records_raw_persisted": 9}, "persisted 9 raw records for 10 fetched"),
    ({"finished_at": None}, "has no finished_at"),
    ({"batches_failed": 2}, "rolled back 2 batches"),
])
def test_untruthful_counts_fail_the_ingestion_check(overrides, message):
    fails(scenario(_ingest_client(run_payload(**overrides))).ingestion, message)


def test_a_run_covering_the_wrong_entities_fails_the_ingestion_check():
    run = run_payload(entities=[{"entity_type": "customers", "status": "completed",
                                 "records_fetched": 10, "failure": None}])

    fails(scenario(_ingest_client(run)).ingestion, "the run covered ['customers'], not")


def test_an_entity_that_did_not_complete_fails_the_ingestion_check():
    entities = run_payload()["entities"]
    entities[0] = {**entities[0], "status": "failed", "failure": "ConnectorTimeout"}

    fails(scenario(_ingest_client(run_payload(entities=entities))).ingestion,
          "entity customers finished failed (ConnectorTimeout)")


@pytest.mark.parametrize("fetched", [2, 51])
def test_an_entity_count_that_contradicts_the_committed_csv_fails_the_ingestion_check(fetched):
    """Both directions matter: a short read loses records, a long read invents them."""
    entities = [{"entity_type": entity, "status": "completed",
                 "records_fetched": fetched if entity == "customers" else 2, "failure": None}
                for entity in verify_layer1.SCENARIO_ENTITIES]
    check = scenario(_ingest_client(run_payload(entities=entities)))
    check.demo_dataset()

    fails(check.ingestion,
          f"entity customers fetched {fetched} records, but the committed CSV holds 50")


def test_a_successful_ingestion_reports_every_count_it_verified():
    check = scenario(_ingest_client(run_payload()))

    detail = check.ingestion()

    assert detail == (f"run {check.state['run']['run_id'][:8]} SUCCESS: fetched 10 = "
                      "10 inserted + 0 updated + 0 unchanged + 0 rejected + 0 failed, "
                      "10 raw records persisted over 5 entity types")


# ---------------------------------------------------------------------------
# Steps G-H — querying canonical records
# ---------------------------------------------------------------------------


def _query_client(pages: dict[str, list[dict[str, Any]]] | None = None) -> StubClient:
    client = _ready_client()
    for entity in verify_layer1.QUERIED_ENTITIES:
        items = (pages or {}).get(entity) or [record(f"{entity}-1"), record(f"{entity}-2")]
        rest = [record(f"{entity}-3")]

        def answer(kwargs: dict[str, Any], items=items, rest=rest) -> StubResponse:
            offset = kwargs["params"]["offset"]
            shown = items if offset == 0 else rest
            return StubResponse(page_payload(shown, total=len(items) + len(rest),
                                             limit=kwargs["params"]["limit"], offset=offset))

        client.dynamic("GET", f"{API}/entities/{entity}", answer)
        client.route("GET", f"{API}/entities/{entity}/{items[0]['id']}", items[0])
    return client


def test_querying_canonical_records_reports_each_total():
    check = scenario(_query_client())
    check.state["run"] = run_payload()

    assert check.api_query() == ("full provenance and consistent pagination for "
                                "customers 3, deals 3, support_tickets 3")


def test_the_query_check_needs_the_ingestion_to_have_run():
    fails(scenario(_query_client()).api_query, "the step E-F ingestion did not complete")


def test_an_entity_type_with_no_records_fails_the_query_check():
    client = _query_client()
    client.dynamic("GET", f"{API}/entities/customers",
                   lambda kwargs: StubResponse(page_payload([], total=0)))
    check = scenario(client)
    check.state["run"] = run_payload()

    fails(check.api_query, "the API reports no customers")


def test_a_route_that_does_not_echo_its_page_fails_the_query_check():
    client = _query_client()
    client.dynamic("GET", f"{API}/entities/customers",
                   lambda kwargs: StubResponse(page_payload([record("CUST-001")], total=9,
                                                            limit=50, offset=0)))
    check = scenario(client)
    check.state["run"] = run_payload()

    fails(check.api_query, "customers echoed limit 50 offset 0, not 2/0")


def test_a_page_larger_than_its_limit_fails_the_query_check():
    client = _query_client()
    client.dynamic("GET", f"{API}/entities/customers",
                   lambda kwargs: StubResponse(page_payload(
                       [record("CUST-001"), record("CUST-002"), record("CUST-003")],
                       total=9, limit=2, offset=kwargs["params"]["offset"])))
    check = scenario(client)
    check.state["run"] = run_payload()

    fails(check.api_query, "customers returned 3 items for limit 2")


@pytest.mark.parametrize("field", verify_layer1.PROVENANCE_FIELDS)
def test_a_record_without_full_provenance_fails_the_query_check(field):
    incomplete = record("CUST-001") | {field: None}
    check = scenario(_query_client({"customers": [incomplete, record("CUST-002")]}))
    check.state["run"] = run_payload()

    fails(check.api_query, f"is missing provenance: {field}")


def test_a_total_that_moves_between_pages_fails_the_query_check():
    client = _query_client()
    client.dynamic("GET", f"{API}/entities/customers", lambda kwargs: StubResponse(page_payload(
        [record("CUST-001"), record("CUST-002")],
        total=3 if kwargs["params"]["offset"] == 0 else 4,
        limit=2, offset=kwargs["params"]["offset"])))
    check = scenario(client)
    check.state["run"] = run_payload()

    fails(check.api_query, "customers reported total 4 on page 2 and 3 on page 1")


def test_overlapping_pages_fail_the_query_check():
    repeated = [record("CUST-001"), record("CUST-002")]
    client = _query_client()
    client.dynamic("GET", f"{API}/entities/customers", lambda kwargs: StubResponse(page_payload(
        repeated, total=4, limit=2, offset=kwargs["params"]["offset"])))
    client.route("GET", f"{API}/entities/customers/{repeated[0]['id']}", repeated[0])
    check = scenario(client)
    check.state["run"] = run_payload()

    fails(check.api_query, "customers pages 1 and 2 return overlapping records")


def test_a_record_read_by_id_that_differs_fails_the_query_check():
    items = [record("CUST-001"), record("CUST-002")]
    client = _query_client({"customers": items})
    client.route("GET", f"{API}/entities/customers/{items[0]['id']}", record("CUST-999"))
    check = scenario(client)
    check.state["run"] = run_payload()

    fails(check.api_query, "customers record read by id does not match the page it came from")


# ---------------------------------------------------------------------------
# Steps I-J — idempotency and source identity
# ---------------------------------------------------------------------------


def _identity_client(identities: dict[str, list[str]] | None = None,
                     counts: dict[str, int] | None = None) -> StubClient:
    client = _ready_client(counts)
    for entity in ENTITY_TYPES:
        ids = (identities or {}).get(entity, [])
        items = [record(source_id, source_entity=entity) for source_id in ids]
        client.dynamic("GET", f"{API}/entities/{entity}",
                       lambda kwargs, items=items: StubResponse(
                           page_payload(items, total=len(items),
                                        limit=kwargs["params"]["limit"],
                                        offset=kwargs["params"]["offset"])))
    return client


def _repeatable(client: StubClient, second: dict[str, Any]) -> Scenario:
    client.route("POST", f"{API}/ingestion/runs", second, 201)
    check = scenario(client)
    check.state["run"] = run_payload()
    check.state["counts_after_run"] = dict.fromkeys(ENTITY_TYPES, 0)
    return check


def test_a_repeated_run_that_changes_nothing_passes_the_idempotency_check():
    noop = run_payload(status="NOOP", records_inserted=0, records_unchanged=10)
    check = _repeatable(_identity_client({"customers": ["CUST-001", "CUST-002"]}), noop)

    detail = check.idempotency()

    assert f"second run {noop['run_id'][:8]} NOOP inserted 0 and updated 0" in detail
    assert "2 records across 7 entity types with 2 distinct source identities" in detail


def test_the_idempotency_check_needs_the_first_run():
    fails(scenario(_identity_client()).idempotency, "the step E-F ingestion did not complete")


def test_a_reused_run_id_fails_the_idempotency_check():
    check = _repeatable(_identity_client(), run_payload(status="NOOP", records_inserted=0,
                                                        records_unchanged=10))
    check.state["run"] = dict(check.state["run"],
                              run_id=check.client.routes[("POST", f"{API}/ingestion/runs")]
                              .json()["run_id"])

    fails(check.idempotency, "the repeated ingestion reused the first run's id")


@pytest.mark.parametrize("inserted, updated", [(4, 6), (4, 0), (0, 6)])
def test_a_repeated_run_that_writes_again_fails_the_idempotency_check(inserted, updated):
    """Either counter alone means the second run changed the canonical tables."""
    check = _repeatable(_identity_client(),
                        run_payload(records_inserted=inserted, records_updated=updated,
                                    records_unchanged=10 - inserted - updated))

    fails(check.idempotency,
          f"repeating the identical run inserted {inserted} and updated {updated} records")


def test_canonical_counts_that_move_fail_the_idempotency_check():
    counts = dict.fromkeys(ENTITY_TYPES, 0) | {"deals": 3}
    check = _repeatable(_identity_client(counts=counts),
                        run_payload(status="NOOP", records_inserted=0, records_unchanged=10))

    fails(check.idempotency, "canonical counts changed when the identical run repeated: "
                             "deals 0->3")


def test_a_duplicate_source_identity_fails_the_idempotency_check():
    check = _repeatable(_identity_client({"customers": ["CUST-001", "CUST-001"]}),
                        run_payload(status="NOOP", records_inserted=0, records_unchanged=10))

    fails(check.idempotency, "duplicate canonical source identities after repeated ingestion: "
                             "customers (1)")


def test_a_page_that_contradicts_its_total_fails_the_identity_sweep():
    client = _ready_client()
    for entity in ENTITY_TYPES:
        client.dynamic("GET", f"{API}/entities/{entity}",
                       lambda kwargs: StubResponse(page_payload([record("CUST-001")], total=9,
                                                                limit=verify_layer1.PAGE_LIMIT,
                                                                offset=0)))
    check = _repeatable(client, run_payload(status="NOOP", records_inserted=0,
                                            records_unchanged=10))

    fails(check.idempotency, "paging organizations returned 1 of 9 records")


def test_the_identity_sweep_follows_every_page():
    client = _ready_client()
    ids = [f"CUST-{index:04d}" for index in range(verify_layer1.PAGE_LIMIT + 3)]
    items = [record(source_id) for source_id in ids]
    for entity in ENTITY_TYPES:
        client.dynamic("GET", f"{API}/entities/{entity}",
                       lambda kwargs, items=items: StubResponse(page_payload(
                           items[kwargs["params"]["offset"]:
                                 kwargs["params"]["offset"] + kwargs["params"]["limit"]],
                           total=len(items), limit=kwargs["params"]["limit"],
                           offset=kwargs["params"]["offset"])))
    check = _repeatable(client, run_payload(status="NOOP", records_inserted=0,
                                            records_unchanged=10))

    assert f"{len(ids) * len(ENTITY_TYPES)} records across 7 entity types" in check.idempotency()


# ---------------------------------------------------------------------------
# Steps K-L — the malformed fixture
# ---------------------------------------------------------------------------


def summary_stub(status: str = "PARTIAL_SUCCESS", rejected: int = 3, run_id=None):
    return SimpleNamespace(run_id=run_id or uuid.uuid4(),
                           status=SimpleNamespace(value=status),
                           counts=SimpleNamespace(rejected=rejected))


def error_item(source_id: str, severity: str = "ERROR", **overrides: Any) -> dict[str, Any]:
    item = {"id": str(uuid.uuid4()), "severity": severity, "code": "UNKNOWN_ENUM_VALUE",
            "message": "value is not in the canonical vocabulary for this field",
            "source_system": "csv_demo", "source_entity": "customers", "source_id": source_id,
            "created_at": "2026-09-16T10:00:00Z",
            "findings": [{"code": "UNKNOWN_ENUM_VALUE", "field_name": "status",
                          "severity": severity, "message": "unknown value"}]}
    item.update(overrides)
    return item


def _fixture_scenario(summary, errors: list[dict[str, Any]] | None = None,
                      run: dict[str, Any] | None = None,
                      present: dict[str, list[str]] | None = None) -> Scenario:
    items = errors if errors is not None else [error_item("CUST-903"), error_item("DEAL-903"),
                                               error_item("DEAL-904")]
    run_id = str(summary.run_id)
    present = present if present is not None else {
        "customers": ["CUST-901", "CUST-902"], "deals": ["DEAL-901", "DEAL-902"]}
    client = _identity_client(present)
    client.route("GET", f"{API}/ingestion/runs/{run_id}",
                 run if run is not None else {"status": "PARTIAL_SUCCESS",
                                              "records_rejected": summary.counts.rejected})
    client.route("GET", f"{API}/ingestion/runs/{run_id}/errors",
                 {"items": items, "total": len(items), "limit": 500, "offset": 0})
    check = scenario(client)
    check._ingest_malformed_fixture = lambda: summary  # type: ignore[method-assign]
    return check


def test_the_malformed_fixture_is_quarantined_and_its_valid_rows_stay_usable():
    summary = summary_stub()

    detail = _fixture_scenario(summary).validation()

    assert f"run {str(summary.run_id)[:8]} PARTIAL_SUCCESS: 3 records quarantined" in detail
    assert "3 structured errors over 3 source ids" in detail
    assert "4 valid fixture records still queryable, no source values disclosed" in detail


def test_a_malformed_fixture_that_does_not_partially_succeed_fails_the_validation_check():
    fails(_fixture_scenario(summary_stub(status="SUCCESS", rejected=0)).validation,
          "the malformed fixture run finished SUCCESS, not PARTIAL_SUCCESS")


def test_a_malformed_fixture_that_rejects_nothing_fails_the_validation_check():
    fails(_fixture_scenario(summary_stub(rejected=0)).validation,
          "the malformed fixture produced no rejected records")


@pytest.mark.parametrize("run", [
    {"status": "SUCCESS", "records_rejected": 0},
    {"status": "SUCCESS", "records_rejected": 3},
    {"status": "PARTIAL_SUCCESS", "records_rejected": 1},
])
def test_an_api_that_does_not_see_the_run_fails_the_validation_check(run):
    """Status and rejection count must both match, or the two views are of different rows."""
    fails(_fixture_scenario(summary_stub(), run=run).validation,
          "the API may use a different database")


def test_fewer_structured_errors_than_rejections_fails_the_validation_check():
    fails(_fixture_scenario(summary_stub(), errors=[error_item("CUST-903")]).validation,
          "rejected 3 records but published 1 structured errors")


@pytest.mark.parametrize("missing", ["code", "message", "findings"])
def test_an_unstructured_error_fails_the_validation_check(missing):
    empty: Any = [] if missing == "findings" else ""
    errors = [error_item("CUST-903", **{missing: empty}), error_item("DEAL-903"),
              error_item("DEAL-904")]

    fails(_fixture_scenario(summary_stub(), errors=errors).validation,
          "carries no code, message or findings")


def test_a_source_value_in_an_error_payload_fails_the_validation_check():
    errors = [error_item("CUST-903", message="rejected 'Mosaic Foods' as a customer name"),
              error_item("DEAL-903"), error_item("DEAL-904")]

    check = _fixture_scenario(summary_stub(), errors=errors)

    with pytest.raises(CheckFailed) as failure:
        check.validation()
    assert "1 source values from the malformed fixture appear in its error payload" in str(
        failure.value)
    assert "Mosaic Foods" not in str(failure.value), "the report must not repeat the value"


def test_a_valid_fixture_row_that_is_not_queryable_fails_the_validation_check():
    check = _fixture_scenario(summary_stub(), present={"customers": ["CUST-901"],
                                                       "deals": ["DEAL-901", "DEAL-902"]})

    fails(check.validation,
          "valid customers rows of the malformed fixture are not queryable: CUST-902")


def test_a_warning_does_not_excuse_a_missing_row():
    """DEAL-902 keeps an unresolved reference: that is a warning, so the row must survive."""
    errors = [error_item("CUST-903"), error_item("DEAL-903"), error_item("DEAL-904"),
              error_item("DEAL-902", severity="WARNING", code="UNRESOLVED_REFERENCE")]
    check = _fixture_scenario(summary_stub(), errors=errors,
                              present={"customers": ["CUST-901", "CUST-902"],
                                       "deals": ["DEAL-901"]})

    fails(check.validation,
          "valid deals rows of the malformed fixture are not queryable: DEAL-902")


def test_a_connector_that_cannot_read_the_fixture_fails_the_validation_check(monkeypatch):
    def refuse(source: str, **kwargs: Any) -> None:
        raise verify_layer1.ConnectorConfigurationError("data_directory not found",
                                                        source_name=source)

    monkeypatch.setattr(verify_layer1, "build_connector", refuse)

    fails(scenario(StubClient()).validation,
          "the malformed fixture could not be read: data_directory not found")


def test_a_database_failure_during_the_fixture_run_is_reported_as_a_check_failure(monkeypatch):
    def unreachable(*args: object, **kwargs: object) -> None:
        raise verify_layer1.SQLAlchemyError("connection refused")

    monkeypatch.setattr(verify_layer1, "build_connector", lambda source, **kwargs: object())
    monkeypatch.setattr(verify_layer1, "run_ingestion", unreachable)

    fails(scenario(StubClient()).validation,
          "the malformed fixture run could not reach the database (SQLAlchemyError); "
          "check DATABASE_URL")


def test_the_fixture_run_uses_the_committed_connector_over_the_malformed_directory(monkeypatch):
    seen: dict[str, Any] = {}

    def build(source: str, **kwargs: Any) -> object:
        seen.update(source=source, **kwargs)
        return object()

    summary = summary_stub()

    def ingest(connector: object, sessions: object, request: object) -> object:
        seen["request"] = request
        return summary

    monkeypatch.setattr(verify_layer1, "build_connector", build)
    monkeypatch.setattr(verify_layer1, "run_ingestion", ingest)

    check = _fixture_scenario(summary)
    check._ingest_malformed_fixture = Scenario._ingest_malformed_fixture.__get__(check)
    check.validation()

    assert seen["source"] == "csv_demo"
    assert seen["data_directory"] == verify_layer1.BAD_FIXTURE_DIR
    assert seen["request"].page_size == verify_layer1.DEFAULT_PAGE_SIZE


# ---------------------------------------------------------------------------
# Step M — connector health
# ---------------------------------------------------------------------------


def source_entry(name: str, read_only: bool = True,
                 entity_types: list[str] | None = None) -> dict[str, Any]:
    return {"source": name, "source_type": "csv",
            "capabilities": {"read_only": read_only,
                             "supported_entity_types": list(ENTITY_TYPES)
                             if entity_types is None else entity_types}}


def _sources_client(entries: list[dict[str, Any]],
                    health: dict[str, dict[str, Any]] | None = None) -> StubClient:
    client = _ready_client().route("GET", f"{API}/sources", {"sources": entries})
    for entry in entries:
        name = entry["source"]
        answer = (health or {}).get(name, {"source": name, "status": "healthy",
                                           "latency_ms": 1.0, "error_type": None})
        client.route("GET", f"{API}/sources/{name}/health", answer)
    return client


def test_every_healthy_read_only_source_is_reported():
    entries = [source_entry("csv_demo"), source_entry("odoo_mock"), source_entry("rest_mock")]

    detail = scenario(_sources_client(entries)).connector_health()

    assert detail == ("3 configured sources healthy and read-only: "
                      "csv_demo, odoo_mock, rest_mock")


def test_an_api_with_no_configured_sources_fails_the_health_check():
    fails(scenario(_sources_client([])).connector_health,
          "the API reports no configured sources")


def test_a_source_that_is_not_read_only_fails_the_health_check():
    fails(scenario(_sources_client([source_entry("csv_demo", read_only=False)])).connector_health,
          "source csv_demo does not declare itself read-only")


def test_a_source_that_offers_no_entities_fails_the_health_check():
    entries = [source_entry("csv_demo", entity_types=[])]

    fails(scenario(_sources_client(entries)).connector_health,
          "source csv_demo declares no supported entity types")


def test_an_unhealthy_source_fails_the_health_check_with_its_error_type():
    entries = [source_entry("rest_mock")]
    health = {"rest_mock": {"source": "rest_mock", "status": "unhealthy", "latency_ms": None,
                            "error_type": "ConnectorConnectionError"}}

    fails(scenario(_sources_client(entries, health)).connector_health,
          "source rest_mock reports health unhealthy (ConnectorConnectionError)")


# ---------------------------------------------------------------------------
# Steps N and O — the operator steps
# ---------------------------------------------------------------------------


def test_the_test_suite_step_is_skipped_unless_requested():
    check = scenario(StubClient(), test_runner=lambda: pytest.fail("must not run")).test_suite()

    assert check.outcome is Outcome.SKIPPED
    assert check.steps == "N"
    assert "pass --with-tests" in check.detail


@pytest.mark.parametrize("code, outcome", [(0, Outcome.PASS), (1, Outcome.FAIL),
                                           (2, Outcome.FAIL)])
def test_the_test_suite_step_reports_what_pytest_returned(code, outcome):
    check = scenario(StubClient(), with_tests=True,
                     test_runner=lambda: (code, "3973 passed")).test_suite()

    assert (check.outcome, check.detail) == (outcome, "3973 passed")


def test_the_clean_rebuild_step_is_an_operator_step_naming_its_commands():
    check = Scenario.clean_rebuild()

    assert (check.steps, check.outcome) == ("O", Outcome.OPERATOR)
    assert "make docker-down" in check.detail and "make docker-build" in check.detail
    assert "make docker-up" in check.detail


def test_the_default_test_runner_invokes_the_whole_suite(monkeypatch):
    seen: dict[str, Any] = {}

    def fake_run(command, **kwargs):
        seen.update(command=command, kwargs=kwargs)
        return subprocess.CompletedProcess(command, 0, "...\n\n3973 passed in 160s\n", "")

    monkeypatch.setattr(verify_layer1.subprocess, "run", fake_run)

    assert verify_layer1.pytest_runner() == (0, "3973 passed in 160s")
    assert seen["command"][1:] == ["-m", "pytest", "-q", "-o", "addopts="]
    assert seen["kwargs"]["cwd"] == verify_layer1.PROJECT_ROOT
    assert seen["kwargs"]["check"] is False


def test_a_silent_pytest_still_reports_its_exit_status(monkeypatch):
    monkeypatch.setattr(verify_layer1.subprocess, "run",
                        lambda command, **kwargs: subprocess.CompletedProcess(command, 4, "", ""))

    assert verify_layer1.pytest_runner() == (4, "pytest exited 4 with no output")


# ---------------------------------------------------------------------------
# main() — wiring the command to the scenario
# ---------------------------------------------------------------------------


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


def _stub_wiring(monkeypatch, scenario_fn) -> FakeEngine:
    engine = FakeEngine()
    monkeypatch.setattr(verify_layer1, "create_engine", lambda url, **kwargs: engine)
    monkeypatch.setattr(verify_layer1, "sessionmaker", lambda **kwargs: "sessions")
    monkeypatch.setattr(verify_layer1, "run_scenario", scenario_fn)
    return engine


def test_main_streams_every_check_then_the_summary(monkeypatch, capsys):
    report = Report((Check("A-C", "stack_ready", Outcome.PASS, "ready"),
                     Check("N", "test_suite", Outcome.SKIPPED, "not run")))
    seen: dict[str, Any] = {}

    def fake_scenario(client, sessions, **kwargs):
        seen.update(base_url=str(client.base_url), sessions=sessions, **kwargs)
        for check in report.checks:
            kwargs["report_line"](check)
        return report

    engine = _stub_wiring(monkeypatch, fake_scenario)

    assert verify_layer1.main(["--base-url", "http://api:9000", "--page-size", "7"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines == [str(check) for check in report.checks] + [report.summary()]
    assert seen["base_url"] == "http://api:9000"
    assert (seen["page_size"], seen["with_tests"], seen["sessions"]) == (7, False, "sessions")
    assert engine.disposed


def test_main_returns_one_when_a_check_failed(monkeypatch, capsys):
    report = Report((Check("M", "connector_health", Outcome.FAIL, "unreachable"),))
    _stub_wiring(monkeypatch, lambda client, sessions, **kwargs: report)

    assert verify_layer1.main([]) == 1
    assert "1 failed" in capsys.readouterr().out


def test_main_returns_two_and_releases_the_engine_when_the_stack_is_unreachable(
        monkeypatch, capsys):
    def abort(client, sessions, **kwargs):
        raise ScenarioAborted("the Layer 1 API could not be reached (ConnectError)")

    engine = _stub_wiring(monkeypatch, abort)

    assert verify_layer1.main([]) == 2
    assert "could not be reached (ConnectError)" in capsys.readouterr().err
    assert engine.disposed


def test_main_passes_the_test_suite_flag_through(monkeypatch):
    seen: dict[str, Any] = {}

    def fake_scenario(client, sessions, **kwargs):
        seen.update(kwargs)
        return Report(())

    _stub_wiring(monkeypatch, fake_scenario)

    assert verify_layer1.main(["--with-tests"]) == 0
    assert seen["with_tests"] is True


# ---------------------------------------------------------------------------
# The one write the acceptance command is allowed to make
# ---------------------------------------------------------------------------


def demo_run_payload(**overrides: Any) -> dict[str, Any]:
    """A run over the five scenario entities with the committed CSVs' row counts."""
    rows = {"customers": 50, "employees": 24, "deals": 44, "projects": 22, "support_tickets": 80}
    fetched = sum(rows.values())
    run = run_payload(records_fetched=fetched, records_raw_persisted=fetched,
                      records_inserted=fetched,
                      entities=[{"entity_type": entity, "status": "completed",
                                 "records_fetched": count, "failure": None}
                                for entity, count in rows.items()])
    run.update(overrides)
    return run


def test_the_only_non_get_request_the_scenario_makes_is_starting_an_ingestion_run():
    """tests/unit/test_g2_security_boundary.py exempts this script from the read-only
    HTTP client on the strength of this assertion: it drives Layer 1's own API, where
    the documented way to start a run is a POST, and it writes nothing else."""
    runs = [demo_run_payload(),
            demo_run_payload(status="NOOP", records_inserted=0, records_unchanged=220)]
    client = _identity_client({"customers": ["CUST-001"]})
    client.dynamic("POST", f"{API}/ingestion/runs",
                   lambda kwargs: StubResponse(runs.pop(0), 201))
    check = scenario(client)

    assert check.stack_ready()
    assert check.demo_dataset()
    assert check.ingestion()
    assert check.idempotency()

    writes = [(method, path) for method, path, _ in client.calls if method != "GET"]
    assert writes == [("POST", f"{API}/ingestion/runs")] * 2


@pytest.mark.parametrize("variable, value", [("APP_LOG_LEVEL", "LOUD"), ("LOG_FORMAT", "yaml")])
def test_invalid_logging_settings_exit_two_before_the_scenario(variable, value, monkeypatch,
                                                               capsys):
    monkeypatch.setenv(variable, value)
    monkeypatch.setattr(verify_layer1, "create_engine",
                        lambda *args, **kwargs: pytest.fail("must not open a connection"))

    assert verify_layer1.main([]) == 2
    error = capsys.readouterr().err
    assert error.startswith("verify_layer1: invalid logging settings: ")
    assert variable in error
    assert value not in error, "the rejected value is echoed back by the settings API, not here"


def test_the_scenario_runs_inside_configured_logging(monkeypatch):
    """The malformed-fixture run logs like every other Layer 1 command."""
    entered: list[tuple[str, str]] = []

    @contextlib.contextmanager
    def fake_logging(level: str, log_format: str):
        entered.append((level, log_format))
        yield

    monkeypatch.setenv("APP_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("LOG_FORMAT", "text")
    monkeypatch.setattr(verify_layer1, "configured_logging", fake_logging)
    _stub_wiring(monkeypatch, lambda client, sessions, **kwargs: Report(()))

    assert verify_layer1.main([]) == 0
    assert entered == [("WARNING", "text")]


# ---------------------------------------------------------------------------
# make verify-layer1
# ---------------------------------------------------------------------------

MAKEFILE = (REPO / "Makefile").read_text(encoding="utf-8")


def _recipe(target: str) -> list[str]:
    """The command lines of one Makefile target, empty when it has no rule."""
    lines = MAKEFILE.splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith(f"{target}:")]
    if not starts:
        return []
    return [line.lstrip("\t") for line in
            itertools.takewhile(lambda line: line.startswith("\t"), lines[starts[0] + 1:])]


def _phony_targets() -> list[str]:
    declaration = MAKEFILE.split(".PHONY:")[1].split("\n\n")[0]
    return declaration.replace("\\", " ").split()


def test_the_verify_layer1_target_runs_the_acceptance_script():
    recipe = _recipe("verify-layer1")

    assert any(line.endswith("python scripts/verify_layer1.py $(ARGS)") for line in recipe)
    assert any(".venv/bin/python" in line for line in recipe), "the target uses make install's venv"


def test_the_verify_layer1_target_is_declared_phony_and_documented():
    assert "verify-layer1" in _phony_targets()
    assert any("make verify-layer1" in line for line in _recipe("help"))


def test_every_declared_target_has_a_recipe_and_is_listed_by_make_help():
    """A target declared and documented but never given a rule silently does nothing."""
    help_text = "\n".join(_recipe("help"))
    for target in _phony_targets():
        assert _recipe(target), f"make {target} is declared but has no recipe"
        if target != "help":
            assert f"make {target}" in help_text, f"make {target} is not listed by make help"


def test_no_makefile_target_is_still_a_stub():
    assert "STUB" not in MAKEFILE
    assert "[verify-layer1] Running Layer 1 acceptance scenario..." in MAKEFILE


def test_every_command_the_makefile_runs_exists():
    for script in ("seed_demo.py", "ingest_demo.py", "secret_scan.py", "verify_layer1.py"):
        assert f"scripts/{script}" in MAKEFILE
        assert (REPO / "scripts" / script).is_file()


# ---------------------------------------------------------------------------
# Step N's precondition: the suite must survive step E
# ---------------------------------------------------------------------------


def test_no_test_opens_an_engine_on_the_development_database():
    """Spec Section 20 runs the whole suite (step N) after ingesting the demo dataset
    into the configured database (step E), so no test may assume that database is
    empty. Every suite uses the isolated <database>_test harness in tests/conftest.py."""
    opens_configured_database = re.compile(r"create_engine\(\s*[^)]*effective_database_url")
    offenders = [path.relative_to(REPO).as_posix()
                 for path in sorted((REPO / "tests").rglob("*.py"))
                 if opens_configured_database.search(path.read_text(encoding="utf-8"))]

    assert offenders == []


def test_the_shared_harness_refuses_any_database_that_is_not_a_test_database():
    harness = (REPO / "tests" / "conftest.py").read_text(encoding="utf-8")

    assert 'f"{url.database}_test"' in harness
    assert "refusing to use non-test database" in harness
