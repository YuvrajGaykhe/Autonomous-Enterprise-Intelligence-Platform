"""
E1 batch unit-of-work tests against a real, migrated PostgreSQL database.

Real D1 + D2 quality gate output, persisted through commit_batch: raw
capture, quarantine and warning rows, idempotency, reconciliation, FK
resolution, rollback, checkpoints, and advisory locking.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest
from e1_support import NOW, csv_canonical, csv_row, make_run
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import DataError, OperationalError
from sqlalchemy.orm import sessionmaker

from app.ingestion import batch
from app.ingestion.batch import (
    Checkpoint,
    acquire_batch_lock,
    commit_batch,
    lock_key,
    valid_record_indices,
)
from app.normalization import canonical_id
from app.persistence.models import (
    Customer,
    Deal,
    Employee,
    IngestionCursor,
    IngestionError,
    IngestionRun,
    SourceRecord,
    SupportTicket,
)
from app.persistence.repositories import canonical as canonical_repo
from app.persistence.repositories import raw, runs
from app.validation import validate_canonical_batch, validate_source_batch

pytestmark = pytest.mark.integration

SECRET = "SYNTHETIC_BEARER_CREDENTIAL_0123456789"


def _commit(sessions, run_id, entity, rows, *, checkpoint=None, ingested_at=NOW):
    gate = validate_source_batch("csv_demo", entity, rows, run_id, ingested_at)
    return commit_batch(sessions, run_id=run_id, gate=gate, raw_records=rows,
                        ingested_at=ingested_at, checkpoint=checkpoint)


def _all(sessions, model, *order):
    with sessions() as session:
        return session.scalars(select(model).order_by(*order)).all()


def _count(sessions, model) -> int:
    with sessions() as session:
        return session.scalar(select(func.count()).select_from(model))


def _run(sessions, run_id):
    with sessions() as session:
        return session.get(IngestionRun, run_id)


def _run_counts(run):
    return runs.RunCounts(run.records_fetched, run.records_inserted, run.records_updated,
                          run.records_unchanged, run.records_rejected, run.records_warnings)


def _customer_batch():
    return [
        csv_row("customers"),
        csv_row("customers", customer_id="CUST-002", customer_name=""),
        None,
        csv_row("customers", customer_id="CUST-003", email_address="",
                api_key=f"Bearer {SECRET}"),
    ]


# ---------------------------------------------------------------------------
# Normal, invalid and warning records
# ---------------------------------------------------------------------------


def test_mixed_batch_persists_valid_records_quarantine_and_warnings(e1_sessions):
    run_id = make_run(e1_sessions)
    result = _commit(e1_sessions, run_id, "customers", _customer_batch())

    expected = runs.RunCounts(fetched=4, inserted=2, rejected=2, warnings=1)
    assert result.counts == expected
    assert (result.raw_persisted, result.errors_recorded, result.unresolved_references) == (3, 3, 0)
    assert _run_counts(_run(e1_sessions, run_id)) == expected

    customers = _all(e1_sessions, Customer, Customer.source_id)
    assert [(c.source_id, c.id, c.ingestion_run_id) for c in customers] == [
        ("CUST-001", canonical_id("csv_demo", "customers", "CUST-001"), run_id),
        ("CUST-003", canonical_id("csv_demo", "customers", "CUST-003"), run_id)]

    raws = _all(e1_sessions, SourceRecord, SourceRecord.source_id)
    assert [r.source_id for r in raws] == ["CUST-001", "CUST-002", "CUST-003"]
    assert raws[1].raw_payload == _customer_batch()[1]

    rows = _all(e1_sessions, IngestionError, IngestionError.severity, IngestionError.source_id)
    findings = sorted((r.severity, r.error_code, r.source_id, json.loads(r.detail)["record_index"])
                      for r in rows)
    assert findings == [
        ("ERROR", "INVALID_RECORD", None, 2),
        ("ERROR", "REQUIRED_FIELD_MISSING", "CUST-002", 1),
        ("WARNING", "MISSING_RECOMMENDED_FIELD", "CUST-003", 3),
    ]
    assert all(r.ingestion_run_id == run_id and r.source_entity == "customers" for r in rows)
    quarantined = next(r for r in rows if r.source_id == "CUST-002")
    detail = json.loads(quarantined.detail)
    assert (detail["stage"], detail["raw_record"]["customer_id"]) == ("normalization", "CUST-002")


def test_quarantine_rows_keep_d2_redaction(e1_sessions):
    run_id = make_run(e1_sessions)
    invalid = csv_row("customers", customer_id="CUST-009", status="churned",
                      api_key=f"Bearer {SECRET}", note=f"token={SECRET}")
    _commit(e1_sessions, run_id, "customers", [invalid])
    (row,) = _all(e1_sessions, IngestionError)
    assert row.error_code == "UNKNOWN_ENUM_VALUE"
    assert SECRET not in row.detail and SECRET not in row.message
    assert "[REDACTED]" in row.detail


def test_empty_batch_records_zero_counts(e1_sessions):
    run_id = make_run(e1_sessions)
    result = _commit(e1_sessions, run_id, "customers", [], checkpoint=Checkpoint())
    assert result.counts == runs.RunCounts()
    assert _count(e1_sessions, IngestionCursor) == 1


# ---------------------------------------------------------------------------
# Idempotency and reconciliation across runs
# ---------------------------------------------------------------------------


def test_identical_rerun_is_unchanged_and_never_duplicates(e1_sessions):
    first, second = make_run(e1_sessions), make_run(e1_sessions)
    _commit(e1_sessions, first, "customers", _customer_batch())
    before = [(c.id, c.record_hash, c.ingestion_run_id, c.ingested_at)
              for c in _all(e1_sessions, Customer, Customer.source_id)]
    result = _commit(e1_sessions, second, "customers", _customer_batch(),
                     ingested_at=NOW + timedelta(hours=1))

    assert result.counts == runs.RunCounts(fetched=4, unchanged=2, rejected=2, warnings=1)
    after = [(c.id, c.record_hash, c.ingestion_run_id, c.ingested_at)
             for c in _all(e1_sessions, Customer, Customer.source_id)]
    assert after == before
    with e1_sessions() as session:
        identities = session.execute(
            select(Customer.source_system, Customer.source_entity, Customer.source_id,
                   func.count()).group_by(Customer.source_system, Customer.source_entity,
                                          Customer.source_id)).all()
    assert all(count == 1 for *_, count in identities) and len(identities) == 2
    assert _count(e1_sessions, SourceRecord) == 6


def test_source_update_in_a_later_run_updates_in_place(e1_sessions):
    first, second = make_run(e1_sessions), make_run(e1_sessions)
    _commit(e1_sessions, first, "customers", [csv_row("customers")])
    later = NOW + timedelta(days=1)
    result = _commit(e1_sessions, second, "customers",
                     [csv_row("customers", customer_segment="SMB")], ingested_at=later)
    assert result.counts == runs.RunCounts(fetched=1, updated=1)
    (customer,) = _all(e1_sessions, Customer)
    assert (customer.segment, customer.ingestion_run_id, customer.ingested_at) == (
        "SMB", second, later)


def test_duplicates_in_a_batch_resolve_to_the_last_occurrence(e1_sessions):
    run_id = make_run(e1_sessions)
    rows = [csv_row("customers"), csv_row("customers"),
            csv_row("customers", customer_name="Acme Final")]
    result = _commit(e1_sessions, run_id, "customers", rows)
    assert result.counts == runs.RunCounts(fetched=3, inserted=1, unchanged=1, updated=1,
                                           warnings=2)
    (customer,) = _all(e1_sessions, Customer)
    assert customer.name == "Acme Final"
    codes = sorted(r.error_code for r in _all(e1_sessions, IngestionError))
    assert codes == ["DUPLICATE_SOURCE_IDENTITY_CONFLICT", "DUPLICATE_SOURCE_RECORD"]


def test_duplicates_across_batches_of_one_run_reconcile_in_order(e1_sessions):
    run_id = make_run(e1_sessions)
    _commit(e1_sessions, run_id, "customers", [csv_row("customers")])
    result = _commit(e1_sessions, run_id, "customers",
                     [csv_row("customers", customer_name="Acme Page Two")])
    assert result.counts == runs.RunCounts(fetched=1, updated=1)
    assert _run_counts(_run(e1_sessions, run_id)) == runs.RunCounts(fetched=2, inserted=1,
                                                                    updated=1)


# ---------------------------------------------------------------------------
# Foreign-key resolution
# ---------------------------------------------------------------------------


def test_children_resolve_same_run_parents_and_report_missing_ones(e1_sessions):
    run_id = make_run(e1_sessions)
    _commit(e1_sessions, run_id, "customers", [csv_row("customers")])
    result = _commit(e1_sessions, run_id, "deals", [
        csv_row("deals"),
        csv_row("deals", deal_id="DEAL-002", customer_id="CUST-404"),
        csv_row("deals", deal_id="DEAL-003", customer_id=""),
    ])
    assert result.counts == runs.RunCounts(fetched=3, inserted=3, warnings=1)
    assert result.unresolved_references == 1
    deals = {d.source_id: d for d in _all(e1_sessions, Deal)}
    parent = canonical_id("csv_demo", "customers", "CUST-001")
    assert (deals["DEAL-001"].customer_id, deals["DEAL-001"].customer_source_id) == (parent,
                                                                                    "CUST-001")
    assert (deals["DEAL-002"].customer_id, deals["DEAL-002"].customer_source_id) == (None,
                                                                                    "CUST-404")
    assert (deals["DEAL-003"].customer_id, deals["DEAL-003"].customer_source_id) == (None, None)
    (warning,) = _all(e1_sessions, IngestionError)
    detail = json.loads(warning.detail)
    assert (warning.severity, warning.error_code, warning.source_id) == (
        "WARNING", "UNRESOLVED_REFERENCE", "DEAL-002")
    assert (detail["source_key"], detail["field_name"], detail["record_index"]) == (
        "CUST-404", "customer_id", 1)


def test_quarantined_parent_does_not_resolve(e1_sessions):
    run_id = make_run(e1_sessions)
    _commit(e1_sessions, run_id, "customers",
            [csv_row("customers", customer_id="CUST-002", customer_name="")])
    result = _commit(e1_sessions, run_id, "projects",
                     [csv_row("projects", customer_id="CUST-002")])
    assert result.unresolved_references == 1
    assert _all(e1_sessions, Customer) == []


def test_parents_from_another_source_system_are_never_used(e1_sessions):
    run_id = make_run(e1_sessions)
    foreign = csv_canonical("customers", run_id).model_copy(update={
        "source_system": "rest_mock", "id": canonical_id("rest_mock", "customers", "CUST-001")})
    with e1_sessions.begin() as session:
        canonical_repo.upsert(session, "customers",
                              [canonical_repo.canonical_row("customers", foreign, {})])
    result = _commit(e1_sessions, run_id, "support_tickets", [csv_row("support_tickets")])
    assert result.unresolved_references == 1
    (ticket,) = _all(e1_sessions, SupportTicket)
    assert (ticket.customer_id, ticket.customer_source_id) == (None, "CUST-001")


def test_parent_lookup_uses_the_batch_source_system(e1_sessions):
    run_id = make_run(e1_sessions, source_system="rest_mock")
    csv_customer = csv_canonical("customers", run_id)
    rest_customer = csv_customer.model_copy(update={
        "source_system": "rest_mock", "id": canonical_id("rest_mock", "customers", "CUST-001")})
    with e1_sessions.begin() as session:
        canonical_repo.upsert(session, "customers", [
            canonical_repo.canonical_row("customers", customer, {})
            for customer in (csv_customer, rest_customer)])
    rest_deal = csv_canonical("deals", run_id).model_copy(update={
        "source_system": "rest_mock", "id": canonical_id("rest_mock", "deals", "DEAL-001")})
    gate = validate_canonical_batch("rest_mock", "deals", [rest_deal], run_id)
    result = commit_batch(e1_sessions, run_id=run_id, gate=gate,
                          raw_records=[{"id": "DEAL-001", "customerId": "CUST-001"}],
                          ingested_at=NOW)
    assert result.unresolved_references == 0
    (deal,) = _all(e1_sessions, Deal)
    assert (deal.source_system, deal.customer_id) == ("rest_mock", rest_customer.id)


def test_child_is_updated_when_its_parent_arrives_in_a_later_run(e1_sessions):
    first, second = make_run(e1_sessions), make_run(e1_sessions)
    assert _commit(e1_sessions, first, "deals", [csv_row("deals")]).unresolved_references == 1
    _commit(e1_sessions, second, "customers", [csv_row("customers")])
    result = _commit(e1_sessions, second, "deals", [csv_row("deals")])
    assert result.counts == runs.RunCounts(fetched=1, updated=1)
    (deal,) = _all(e1_sessions, Deal)
    assert deal.customer_id == canonical_id("csv_demo", "customers", "CUST-001")


def test_employees_persist_with_null_organization(e1_sessions):
    run_id = make_run(e1_sessions)
    _commit(e1_sessions, run_id, "organizations", [csv_row("organizations")])
    result = _commit(e1_sessions, run_id, "employees", [csv_row("employees")])
    assert result.counts == runs.RunCounts(fetched=1, inserted=1)
    (employee,) = _all(e1_sessions, Employee)
    assert employee.organization_id is None
    assert _count(e1_sessions, IngestionError) == 0


# ---------------------------------------------------------------------------
# Rollback and checkpoints
# ---------------------------------------------------------------------------


def _assert_nothing_persisted(sessions, run_id):
    for model in (Customer, SourceRecord, IngestionError, IngestionCursor):
        assert _count(sessions, model) == 0, model.__name__
    assert _run_counts(_run(sessions, run_id)) == runs.RunCounts()


def test_database_failure_rolls_back_the_whole_batch(e1_sessions):
    run_id = make_run(e1_sessions)
    rows = _customer_batch() + [csv_row("customers", customer_id="CUST-LONG",
                                        customer_name="N" * 300)]
    with pytest.raises(DataError):
        _commit(e1_sessions, run_id, "customers", rows, checkpoint=Checkpoint())
    _assert_nothing_persisted(e1_sessions, run_id)


def test_non_json_raw_payload_rolls_back_the_whole_batch(e1_sessions):
    run_id = make_run(e1_sessions)
    rows = [csv_row("customers", customer_id="CUST-005"),
            {**csv_row("customers"), "tags": {"vip"}}]
    with pytest.raises(raw.RawPayloadError):
        _commit(e1_sessions, run_id, "customers", rows, checkpoint=Checkpoint())
    _assert_nothing_persisted(e1_sessions, run_id)


def test_finished_run_rejects_further_batches_atomically(e1_sessions):
    run_id = make_run(e1_sessions)
    with e1_sessions.begin() as session:
        runs.finish_run(session, run_id, status=runs.RunStatus.FAILED, finished_at=NOW,
                        error_summary=None)
    with pytest.raises(runs.RunStateError):
        _commit(e1_sessions, run_id, "customers", [csv_row("customers")])
    assert _count(e1_sessions, Customer) == 0 and _count(e1_sessions, SourceRecord) == 0


def test_checkpoint_advances_only_with_a_checkpointed_batch(e1_sessions):
    run_id = make_run(e1_sessions)
    _commit(e1_sessions, run_id, "customers", [csv_row("customers")])
    assert _count(e1_sessions, IngestionCursor) == 0
    _commit(e1_sessions, run_id, "customers", [csv_row("customers", customer_id="CUST-002")],
            checkpoint=Checkpoint(last_cursor=None))
    (cursor,) = _all(e1_sessions, IngestionCursor)
    assert (cursor.source_system, cursor.source_entity, cursor.last_successful_run_id,
            cursor.last_cursor) == ("csv_demo", "customers", run_id, None)


def test_batch_arguments_are_validated_before_any_write(e1_sessions):
    run_id, other = make_run(e1_sessions), make_run(e1_sessions)
    rows = [csv_row("customers")]
    gate = validate_source_batch("csv_demo", "customers", rows, other, NOW)
    with pytest.raises(ValueError):
        commit_batch(e1_sessions, run_id=run_id, gate=gate, raw_records=rows, ingested_at=NOW)
    gate = validate_source_batch("csv_demo", "customers", rows, run_id, NOW)
    with pytest.raises(ValueError):
        commit_batch(e1_sessions, run_id=run_id, gate=gate, raw_records=rows * 2, ingested_at=NOW)
    with pytest.raises(ValueError):
        commit_batch(e1_sessions, run_id=run_id, gate=gate, raw_records=rows,
                     ingested_at=NOW.replace(tzinfo=None))
    assert _count(e1_sessions, SourceRecord) == 0


def test_error_entries_are_ordered_by_record_index_then_kind():
    rows = [csv_row("customers", email_address=""), None,
            csv_row("customers", customer_id="CUST-002", customer_name="")]
    gate = validate_source_batch("csv_demo", "customers", rows, uuid.uuid4(), NOW)
    entries = batch._error_entries(gate, ())
    assert [(e.severity, e.error_code) for e in entries] == [
        ("WARNING", "MISSING_RECOMMENDED_FIELD"), ("ERROR", "INVALID_RECORD"),
        ("ERROR", "REQUIRED_FIELD_MISSING")]


def test_valid_record_indices_follow_the_gate_partition():
    run_id = uuid.uuid4()
    gate = validate_source_batch("csv_demo", "customers", _customer_batch(), run_id, NOW)
    assert valid_record_indices(gate) == (0, 3)


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def _try_lock(connection, source_system, entity):
    key = func.hashtextextended(lock_key(source_system, entity), 0)
    return connection.scalar(select(func.pg_try_advisory_xact_lock(key)))


def test_commit_batch_waits_for_the_source_entity_lock(e1_sessions, e1_engine):
    run_id = make_run(e1_sessions)
    impatient = create_engine(e1_engine.url, connect_args={"options": "-c lock_timeout=200"})
    try:
        with e1_sessions.begin() as holder:
            acquire_batch_lock(holder, "csv_demo", "customers")
            with pytest.raises(OperationalError):
                _commit(sessionmaker(bind=impatient), run_id, "customers", [csv_row("customers")])
    finally:
        impatient.dispose()
    assert _count(e1_sessions, Customer) == 0 and _count(e1_sessions, SourceRecord) == 0


def test_batch_lock_is_exclusive_per_source_entity_until_commit(e1_sessions, e1_engine):
    with e1_sessions.begin() as holder:
        acquire_batch_lock(holder, "csv_demo", "customers")
        with e1_engine.connect() as other:
            assert _try_lock(other, "csv_demo", "customers") is False
            assert _try_lock(other, "csv_demo", "deals") is True
            assert _try_lock(other, "rest_mock", "customers") is True
            other.rollback()
    with e1_engine.connect() as other:
        assert _try_lock(other, "csv_demo", "customers") is True
        other.rollback()
