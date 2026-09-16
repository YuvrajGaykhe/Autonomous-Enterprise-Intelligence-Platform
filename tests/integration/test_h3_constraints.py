"""
H3 database constraint tests (spec Section 15, "Database integration").

The B1 suite proves that a well-formed row can be written and read back.
This module proves the database refuses the rows it must refuse, and that
the behaviour Layer 1 relies on is enforced by PostgreSQL rather than by
convention in application code:

1. Source identity is unique per canonical table. This is what makes
   repeated ingestion idempotent (spec Section 20 I/J); without it the
   upsert would silently insert duplicates.
2. Provenance columns are NOT NULL, so an accepted record can never lose
   its traceability (Section 20 "Traceability").
3. Foreign keys reject unknown parents, and the declared ON DELETE rules
   are what implement "unresolved FK -> canonical FK NULL, source_id
   preserved" and the cascade of a run's dependent rows.
4. The upsert writes by source identity: the same identity twice updates
   one row and keeps its canonical id.
5. Run tracking persists truthful counts and a single terminal status.

Every assertion runs against the real migrated schema: the constraints are
checked by driving the database into the failing state, not by reading the
model definitions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from e1_support import NOW, csv_canonical, make_run
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.persistence.models import (
    ConnectorConfig,
    Customer,
    Deal,
    Employee,
    IngestionCursor,
    IngestionError,
    IngestionRun,
    Organization,
    SourceRecord,
    SupportTicket,
)
from app.persistence.repositories import canonical as canonical_repo
from app.persistence.repositories import cursors, errors, runs

pytestmark = pytest.mark.integration

CANONICAL_TABLES = (
    "organizations", "employees", "customers", "deals",
    "projects", "support_tickets", "documents",
)


def _row(entity: str, run_id: uuid.UUID, **overrides):
    """A full canonical table row with every E1 reference unresolved."""
    record = csv_canonical(entity, run_id, **overrides)
    references = dict.fromkeys(canonical_repo.reference_fields(entity))
    return canonical_repo.canonical_row(entity, record, references)


# ---------------------------------------------------------------------------
# 1. Source identity uniqueness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entity", CANONICAL_TABLES)
def test_source_identity_is_unique_in_every_canonical_table(e1_sessions, entity):
    """Two rows with the same (source_system, source_entity, source_id) cannot coexist."""
    run_id = make_run(e1_sessions)
    row = _row(entity, run_id)
    duplicate = {**row, "id": uuid.uuid4()}

    with pytest.raises(IntegrityError) as exc:
        with e1_sessions.begin() as session:
            session.execute(canonical_repo._table(entity).insert().values([row, duplicate]))
    assert f"uq_{entity}_source_identity" in str(exc.value.orig)


@pytest.mark.parametrize("entity", CANONICAL_TABLES)
def test_the_same_source_id_from_another_source_system_is_a_different_record(
    e1_sessions, entity
):
    """Identity is the whole triple: two sources may reuse an id string."""
    run_id = make_run(e1_sessions)
    row = _row(entity, run_id)
    other = {**row, "id": uuid.uuid4(), "source_system": "odoo_mock"}

    with e1_sessions.begin() as session:
        session.execute(canonical_repo._table(entity).insert().values([row, other]))

    with e1_sessions() as session:
        assert session.scalar(
            select(func.count()).select_from(canonical_repo._table(entity))
        ) == 2


def test_a_connector_config_source_name_is_unique(e1_sessions):
    with pytest.raises(IntegrityError) as exc:
        with e1_sessions.begin() as session:
            session.add_all([
                ConnectorConfig(id=uuid.uuid4(), source_name="csv_demo", source_type="csv"),
                ConnectorConfig(id=uuid.uuid4(), source_name="csv_demo", source_type="csv"),
            ])
    assert "uq_connector_configs_source_name" in str(exc.value.orig)


def test_a_checkpoint_is_unique_per_source_entity(e1_sessions):
    """One checkpoint per (source_system, source_entity), per spec Section 5."""
    run_id = make_run(e1_sessions)
    with pytest.raises(IntegrityError) as exc:
        with e1_sessions.begin() as session:
            session.add_all([
                IngestionCursor(id=uuid.uuid4(), source_system="csv_demo",
                                source_entity="customers", last_cursor="1",
                                last_successful_run_id=run_id, updated_at=NOW),
                IngestionCursor(id=uuid.uuid4(), source_system="csv_demo",
                                source_entity="customers", last_cursor="2",
                                last_successful_run_id=run_id, updated_at=NOW),
            ])
    assert "uq_ingestion_cursors_source_key" in str(exc.value.orig)


# ---------------------------------------------------------------------------
# 2. Provenance is mandatory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entity", CANONICAL_TABLES)
@pytest.mark.parametrize(
    "column",
    ["source_system", "source_entity", "source_id", "ingested_at",
     "ingestion_run_id", "record_hash"],
)
def test_provenance_columns_cannot_be_null(e1_sessions, entity, column):
    """An accepted record can never lose the trail back to its source."""
    run_id = make_run(e1_sessions)
    row = {**_row(entity, run_id), column: None}

    with pytest.raises(IntegrityError) as exc:
        with e1_sessions.begin() as session:
            session.execute(canonical_repo._table(entity).insert().values(row))
    assert column in str(exc.value.orig)


def test_source_updated_at_may_be_null(e1_sessions):
    """The one provenance field the spec marks nullable stays nullable."""
    run_id = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        session.execute(canonical_repo._table("customers").insert().values(
            {**_row("customers", run_id), "source_updated_at": None}))

    with e1_sessions() as session:
        assert session.scalars(select(Customer)).one().source_updated_at is None


def test_a_run_cannot_be_created_without_a_source_system(e1_sessions):
    with pytest.raises(IntegrityError):
        with e1_sessions.begin() as session:
            session.add(IngestionRun(id=uuid.uuid4(), source_system=None,
                                     status="RUNNING", mode="full", started_at=NOW))


# ---------------------------------------------------------------------------
# 3. Foreign keys
# ---------------------------------------------------------------------------


def test_a_canonical_fk_must_reference_an_existing_parent(e1_sessions):
    """A deal cannot point at a customer row that does not exist."""
    run_id = make_run(e1_sessions)
    row = {**_row("deals", run_id), "customer_id": uuid.uuid4()}

    with pytest.raises(IntegrityError) as exc:
        with e1_sessions.begin() as session:
            session.execute(canonical_repo._table("deals").insert().values(row))
    assert "fk_deals_customer_id_customers" in str(exc.value.orig)


def test_an_unresolved_canonical_fk_is_accepted_as_null(e1_sessions):
    """Spec Section 7: unresolved references are preserved, never rejected."""
    run_id = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        session.execute(canonical_repo._table("deals").insert().values(_row("deals", run_id)))

    with e1_sessions() as session:
        deal = session.scalars(select(Deal)).one()
    assert deal.customer_id is None
    assert deal.customer_source_id == "CUST-001", "the source key is still preserved"


def test_deleting_a_customer_nulls_the_canonical_fk_and_keeps_the_child(e1_sessions):
    """ON DELETE SET NULL: a child record survives losing its parent."""
    run_id = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        customer_row = _row("customers", run_id)
        session.execute(canonical_repo._table("customers").insert().values(customer_row))
        session.execute(canonical_repo._table("deals").insert().values(
            {**_row("deals", run_id), "customer_id": customer_row["id"]}))
        session.execute(canonical_repo._table("support_tickets").insert().values(
            {**_row("support_tickets", run_id), "customer_id": customer_row["id"]}))

    with e1_sessions.begin() as session:
        session.execute(text("DELETE FROM customers"))

    with e1_sessions() as session:
        assert session.scalars(select(Deal)).one().customer_id is None
        assert session.scalars(select(SupportTicket)).one().customer_id is None


def test_deleting_an_organization_nulls_the_employee_reference(e1_sessions):
    run_id = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        organization = _row("organizations", run_id)
        session.execute(canonical_repo._table("organizations").insert().values(organization))
        session.execute(canonical_repo._table("employees").insert().values(
            {**_row("employees", run_id), "organization_id": organization["id"]}))

    with e1_sessions.begin() as session:
        session.execute(text("DELETE FROM organizations"))

    with e1_sessions() as session:
        assert session.scalars(select(Employee)).one().organization_id is None


def test_deleting_a_run_cascades_to_its_errors_and_raw_records(e1_sessions):
    """ON DELETE CASCADE: operational children never outlive their run."""
    run_id = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        errors.add_errors(session, run_id, [errors.ErrorEntry(
            severity="ERROR", error_code="X", message="m",
            source_system="csv_demo", source_entity="customers", source_id="CUST-001",
        )], created_at=NOW)
        session.add(SourceRecord(
            id=uuid.uuid4(), ingestion_run_id=run_id, source_system="csv_demo",
            source_entity="customers", source_id="CUST-001",
            raw_payload={"customer_id": "CUST-001"}, content_hash="a" * 64, ingested_at=NOW,
        ))

    with e1_sessions() as session:
        assert session.scalar(select(func.count()).select_from(IngestionError)) == 1
        assert session.scalar(select(func.count()).select_from(SourceRecord)) == 1

    with e1_sessions.begin() as session:
        session.execute(text("DELETE FROM ingestion_runs"))

    with e1_sessions() as session:
        assert session.scalar(select(func.count()).select_from(IngestionError)) == 0
        assert session.scalar(select(func.count()).select_from(SourceRecord)) == 0


def test_an_error_row_must_belong_to_a_real_run(e1_sessions):
    with pytest.raises(IntegrityError) as exc:
        with e1_sessions.begin() as session:
            errors.add_errors(session, uuid.uuid4(), [errors.ErrorEntry(
                severity="ERROR", error_code="X", message="m")], created_at=NOW)
    assert "ingestion_run_id" in str(exc.value.orig)


def test_deleting_a_run_nulls_a_checkpoint_rather_than_dropping_it(e1_sessions):
    """A checkpoint outlives the run that set it: progress is not lost."""
    run_id = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        cursors.record_entity_success(session, source_system="csv_demo",
                                      source_entity="customers", run_id=run_id,
                                      last_cursor="50", updated_at=NOW)

    with e1_sessions.begin() as session:
        session.execute(text("DELETE FROM ingestion_runs"))

    with e1_sessions() as session:
        cursor = session.scalars(select(IngestionCursor)).one()
    assert cursor.last_cursor == "50"
    assert cursor.last_successful_run_id is None


# ---------------------------------------------------------------------------
# 4. Upsert by source identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entity", CANONICAL_TABLES)
def test_upserting_the_same_identity_twice_keeps_one_row(e1_sessions, entity):
    """Spec Section 20 J: no duplicate source identities after re-ingestion."""
    first_run = make_run(e1_sessions)
    second_run = make_run(e1_sessions)
    table = canonical_repo._table(entity)

    with e1_sessions.begin() as session:
        canonical_repo.upsert(session, entity, [_row(entity, first_run)])
    with e1_sessions() as session:
        original = session.execute(select(table)).one()._mapping["id"]

    with e1_sessions.begin() as session:
        canonical_repo.upsert(session, entity, [_row(entity, second_run)])

    with e1_sessions() as session:
        rows = session.execute(select(table)).all()
    assert len(rows) == 1
    assert rows[0]._mapping["id"] == original, "the canonical id is stable across runs"
    assert rows[0]._mapping["ingestion_run_id"] == second_run, "provenance follows the new run"


def test_an_upsert_updates_business_fields_and_the_record_hash(e1_sessions):
    """A changed source value reaches the canonical row and its content hash."""
    first_run = make_run(e1_sessions)
    second_run = make_run(e1_sessions)

    with e1_sessions.begin() as session:
        canonical_repo.upsert(session, "customers", [_row("customers", first_run)])
    with e1_sessions() as session:
        before = session.scalars(select(Customer)).one()
        before_hash, before_id = before.record_hash, before.id

    with e1_sessions.begin() as session:
        canonical_repo.upsert(session, "customers", [
            _row("customers", second_run, customer_name="Renamed Industries")])

    with e1_sessions() as session:
        after = session.scalars(select(Customer)).one()
    assert after.id == before_id
    assert after.name == "Renamed Industries"
    assert after.record_hash != before_hash


def test_an_upsert_never_rewrites_the_source_identity(e1_sessions):
    """Identity columns are excluded from the conflict update set."""
    run_id = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        canonical_repo.upsert(session, "customers", [_row("customers", run_id)])
    with e1_sessions.begin() as session:
        canonical_repo.upsert(session, "customers", [_row("customers", run_id)])

    with e1_sessions() as session:
        customer = session.scalars(select(Customer)).one()
    assert (customer.source_system, customer.source_entity, customer.source_id) == (
        "csv_demo", "customers", "CUST-001")


def test_an_upsert_reconciles_by_source_identity_not_by_canonical_id(e1_sessions):
    """The conflict target is the identity constraint, not the primary key.

    A caller that supplies a different canonical id for the same source
    identity must still update the existing row. Resolving the conflict on
    the primary key instead would attempt a second INSERT and violate the
    identity constraint.
    """
    first_run = make_run(e1_sessions)
    second_run = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        canonical_repo.upsert(session, "customers", [_row("customers", first_run)])
    with e1_sessions() as session:
        original_id = session.scalars(select(Customer)).one().id

    relabelled = {**_row("customers", second_run), "id": uuid.uuid4()}
    assert relabelled["id"] != original_id
    with e1_sessions.begin() as session:
        canonical_repo.upsert(session, "customers", [relabelled])

    with e1_sessions() as session:
        rows = session.scalars(select(Customer)).all()
    assert len(rows) == 1
    assert rows[0].id == original_id, "the stored canonical id wins"
    assert rows[0].ingestion_run_id == second_run


def test_advancing_the_same_checkpoint_twice_updates_one_row(e1_sessions):
    """The checkpoint upsert reconciles on (source_system, source_entity)."""
    first_run = make_run(e1_sessions)
    second_run = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        cursors.record_entity_success(session, source_system="csv_demo",
                                      source_entity="customers", run_id=first_run,
                                      last_cursor="25", updated_at=NOW)
    with e1_sessions.begin() as session:
        cursors.record_entity_success(session, source_system="csv_demo",
                                      source_entity="customers", run_id=second_run,
                                      last_cursor="50", updated_at=NOW)

    with e1_sessions() as session:
        rows = session.scalars(select(IngestionCursor)).all()
    assert len(rows) == 1
    assert rows[0].last_cursor == "50"
    assert rows[0].last_successful_run_id == second_run


def test_checkpoints_of_different_entities_are_separate_rows(e1_sessions):
    """The checkpoint key is the pair, so entities advance independently."""
    run_id = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        for entity in ("customers", "deals"):
            cursors.record_entity_success(session, source_system="csv_demo",
                                          source_entity=entity, run_id=run_id,
                                          last_cursor="7", updated_at=NOW)

    with e1_sessions() as session:
        assert session.scalar(select(func.count()).select_from(IngestionCursor)) == 2


def test_an_upsert_batch_rejects_a_duplicate_identity_before_touching_the_database(
    e1_sessions
):
    """Two rows for one identity in one batch is a caller error, not a conflict."""
    run_id = make_run(e1_sessions)
    with pytest.raises(ValueError, match="duplicate source identity"):
        with e1_sessions.begin() as session:
            canonical_repo.upsert(session, "customers",
                                  [_row("customers", run_id), _row("customers", run_id)])


def test_a_failed_batch_leaves_no_partial_rows(e1_sessions):
    """Transaction policy: a batch commits entirely or not at all."""
    run_id = make_run(e1_sessions)
    good = _row("customers", run_id)
    bad = {**_row("customers", run_id, customer_id="CUST-002"), "record_hash": None}

    with pytest.raises(IntegrityError):
        with e1_sessions.begin() as session:
            session.execute(canonical_repo._table("customers").insert().values([good, bad]))

    with e1_sessions() as session:
        assert session.scalar(select(func.count()).select_from(Customer)) == 0


def test_an_oversized_source_id_is_refused_rather_than_truncated(e1_sessions):
    """Silent truncation would merge two distinct source records."""
    run_id = make_run(e1_sessions)
    row = {**_row("customers", run_id), "source_id": "C" * 300}
    with pytest.raises(DBAPIError):
        with e1_sessions.begin() as session:
            session.execute(canonical_repo._table("customers").insert().values(row))


# ---------------------------------------------------------------------------
# 5. Run tracking
# ---------------------------------------------------------------------------


def test_a_run_records_truthful_counts(e1_sessions):
    """Spec Section 20 F: the run row carries the counts it accumulated."""
    run_id = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        runs.add_run_counts(session, run_id, runs.RunCounts(10, 4, 3, 2, 1, 5))
        runs.add_run_counts(session, run_id, runs.RunCounts(2, 1, 0, 1, 0, 0))
    with e1_sessions.begin() as session:
        runs.finish_run(session, run_id, status=runs.RunStatus.PARTIAL_SUCCESS,
                        finished_at=NOW, error_summary="1 record rejected")

    with e1_sessions() as session:
        run = session.get(IngestionRun, run_id)
    assert (run.records_fetched, run.records_inserted, run.records_updated) == (12, 5, 3)
    assert (run.records_unchanged, run.records_rejected, run.records_warnings) == (3, 1, 5)
    assert run.status == "PARTIAL_SUCCESS"
    assert run.error_summary == "1 record rejected"


def test_a_run_can_reach_a_terminal_status_only_once(e1_sessions):
    """A finished run is never re-finished, so its outcome cannot be rewritten."""
    run_id = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        runs.finish_run(session, run_id, status=runs.RunStatus.SUCCESS,
                        finished_at=NOW, error_summary=None)

    with pytest.raises(runs.RunStateError):
        with e1_sessions.begin() as session:
            runs.finish_run(session, run_id, status=runs.RunStatus.FAILED,
                            finished_at=NOW, error_summary="late")

    with e1_sessions() as session:
        assert session.get(IngestionRun, run_id).status == "SUCCESS"


def test_counts_cannot_be_added_to_a_finished_run(e1_sessions):
    """Counts and status stay consistent: nothing accrues after the run ends."""
    run_id = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        runs.finish_run(session, run_id, status=runs.RunStatus.SUCCESS,
                        finished_at=NOW, error_summary=None)

    with pytest.raises(runs.RunStateError):
        with e1_sessions.begin() as session:
            runs.add_run_counts(session, run_id, runs.RunCounts(1, 1, 0, 0, 0, 0))


def test_a_new_run_starts_with_zero_counts_and_no_finish_time(e1_sessions):
    run_id = make_run(e1_sessions)
    with e1_sessions() as session:
        run = session.get(IngestionRun, run_id)
    assert run.status == "RUNNING"
    assert run.finished_at is None
    assert (run.records_fetched, run.records_inserted, run.records_updated,
            run.records_unchanged, run.records_rejected, run.records_warnings) == (0,) * 6


def test_timestamps_round_trip_as_utc(e1_sessions):
    """Timezone-aware columns must not lose their offset in PostgreSQL."""
    run_id = make_run(e1_sessions)
    finished = datetime(2026, 9, 16, 8, 30, 15, tzinfo=UTC)
    with e1_sessions.begin() as session:
        runs.finish_run(session, run_id, status=runs.RunStatus.SUCCESS,
                        finished_at=finished, error_summary=None)

    with e1_sessions() as session:
        run = session.get(IngestionRun, run_id)
    assert run.finished_at == finished
    assert run.finished_at.utcoffset().total_seconds() == 0


def test_a_raw_source_record_keeps_its_payload_as_json(e1_sessions):
    """Section 4.2: the raw payload is preserved for provenance."""
    run_id = make_run(e1_sessions)
    payload = {"customer_id": "CUST-001", "nested": {"tags": ["a", "b"]}, "count": 3}
    with e1_sessions.begin() as session:
        session.add(SourceRecord(
            id=uuid.uuid4(), ingestion_run_id=run_id, source_system="csv_demo",
            source_entity="customers", source_id="CUST-001",
            raw_payload=payload, content_hash="b" * 64, ingested_at=NOW,
        ))

    with e1_sessions() as session:
        assert session.scalars(select(SourceRecord)).one().raw_payload == payload


def test_every_operational_table_is_empty_between_tests(e1_sessions):
    """Guards the harness: leakage between tests would mask real failures."""
    with e1_sessions() as session:
        for model in (Organization, Customer, Deal, IngestionRun, IngestionError,
                      SourceRecord, IngestionCursor, ConnectorConfig):
            assert session.scalar(select(func.count()).select_from(model)) == 0
