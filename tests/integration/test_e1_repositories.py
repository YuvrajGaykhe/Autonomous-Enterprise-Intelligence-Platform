"""
E1 persistence repository tests against a real, migrated PostgreSQL database.

Covers run lifecycle guards, append-only raw capture, source-identity
upserts, constraints, rollback, and checkpoint state.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from e1_support import NOW, csv_canonical, make_run
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.normalization import canonical_id
from app.normalization.contract import CANONICAL_SCHEMAS, E1_RESOLVED_FIELDS
from app.persistence.models import Customer, Deal, IngestionError, IngestionRun, SourceRecord
from app.persistence.repositories import canonical as canonical_repo
from app.persistence.repositories import cursors, errors, raw, runs

pytestmark = pytest.mark.integration

ENTITY_ORDER = ("organizations", "employees", "customers", "deals", "projects",
                "support_tickets", "documents")


def _count(sessions, model) -> int:
    with sessions() as session:
        return session.scalar(select(func.count()).select_from(model))


def _no_references(entity):
    return dict.fromkeys(canonical_repo.reference_fields(entity))


def _write(sessions, entity, record, references=None):
    with sessions.begin() as session:
        row = canonical_repo.canonical_row(entity, record,
                                           references or _no_references(entity))
        canonical_repo.upsert(session, entity, [row])


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def test_create_run_starts_running_with_zero_counts(e1_sessions):
    run_id = make_run(e1_sessions)
    with e1_sessions() as session:
        run = session.get(IngestionRun, run_id)
    assert (run.status, run.mode, run.source_system, run.finished_at) == (
        "RUNNING", "full", "csv_demo", None)
    assert [run.records_fetched, run.records_inserted, run.records_updated,
            run.records_unchanged, run.records_rejected, run.records_warnings] == [0] * 6


def test_run_counts_accumulate_across_batches(e1_sessions):
    run_id = make_run(e1_sessions)
    for counts in (runs.RunCounts(fetched=3, inserted=2, rejected=1, warnings=1),
                   runs.RunCounts(fetched=2, updated=1, unchanged=1, warnings=2)):
        with e1_sessions.begin() as session:
            runs.add_run_counts(session, run_id, counts)
    with e1_sessions() as session:
        run = session.get(IngestionRun, run_id)
    assert [run.records_fetched, run.records_inserted, run.records_updated,
            run.records_unchanged, run.records_rejected, run.records_warnings] == [5, 2, 1, 1, 1, 3]


def test_rolled_back_counts_are_not_persisted(e1_sessions):
    run_id = make_run(e1_sessions)
    with e1_sessions() as session:
        runs.add_run_counts(session, run_id, runs.RunCounts(fetched=9))
        session.rollback()
    with e1_sessions() as session:
        assert session.get(IngestionRun, run_id).records_fetched == 0


@pytest.mark.parametrize("value", [-1, True, 1.0, "1"])
def test_run_counts_must_be_non_negative_ints(value):
    with pytest.raises(ValueError):
        runs.RunCounts(fetched=value)


def test_run_counts_add():
    total = runs.RunCounts(fetched=1, warnings=2) + runs.RunCounts(fetched=4, rejected=1)
    assert total == runs.RunCounts(fetched=5, rejected=1, warnings=2)


def test_finish_run_is_terminal_and_single_use(e1_sessions):
    run_id = make_run(e1_sessions)
    finished = NOW + timedelta(seconds=5)
    with e1_sessions.begin() as session:
        runs.finish_run(session, run_id, status=runs.RunStatus.PARTIAL_SUCCESS,
                        finished_at=finished, error_summary="1 record rejected")
    with e1_sessions() as session:
        run = session.get(IngestionRun, run_id)
    assert (run.status, run.finished_at, run.error_summary) == (
        "PARTIAL_SUCCESS", finished, "1 record rejected")
    with e1_sessions() as session, pytest.raises(runs.RunStateError):
        runs.finish_run(session, run_id, status=runs.RunStatus.SUCCESS, finished_at=finished,
                        error_summary=None)
    with e1_sessions() as session, pytest.raises(runs.RunStateError):
        runs.add_run_counts(session, run_id, runs.RunCounts(fetched=1))


def test_finish_run_requires_terminal_status(e1_sessions):
    run_id = make_run(e1_sessions)
    with e1_sessions() as session, pytest.raises(ValueError):
        runs.finish_run(session, run_id, status=runs.RunStatus.RUNNING, finished_at=NOW,
                        error_summary=None)


def test_unknown_run_is_rejected(e1_sessions):
    with e1_sessions() as session:
        with pytest.raises(runs.RunStateError):
            runs.add_run_counts(session, uuid.uuid4(), runs.RunCounts(fetched=1))
        with pytest.raises(runs.RunStateError):
            runs.finish_run(session, uuid.uuid4(), status=runs.RunStatus.FAILED,
                            finished_at=NOW, error_summary=None)


def test_run_timestamps_must_be_timezone_aware(e1_sessions):
    naive = datetime(2026, 9, 14, 12, 0)
    with e1_sessions() as session:
        with pytest.raises(ValueError):
            runs.create_run(session, run_id=uuid.uuid4(), source_system="csv_demo",
                            source_entity=None, mode=runs.RunMode.FULL, started_at=naive)
    run_id = make_run(e1_sessions)
    with e1_sessions() as session, pytest.raises(ValueError):
        runs.finish_run(session, run_id, status=runs.RunStatus.SUCCESS, finished_at=naive,
                        error_summary=None)


# ---------------------------------------------------------------------------
# Raw capture
# ---------------------------------------------------------------------------


def test_content_hash_is_key_order_independent_and_matches_golden_value():
    first = raw.content_hash({"b": "2", "a": " 1 ", "n": [1, None, True, 2.5]})
    second = raw.content_hash({"n": [1, None, True, 2.5], "a": " 1 ", "b": "2"})
    golden = hashlib.sha256(b'{"a":" 1 ","b":"2","n":[1,null,true,2.5]}').hexdigest()
    assert first == second == golden
    assert raw.content_hash({"a": " 1"}) != raw.content_hash({"a": " 1 "})


@pytest.mark.parametrize("payload", [
    {"token": {"SYNTHETIC_SECRET_VALUE"}},
    {"amount": float("nan")},
    {"amount": float("inf")},
    {1: "SYNTHETIC_SECRET_VALUE"},
    {"blob": b"SYNTHETIC_SECRET_VALUE"},
    {"when": datetime(2026, 1, 1, tzinfo=UTC)},
    {"nested": [{"deep": Decimal("1.5")}]},
    ["SYNTHETIC_SECRET_VALUE"],
    None,
])
def test_non_json_payloads_are_rejected_without_leaking_values(payload):
    with pytest.raises(raw.RawPayloadError) as caught:
        raw.content_hash(payload)
    assert "SYNTHETIC_SECRET_VALUE" not in str(caught.value)


def test_source_records_are_append_only_and_preserve_payloads(e1_sessions):
    payload = {"customer_id": "CUST-001", "customer_name": "  Zoë Industries ₹ ", "extra": ""}
    run_ids = [make_run(e1_sessions), make_run(e1_sessions)]
    for run_id in run_ids:
        with e1_sessions.begin() as session:
            written = raw.add_source_records(
                session, run_id=run_id, source_system="csv_demo", source_entity="customers",
                records=[raw.RawRecord("CUST-001", payload)], ingested_at=NOW)
        assert written == 1
    with e1_sessions() as session:
        rows = session.scalars(select(SourceRecord).order_by(SourceRecord.ingestion_run_id)).all()
    assert len(rows) == 2
    assert {row.ingestion_run_id for row in rows} == set(run_ids)
    for row in rows:
        assert row.raw_payload == payload
        assert row.content_hash == raw.content_hash(payload)
        assert (row.source_system, row.source_entity, row.source_id, row.ingested_at) == (
            "csv_demo", "customers", "CUST-001", NOW)


def test_source_records_require_an_existing_run(e1_sessions):
    with e1_sessions() as session, pytest.raises(IntegrityError):
        raw.add_source_records(session, run_id=uuid.uuid4(), source_system="csv_demo",
                               source_entity="customers",
                               records=[raw.RawRecord("CUST-001", {"a": "b"})], ingested_at=NOW)
        session.flush()


def test_invalid_raw_payload_writes_nothing(e1_sessions):
    run_id = make_run(e1_sessions)
    with e1_sessions() as session, pytest.raises(raw.RawPayloadError):
        raw.add_source_records(
            session, run_id=run_id, source_system="csv_demo", source_entity="customers",
            records=[raw.RawRecord("CUST-001", {"a": "b"}),
                     raw.RawRecord("CUST-002", {"a": {"set"}})],
            ingested_at=NOW)
    assert _count(e1_sessions, SourceRecord) == 0


# ---------------------------------------------------------------------------
# Canonical upserts
# ---------------------------------------------------------------------------


def test_entity_models_cover_schemas_and_references_match_the_d1_contract():
    assert set(canonical_repo.ENTITY_MODELS) == set(CANONICAL_SCHEMAS)
    for entity, schema in CANONICAL_SCHEMAS.items():
        model = canonical_repo.ENTITY_MODELS[entity]
        assert {column.name for column in model.__table__.columns} == set(schema.model_fields)
        assert set(canonical_repo.reference_fields(entity)) == E1_RESOLVED_FIELDS[entity]


def test_canonical_row_covers_every_column_and_applies_references():
    run_id = uuid.uuid4()
    deal = csv_canonical("deals", run_id)
    parent = uuid.uuid4()
    row = canonical_repo.canonical_row("deals", deal, {"customer_id": parent})
    assert set(row) == {column.name for column in Deal.__table__.columns}
    assert row["customer_id"] == parent
    assert row["id"] == deal.id and row["record_hash"] == deal.record_hash
    assert row["amount"] == Decimal("150000.50")


@pytest.mark.parametrize("references", [{}, {"customer_id": None, "organization_id": None},
                                        {"organization_id": None}])
def test_canonical_row_requires_exact_references(references):
    deal = csv_canonical("deals", uuid.uuid4())
    with pytest.raises(ValueError):
        canonical_repo.canonical_row("deals", deal, references)


def test_canonical_row_rejects_entity_mismatch_and_unknown_entities():
    deal = csv_canonical("deals", uuid.uuid4())
    with pytest.raises(ValueError):
        canonical_repo.canonical_row("projects", deal, {"customer_id": None})
    with pytest.raises(ValueError):
        canonical_repo.canonical_row("invoices", deal, {})


@pytest.mark.parametrize("entity", ENTITY_ORDER)
def test_every_entity_round_trips_through_upsert(e1_sessions, entity):
    run_id = make_run(e1_sessions)
    record = csv_canonical(entity, run_id)
    _write(e1_sessions, entity, record)
    with e1_sessions() as session:
        states = canonical_repo.load_states(session, entity, "csv_demo", [record.source_id])
        stored = session.get(canonical_repo.ENTITY_MODELS[entity], record.id)
    state = states[record.source_id]
    assert state.id == record.id == canonical_id("csv_demo", entity, record.source_id)
    assert state.record_hash == record.record_hash
    assert state.source_updated_at == record.source_updated_at
    assert dict(state.references) == _no_references(entity)
    for name in CANONICAL_SCHEMAS[entity].model_fields:
        assert getattr(stored, name) == getattr(record, name), name


def test_upsert_stores_exact_decimal_and_date_values(e1_sessions):
    run_id = make_run(e1_sessions)
    _write(e1_sessions, "deals", csv_canonical("deals", run_id, amount="0.10", probability="100"))
    with e1_sessions() as session:
        deal = session.scalars(select(Deal)).one()
    assert (deal.amount, deal.probability, deal.expected_close_date) == (
        Decimal("0.10"), Decimal("100.00"), date(2026, 12, 31))


def test_repeated_upsert_updates_in_place_without_duplicates(e1_sessions):
    first_run, second_run = make_run(e1_sessions), make_run(e1_sessions)
    original = csv_canonical("customers", first_run)
    _write(e1_sessions, "customers", original)
    _write(e1_sessions, "customers", original)
    later = NOW + timedelta(hours=1)
    changed = csv_canonical("customers", second_run, ingested_at=later,
                            customer_name="Acme Industries Ltd")
    _write(e1_sessions, "customers", changed)
    with e1_sessions() as session:
        rows = session.scalars(select(Customer)).all()
    assert len(rows) == 1
    assert (rows[0].id, rows[0].name, rows[0].ingestion_run_id, rows[0].ingested_at,
            rows[0].record_hash) == (original.id, "Acme Industries Ltd", second_run, later,
                                     changed.record_hash)


def test_upsert_keeps_the_primary_key_of_an_existing_row(e1_sessions):
    run_id = make_run(e1_sessions)
    record = csv_canonical("customers", run_id)
    legacy_id = uuid.uuid4()
    with e1_sessions.begin() as session:
        session.add(Customer(**{**record.model_dump(), "id": legacy_id, "name": "Old"}))
    _write(e1_sessions, "customers", record)
    with e1_sessions() as session:
        stored = session.scalars(select(Customer)).one()
        state = canonical_repo.load_states(session, "customers", "csv_demo", ["CUST-001"])
    assert (stored.id, stored.name) == (legacy_id, "Acme Industries")
    assert state["CUST-001"].id == legacy_id


def test_upsert_rejects_duplicate_identities_and_malformed_rows(e1_sessions):
    run_id = make_run(e1_sessions)
    row = canonical_repo.canonical_row("customers", csv_canonical("customers", run_id), {})
    with e1_sessions() as session:
        with pytest.raises(ValueError):
            canonical_repo.upsert(session, "customers", [row, dict(row)])
        with pytest.raises(ValueError):
            canonical_repo.upsert(session, "customers", [{k: v for k, v in row.items()
                                                          if k != "email"}])
        with pytest.raises(ValueError):
            canonical_repo.upsert(session, "deals", [row])
        with pytest.raises(ValueError):
            canonical_repo.upsert(session, "customers", [{**row, "source_entity": "deals"}])
    assert _count(e1_sessions, Customer) == 0


def test_upsert_orders_multiple_rows_and_writes_all(e1_sessions):
    run_id = make_run(e1_sessions)
    records = [csv_canonical("customers", run_id, customer_id=f"CUST-{n:03d}")
               for n in (3, 1, 2)]
    with e1_sessions.begin() as session:
        canonical_repo.upsert(session, "customers",
                              [canonical_repo.canonical_row("customers", r, {}) for r in records])
    with e1_sessions() as session:
        states = canonical_repo.load_states(session, "customers", "csv_demo",
                                            ["CUST-001", "CUST-002", "CUST-003", "CUST-404"])
    assert sorted(states) == ["CUST-001", "CUST-002", "CUST-003"]


def test_load_states_is_scoped_by_source_system_and_entity(e1_sessions):
    run_id = make_run(e1_sessions)
    csv_record = csv_canonical("customers", run_id)
    rest_record = csv_record.model_copy(update={
        "source_system": "rest_mock", "id": canonical_id("rest_mock", "customers", "CUST-001")})
    _write(e1_sessions, "customers", csv_record)
    _write(e1_sessions, "customers", rest_record)
    with e1_sessions() as session:
        csv_states = canonical_repo.load_states(session, "customers", "csv_demo", ["CUST-001"])
        rest_states = canonical_repo.load_states(session, "customers", "rest_mock", ["CUST-001"])
        other_entity = canonical_repo.load_states(session, "deals", "csv_demo", ["CUST-001"])
        empty = canonical_repo.load_states(session, "customers", "csv_demo", [])
    assert csv_states["CUST-001"].id == csv_record.id
    assert rest_states["CUST-001"].id == rest_record.id
    assert other_entity == {} and empty == {}


def test_load_states_returns_resolved_references(e1_sessions):
    run_id = make_run(e1_sessions)
    customer = csv_canonical("customers", run_id)
    _write(e1_sessions, "customers", customer)
    _write(e1_sessions, "deals", csv_canonical("deals", run_id), {"customer_id": customer.id})
    with e1_sessions() as session:
        state = canonical_repo.load_states(session, "deals", "csv_demo", ["DEAL-001"])["DEAL-001"]
    assert dict(state.references) == {"customer_id": customer.id}


def test_database_rejects_references_to_missing_parents(e1_sessions):
    run_id = make_run(e1_sessions)
    with e1_sessions() as session, pytest.raises(IntegrityError):
        row = canonical_repo.canonical_row("deals", csv_canonical("deals", run_id),
                                           {"customer_id": uuid.uuid4()})
        canonical_repo.upsert(session, "deals", [row])
        session.flush()
    assert _count(e1_sessions, Deal) == 0


def test_rolled_back_upsert_leaves_no_rows(e1_sessions):
    run_id = make_run(e1_sessions)
    with e1_sessions() as session:
        canonical_repo.upsert(session, "customers", [
            canonical_repo.canonical_row("customers", csv_canonical("customers", run_id), {})])
        session.rollback()
    assert _count(e1_sessions, Customer) == 0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_add_errors_persists_entries_and_truncates_diagnostic_identifiers(e1_sessions):
    run_id = make_run(e1_sessions)
    long_id = "X" * 300
    entries = [
        errors.ErrorEntry("ERROR", "REQUIRED_FIELD_MISSING", "required canonical field has no value",
                          "csv_demo", "customers", long_id, '{"source_id": "' + long_id + '"}'),
        errors.ErrorEntry("WARNING", "MISSING_RECOMMENDED_FIELD", "recommended field has no value",
                          "csv_demo", "customers", "CUST-002"),
        errors.ErrorEntry("INFO", "RUN_NOTE", "operational event"),
    ]
    with e1_sessions.begin() as session:
        assert errors.add_errors(session, run_id, entries, created_at=NOW) == 3
    with e1_sessions() as session:
        rows = session.scalars(select(IngestionError).order_by(IngestionError.severity)).all()
    by_severity = {row.severity: row for row in rows}
    assert by_severity["ERROR"].source_id == "X" * 255
    assert long_id in by_severity["ERROR"].detail
    assert by_severity["WARNING"].source_id == "CUST-002"
    assert by_severity["INFO"].source_system is None
    assert all(row.ingestion_run_id == run_id and row.created_at == NOW for row in rows)


@pytest.mark.parametrize("kwargs", [
    {"severity": "FATAL", "error_code": "X", "message": "m"},
    {"severity": "ERROR", "error_code": "", "message": "m"},
    {"severity": "ERROR", "error_code": "X", "message": ""},
])
def test_error_entries_are_validated(kwargs):
    with pytest.raises(ValueError):
        errors.ErrorEntry(**kwargs)


def test_errors_require_an_existing_run(e1_sessions):
    with e1_sessions() as session, pytest.raises(IntegrityError):
        errors.add_errors(session, uuid.uuid4(), [errors.ErrorEntry("ERROR", "X", "m")],
                          created_at=NOW)
        session.flush()


# ---------------------------------------------------------------------------
# Cursors
# ---------------------------------------------------------------------------


def test_entity_checkpoint_is_a_single_upserted_row(e1_sessions):
    first_run, second_run = make_run(e1_sessions), make_run(e1_sessions)
    with e1_sessions() as session:
        assert cursors.get_cursor(session, "csv_demo", "customers") is None
    for run_id, when in ((first_run, NOW), (second_run, NOW + timedelta(minutes=1))):
        with e1_sessions.begin() as session:
            cursors.record_entity_success(session, source_system="csv_demo",
                                          source_entity="customers", run_id=run_id,
                                          last_cursor=None, updated_at=when)
    with e1_sessions() as session:
        state = cursors.get_cursor(session, "csv_demo", "customers")
        other = cursors.get_cursor(session, "csv_demo", "deals")
    assert state == cursors.CursorState(None, second_run, NOW + timedelta(minutes=1))
    assert other is None
