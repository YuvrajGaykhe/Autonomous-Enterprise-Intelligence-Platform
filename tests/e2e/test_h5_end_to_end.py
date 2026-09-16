"""
H5 end-to-end and idempotency tests (spec Section 15).

    End-to-end   demo source -> ingestion -> PostgreSQL -> API query.
    Idempotency  same source ingested twice without duplicate canonical
                 identities.

Every step runs through HTTP against the real application and the real
migrated database. Nothing here reaches into the orchestrator or the
repositories: a run is started with POST /ingestion/runs, observed with GET
/ingestion/runs/{id}, and the result is read back with GET /entities/... and
GET /metrics/ingestion, which is exactly the path a reviewer follows and the
contract Layer 2 will consume.

Expected values are read from the committed CSV files themselves, so the
assertions describe the demo dataset rather than restating whatever the
pipeline happened to produce.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal

import pytest
from conftest import API, DEMO_DIR, ENTITY_TYPES, csv_ids, csv_rows, page, start_run

pytestmark = [pytest.mark.e2e, pytest.mark.integration]

HEX64 = re.compile(r"[0-9a-f]{64}")

PROVENANCE_FIELDS = (
    "id", "source_system", "source_entity", "source_id",
    "source_updated_at", "ingested_at", "ingestion_run_id", "record_hash",
)


# ---------------------------------------------------------------------------
# The whole path, in the order a reviewer walks it
# ---------------------------------------------------------------------------


def test_the_api_is_ready_before_any_ingestion(api):
    """Spec Section 20 C: readiness verifies the database dependency."""
    response = api.get(f"{API}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["checks"]["database"] == "ok"


def test_the_configured_sources_are_discoverable(api):
    """Section 20 M: connectors are listed and health-checked through the API."""
    sources = api.get(f"{API}/sources").json()["sources"]
    assert [source["source"] for source in sources] == ["csv_demo", "odoo_mock", "rest_mock"]
    for source in sources:
        assert source["capabilities"]["read_only"] is True

    health = api.get(f"{API}/sources/csv_demo/health").json()
    assert health["status"] == "healthy"


def test_a_full_demo_ingestion_succeeds_with_truthful_counts(api):
    """Section 20 E and F: every entity ingests and the counts reconcile."""
    run = start_run(api)

    assert run["status"] == "SUCCESS"
    assert run["source_system"] == "csv_demo"
    expected = sum(len(csv_rows(DEMO_DIR, entity)) for entity in ENTITY_TYPES)
    assert run["records_fetched"] == expected
    assert run["records_inserted"] == expected
    assert run["records_updated"] == 0
    assert run["records_rejected"] == 0
    assert run["records_failed"] == 0
    assert run["records_fetched"] == (
        run["records_inserted"] + run["records_updated"] + run["records_unchanged"]
        + run["records_rejected"] + run["records_failed"]
    )
    assert {result["entity_type"] for result in run["entities"]} == set(ENTITY_TYPES)


def test_the_run_is_queryable_after_it_finishes(api):
    """The run document POST returned is the one GET returns."""
    created = start_run(api)
    fetched = api.get(f"{API}/ingestion/runs/{created['run_id']}").json()

    for field in ("run_id", "source_system", "status", "records_fetched",
                  "records_inserted", "started_at", "finished_at"):
        assert fetched[field] == created[field], field


def test_the_run_appears_in_the_run_listing(api):
    run = start_run(api)
    listing = api.get(f"{API}/ingestion/runs", params={"source_system": "csv_demo"}).json()
    assert listing["total"] == 1
    assert listing["items"][0]["run_id"] == run["run_id"]


@pytest.mark.parametrize("entity", ENTITY_TYPES)
def test_every_ingested_entity_is_queryable_with_full_provenance(api, entity):
    """Section 20 G and H: canonical records carry their whole provenance."""
    run = start_run(api)
    body = page(api, entity)

    assert body["total"] == len(csv_ids(DEMO_DIR, entity))
    assert {item["source_id"] for item in body["items"]} == csv_ids(DEMO_DIR, entity)
    for item in body["items"]:
        assert set(PROVENANCE_FIELDS) <= set(item)
        assert item["source_system"] == "csv_demo"
        assert item["source_entity"] == entity
        assert item["ingestion_run_id"] == run["run_id"]
        assert HEX64.fullmatch(item["record_hash"])
        assert item["ingested_at"]


@pytest.mark.parametrize("entity", ENTITY_TYPES)
def test_every_listed_record_can_be_fetched_by_its_canonical_id(api, entity):
    start_run(api)
    for item in page(api, entity)["items"]:
        response = api.get(f"{API}/entities/{entity}/{item['id']}")
        assert response.status_code == 200
        assert response.json() == item


def test_money_survives_the_whole_path_without_float_conversion(api):
    """Decimals are JSON strings end to end, so no cent is lost."""
    start_run(api)
    amounts = {row["deal_id"]: row["amount"] for row in csv_rows(DEMO_DIR, "deals")}

    for deal in page(api, "deals")["items"]:
        assert isinstance(deal["amount"], str)
        assert Decimal(deal["amount"]) == Decimal(amounts[deal["source_id"]])


def test_unresolved_references_keep_their_source_key(api):
    """Spec Section 7: a deal whose customer resolves gets both; none is lost."""
    start_run(api)
    customers = {item["source_id"]: item["id"] for item in page(api, "customers")["items"]}

    for deal in page(api, "deals")["items"]:
        assert deal["customer_source_id"] is not None
        if deal["customer_source_id"] in customers:
            assert deal["customer_id"] == customers[deal["customer_source_id"]]
        else:
            assert deal["customer_id"] is None


def test_the_metrics_endpoint_reports_the_completed_run(api):
    """Section 16: operational metrics are derived from persisted runs."""
    run = start_run(api)
    metrics = api.get(f"{API}/metrics/ingestion").json()

    totals = metrics["totals"]
    assert totals["runs_total"] == 1
    assert totals["runs_by_status"]["SUCCESS"] == 1
    assert totals["records_fetched_total"] == run["records_fetched"]
    assert totals["records_inserted_total"] == run["records_inserted"]
    assert totals["records_rejected_total"] == 0

    by_source = {source["source_system"]: source for source in metrics["sources"]}
    assert by_source["csv_demo"]["records_inserted_total"] == run["records_inserted"]
    assert by_source["csv_demo"]["last_successful_run"]["run_id"] == run["run_id"]


def test_the_process_counters_see_the_run_this_process_executed(api):
    """G1 in-process counters cover runs this API process executed."""
    run = start_run(api)
    process = api.get(f"{API}/metrics/ingestion").json()["process"]

    assert process["runs_total"] == 1
    assert process["runs_by_status"]["SUCCESS"] == 1
    assert process["records_fetched_total"] == run["records_fetched"]


def test_a_run_with_no_errors_has_an_empty_error_page(api):
    run = start_run(api)
    errors = api.get(f"{API}/ingestion/runs/{run['run_id']}/errors").json()
    assert errors["total"] == 0
    assert errors["items"] == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def _identities(api) -> dict[str, list[tuple[str, str]]]:
    """Every canonical record's (source_id, canonical id), per entity type."""
    return {
        entity: sorted((item["source_id"], item["id"]) for item in page(api, entity)["items"])
        for entity in ENTITY_TYPES
    }


