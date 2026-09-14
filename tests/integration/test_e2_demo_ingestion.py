"""
E2 demo data through E1 against the migrated test database.

The committed data/demo dataset and the bad fixture are ingested as csv_demo,
and data/demo is also served by the C3 mock source to the odoo_mock and
rest_mock connectors (spec Section 20 steps E-L).
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from collections.abc import Iterator
from http.server import HTTPServer
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors import CsvConnector, CsvConnectorConfig, SourceConnector
from app.ingestion.orchestrator import IngestionRequest, RunSummary, run_ingestion
from app.persistence.models import (
    Customer,
    Deal,
    Document,
    Employee,
    IngestionError,
    Organization,
    Project,
    SupportTicket,
)
from app.persistence.repositories.runs import RunStatus

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
BAD_FIXTURE_DIR = REPO / "data" / "fixtures" / "csv_demo_bad"
CanonicalModel = (type[Organization] | type[Employee] | type[Customer] | type[Deal]
                  | type[Project] | type[SupportTicket] | type[Document])
MODELS: dict[str, CanonicalModel] = {
    "organizations": Organization, "employees": Employee, "customers": Customer, "deals": Deal,
    "projects": Project, "support_tickets": SupportTicket, "documents": Document,
}
DEMO_COUNTS = {"organizations": 1, "employees": 24, "customers": 50, "deals": 44, "projects": 22,
               "support_tickets": 80, "documents": 12}
CUSTOMER_CHILDREN = (Deal, Project, SupportTicket)

sys.path.insert(0, str(REPO / "docker"))
import mock_source  # noqa: E402


def _load_ingest_demo():
    spec = importlib.util.spec_from_file_location("ingest_demo", REPO / "scripts" / "ingest_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ingest_demo = _load_ingest_demo()


def _csv(directory: Path) -> SourceConnector:
    config = CsvConnectorConfig.from_yaml(REPO / "config" / "connectors" / "csv_demo.yaml")
    config.data_directory = str(directory)
    return CsvConnector(config)


def _ingest(connector: SourceConnector, sessions: sessionmaker[Session]) -> RunSummary:
    return run_ingestion(connector, sessions, IngestionRequest())


def _entity_counts(summary: RunSummary, field: str) -> dict[str, int]:
    return {entity.entity_type: getattr(entity.counts, field) for entity in summary.entities}


def _table_counts(sessions: sessionmaker[Session]) -> dict[str, int | None]:
    with sessions() as session:
        return {entity: session.scalar(select(func.count()).select_from(model))
                for entity, model in MODELS.items()}


def _unresolved_customers(sessions: sessionmaker[Session], source_system: str) -> int:
    with sessions() as session:
        return sum(session.scalar(select(func.count()).select_from(model).where(
            model.source_system == source_system, model.customer_id.is_(None))) or 0
            for model in CUSTOMER_CHILDREN)


def _snapshot(sessions: sessionmaker[Session]) -> dict[str, list[tuple]]:
    with sessions() as session:
        return {entity: sorted(tuple(row) for row in session.execute(select(
            model.source_id, model.record_hash, model.ingestion_run_id, model.ingested_at)))
            for entity, model in MODELS.items()}


def _errors(sessions: sessionmaker[Session], summary: RunSummary) -> set[tuple[str, str, str, str]]:
    with sessions() as session:
        rows = session.execute(select(
            IngestionError.severity, IngestionError.error_code, IngestionError.source_entity,
            IngestionError.source_id).where(IngestionError.ingestion_run_id == summary.run_id))
        return {tuple(row) for row in rows}


def _assert_clean_first_run(summary: RunSummary, sessions: sessionmaker[Session]) -> None:
    assert summary.status is RunStatus.SUCCESS
    assert _entity_counts(summary, "fetched") == DEMO_COUNTS
    assert _entity_counts(summary, "inserted") == DEMO_COUNTS
    assert (summary.counts.rejected, summary.counts.warnings, summary.batches_failed) == (0, 0, 0)
    assert _errors(sessions, summary) == set()
    assert _unresolved_customers(sessions, summary.source_system) == 0


def _assert_noop_rerun(summary: RunSummary) -> None:
    assert summary.status is RunStatus.NOOP
    assert _entity_counts(summary, "unchanged") == DEMO_COUNTS
    assert (summary.counts.inserted, summary.counts.updated, summary.counts.rejected) == (0, 0, 0)


# ---------------------------------------------------------------------------
# csv_demo
# ---------------------------------------------------------------------------


def test_demo_dataset_ingests_cleanly_with_provenance_and_repeats_as_noop(e1_sessions):
    first = _ingest(_csv(DEMO_DIR), e1_sessions)
    _assert_clean_first_run(first, e1_sessions)
    assert _table_counts(e1_sessions) == DEMO_COUNTS
    with e1_sessions() as session:
        for entity, model in MODELS.items():
            provenance = session.execute(select(
                model.source_system, model.source_entity, model.ingestion_run_id,
                func.count()).group_by(model.source_system, model.source_entity,
                                       model.ingestion_run_id)).all()
            assert provenance == [("csv_demo", entity, first.run_id, DEMO_COUNTS[entity])]
            assert session.scalar(select(func.count()).select_from(model).where(
                (model.record_hash == "") | model.ingested_at.is_(None))) == 0

    snapshot = _snapshot(e1_sessions)
    second = _ingest(_csv(DEMO_DIR), e1_sessions)
    _assert_noop_rerun(second)
    assert _table_counts(e1_sessions) == DEMO_COUNTS
    assert _snapshot(e1_sessions) == snapshot


def test_churn_risk_scenario_is_queryable_after_ingestion(e1_sessions):
    _ingest(_csv(DEMO_DIR), e1_sessions)
    with e1_sessions() as session:
        customer = session.scalars(select(Customer).where(Customer.source_id == "CUST-007")).one()
        tickets = session.scalars(select(SupportTicket).where(
            SupportTicket.customer_id == customer.id)).all()
        deals = session.scalars(select(Deal).where(Deal.customer_id == customer.id,
                                                   Deal.is_active.is_(True))).all()
    created = sorted(ticket.created_at for ticket in tickets if ticket.created_at is not None)
    assert len(created) == 5 and (created[-1] - created[0]).days <= 14
    assert sum(ticket.status == "open" for ticket in tickets) == 4
    assert [(deal.source_id, deal.stage) for deal in deals] == [("DEAL-001", "negotiation")]


def test_bad_fixture_quarantines_invalid_rows_without_corrupting_the_demo(e1_sessions):
    _ingest(_csv(DEMO_DIR), e1_sessions)
    demo = _snapshot(e1_sessions)

    bad = _ingest(_csv(BAD_FIXTURE_DIR), e1_sessions)
    assert bad.status is RunStatus.PARTIAL_SUCCESS
    counts = bad.counts
    assert (counts.fetched, counts.inserted, counts.updated, counts.unchanged, counts.rejected,
            counts.warnings) == (8, 4, 0, 1, 3, 3)
    assert _errors(e1_sessions, bad) == {
        ("WARNING", "MISSING_RECOMMENDED_FIELD", "customers", "CUST-902"),
        ("WARNING", "DUPLICATE_SOURCE_RECORD", "customers", "CUST-901"),
        ("ERROR", "UNKNOWN_ENUM_VALUE", "customers", "CUST-903"),
        ("WARNING", "UNRESOLVED_REFERENCE", "deals", "DEAL-902"),
        ("ERROR", "INVALID_DECIMAL", "deals", "DEAL-903"),
        ("ERROR", "INVALID_DATE", "deals", "DEAL-904"),
    }

    after = _snapshot(e1_sessions)
    for entity, rows in demo.items():
        demo_ids = {row[0] for row in rows}
        assert [row for row in after[entity] if row[0] in demo_ids] == rows, entity
    fixture_ids = {entity: sorted(row[0] for row in after[entity] if "-9" in row[0])
                   for entity in ("customers", "deals")}
    assert fixture_ids == {"customers": ["CUST-901", "CUST-902"], "deals": ["DEAL-901", "DEAL-902"]}
    with e1_sessions() as session:
        deals = {deal.source_id: deal for deal in session.scalars(
            select(Deal).where(Deal.source_id.in_(["DEAL-901", "DEAL-902"])))}
        kestrel = session.scalars(select(Customer).where(Customer.source_id == "CUST-901")).one()
    assert deals["DEAL-901"].customer_id == kestrel.id
    assert (deals["DEAL-902"].customer_id, deals["DEAL-902"].customer_source_id) == (None, "CUST-999")

    again = _ingest(_csv(BAD_FIXTURE_DIR), e1_sessions)
    assert again.status is RunStatus.PARTIAL_SUCCESS
    assert (again.counts.inserted, again.counts.updated, again.counts.unchanged,
            again.counts.rejected) == (0, 0, 5, 3)
    assert _table_counts(e1_sessions) == {**DEMO_COUNTS, "customers": 52, "deals": 46}


# ---------------------------------------------------------------------------
# odoo_mock and rest_mock through the C3 mock source
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mock_source_url() -> Iterator[str]:
    """Serve data/demo on an ephemeral port; restore the module's data afterwards."""
    previous = dict(mock_source.ODOO_DATA), dict(mock_source.REST_DATA)
    odoo, rest = mock_source.load_source_data(DEMO_DIR)
    mock_source.ODOO_DATA.update(odoo)
    mock_source.REST_DATA.update(rest)
    server = HTTPServer(("127.0.0.1", 0), mock_source.MockSourceHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        for store, saved in zip((mock_source.ODOO_DATA, mock_source.REST_DATA), previous,
                                strict=True):
            store.clear()
            store.update(saved)


@pytest.mark.parametrize("source", ["odoo_mock", "rest_mock"])
def test_demo_dataset_ingests_through_the_mock_source_and_repeats_as_noop(
        e1_sessions, mock_source_url, source):
    connector = ingest_demo.build_connector(source, base_url=mock_source_url)
    first = _ingest(connector, e1_sessions)
    assert first.source_system == source
    _assert_clean_first_run(first, e1_sessions)
    assert _table_counts(e1_sessions) == DEMO_COUNTS

    _assert_noop_rerun(_ingest(connector, e1_sessions))
    assert _table_counts(e1_sessions) == DEMO_COUNTS
