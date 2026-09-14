"""
E1 run orchestrator tests: real CSV connector and injected source failures
against a real, migrated PostgreSQL database.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import timedelta
from pathlib import Path

import pytest
from e1_support import CSV_ROWS, ID_COLUMNS, NOW, csv_row
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.connectors import (
    ConnectorAuthenticationError,
    ConnectorCapabilities,
    ConnectorHealth,
    ConnectorUnavailableError,
    CsvConnector,
    CsvConnectorConfig,
    Page,
)
from app.ingestion import orchestrator
from app.ingestion.errors import ConnectorContractError, IngestionRequestError
from app.ingestion.orchestrator import (
    ENTITY_ORDER,
    EntityStatus,
    IngestionRequest,
    run_ingestion,
)
from app.ingestion.reconciliation import REFERENCE_RULES
from app.normalization import canonical_id
from app.persistence.models import (
    Customer,
    Deal,
    IngestionCursor,
    IngestionError,
    IngestionRun,
    SourceRecord,
)
from app.persistence.repositories import canonical as canonical_repo
from app.persistence.repositories import raw, runs

pytestmark = pytest.mark.integration

SECRET = "SYNTHETIC_SECRET_VALUE_FOR_LOG_TESTS"


def clock():
    return NOW


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def valid_dataset() -> dict[str, list[dict[str, str]]]:
    return {
        "organizations": [csv_row("organizations")],
        "employees": [csv_row("employees"),
                      csv_row("employees", employee_id="EMP-002", employee_name="Bob Manager",
                              email_address="bob@acme.example")],
        "customers": [csv_row("customers"),
                      csv_row("customers", customer_id="CUST-002", customer_name="Widget Corp",
                              email_address="info@widget.example")],
        "deals": [csv_row("deals"),
                  csv_row("deals", deal_id="DEAL-002", customer_id="CUST-002")],
        "projects": [csv_row("projects")],
        "support_tickets": [csv_row("support_tickets"),
                            csv_row("support_tickets", ticket_id="TKT-002",
                                    customer_id="CUST-002")],
        "documents": [csv_row("documents")],
    }


def write_dataset(directory: Path, dataset: dict[str, list[dict[str, str]]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for entity in ENTITY_ORDER:
        with open(directory / f"{entity}.csv", "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(CSV_ROWS[entity]))
            writer.writeheader()
            writer.writerows(dataset.get(entity, []))


def csv_connector(directory: Path) -> CsvConnector:
    return CsvConnector(CsvConnectorConfig.from_dict({
        "source_name": "csv_demo", "source_type": "csv", "data_directory": str(directory),
        "entities": {entity: {"file": f"{entity}.csv", "id_column": ID_COLUMNS[entity]}
                     for entity in ENTITY_ORDER},
    }))


class FakeConnector:
    """Deterministic in-memory connector with injectable failures."""

    def __init__(self, pages, *, source_name="csv_demo", healthy=True, health_error=None,
                 failures=None, page_factory=None):
        self.pages = pages
        self._source_name = source_name
        self.healthy = healthy
        self.health_error = health_error
        self.failures = dict(failures or {})
        self.page_factory = page_factory
        self.calls: list[tuple[str, str | None]] = []

    @property
    def source_name(self):
        return self._source_name

    @property
    def source_type(self):
        return "fake"

    def health_check(self):
        if self.health_error is not None:
            raise self.health_error
        return ConnectorHealth(healthy=self.healthy, source_name=self.source_name,
                               message=f"internal host detail {SECRET}")

    def list_entities(self):
        return []

    def fetch_entities(self, entity_type, cursor=None, page_size=100):
        self.calls.append((entity_type, cursor))
        index = int(cursor or 0)
        failure = self.failures.pop((entity_type, index), None)
        if failure is not None:
            raise failure
        if self.page_factory is not None:
            return self.page_factory(entity_type, cursor, page_size)
        pages = self.pages.get(entity_type, [[]])
        has_more = index + 1 < len(pages)
        return Page(items=list(pages[index]), next_cursor=str(index + 1) if has_more else None,
                    has_more=has_more)

    def get_entity(self, entity_type, source_id):
        raise NotImplementedError

    def capabilities(self):
        return ConnectorCapabilities(supported_entity_types=sorted(ENTITY_ORDER))


def _count(sessions, model) -> int:
    with sessions() as session:
        return session.scalar(select(func.count()).select_from(model))


def _run_row(sessions, run_id):
    with sessions() as session:
        return session.get(IngestionRun, run_id)


def _errors(sessions):
    with sessions() as session:
        return session.scalars(select(IngestionError)).all()


def _canonical_snapshot(sessions):
    snapshot = {}
    with sessions() as session:
        for entity, model in canonical_repo.ENTITY_MODELS.items():
            references = canonical_repo.reference_fields(entity)
            rows = session.scalars(select(model).order_by(model.source_id)).all()
            snapshot[entity] = [(r.source_id, r.id, r.record_hash,
                                 tuple(getattr(r, name) for name in references)) for r in rows]
    return snapshot


def _assert_reconciles(summary):
    counts = summary.counts
    assert counts.fetched == (counts.inserted + counts.updated + counts.unchanged
                              + counts.rejected + summary.records_failed)


def _assert_run_row_matches(sessions, summary):
    run = _run_row(sessions, summary.run_id)
    counts = summary.counts
    assert (run.status, run.finished_at, run.error_summary) == (
        summary.status.value, summary.finished_at, summary.error_summary)
    assert runs.RunCounts(run.records_fetched, run.records_inserted, run.records_updated,
                          run.records_unchanged, run.records_rejected,
                          run.records_warnings) == counts


# ---------------------------------------------------------------------------
# Normal, idempotent and updated runs
# ---------------------------------------------------------------------------


def test_entity_order_places_parents_before_children():
    assert set(ENTITY_ORDER) == set(REFERENCE_RULES)
    for child, rules in REFERENCE_RULES.items():
        for rule in rules:
            assert ENTITY_ORDER.index(rule.parent_entity) < ENTITY_ORDER.index(child)


def test_full_csv_ingestion_persists_every_entity(e1_sessions, tmp_path):
    write_dataset(tmp_path, valid_dataset())
    summary = run_ingestion(csv_connector(tmp_path), e1_sessions, clock=clock)

    assert summary.status is runs.RunStatus.SUCCESS and summary.error_summary is None
    assert [e.entity_type for e in summary.entities] == list(ENTITY_ORDER)
    assert all(e.status is EntityStatus.COMPLETED for e in summary.entities)
    assert summary.counts == runs.RunCounts(fetched=11, inserted=11)
    assert (summary.raw_persisted, summary.batches_committed, summary.batches_failed) == (11, 7, 0)
    _assert_reconciles(summary)
    _assert_run_row_matches(e1_sessions, summary)
    run = _run_row(e1_sessions, summary.run_id)
    assert (run.source_system, run.source_entity, run.mode) == ("csv_demo", None, "full")

    snapshot = _canonical_snapshot(e1_sessions)
    assert {entity: len(rows) for entity, rows in snapshot.items()} == {
        entity: len(rows) for entity, rows in valid_dataset().items()}
    with e1_sessions() as session:
        deals = session.scalars(select(Deal).order_by(Deal.source_id)).all()
        cursors = session.scalars(select(IngestionCursor)).all()
    assert [d.customer_id for d in deals] == [
        canonical_id("csv_demo", "customers", "CUST-001"),
        canonical_id("csv_demo", "customers", "CUST-002")]
    assert all(d.ingestion_run_id == summary.run_id for d in deals)
    assert sorted(c.source_entity for c in cursors) == sorted(ENTITY_ORDER)
    assert {c.last_successful_run_id for c in cursors} == {summary.run_id}
    assert _count(e1_sessions, SourceRecord) == 11 and _errors(e1_sessions) == []


def test_identical_rerun_is_noop_without_duplicates(e1_sessions, tmp_path):
    write_dataset(tmp_path, valid_dataset())
    connector = csv_connector(tmp_path)
    first = run_ingestion(connector, e1_sessions, clock=clock)
    before = _canonical_snapshot(e1_sessions)
    second = run_ingestion(connector, e1_sessions, clock=lambda: NOW + timedelta(hours=1))

    assert second.status is runs.RunStatus.NOOP
    assert second.counts == runs.RunCounts(fetched=11, unchanged=11)
    assert _canonical_snapshot(e1_sessions) == before
    with e1_sessions() as session:
        cursors = session.scalars(select(IngestionCursor)).all()
        customers = session.scalars(select(Customer)).all()
    assert {c.last_successful_run_id for c in cursors} == {second.run_id}
    assert {c.ingestion_run_id for c in customers} == {first.run_id}
    assert _count(e1_sessions, SourceRecord) == 22
    _assert_run_row_matches(e1_sessions, second)


def test_updated_source_record_is_reported_as_an_update(e1_sessions, tmp_path):
    dataset = valid_dataset()
    write_dataset(tmp_path, dataset)
    run_ingestion(csv_connector(tmp_path), e1_sessions, clock=clock)
    dataset["customers"][1]["customer_segment"] = "SMB"
    write_dataset(tmp_path, dataset)
    later = NOW + timedelta(days=1)
    summary = run_ingestion(csv_connector(tmp_path), e1_sessions, clock=lambda: later)

    assert summary.status is runs.RunStatus.SUCCESS
    assert summary.counts == runs.RunCounts(fetched=11, updated=1, unchanged=10)
    with e1_sessions() as session:
        widget = session.scalars(select(Customer).where(Customer.source_id == "CUST-002")).one()
    assert (widget.segment, widget.ingestion_run_id, widget.ingested_at) == (
        "SMB", summary.run_id, later)


def test_results_do_not_depend_on_page_size(e1_sessions, tmp_path):
    write_dataset(tmp_path, valid_dataset())
    connector = csv_connector(tmp_path)
    paged = run_ingestion(connector, e1_sessions, IngestionRequest(page_size=1), clock=clock)
    assert paged.status is runs.RunStatus.SUCCESS and paged.batches_committed == 11
    snapshot = _canonical_snapshot(e1_sessions)
    bulk = run_ingestion(connector, e1_sessions, IngestionRequest(page_size=100), clock=clock)
    assert bulk.status is runs.RunStatus.NOOP and bulk.batches_committed == 7
    assert _canonical_snapshot(e1_sessions) == snapshot


def test_empty_source_is_noop_and_completes_checkpoints(e1_sessions, tmp_path):
    write_dataset(tmp_path, {})
    summary = run_ingestion(csv_connector(tmp_path), e1_sessions, clock=clock)
    assert summary.status is runs.RunStatus.NOOP
    assert summary.counts == runs.RunCounts()
    assert _count(e1_sessions, IngestionCursor) == len(ENTITY_ORDER)


def test_bad_fixture_quarantines_without_corrupting_valid_records(e1_sessions, tmp_path):
    dataset = valid_dataset()
    dataset["customers"] = [
        csv_row("customers"),
        csv_row("customers", customer_id="CUST-002", email_address=""),
        csv_row("customers", customer_id="CUST-003", status="churned"),
        csv_row("customers"),
    ]
    dataset["deals"] = [
        csv_row("deals"),
        csv_row("deals", deal_id="DEAL-002", amount="12,00.x"),
        csv_row("deals", deal_id="DEAL-003", customer_id="CUST-404"),
        csv_row("deals", deal_id="DEAL-004", expected_close_date="2026-13-45"),
    ]
    write_dataset(tmp_path, dataset)
    summary = run_ingestion(csv_connector(tmp_path), e1_sessions, clock=clock)

    assert summary.status is runs.RunStatus.PARTIAL_SUCCESS
    assert summary.error_summary == "3 records rejected"
    by_entity = {e.entity_type: e.counts for e in summary.entities}
    assert by_entity["customers"] == runs.RunCounts(fetched=4, inserted=2, unchanged=1,
                                                    rejected=1, warnings=2)
    assert by_entity["deals"] == runs.RunCounts(fetched=4, inserted=2, rejected=2, warnings=1)
    _assert_reconciles(summary)
    _assert_run_row_matches(e1_sessions, summary)

    rows = _errors(e1_sessions)
    assert sorted((r.severity, r.error_code, r.source_id) for r in rows) == [
        ("ERROR", "INVALID_DATE", "DEAL-004"),
        ("ERROR", "INVALID_DECIMAL", "DEAL-002"),
        ("ERROR", "UNKNOWN_ENUM_VALUE", "CUST-003"),
        ("WARNING", "DUPLICATE_SOURCE_RECORD", "CUST-001"),
        ("WARNING", "MISSING_RECOMMENDED_FIELD", "CUST-002"),
        ("WARNING", "UNRESOLVED_REFERENCE", "DEAL-003"),
    ]
    with e1_sessions() as session:
        valid_deal = session.scalars(select(Deal).where(Deal.source_id == "DEAL-001")).one()
    assert valid_deal.customer_id == canonical_id("csv_demo", "customers", "CUST-001")


def test_requested_entities_run_in_dependency_order(e1_sessions, tmp_path):
    write_dataset(tmp_path, valid_dataset())
    summary = run_ingestion(csv_connector(tmp_path), e1_sessions,
                            IngestionRequest(entities=["deals", "customers", "deals"]), clock=clock)
    assert [e.entity_type for e in summary.entities] == ["customers", "deals"]
    assert _run_row(e1_sessions, summary.run_id).source_entity is None
    with e1_sessions() as session:
        assert None not in session.scalars(select(Deal.customer_id)).all()
    single = run_ingestion(csv_connector(tmp_path), e1_sessions,
                           IngestionRequest(entities=("documents",)), clock=clock)
    assert _run_row(e1_sessions, single.run_id).source_entity == "documents"


# ---------------------------------------------------------------------------
# Source failures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("connector", [
    FakeConnector({}, healthy=False),
    FakeConnector({}, health_error=ConnectorUnavailableError(f"refused {SECRET}")),
])
def test_failed_health_check_fails_the_run_without_fetching(e1_sessions, connector):
    summary = run_ingestion(connector, e1_sessions, clock=clock)
    assert summary.status is runs.RunStatus.FAILED
    assert connector.calls == []
    assert all(e.status is EntityStatus.SKIPPED for e in summary.entities)
    assert summary.error_summary == "connector health check failed; 7 entities skipped"
    (row,) = _errors(e1_sessions)
    assert (row.severity, row.error_code) == ("ERROR", "CONNECTOR_UNHEALTHY")
    assert SECRET not in row.message and SECRET not in row.detail
    _assert_run_row_matches(e1_sessions, summary)


def test_authentication_failure_stops_the_run(e1_sessions):
    dataset = valid_dataset()
    connector = FakeConnector(
        {entity: [rows] for entity, rows in dataset.items()},
        failures={("customers", 0): ConnectorAuthenticationError(f"bad key {SECRET}")})
    summary = run_ingestion(connector, e1_sessions, clock=clock)

    assert summary.status is runs.RunStatus.PARTIAL_SUCCESS
    assert [(e.entity_type, e.status) for e in summary.entities] == [
        ("organizations", EntityStatus.COMPLETED), ("employees", EntityStatus.COMPLETED),
        ("customers", EntityStatus.FAILED), ("deals", EntityStatus.SKIPPED),
        ("projects", EntityStatus.SKIPPED), ("support_tickets", EntityStatus.SKIPPED),
        ("documents", EntityStatus.SKIPPED)]
    assert [entity for entity, _ in connector.calls] == ["organizations", "employees", "customers"]
    assert summary.error_summary == (
        "customers failed: ConnectorAuthenticationError; 4 entities skipped")
    (row,) = _errors(e1_sessions)
    assert (row.error_code, row.source_entity, json.loads(row.detail)["run_stopped"]) == (
        "CONNECTOR_FAILED", "customers", True)
    assert SECRET not in row.message + row.detail
    _assert_run_row_matches(e1_sessions, summary)


def test_authentication_failure_before_any_commit_fails_the_run(e1_sessions):
    connector = FakeConnector({}, failures={("organizations", 0): ConnectorAuthenticationError("x")})
    summary = run_ingestion(connector, e1_sessions, IngestionRequest(entities=["organizations",
                                                                              "customers"]),
                            clock=clock)
    assert summary.status is runs.RunStatus.FAILED


def test_non_fatal_fetch_failure_fails_only_that_entity(e1_sessions):
    dataset = valid_dataset()
    connector = FakeConnector({entity: [rows] for entity, rows in dataset.items()},
                              failures={("deals", 0): ConnectorUnavailableError("down")})
    summary = run_ingestion(connector, e1_sessions, clock=clock)

    assert summary.status is runs.RunStatus.PARTIAL_SUCCESS
    statuses = {e.entity_type: e.status for e in summary.entities}
    assert statuses.pop("deals") is EntityStatus.FAILED
    assert set(statuses.values()) == {EntityStatus.COMPLETED}
    with e1_sessions() as session:
        checkpointed = set(session.scalars(select(IngestionCursor.source_entity)).all())
    assert checkpointed == set(ENTITY_ORDER) - {"deals"}
    assert _count(e1_sessions, Deal) == 0


def test_mid_entity_failure_keeps_committed_pages_and_a_retry_completes(e1_sessions):
    pages = {"customers": [[csv_row("customers")],
                           [csv_row("customers", customer_id="CUST-002")]]}
    request = IngestionRequest(entities=["customers"])
    failing = FakeConnector(pages, failures={("customers", 1): ConnectorUnavailableError("down")})
    first = run_ingestion(failing, e1_sessions, request, clock=clock)
    assert first.status is runs.RunStatus.PARTIAL_SUCCESS
    assert first.counts == runs.RunCounts(fetched=1, inserted=1)
    assert _count(e1_sessions, IngestionCursor) == 0

    retry = run_ingestion(FakeConnector(pages), e1_sessions, request, clock=clock)
    assert retry.status is runs.RunStatus.SUCCESS
    assert retry.counts == runs.RunCounts(fetched=2, inserted=1, unchanged=1)
    assert _count(e1_sessions, Customer) == 2
    with e1_sessions() as session:
        cursor = session.scalars(select(IngestionCursor)).one()
    assert cursor.last_successful_run_id == retry.run_id


# ---------------------------------------------------------------------------
# Batch (database) failures
# ---------------------------------------------------------------------------


def test_batch_database_failure_is_recorded_and_stops_only_its_entity(e1_sessions):
    long_name = "N" * 300
    pages = {
        "customers": [[csv_row("customers", customer_name=long_name)],
                      [csv_row("customers", customer_id="CUST-002")]],
        "deals": [[csv_row("deals")]],
    }
    connector = FakeConnector(pages)
    summary = run_ingestion(connector, e1_sessions, IngestionRequest(entities=["customers",
                                                                              "deals"]),
                            clock=clock)

    assert summary.status is runs.RunStatus.PARTIAL_SUCCESS
    customers, deals = summary.entities
    assert (customers.status, customers.batches_failed, customers.records_failed,
            customers.failure) == (EntityStatus.FAILED, 1, 1, "BATCH_FAILED")
    assert ("customers", "1") not in connector.calls
    assert deals.status is EntityStatus.COMPLETED
    assert summary.counts == runs.RunCounts(fetched=2, inserted=1, warnings=1)
    _assert_reconciles(summary)
    _assert_run_row_matches(e1_sessions, summary)

    failure = next(r for r in _errors(e1_sessions) if r.error_code == "BATCH_FAILED")
    detail = json.loads(failure.detail)
    assert (failure.source_entity, detail["sqlstate"], detail["records"]) == ("customers",
                                                                             "22001", 1)
    assert long_name not in failure.message + failure.detail
    assert _count(e1_sessions, Customer) == 0


def test_run_whose_only_batch_fails_is_failed(e1_sessions):
    connector = FakeConnector({"customers": [[csv_row("customers", customer_name="N" * 300)]]})
    summary = run_ingestion(connector, e1_sessions, IngestionRequest(entities=["customers"]),
                            clock=clock)
    assert summary.status is runs.RunStatus.FAILED
    assert summary.error_summary == "customers failed: BATCH_FAILED"


# ---------------------------------------------------------------------------
# System failures
# ---------------------------------------------------------------------------


def _page(items, **kwargs):
    return lambda entity, cursor, page_size: Page(items=items, **kwargs)


@pytest.mark.parametrize(("factory", "expected"), [
    (lambda entity, cursor, page_size: None, ConnectorContractError),
    (_page([csv_row("customers")], has_more=True, next_cursor=None), ConnectorContractError),
    (lambda entity, cursor, page_size: Page(items=[None], has_more=True,
                                            next_cursor=cursor or "1"), ConnectorContractError),
    (_page([], has_more=0), ConnectorContractError),
    (_page([csv_row("customers")] * 3), ConnectorContractError),
    (_page([{**csv_row("customers"), "tags": {"vip"}}]), raw.RawPayloadError),
])
def test_connector_contract_violations_fail_the_run_loudly(e1_sessions, factory, expected):
    connector = FakeConnector({}, page_factory=factory)
    with pytest.raises(expected):
        run_ingestion(connector, e1_sessions,
                      IngestionRequest(entities=["customers"], page_size=2), clock=clock)
    (run,) = _all_runs(e1_sessions)
    assert (run.status, run.error_summary) == (
        "FAILED", f"run aborted by system failure: {expected.__name__}")
    assert run.finished_at == NOW
    assert _count(e1_sessions, Customer) == 0


def _all_runs(sessions):
    with sessions() as session:
        return session.scalars(select(IngestionRun)).all()


def test_health_check_must_return_connector_health(e1_sessions):
    class BadHealth(FakeConnector):
        def health_check(self):
            return {"healthy": True}

    with pytest.raises(ConnectorContractError):
        run_ingestion(BadHealth({}), e1_sessions, clock=clock)
    (run,) = _all_runs(e1_sessions)
    assert (run.status, run.error_summary) == (
        "FAILED", "run aborted by system failure: ConnectorContractError")


def test_database_connectivity_failure_is_not_a_batch_failure(e1_sessions, monkeypatch):
    def outage(*args, **kwargs):
        raise OperationalError("COMMIT", {}, ConnectionError("server closed the connection"))

    monkeypatch.setattr(orchestrator, "commit_batch", outage)
    connector = FakeConnector({"customers": [[csv_row("customers")]]})
    with pytest.raises(OperationalError):
        run_ingestion(connector, e1_sessions, IngestionRequest(entities=["customers"]),
                      clock=clock)
    (run,) = _all_runs(e1_sessions)
    assert (run.status, run.error_summary) == ("FAILED",
                                               "run aborted by system failure: OperationalError")
    assert _errors(e1_sessions) == []


def test_naive_clock_is_rejected_before_a_run_is_created(e1_sessions):
    with pytest.raises(ValueError):
        run_ingestion(FakeConnector({}), e1_sessions, clock=lambda: NOW.replace(tzinfo=None))
    assert _all_runs(e1_sessions) == []


@pytest.mark.parametrize("request_", [
    IngestionRequest(mode="incremental"),
    IngestionRequest(mode="bogus"),
    IngestionRequest(page_size=0),
    IngestionRequest(page_size=orchestrator.MAX_PAGE_SIZE + 1),
    IngestionRequest(page_size=True),
    IngestionRequest(entities=[]),
    IngestionRequest(entities="customers"),
    IngestionRequest(entities=["invoices"]),
])
def test_invalid_requests_create_no_run(e1_sessions, request_):
    connector = FakeConnector({})
    with pytest.raises(IngestionRequestError):
        run_ingestion(connector, e1_sessions, request_, clock=clock)
    assert _all_runs(e1_sessions) == [] and connector.calls == []


def test_unsupported_source_and_entities_create_no_run(e1_sessions):
    with pytest.raises(IngestionRequestError):
        run_ingestion(FakeConnector({}, source_name="unmapped_source"), e1_sessions, clock=clock)

    class Limited(FakeConnector):
        def capabilities(self):
            return ConnectorCapabilities(supported_entity_types=["customers"])

    with pytest.raises(IngestionRequestError):
        run_ingestion(Limited({}), e1_sessions, IngestionRequest(entities=["deals"]), clock=clock)
    summary = run_ingestion(Limited({}), e1_sessions, clock=clock)
    assert [e.entity_type for e in summary.entities] == ["customers"]
    assert len(_all_runs(e1_sessions)) == 1


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


def test_logs_and_summaries_carry_identifiers_not_payloads(e1_sessions, caplog):
    rows = [csv_row("customers", customer_name=SECRET, api_key=f"Bearer {SECRET}"),
            csv_row("customers", customer_id="CUST-002", status=SECRET)]
    connector = FakeConnector({"customers": [rows]},
                              failures={("deals", 0): ConnectorUnavailableError(SECRET)})
    with caplog.at_level(logging.DEBUG, logger="app.ingestion"):
        summary = run_ingestion(connector, e1_sessions,
                                IngestionRequest(entities=["customers", "deals"]), clock=clock)
    text = json.dumps(summary.to_dict()) + caplog.text
    assert SECRET not in text
    assert str(summary.run_id) in caplog.text
    for event in ("run_started", "batch_committed", "entity_failed", "run_finished"):
        assert event in caplog.text
    run = _run_row(e1_sessions, summary.run_id)
    assert SECRET not in (run.error_summary or "")