def test_a_second_identical_ingestion_changes_nothing(api):
    """Section 20 I and J: the same source twice, no duplicates, no churn."""
    first = start_run(api)
    before = _identities(api)

    second = start_run(api)

    assert second["status"] == "NOOP"
    assert second["records_fetched"] == first["records_fetched"]
    assert second["records_inserted"] == 0
    assert second["records_updated"] == 0
    assert second["records_unchanged"] == first["records_inserted"]
    assert _identities(api) == before


def test_canonical_ids_are_stable_across_runs(api):
    """A canonical id is the record's identity for Layer 2; it must not move."""
    start_run(api)
    before = {entity: {item["source_id"]: item["id"] for item in page(api, entity)["items"]}
              for entity in ENTITY_TYPES}

    start_run(api)
    after = {entity: {item["source_id"]: item["id"] for item in page(api, entity)["items"]}
             for entity in ENTITY_TYPES}
    assert after == before


def test_record_hashes_are_unchanged_by_a_repeat_ingestion(api):
    """Content identity is deterministic: same input, same hash."""
    start_run(api)
    before = {item["source_id"]: item["record_hash"] for item in page(api, "customers")["items"]}
    start_run(api)
    after = {item["source_id"]: item["record_hash"] for item in page(api, "customers")["items"]}
    assert after == before


