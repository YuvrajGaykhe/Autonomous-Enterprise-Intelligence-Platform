"""
M1 scope resolution and the Layer 1 fingerprint, against a real database.

The demo dataset is ingested into the isolated test database by the clean
full-dataset path, which makes every run of this module an independent
rebuild. The pinned fingerprint therefore has to be reproduced, not merely
recomputed, which is the property plan A5.1 claims and M0 measured.

What the fingerprint must detect, and what it must ignore, is the whole
point: a source_id rename that leaves every record_hash untouched must
change it, and a re-ingestion that changes only ingested_at must not.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.connectors import CsvConnector, CsvConnectorConfig, SourceConnector
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence.config import RiskRulesConfig, default_risk_rules
from app.intelligence.errors import (
    ContractViolationError,
    FingerprintMismatchError,
    ScopeResolutionError,
)
from app.intelligence.scope import (
    AsOfSource,
    layer1_fingerprint,
    resolve_pinned_scope,
    resolve_scope,
)
from app.persistence.models import Customer, Deal, Document, SupportTicket
from app.persistence.repositories.canonical import ENTITY_MODELS

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
PINNED = "1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00"
DEMO_COUNTS = {"organizations": 1, "employees": 24, "customers": 50, "deals": 44,
               "projects": 22, "support_tickets": 80, "documents": 12}
#: max(support_tickets.created_at) on the committed dataset, as a UTC date.
LATEST_TICKET_DATE = date(2026, 8, 27)
ACCEPTANCE_AS_OF = date(2026, 9, 18)


def _csv_connector() -> SourceConnector:
    config = CsvConnectorConfig.from_yaml(REPO / "config" / "connectors" / "csv_demo.yaml")
    config.data_directory = str(DEMO_DIR)
    return CsvConnector(config)


@pytest.fixture
def demo(e1_sessions: sessionmaker[Session]) -> sessionmaker[Session]:
    """The clean full-dataset path of plan A28: 233 rows, 7 entity types, 0 rejected."""
    counts = run_ingestion(_csv_connector(), e1_sessions, IngestionRequest()).counts
    assert counts.rejected == 0
    assert counts.fetched == counts.inserted == sum(DEMO_COUNTS.values())
    return e1_sessions


def fingerprint_of(sessions: sessionmaker[Session], source_system: str = "csv_demo") -> str:
    with sessions() as session:
        digest, _ = layer1_fingerprint(session, source_system)
    return digest


def canonical_snapshot(sessions: sessionmaker[Session]) -> dict[str, list[tuple]]:
    """Every canonical row, provenance included, as it stands right now."""
    snapshot = {}
    with sessions() as session:
        for entity_type, model in ENTITY_MODELS.items():
            snapshot[entity_type] = sorted(
                session.execute(
                    select(model.source_system, model.source_entity, model.source_id,
                           model.record_hash, model.ingested_at, model.ingestion_run_id,
                           model.source_updated_at)
                ).all()
            )
    return snapshot


# ---------------------------------------------------------------------------
# The pinned snapshot
# ---------------------------------------------------------------------------


def test_the_clean_demo_dataset_reproduces_the_pinned_fingerprint(demo):
    """An independent rebuild must reproduce the value, not merely compute one."""
    with demo() as session:
        digest, counts = layer1_fingerprint(session, "csv_demo")

    assert digest == PINNED
    assert dict(counts) == DEMO_COUNTS
    assert sum(counts.values()) == 233


def test_the_pinned_value_in_configuration_is_the_one_the_database_yields(demo):
    assert default_risk_rules().pinned_fingerprint("csv_demo") == fingerprint_of(demo)


def test_the_fingerprint_is_stable_across_repeated_reads(demo):
    assert fingerprint_of(demo) == fingerprint_of(demo) == PINNED


def test_the_fingerprint_is_stable_across_processes(demo, e1_engine):
    """A different interpreter, a different hash seed, the same bytes."""
    script = (
        "import sys;"
        "from sqlalchemy import create_engine;"
        "from sqlalchemy.orm import Session;"
        "from app.intelligence.scope import layer1_fingerprint;"
        "engine = create_engine(sys.argv[1]);"
        "session = Session(engine);"
        "print(layer1_fingerprint(session, 'csv_demo')[0])"
    )
    url = e1_engine.url.render_as_string(hide_password=False)
    completed = subprocess.run(
        [sys.executable, "-c", script, url],
        cwd=REPO, capture_output=True, text=True, check=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "1", "HOME": str(Path.home())},
    )

    assert completed.stdout.strip() == PINNED


# ---------------------------------------------------------------------------
# What the fingerprint must detect
# ---------------------------------------------------------------------------


def test_a_business_content_change_changes_the_fingerprint(demo):
    with demo.begin() as session:
        customer = session.scalars(
            select(Customer).where(Customer.source_id == "CUST-007")).one()
        customer.name = "Meridian Textiles Renamed"
        customer.record_hash = "f" * 64

    assert fingerprint_of(demo) != PINNED


def test_a_source_id_rename_that_preserves_sort_position_changes_the_fingerprint(demo):
    """
    The defect a composition over record_hash values alone cannot catch.

    record_hash excludes source_id, so this rename leaves every hash and
    every count untouched. source_id is nevertheless the join key for every
    source-key edge and the token quoted in citations, so the snapshot has
    genuinely changed.
    """
    before = canonical_snapshot(demo)
    with demo.begin() as session:
        customer = session.scalars(
            select(Customer).where(Customer.source_id == "CUST-007")).one()
        customer.source_id = "CUST-007Z"

    after = canonical_snapshot(demo)
    renamed = {row[3] for row in after["customers"]}
    assert renamed == {row[3] for row in before["customers"]}, "no record_hash changed"
    assert len(after["customers"]) == len(before["customers"]), "no count changed"
    assert fingerprint_of(demo) != PINNED


def test_a_source_id_rename_that_reorders_the_sequence_changes_the_fingerprint(demo):
    with demo.begin() as session:
        customer = session.scalars(
            select(Customer).where(Customer.source_id == "CUST-007")).one()
        customer.source_id = "CUST-999"

    assert fingerprint_of(demo) != PINNED


def test_adding_a_record_changes_the_fingerprint(demo):
    with demo.begin() as session:
        session.add(Customer(
            id=uuid.uuid4(), source_system="csv_demo", source_entity="customers",
            source_id="CUST-900", name="Added Industries", is_active=True,
            ingestion_run_id=uuid.uuid4(), record_hash="a" * 64,
        ))

    assert fingerprint_of(demo) != PINNED


def test_removing_a_record_changes_the_fingerprint(demo):
    with demo.begin() as session:
        ticket = session.scalars(
            select(SupportTicket).where(SupportTicket.source_id == "TKT-080")).one()
        session.delete(ticket)

    assert fingerprint_of(demo) != PINNED


def test_removing_a_whole_entity_type_changes_the_fingerprint(demo):
    """A verify-layer1 residue has no documents at all, and must not pass the gate."""
    with demo.begin() as session:
        for document in session.scalars(select(Document)).all():
            session.delete(document)

    assert fingerprint_of(demo) != PINNED


# ---------------------------------------------------------------------------
# What the fingerprint must ignore
# ---------------------------------------------------------------------------


def test_re_ingesting_an_unchanged_dataset_leaves_the_fingerprint_alone(demo):
    counts = run_ingestion(_csv_connector(), demo, IngestionRequest()).counts

    assert (counts.inserted, counts.updated, counts.unchanged) == (0, 0, 233)
    assert fingerprint_of(demo) == PINNED


def test_ingestion_provenance_is_excluded_from_the_fingerprint(demo):
    """
    ingested_at, ingestion_run_id and source_updated_at change on every run.

    Including them would make an unchanged re-ingestion mint a new snapshot
    identity and destroy the idempotency the fingerprint exists to protect.
    """
    with demo.begin() as session:
        for ticket in session.scalars(select(SupportTicket)).all():
            ticket.ingested_at = datetime(2030, 1, 1, tzinfo=UTC)
            ticket.ingestion_run_id = uuid.uuid4()
            ticket.source_updated_at = datetime(2030, 1, 1, tzinfo=UTC)

    assert fingerprint_of(demo) == PINNED


def test_another_source_system_is_outside_the_scope(demo):
    with demo.begin() as session:
        session.add(Customer(
            id=uuid.uuid4(), source_system="odoo_mock", source_entity="customers",
            source_id="CUST-001", name="Elsewhere Industries", is_active=True,
            ingestion_run_id=uuid.uuid4(), record_hash="b" * 64,
        ))

    assert fingerprint_of(demo, "csv_demo") == PINNED
    assert fingerprint_of(demo, "odoo_mock") != PINNED


def test_the_ordering_is_total_even_when_two_rows_share_a_source_id(demo):
    """
    A canonical table is unique over (source_system, source_entity, source_id),
    so source_id alone is not provably a total order. The tiebreaker makes it
    one, and an update - which moves a row in the PostgreSQL heap - must not
    move the digest.
    """
    with demo.begin() as session:
        session.add(Customer(
            id=uuid.uuid4(), source_system="csv_demo", source_entity="res.partner",
            source_id="CUST-007", name="Same Id Other Entity", is_active=True,
            ingestion_run_id=uuid.uuid4(), record_hash="9" * 64,
        ))

    with_tie = fingerprint_of(demo)
    assert with_tie != PINNED

    with demo.begin() as session:
        for customer in session.scalars(
                select(Customer).where(Customer.source_id == "CUST-007")).all():
            customer.ingested_at = datetime(2030, 6, 1, tzinfo=UTC)

    assert fingerprint_of(demo) == with_tie


def test_physical_row_order_does_not_move_the_fingerprint(demo):
    """
    PostgreSQL guarantees no row order without an ORDER BY.

    Deleting a row and re-inserting it identically appends a new heap tuple,
    so an unordered read would return it last. The digest must not notice.
    """
    with demo.begin() as session:
        document = session.scalars(
            select(Document).where(Document.source_id == "DOC-001")).one()
        values = {column.name: getattr(document, column.name)
                  for column in Document.__table__.columns}
        session.delete(document)
        session.flush()
        session.add(Document(**values))

    assert fingerprint_of(demo) == PINNED


def test_an_empty_scope_has_its_own_fingerprint(e1_sessions):
    empty = fingerprint_of(e1_sessions)

    assert empty != PINNED
    assert fingerprint_of(e1_sessions) == empty


# ---------------------------------------------------------------------------
# as_of resolution
# ---------------------------------------------------------------------------


def test_an_explicit_as_of_is_used_and_recorded_as_explicit(demo):
    with demo() as session:
        scope = resolve_scope(session, as_of=ACCEPTANCE_AS_OF)

    assert scope.as_of == ACCEPTANCE_AS_OF
    assert scope.as_of_source is AsOfSource.EXPLICIT


def test_a_timestamp_is_refused_as_an_evaluation_date(demo):
    """A caller error is named at the entry point, before any snapshot is read."""
    with demo() as session, pytest.raises(ContractViolationError, match="not a timestamp"):
        resolve_scope(session, as_of=datetime(2026, 9, 18, 10, 30, tzinfo=UTC))


def test_without_an_as_of_the_latest_ticket_date_is_used_and_recorded(demo):
    with demo() as session:
        scope = resolve_scope(session)

    assert scope.as_of == LATEST_TICKET_DATE
    assert scope.as_of_source is AsOfSource.MAX_TICKET_CREATED_AT


def test_the_fallback_date_is_not_the_acceptance_date(demo):
    """Plan defect 3: the two differ, and the acceptance run must never rely on the fallback."""
    with demo() as session:
        fallback = resolve_scope(session).as_of

    assert fallback != default_risk_rules().acceptance_as_of


def test_the_fallback_date_is_the_utc_date_whatever_the_server_timezone_is(demo):
    """
    A ticket at 20:00 UTC is already the next day in Asia/Kolkata.

    The driver hands back the timestamp in the session timezone, so reading
    its local date instead of its UTC date would silently move the evaluation
    date by a day and shift every window boundary with it.
    """
    with demo.begin() as session:
        session.add(SupportTicket(
            id=uuid.uuid4(), source_system="csv_demo", source_entity="support_tickets",
            source_id="TKT-901", created_at=datetime(2026, 8, 27, 20, 0, tzinfo=UTC),
            ingestion_run_id=uuid.uuid4(), record_hash="8" * 64,
        ))

    with demo() as session:
        session.execute(text("SET TIME ZONE 'Asia/Kolkata'"))
        latest = session.scalar(select(func.max(SupportTicket.created_at)))
        assert latest.utcoffset() is not None, "the driver must return an aware timestamp"
        assert latest.date() == date(2026, 8, 28), "the local date is the next day"

        assert resolve_scope(session).as_of == LATEST_TICKET_DATE


def test_the_fallback_reads_only_tickets_of_the_scoped_source_system(demo):
    with demo.begin() as session:
        session.add(SupportTicket(
            id=uuid.uuid4(), source_system="odoo_mock", source_entity="support_tickets",
            source_id="TKT-900", created_at=datetime(2030, 1, 1, tzinfo=UTC),
            ingestion_run_id=uuid.uuid4(), record_hash="c" * 64,
        ))

    with demo() as session:
        assert resolve_scope(session).as_of == LATEST_TICKET_DATE


def test_an_empty_scope_without_an_as_of_is_refused_rather_than_clocked(e1_sessions):
    """now() is forbidden, so a scope with no ticket has no defensible date."""
    with e1_sessions() as session, pytest.raises(ScopeResolutionError, match="now\\(\\) is forbidden"):
        resolve_scope(session)


def test_an_empty_scope_with_an_as_of_resolves_to_an_empty_snapshot(e1_sessions):
    with e1_sessions() as session:
        scope = resolve_scope(session, as_of=ACCEPTANCE_AS_OF)

    assert scope.record_count == 0
    assert scope.as_of == ACCEPTANCE_AS_OF


# ---------------------------------------------------------------------------
# The fingerprint gate
# ---------------------------------------------------------------------------


def test_the_expected_fingerprint_is_accepted(demo):
    with demo() as session:
        scope = resolve_scope(session, as_of=ACCEPTANCE_AS_OF, expected_fingerprint=PINNED)

    assert scope.layer1_fingerprint == PINNED


def test_an_unexpected_snapshot_fails_closed_with_both_values_named(demo):
    with demo() as session, pytest.raises(FingerprintMismatchError) as raised:
        resolve_scope(session, as_of=ACCEPTANCE_AS_OF, expected_fingerprint="0" * 64)

    assert raised.value.expected == "0" * 64
    assert raised.value.computed == PINNED
    assert raised.value.source_system == "csv_demo"
    assert "rebuild the database" in str(raised.value)


def test_the_pinned_scope_accepts_a_database_built_the_clean_way(demo):
    with demo() as session:
        scope = resolve_pinned_scope(session, as_of=ACCEPTANCE_AS_OF)

    assert scope.layer1_fingerprint == PINNED
    assert scope.record_count == 233


def test_the_pinned_scope_refuses_a_contaminated_database(demo):
    """Four malformed-fixture rows inside the csv_demo scope are what verify-layer1 leaves."""
    with demo.begin() as session:
        for source_id in ("CUST-901", "CUST-902"):
            session.add(Customer(
                id=uuid.uuid4(), source_system="csv_demo", source_entity="customers",
                source_id=source_id, name="Fixture Industries", is_active=True,
                ingestion_run_id=uuid.uuid4(), record_hash="d" * 64,
            ))
        for source_id in ("DEAL-901", "DEAL-902"):
            session.add(Deal(
                id=uuid.uuid4(), source_system="csv_demo", source_entity="deals",
                source_id=source_id, name="Fixture Deal", is_active=True,
                ingestion_run_id=uuid.uuid4(), record_hash="e" * 64,
            ))

    with demo() as session, pytest.raises(FingerprintMismatchError):
        resolve_pinned_scope(session, as_of=ACCEPTANCE_AS_OF)


def test_a_caller_may_supply_its_own_rules_configuration(demo):
    """
    Scope resolution reads only the pin, but the type is whole.

    M3 added the lookback, DOC-003's targets and window, and the band
    table, so a hand-built configuration has to carry them. Only the
    fingerprint pin is what this test is about.
    """
    committed = default_risk_rules()
    config = RiskRulesConfig(
        rules_version=9, acceptance_as_of=ACCEPTANCE_AS_OF,
        layer1_fingerprints={"csv_demo": PINNED},
        lookback_days=committed.lookback_days,
        sla_resolution_targets=committed.sla_resolution_targets,
        escalation=committed.escalation,
        band_rules=committed.band_rules,
    )

    with demo() as session:
        assert resolve_pinned_scope(session, config=config).layer1_fingerprint == PINNED


# ---------------------------------------------------------------------------
# Layer 1 immutability
# ---------------------------------------------------------------------------


def test_resolving_a_scope_changes_no_canonical_row(demo):
    before = canonical_snapshot(demo)

    with demo() as session:
        resolve_pinned_scope(session, as_of=ACCEPTANCE_AS_OF)
        resolve_scope(session)
        layer1_fingerprint(session, "csv_demo")

    assert canonical_snapshot(demo) == before


def test_resolving_a_scope_writes_no_row_of_any_kind(demo):
    def counts() -> dict[str, int]:
        with demo() as session:
            return {
                entity_type: session.scalar(select(func.count()).select_from(model))
                for entity_type, model in ENTITY_MODELS.items()
            }

    before = counts()
    with demo() as session:
        resolve_pinned_scope(session, as_of=ACCEPTANCE_AS_OF)

    assert counts() == before == DEMO_COUNTS