@pytest.mark.parametrize("entity", ENTITY_TYPES)
def test_no_duplicate_source_identity_exists_after_repeated_ingestion(api, entity):
    """Section 20 J, checked per entity over the API's own view."""
    start_run(api)
    start_run(api)
    start_run(api)

    items = page(api, entity)["items"]
    identities = [(item["source_system"], item["source_entity"], item["source_id"])
                  for item in items]
    assert len(identities) == len(set(identities))
    assert len(identities) == len(csv_ids(DEMO_DIR, entity))


def test_repeated_ingestion_still_records_every_run(api):
    """Idempotent data does not mean a silent run: each attempt is tracked."""
    start_run(api)
    start_run(api)

    listing = api.get(f"{API}/ingestion/runs").json()
    assert listing["total"] == 2
    assert [item["status"] for item in listing["items"]] == ["NOOP", "SUCCESS"]

    totals = api.get(f"{API}/metrics/ingestion").json()["totals"]
    assert totals["runs_total"] == 2
    assert totals["runs_by_status"]["NOOP"] == 1
    assert totals["runs_by_status"]["SUCCESS"] == 1


def test_a_partial_entity_selection_does_not_disturb_other_entities(api):
    """Re-running one entity leaves the rest of the canonical store alone."""
    start_run(api)
    before = _identities(api)

    run = start_run(api, entities=["customers"])
    assert run["status"] == "NOOP"
    assert _identities(api) == before


def test_ingesting_a_child_entity_alone_preserves_its_resolved_reference(api):
    """Parents already stored keep resolving for a later child-only run."""
    start_run(api)
    resolved = {item["source_id"]: item["customer_id"] for item in page(api, "deals")["items"]}

    start_run(api, entities=["deals"])
    assert {item["source_id"]: item["customer_id"]
            for item in page(api, "deals")["items"]} == resolved


# ---------------------------------------------------------------------------
# The churn scenario the demo dataset exists to support
# ---------------------------------------------------------------------------


def test_the_churn_signal_is_queryable_through_the_api(api):
    """Section 12: a customer with repeated tickets and an active deal."""
    start_run(api)
    tickets = page(api, "support_tickets")["items"]
    deals = page(api, "deals")["items"]

    by_customer: dict[str, int] = {}
    for ticket in tickets:
        key = ticket["customer_source_id"]
        if key:
            by_customer[key] = by_customer.get(key, 0) + 1

    repeat_customers = {key for key, count in by_customer.items() if count > 1}
    assert repeat_customers, "the demo dataset must carry a repeat-ticket customer"

    active_deal_customers = {deal["customer_source_id"] for deal in deals if deal["is_active"]}
    assert repeat_customers & active_deal_customers


def test_layer_two_can_read_every_handoff_endpoint(api):
    """Section 19: the six handoff contracts answer with records."""
    start_run(api)
    for entity in ("customers", "deals", "support_tickets",
                   "employees", "projects", "documents"):
        body = page(api, entity)
        assert body["total"] > 0, entity
        assert body["items"], entity


def test_an_unrelated_run_id_returns_nothing_from_this_run(api):
    """Run scoping is real: a random id is not silently treated as the latest."""
    start_run(api)
    assert api.get(f"{API}/ingestion/runs/{uuid.uuid4()}").status_code == 404
