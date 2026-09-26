"""
M8's decision record against a real database (§0.7.5, §0.7.6).

brief_decisions is append-only twice over (OPEN-M8-4): the repository only
inserts, and the database rejects every UPDATE and DELETE, through the ORM
and through Core alike, by the trigger the M8 migration creates. Both foreign
keys RESTRICT (OPEN-M8-5), so a decided brief cannot be deleted, directly or
through its assessment's cascade.

The database's share of one linear chain per brief (OPEN-M8-6, §0.7.18
Q-M8-2) is the two partial unique indexes: one first decision per brief and
one successor per decision. Each is shown twice: a plain Core INSERT is
refused by the index itself, and insert_decision's ON CONFLICT DO NOTHING,
which names no conflict target, skips the row and returns None. The
concurrent cases hold the first transaction open until pg_stat_activity shows
the second one waiting on its lock, so the race is real, not sequential.

Parent rows are written with M7's own repositories, so every brief a decision
references is a row M7 could have written.

risk_queries.py's reads are proved here too, at the repository level
(§0.7.6, §0.7.16 Phase 3). Route 2's order is checked on a fixture built one
pair per ordering key, each pair decided by its own key and reversed by every
later one, so dropping, reversing or re-collating any key reorders it; and
on the corpus, where it must equal the order run_assessment returns, which is
order_reconciliations() order.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import delete, event, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import read_snapshot
from app.connectors import CsvConnector, CsvConnectorConfig
from app.core.database import Base
from app.core.logging import FIELDS_ATTRIBUTE
from app.decisions.approval import (
    MAX_ACTOR_CHARS,
    MAX_NOTE_CHARS,
    ApprovalError,
    Decision,
    DecisionConflict,
    DecisionConflictError,
    DecisionRecord,
    DecisionStatus,
    HashConflict,
    PayloadHashConflictError,
    UnknownBriefError,
    decision_history,
    decision_status,
    record_decision,
)
from app.decisions.assessment import run_assessment
from app.decisions.payload import payload_hash
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence.errors import ContractViolationError, IntelligenceError
from app.persistence.models import (
    BriefDecision,
    Customer,
    RiskAssessment,
    RiskBrief,
    RiskPosition,
)
from app.persistence.repositories.brief_decisions import NewDecision, insert_decision
from app.persistence.repositories.risk_assessments import (
    AssessmentRow,
    BriefRow,
    insert_assessment,
    insert_brief,
)
from app.persistence.repositories.risk_queries import (
    AssessmentListing,
    BriefReference,
    StoredAssessment,
    StoredPosition,
    brief_ids_for,
    briefs_for,
    decisions_for,
    get_assessment,
    get_brief,
    list_assessments,
    positions_for,
)

pytestmark = pytest.mark.integration

SOURCE_SYSTEM = "csv_demo"
PAYLOAD_HASH = "c" * 64
OTHER_PAYLOAD_HASH = "e" * 64
DECIDED_AT = datetime(2026, 9, 25, 9, 30, tzinfo=UTC)
LATER = DECIDED_AT + timedelta(hours=1)
APPEND_ONLY_MESSAGE = "brief_decisions is append-only"

#: PostgreSQL SQLSTATEs: restrict_violation (the trigger), foreign_key_violation, unique_violation.
RESTRICT_VIOLATION, FOREIGN_KEY_VIOLATION, UNIQUE_VIOLATION = "23001", "23503", "23505"
FIRST_DECISION_INDEX = "uq_brief_decisions_first_decision"
ONE_SUCCESSOR_INDEX = "uq_brief_decisions_one_successor"
BRIEF_KEY = "fk_brief_decisions_brief_id_risk_briefs"
PREDECESSOR_KEY = "fk_brief_decisions_supersedes_id_brief_decisions"

#: How long a concurrent test waits for the second transaction to block on the first.
LOCK_WAIT_ATTEMPTS, LOCK_WAIT_INTERVAL = 500, 0.02


@pytest.fixture
def sessions(e1_sessions: sessionmaker[Session]) -> sessionmaker[Session]:
    """A truncated database holding one customer, so M7's repositories can write under it."""
    with e1_sessions.begin() as session:
        session.add(Customer(
            source_system=SOURCE_SYSTEM, source_entity="customers", source_id="CUST-007",
            record_hash="d" * 64, ingestion_run_id=uuid.uuid4(), name="Decided Customer",
        ))
    return e1_sessions


def new_assessment(sessions, as_of: date = date(2026, 9, 18)) -> uuid.UUID:
    with sessions.begin() as session:
        identifier, _ = insert_assessment(session, AssessmentRow(
            customer_source_id="CUST-007", as_of=as_of, source_system=SOURCE_SYSTEM,
            layer1_fingerprint="a" * 64, rules_version=1, linker_version="1",
            band="CRITICAL", executive_worthy=True, signals={}, satisfied_rules=["R1"],
            ranking_key=[-3, -3, -5, "CUST-007"],
        ))
    return identifier


def new_brief(sessions, assessment_id: uuid.UUID, payload_hash: str = PAYLOAD_HASH,
              payload: object = None) -> uuid.UUID:
    with sessions.begin() as session:
        identifier, created = insert_brief(session, BriefRow(
            assessment_id=assessment_id, policy_version=1, template_version="1",
            decision_payload={"payload_version": 1} if payload is None else payload,
            payload_hash=payload_hash, narrative="the narrative",
        ))
    assert created
    return identifier


@pytest.fixture
def assessment_id(sessions) -> uuid.UUID:
    return new_assessment(sessions)


@pytest.fixture
def brief_id(sessions, assessment_id) -> uuid.UUID:
    return new_brief(sessions, assessment_id)


def decision(brief_id: uuid.UUID, **changes) -> NewDecision:
    row = NewDecision(
        brief_id=brief_id, payload_hash=PAYLOAD_HASH, actor="reviewer one", decision="APPROVED",
        note=None, decided_at=DECIDED_AT, supersedes_id=None,
    )
    return row._replace(**changes)


def record(sessions, row: NewDecision) -> uuid.UUID | None:
    with sessions.begin() as session:
        return insert_decision(session, row)


def core_insert(sessions, row: NewDecision, identifier: uuid.UUID | None = None) -> uuid.UUID:
    """A plain INSERT with no ON CONFLICT clause, so only the database decides."""
    identifier = uuid.uuid4() if identifier is None else identifier
    with sessions.begin() as session:
        session.execute(insert(BriefDecision).values(id=identifier, **row._asdict()))
    return identifier


def stored(sessions) -> list[tuple]:
    with sessions() as session:
        return [tuple(row) for row in session.execute(
            select(BriefDecision.id, BriefDecision.brief_id, BriefDecision.payload_hash,
                   BriefDecision.actor, BriefDecision.decision, BriefDecision.note,
                   BriefDecision.decided_at, BriefDecision.supersedes_id)
            .order_by(BriefDecision.decided_at, BriefDecision.id)).all()]


def count(sessions, model) -> int:
    with sessions() as session:
        return session.scalar(select(func.count()).select_from(model))


def all_counts(sessions) -> dict[str, int]:
    with sessions() as session:
        return {
            table.name: session.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.sorted_tables
        }


def assert_refused(caught: pytest.ExceptionInfo[IntegrityError], sqlstate: str,
                   constraint: str | None = None) -> None:
    diagnostics = caught.value.orig.diag
    assert caught.value.orig.pgcode == sqlstate
    if sqlstate == RESTRICT_VIOLATION:
        assert diagnostics.message_primary == APPEND_ONLY_MESSAGE
    else:
        assert diagnostics.constraint_name == constraint


# ---------------------------------------------------------------------------
# insert_decision writes one row, verbatim, and owns no transaction
# ---------------------------------------------------------------------------


def test_a_decision_is_inserted_and_its_new_id_returned(sessions, brief_id):
    identifier = record(sessions, decision(brief_id, note="looks right"))

    assert isinstance(identifier, uuid.UUID)
    assert stored(sessions) == [(identifier, brief_id, PAYLOAD_HASH, "reviewer one",
                                 "APPROVED", "looks right", DECIDED_AT, None)]


def test_every_column_is_stored_exactly_as_supplied(sessions, brief_id):
    """OPEN-M8-9: the actor is stored as supplied; decided_at keeps its instant and zone."""
    first = record(sessions, decision(brief_id))
    later = datetime(2026, 9, 25, 16, 5, 7, 123456, tzinfo=UTC)
    actor = "  Reviewer Two <not validated>  "
    second = record(sessions, decision(
        brief_id, actor=actor, decision="REJECTED", note="n" * 2000, decided_at=later,
        supersedes_id=first, payload_hash=OTHER_PAYLOAD_HASH))

    with sessions() as session:
        row = session.get(BriefDecision, second)
        assert (row.brief_id, row.payload_hash, row.actor, row.decision, row.note,
                row.supersedes_id) == (brief_id, OTHER_PAYLOAD_HASH, actor, "REJECTED",
                                       "n" * 2000, first)
        assert row.decided_at == later
        assert row.decided_at.utcoffset() == timedelta(0)


def test_the_repository_owns_no_transaction(sessions, brief_id):
    """The caller's rollback removes what the repository wrote."""
    with sessions() as session:
        assert insert_decision(session, decision(brief_id)) is not None
        session.rollback()

    assert count(sessions, BriefDecision) == 0


def test_a_decision_writes_one_row_and_changes_no_other_table(sessions, brief_id):
    before = all_counts(sessions)

    record(sessions, decision(brief_id))

    after = all_counts(sessions)
    assert after.pop("brief_decisions") == before.pop("brief_decisions") + 1
    assert after == before
    with sessions() as session:
        assert session.scalar(select(RiskBrief.status)) == "DRAFT"


def test_a_missing_brief_is_a_foreign_key_violation_not_a_skipped_row(sessions, brief_id):
    """ON CONFLICT covers unique indexes only; a missing parent still raises."""
    with pytest.raises(IntegrityError) as caught:
        record(sessions, decision(uuid.uuid4()))

    assert_refused(caught, FOREIGN_KEY_VIOLATION, BRIEF_KEY)
    assert count(sessions, BriefDecision) == 0


def test_a_missing_predecessor_is_a_foreign_key_violation(sessions, brief_id):
    record(sessions, decision(brief_id))

    with pytest.raises(IntegrityError) as caught:
        record(sessions, decision(brief_id, supersedes_id=uuid.uuid4()))

    assert_refused(caught, FOREIGN_KEY_VIOLATION, PREDECESSOR_KEY)
    assert count(sessions, BriefDecision) == 1


# ---------------------------------------------------------------------------
# Append-only: the database refuses UPDATE and DELETE (OPEN-M8-4)
# ---------------------------------------------------------------------------


@pytest.fixture
def decided(sessions, brief_id) -> uuid.UUID:
    return record(sessions, decision(brief_id, note="first"))


def test_an_orm_attribute_change_is_refused(sessions, decided):
    with sessions() as session:
        row = session.get(BriefDecision, decided)
        row.note = "rewritten"
        with pytest.raises(IntegrityError) as caught:
            session.flush()

    assert_refused(caught, RESTRICT_VIOLATION)
    assert [row[5] for row in stored(sessions)] == ["first"]


def test_an_orm_delete_is_refused(sessions, decided):
    with sessions() as session:
        session.delete(session.get(BriefDecision, decided))
        with pytest.raises(IntegrityError) as caught:
            session.flush()

    assert_refused(caught, RESTRICT_VIOLATION)
    assert count(sessions, BriefDecision) == 1


@pytest.mark.parametrize("values", [
    {"note": "rewritten"},
    {"decision": "REJECTED"},
    {"actor": "someone else"},
    {"decided_at": DECIDED_AT + timedelta(days=1)},
    {"payload_hash": OTHER_PAYLOAD_HASH},
], ids=lambda values: next(iter(values)))
def test_a_core_update_is_refused(sessions, decided, values):
    before = stored(sessions)

    with pytest.raises(IntegrityError) as caught, sessions.begin() as session:
        session.execute(update(BriefDecision).where(BriefDecision.id == decided).values(**values))

    assert_refused(caught, RESTRICT_VIOLATION)
    assert stored(sessions) == before


def test_a_core_delete_is_refused(sessions, decided):
    with pytest.raises(IntegrityError) as caught, sessions.begin() as session:
        session.execute(delete(BriefDecision))

    assert_refused(caught, RESTRICT_VIOLATION)
    assert count(sessions, BriefDecision) == 1


def test_an_unfiltered_update_is_refused_for_every_row(sessions, decided, brief_id):
    record(sessions, decision(
        brief_id, supersedes_id=decided, decision="REJECTED", decided_at=LATER))
    before = stored(sessions)

    with pytest.raises(IntegrityError) as caught, sessions.begin() as session:
        session.execute(update(BriefDecision).values(note=None))

    assert_refused(caught, RESTRICT_VIOLATION)
    assert stored(sessions) == before


def test_truncate_is_not_blocked(sessions, decided):
    """§0.7.17's recorded limitation, which the test harness relies on between tests."""
    with sessions.begin() as session:
        session.execute(text("TRUNCATE TABLE brief_decisions"))

    assert count(sessions, BriefDecision) == 0


# ---------------------------------------------------------------------------
# RESTRICT: a decided brief cannot disappear (OPEN-M8-5)
# ---------------------------------------------------------------------------


def test_a_decided_brief_cannot_be_deleted(sessions, decided, brief_id):
    with pytest.raises(IntegrityError) as caught, sessions.begin() as session:
        session.execute(delete(RiskBrief).where(RiskBrief.id == brief_id))

    assert_refused(caught, FOREIGN_KEY_VIOLATION, BRIEF_KEY)
    assert count(sessions, RiskBrief) == 1


def test_a_decided_briefs_assessment_cannot_be_deleted_through_its_cascade(
        sessions, decided, assessment_id):
    before = all_counts(sessions)

    with pytest.raises(IntegrityError) as caught, sessions.begin() as session:
        session.execute(delete(RiskAssessment).where(RiskAssessment.id == assessment_id))

    assert_refused(caught, FOREIGN_KEY_VIOLATION, BRIEF_KEY)
    assert all_counts(sessions) == before


def test_an_undecided_brief_is_still_deleted_by_its_assessments_cascade(sessions, assessment_id):
    """The control: RESTRICT refuses only because a decision references the brief."""
    new_brief(sessions, assessment_id)
    with sessions.begin() as session:
        session.execute(delete(RiskAssessment).where(RiskAssessment.id == assessment_id))

    assert count(sessions, RiskBrief) == 0


# ---------------------------------------------------------------------------
# The partial unique indexes, sequentially (OPEN-M8-6)
# ---------------------------------------------------------------------------


def test_the_database_refuses_a_second_first_decision(sessions, decided, brief_id):
    with pytest.raises(IntegrityError) as caught:
        core_insert(sessions, decision(brief_id, decision="REJECTED"))

    assert_refused(caught, UNIQUE_VIOLATION, FIRST_DECISION_INDEX)
    assert count(sessions, BriefDecision) == 1


def test_insert_decision_skips_a_second_first_decision(sessions, decided, brief_id):
    assert record(sessions, decision(brief_id, decision="REJECTED")) is None
    assert [row[0] for row in stored(sessions)] == [decided]


def test_each_brief_has_its_own_first_decision(sessions, decided, assessment_id):
    other = new_brief(sessions, assessment_id, OTHER_PAYLOAD_HASH)

    assert record(sessions, decision(other, payload_hash=OTHER_PAYLOAD_HASH)) is not None
    assert count(sessions, BriefDecision) == 2


def test_the_database_refuses_a_second_successor(sessions, decided, brief_id):
    record(sessions, decision(
        brief_id, supersedes_id=decided, decision="REJECTED", decided_at=LATER))

    with pytest.raises(IntegrityError) as caught:
        core_insert(sessions, decision(brief_id, supersedes_id=decided, decided_at=LATER))

    assert_refused(caught, UNIQUE_VIOLATION, ONE_SUCCESSOR_INDEX)
    assert count(sessions, BriefDecision) == 2


def test_insert_decision_skips_a_second_successor(sessions, decided, brief_id):
    successor = record(sessions, decision(
        brief_id, supersedes_id=decided, decision="REJECTED", decided_at=LATER))

    assert record(sessions, decision(brief_id, supersedes_id=decided, decided_at=LATER)) is None
    assert [row[0] for row in stored(sessions)] == [decided, successor]


def test_a_linear_chain_is_accepted(sessions, decided, brief_id):
    second = record(sessions, decision(
        brief_id, supersedes_id=decided, decision="REJECTED", decided_at=LATER))
    third = record(sessions, decision(
        brief_id, supersedes_id=second, decided_at=DECIDED_AT + timedelta(hours=2)))

    assert [(row[0], row[7]) for row in stored(sessions)] == [
        (decided, None), (second, decided), (third, second)]


# ---------------------------------------------------------------------------
# The partial unique indexes, concurrently (OPEN-M8-6)
# ---------------------------------------------------------------------------


def _wait_until_blocked(sessions, pid: int) -> None:
    """Return once the backend `pid` is waiting on a lock; fail if it never does."""
    query = text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid")
    for _ in range(LOCK_WAIT_ATTEMPTS):
        with sessions() as observer:
            if observer.execute(query, {"pid": pid}).scalar_one_or_none() == "Lock":
                return
        time.sleep(LOCK_WAIT_INTERVAL)
    pytest.fail(f"backend {pid} never waited on a lock")


def race(sessions, first: Callable[[Session], Any], second: Callable[[Session], Any], *,
         winner_commits: bool = True) -> tuple[Any, dict[str, Any]]:
    """
    Run `first` in one open transaction, then `second` in another, which must
    block on the first's index entry. The first then commits (or rolls back)
    and the second finishes: it commits, or it rolls back if it raised.
    Returns the first's result and the second's outcome, {"result": ...} or
    {"error": ...}.
    """
    winner, loser = sessions(), sessions()
    outcome: dict[str, Any] = {}
    try:
        won = first(winner)
        pid = loser.execute(select(func.pg_backend_pid())).scalar_one()

        def contend() -> None:
            try:
                outcome["result"] = second(loser)
                loser.commit()
            except Exception as error:  # returned to the test's own thread
                loser.rollback()
                outcome["error"] = error

        thread = threading.Thread(target=contend)
        thread.start()
        _wait_until_blocked(sessions, pid)
        assert not outcome, "the second transaction did not wait for the first"
        if winner_commits:
            winner.commit()
        else:
            winner.rollback()
        thread.join(timeout=LOCK_WAIT_ATTEMPTS * LOCK_WAIT_INTERVAL)
        assert not thread.is_alive()
    finally:
        winner.close()
        loser.close()
    return won, outcome


def inserting(row: NewDecision) -> Callable[[Session], uuid.UUID | None]:
    return lambda session: insert_decision(session, row)


def test_two_concurrent_first_decisions_leave_exactly_one(sessions, brief_id):
    won, outcome = race(sessions, inserting(decision(brief_id)),
                        inserting(decision(brief_id, decision="REJECTED")))

    assert won is not None and outcome == {"result": None}
    assert [(row[0], row[4]) for row in stored(sessions)] == [(won, "APPROVED")]


def test_two_concurrent_successors_of_one_head_leave_exactly_one(sessions, decided, brief_id):
    won, outcome = race(
        sessions,
        inserting(decision(brief_id, supersedes_id=decided, decision="REJECTED", decided_at=LATER)),
        inserting(decision(brief_id, supersedes_id=decided, decided_at=LATER)))

    assert won is not None and outcome == {"result": None}
    assert [(row[0], row[7]) for row in stored(sessions)] == [(decided, None), (won, decided)]


def test_a_first_decision_that_rolls_back_does_not_block_the_other(sessions, brief_id):
    """The index waits on an uncommitted row; it refuses only a committed one."""
    won, outcome = race(sessions, inserting(decision(brief_id)),
                        inserting(decision(brief_id, decision="REJECTED")), winner_commits=False)

    lost = outcome["result"]
    assert won is not None and lost is not None
    assert [(row[0], row[4]) for row in stored(sessions)] == [(lost, "REJECTED")]


# ---------------------------------------------------------------------------
# record_decision: decisions on an immutable stored brief (§0.7.7)
# ---------------------------------------------------------------------------


#: A stored payload, and the hash M7's own function gives it.
PAYLOAD = {"payload_version": 1, "customer": {"id": "CUST-007"}, "band": "CRITICAL"}
DIGEST = payload_hash(PAYLOAD)
#: Canary strings: each must reach its column and never a log line or an error message.
ACTOR = "canary-actor-5d1e@example.invalid"
NOTE = "canary-note-8b2c: approved against the DOC-006 renewal clause"
EVENTS_LOGGER = "app.decisions.approval"


@pytest.fixture
def decidable(sessions, assessment_id) -> uuid.UUID:
    """A brief whose stored payload re-hashes to its payload_hash, as every M7 brief does."""
    return new_brief(sessions, assessment_id, DIGEST, PAYLOAD)


def decide(sessions, brief_id: uuid.UUID, **changes) -> DecisionRecord:
    arguments: dict[str, Any] = {
        "brief_id": brief_id, "payload_hash": DIGEST, "actor": ACTOR,
        "decision": Decision.APPROVED, "note": NOTE, "supersedes_id": None,
        "decided_at": DECIDED_AT,
    }
    arguments.update(changes)
    with sessions.begin() as session:
        return record_decision(session, **arguments)


def history(sessions, brief_id: uuid.UUID) -> tuple[DecisionRecord, ...]:
    with sessions() as session:
        return decision_history(session, brief_id)


def events(caplog) -> list[tuple[int, str, dict]]:
    return [(record.levelno, record.getMessage().split(" ", 1)[0],
             getattr(record, FIELDS_ATTRIBUTE))
            for record in caplog.records if record.name == EVENTS_LOGGER]


def refused(sessions, caplog, error: type[Exception], brief_id: uuid.UUID, **changes):
    """Record a decision that must fail: nothing is written and nothing is emitted."""
    caplog.set_level(logging.INFO)
    before = all_counts(sessions)
    with pytest.raises(error) as caught:
        decide(sessions, brief_id, **changes)
    assert all_counts(sessions) == before
    assert events(caplog) == []
    for line in caplog.messages:
        assert ACTOR not in line and NOTE not in line
    assert ACTOR not in str(caught.value) and NOTE not in str(caught.value)
    return caught.value


def test_a_first_approval_is_recorded_exactly_as_supplied(sessions, decidable):
    record = decide(sessions, decidable)

    assert isinstance(record, DecisionRecord)
    assert (record.brief_id, record.payload_hash, record.actor, record.decision, record.note,
            record.decided_at, record.supersedes_id) == (
        decidable, DIGEST, ACTOR, Decision.APPROVED, NOTE, DECIDED_AT, None)
    assert stored(sessions) == [(record.id, decidable, DIGEST, ACTOR, "APPROVED", NOTE,
                                 DECIDED_AT, None)]
    assert history(sessions, decidable) == (record,)


def test_a_first_rejection_is_a_durable_row_and_heads_the_history(sessions, decidable):
    """Criterion 9: a rejection is recorded, not discarded."""
    record = decide(sessions, decidable, decision=Decision.REJECTED, note=None)

    assert [row[4] for row in stored(sessions)] == ["REJECTED"]
    assert history(sessions, decidable)[-1] == record
    assert decision_status(history(sessions, decidable)) is DecisionStatus.REJECTED


def test_a_plain_string_decision_is_accepted_and_returned_as_the_vocabulary(sessions, decidable):
    record = decide(sessions, decidable, decision="REJECTED")

    assert record.decision is Decision.REJECTED


def test_a_successor_naming_the_head_extends_the_history(sessions, decidable):
    first = decide(sessions, decidable, decision=Decision.REJECTED)
    second = decide(sessions, decidable, supersedes_id=first.id, decided_at=LATER)

    assert second.supersedes_id == first.id
    assert history(sessions, decidable) == (first, second)
    assert decision_status(history(sessions, decidable)) is DecisionStatus.APPROVED


def test_a_decision_may_repeat_its_predecessors_value(sessions, decidable):
    """§0.7.7: APPROVED after APPROVED is allowed."""
    first = decide(sessions, decidable)
    second = decide(sessions, decidable, supersedes_id=first.id, decided_at=LATER)

    assert [record.decision for record in history(sessions, decidable)] == [
        Decision.APPROVED, Decision.APPROVED]
    assert history(sessions, decidable)[-1] == second


def test_the_actor_and_note_are_stored_unvalidated_at_their_bounds(sessions, decidable):
    """OPEN-M8-9: 255 characters of anything, never checked as an email; a 2000-character note."""
    actor, note = "A" * MAX_ACTOR_CHARS, "n" * MAX_NOTE_CHARS
    record = decide(sessions, decidable, actor=actor, note=note)

    assert (MAX_ACTOR_CHARS, MAX_NOTE_CHARS) == (255, 2000)
    assert stored(sessions)[0][3:6] == (actor, "APPROVED", note)
    assert (record.actor, record.note) == (actor, note)


def test_decided_at_is_the_callers_instant_in_any_zone(sessions, decidable):
    """X7: the argument is recorded; no clock is read. The chain, not the time, orders."""
    elsewhere = datetime(2026, 9, 25, 15, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    record = decide(sessions, decidable, decided_at=elsewhere)

    (stored_record,) = history(sessions, decidable)
    assert record.decided_at == stored_record.decided_at == elsewhere
    assert stored_record.decided_at.utcoffset() is not None


def test_a_decision_writes_one_row_and_never_touches_a_brief(sessions, decidable):
    """Criteria 10 and 12: one brief_decisions row; the brief, and every other table, unchanged."""
    before_counts = all_counts(sessions)
    with sessions() as session:
        before = tuple(session.execute(select(RiskBrief.__table__)).one())

    decide(sessions, decidable, decision=Decision.REJECTED)

    after_counts = all_counts(sessions)
    assert after_counts.pop("brief_decisions") == before_counts.pop("brief_decisions") + 1
    assert after_counts == before_counts
    with sessions() as session:
        after = tuple(session.execute(select(RiskBrief.__table__)).one())
    assert after == before
    assert after[-1] == "DRAFT"


# ---------------------------------------------------------------------------
# Refusals, in §0.7.7's step order; each writes nothing and emits nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("changes", [
    {"decided_at": datetime(2026, 9, 25, 9, 30)},
    {"actor": ""},
    {"actor": "A" * 256},
    {"note": "n" * 2001},
    {"decision": "MAYBE"},
    {"decision": None},
], ids=["naive-decided-at", "empty-actor", "long-actor", "long-note", "unknown-decision",
        "no-decision"])
def test_step_0_refuses_arguments_the_route_would_never_send(sessions, caplog, decidable, changes):
    error = refused(sessions, caplog, ContractViolationError, decidable, **changes)

    assert type(error) is ContractViolationError


def test_step_0_runs_before_the_brief_is_read(sessions, caplog):
    refused(sessions, caplog, ContractViolationError, uuid.uuid4(), actor="")


def test_step_1_an_unknown_brief(sessions, caplog, decidable):
    error = refused(sessions, caplog, UnknownBriefError, uuid.uuid4())

    assert str(error) == "risk brief does not exist"
    assert isinstance(error, ApprovalError) and isinstance(error, IntelligenceError)


def test_step_2_a_request_hash_that_is_not_the_briefs(sessions, caplog, decidable):
    """Criterion 7: a stale hash is refused, and no row is written."""
    error = refused(sessions, caplog, PayloadHashConflictError, decidable,
                    payload_hash=payload_hash({"payload_version": 1}))

    assert error.reason is HashConflict.REQUEST_HASH_MISMATCH
    assert str(error) == "payload_hash is not the brief's payload hash"


def corrupt(sessions, brief_id: uuid.UUID) -> None:
    """Alter the stored payload in the isolated test database, leaving its hash column."""
    with sessions.begin() as session:
        session.execute(update(RiskBrief).where(RiskBrief.id == brief_id)
                        .values(decision_payload={**PAYLOAD, "band": "NONE"}))


def test_step_3_a_stored_payload_that_no_longer_re_hashes(sessions, caplog, decidable):
    """Criterion 8: the stored JSONB must re-hash to its own column, through M7's function."""
    corrupt(sessions, decidable)

    error = refused(sessions, caplog, PayloadHashConflictError, decidable)

    assert error.reason is HashConflict.STORED_PAYLOAD_MISMATCH
    assert str(error) == "the brief's stored decision payload does not re-hash to its payload hash"


def test_step_2_runs_before_step_3(sessions, caplog, decidable):
    corrupt(sessions, decidable)

    error = refused(sessions, caplog, PayloadHashConflictError, decidable, payload_hash="0" * 64)

    assert error.reason is HashConflict.REQUEST_HASH_MISMATCH


def test_step_3_runs_before_supersession(sessions, caplog, decidable):
    corrupt(sessions, decidable)

    error = refused(sessions, caplog, PayloadHashConflictError, decidable,
                    supersedes_id=uuid.uuid4())

    assert error.reason is HashConflict.STORED_PAYLOAD_MISMATCH


def test_step_5_a_later_decision_must_supersede(sessions, caplog, decidable):
    decide(sessions, decidable)

    error = refused(sessions, caplog, DecisionConflictError, decidable, decided_at=LATER)

    assert error.reason is DecisionConflict.SUPERSEDES_REQUIRED


def test_step_5_a_first_decision_cannot_supersede(sessions, caplog, decidable):
    """A supersedes_id on a brief with no decision names nothing on it."""
    error = refused(sessions, caplog, DecisionConflictError, decidable, supersedes_id=uuid.uuid4())

    assert error.reason is DecisionConflict.PREDECESSOR_NOT_ON_BRIEF


def test_step_5_a_missing_predecessor(sessions, caplog, decidable):
    decide(sessions, decidable)

    error = refused(sessions, caplog, DecisionConflictError, decidable,
                    supersedes_id=uuid.uuid4(), decided_at=LATER)

    assert error.reason is DecisionConflict.PREDECESSOR_NOT_ON_BRIEF


def test_step_5_another_briefs_decision(sessions, caplog, decidable, assessment_id):
    """Same-brief is the application's check: the plain self-FK cannot express it (Q-M8-2)."""
    payload = {**PAYLOAD, "band": "HIGH"}
    other = new_brief(sessions, assessment_id, payload_hash(payload), payload)
    foreign = decide(sessions, other, payload_hash=payload_hash(payload))
    decide(sessions, decidable)

    error = refused(sessions, caplog, DecisionConflictError, decidable,
                    supersedes_id=foreign.id, decided_at=LATER)

    assert error.reason is DecisionConflict.PREDECESSOR_NOT_ON_BRIEF


def test_step_5_a_fork_is_refused_as_not_the_head(sessions, caplog, decidable):
    """Criterion 6, sequentially: superseding a non-current decision."""
    first = decide(sessions, decidable)
    decide(sessions, decidable, supersedes_id=first.id, decision=Decision.REJECTED,
           decided_at=LATER)

    error = refused(sessions, caplog, DecisionConflictError, decidable,
                    supersedes_id=first.id, decided_at=LATER)

    assert error.reason is DecisionConflict.PREDECESSOR_NOT_HEAD


def test_every_refusal_message_is_fixed_per_reason():
    """§0.7.7: never the actor, the note, payload text or an email; nothing interpolated."""
    assert {reason: str(DecisionConflictError(reason)) for reason in DecisionConflict} == {
        DecisionConflict.SUPERSEDES_REQUIRED:
            "the brief already has a decision, so supersedes_id must name its current head",
        DecisionConflict.PREDECESSOR_NOT_ON_BRIEF: "supersedes_id names no decision on this brief",
        DecisionConflict.PREDECESSOR_NOT_HEAD: "supersedes_id is not the brief's current head",
        DecisionConflict.CONCURRENT_DECISION:
            "a concurrent decision extended the brief's history first",
    }
    assert {reason: str(PayloadHashConflictError(reason)) for reason in HashConflict} == {
        HashConflict.REQUEST_HASH_MISMATCH: "payload_hash is not the brief's payload hash",
        HashConflict.STORED_PAYLOAD_MISMATCH:
            "the brief's stored decision payload does not re-hash to its payload hash",
    }


# ---------------------------------------------------------------------------
# Step 6: concurrent decisions (criterion 6, and OPEN-M8-6 under concurrency)
# ---------------------------------------------------------------------------


def deciding(brief_id: uuid.UUID, **changes) -> Callable[[Session], DecisionRecord]:
    arguments: dict[str, Any] = {
        "brief_id": brief_id, "payload_hash": DIGEST, "actor": ACTOR,
        "decision": Decision.APPROVED, "note": None, "supersedes_id": None,
        "decided_at": DECIDED_AT,
    }
    arguments.update(changes)
    return lambda session: record_decision(session, **arguments)


def test_two_concurrent_first_decisions_one_is_refused_as_concurrent(sessions, caplog, decidable):
    caplog.set_level(logging.INFO)

    won, outcome = race(sessions, deciding(decidable),
                        deciding(decidable, decision=Decision.REJECTED))

    error = outcome["error"]
    assert isinstance(error, DecisionConflictError)
    assert error.reason is DecisionConflict.CONCURRENT_DECISION
    assert history(sessions, decidable) == (won,)
    assert [name for _, name, _ in events(caplog)] == ["vs01.decision_recorded"]


def test_two_concurrent_successors_one_is_refused_as_concurrent(sessions, caplog, decidable):
    head = decide(sessions, decidable)
    caplog.set_level(logging.INFO)

    won, outcome = race(
        sessions,
        deciding(decidable, supersedes_id=head.id, decision=Decision.REJECTED, decided_at=LATER),
        deciding(decidable, supersedes_id=head.id, decided_at=LATER))

    assert outcome["error"].reason is DecisionConflict.CONCURRENT_DECISION
    assert history(sessions, decidable) == (head, won)
    # Captured from the race on: the winner's event only, none for the loser.
    assert [name for _, name, _ in events(caplog)] == ["vs01.decision_recorded"]


# ---------------------------------------------------------------------------
# risk_queries: the two reads approval.py uses (§0.7.6)
# ---------------------------------------------------------------------------


def test_get_brief_returns_every_column_exactly_as_stored(sessions, decidable, assessment_id):
    with sessions() as session:
        row = get_brief(session, decidable)
        missing = get_brief(session, uuid.uuid4())

    assert missing is None
    assert row is not None
    assert row._fields == tuple(column.name for column in RiskBrief.__table__.columns)
    assert tuple(row) == (decidable, assessment_id, 1, "1", PAYLOAD, DIGEST, "the narrative",
                          "DRAFT")


def test_decisions_for_returns_every_column_of_the_briefs_own_rows(sessions, decidable,
                                                                   assessment_id):
    other = new_brief(sessions, assessment_id, OTHER_PAYLOAD_HASH)
    core_insert(sessions, decision(other, payload_hash=OTHER_PAYLOAD_HASH))
    record = decide(sessions, decidable)

    with sessions() as session:
        rows = decisions_for(session, decidable)
        none = decisions_for(session, uuid.uuid4())

    assert none == []
    assert [row._fields for row in rows] == [
        tuple(column.name for column in BriefDecision.__table__.columns)]
    assert [tuple(row) for row in rows] == [
        (record.id, decidable, DIGEST, ACTOR, "APPROVED", NOTE, DECIDED_AT, None)]


def test_the_reads_write_nothing(sessions, decidable):
    decide(sessions, decidable)
    before = all_counts(sessions)
    with sessions() as session:
        get_brief(session, decidable)
        decisions_for(session, decidable)
        decision_history(session, decidable)
        session.commit()

    assert all_counts(sessions) == before


# ---------------------------------------------------------------------------
# decision_history and decision_status (OPEN-M8-6, OPEN-M8-8)
# ---------------------------------------------------------------------------


def test_the_history_of_an_undecided_brief_is_empty_and_pending(sessions, decidable):
    assert history(sessions, decidable) == ()
    assert decision_status(()) is DecisionStatus.PENDING


def test_the_history_of_a_missing_brief_is_refused(sessions):
    with pytest.raises(UnknownBriefError):
        history(sessions, uuid.uuid4())


def test_the_chain_orders_the_history_not_the_id_or_the_time(sessions, decidable):
    """
    decisions_for returns rows by id; the chain is rebuilt from supersedes_id.
    Here the ids and the times both run against the chain.
    """
    first = core_insert(sessions, decision(decidable, payload_hash=DIGEST, decided_at=LATER),
                        uuid.UUID(int=(1 << 128) - 1))
    second = core_insert(sessions, decision(decidable, payload_hash=DIGEST, supersedes_id=first,
                                            decision="REJECTED"), uuid.UUID(int=1))
    with sessions() as session:
        assert [row.id for row in decisions_for(session, decidable)] == [second, first]

    assert [record.id for record in history(sessions, decidable)] == [first, second]
    assert decision_status(history(sessions, decidable)) is DecisionStatus.REJECTED


@pytest.mark.parametrize(("decisions", "status"), [
    ((), DecisionStatus.PENDING),
    ((Decision.APPROVED,), DecisionStatus.APPROVED),
    ((Decision.REJECTED,), DecisionStatus.REJECTED),
    ((Decision.APPROVED, Decision.REJECTED), DecisionStatus.REJECTED),
    ((Decision.REJECTED, Decision.APPROVED), DecisionStatus.APPROVED),
], ids=["empty", "approved", "rejected", "approved-then-rejected", "rejected-then-approved"])
def test_the_status_is_the_heads_decision_or_pending(decisions, status):
    """OPEN-M8-8: derived from the chain alone, and never from risk_briefs.status."""
    records = tuple(
        DecisionRecord(id=uuid.uuid4(), brief_id=uuid.uuid4(), payload_hash=DIGEST, actor=ACTOR,
                       decision=value, note=None, decided_at=DECIDED_AT, supersedes_id=None)
        for value in decisions)

    assert decision_status(records) is status


def test_rows_chained_across_briefs_are_not_one_linear_history(sessions, decidable, assessment_id):
    """Written around approval.py: a row on this brief superseding another brief's decision."""
    other = new_brief(sessions, assessment_id, OTHER_PAYLOAD_HASH)
    foreign = core_insert(sessions, decision(other, payload_hash=OTHER_PAYLOAD_HASH))
    core_insert(sessions, decision(decidable, payload_hash=DIGEST))
    core_insert(sessions, decision(decidable, payload_hash=DIGEST, supersedes_id=foreign))

    with pytest.raises(ContractViolationError, match="one linear chain"):
        history(sessions, decidable)


def test_a_history_with_no_first_decision_is_not_linear(sessions, decidable, assessment_id):
    other = new_brief(sessions, assessment_id, OTHER_PAYLOAD_HASH)
    foreign = core_insert(sessions, decision(other, payload_hash=OTHER_PAYLOAD_HASH))
    core_insert(sessions, decision(decidable, payload_hash=DIGEST, supersedes_id=foreign))

    with pytest.raises(ContractViolationError, match="one linear chain"):
        history(sessions, decidable)


def test_a_self_superseding_row_is_not_linear(sessions, decidable):
    core_insert(sessions, decision(decidable, payload_hash=DIGEST))
    looped = uuid.uuid4()
    core_insert(sessions, decision(decidable, payload_hash=DIGEST, supersedes_id=looped), looped)

    with pytest.raises(ContractViolationError, match="one linear chain"):
        history(sessions, decidable)


def test_a_stored_decision_outside_the_vocabulary_is_refused(sessions, decidable):
    core_insert(sessions, decision(decidable, payload_hash=DIGEST, decision="MAYBE"))

    with pytest.raises(ContractViolationError, match="neither APPROVED nor REJECTED"):
        history(sessions, decidable)


# ---------------------------------------------------------------------------
# The event (§0.7.10)
# ---------------------------------------------------------------------------


def test_each_recorded_decision_emits_one_event_with_its_three_fields_in_order(
        sessions, caplog, decidable):
    caplog.set_level(logging.INFO)

    first = decide(sessions, decidable)
    decide(sessions, decidable, supersedes_id=first.id, decision=Decision.REJECTED,
           decided_at=LATER)

    emitted = events(caplog)
    assert emitted == [
        (logging.INFO, "vs01.decision_recorded",
         {"payload_hash": DIGEST, "decision": "APPROVED", "supersedes": False}),
        (logging.INFO, "vs01.decision_recorded",
         {"payload_hash": DIGEST, "decision": "REJECTED", "supersedes": True}),
    ]
    assert [list(fields) for _, _, fields in emitted] == [
        ["payload_hash", "decision", "supersedes"]] * 2
    assert [type(fields["decision"]) for _, _, fields in emitted] == [str, str]


def test_no_log_line_carries_the_actor_or_the_note(sessions, caplog, decidable):
    caplog.set_level(logging.DEBUG)

    first = decide(sessions, decidable)
    decide(sessions, decidable, supersedes_id=first.id, decided_at=LATER)
    with sessions() as session:
        decision_history(session, decidable)

    assert caplog.records
    for record in caplog.records:
        rendered = record.getMessage() + repr(getattr(record, FIELDS_ATTRIBUTE, {}))
        assert ACTOR not in rendered and NOTE not in rendered
        assert "@" not in rendered


def test_reading_a_history_emits_nothing(sessions, caplog, decidable):
    decide(sessions, decidable)
    caplog.set_level(logging.INFO)

    history(sessions, decidable)

    assert events(caplog) == []


# ---------------------------------------------------------------------------
# A real brief: CUST-007's, as M7 wrote it over the corpus
# ---------------------------------------------------------------------------


MERIDIAN_PAYLOAD_HASH = "e93c29cfb6094284d7ea6fe84bf966ad0b40995fccdc4e2a671b502a7f16c946"
DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo"


@pytest.fixture
def corpus(e1_sessions: sessionmaker[Session]) -> tuple[sessionmaker[Session], dict[str, Any]]:
    """The clean full-dataset path, assessed at ACCEPTANCE_AS_OF: the three briefed customers."""
    config = CsvConnectorConfig.from_yaml(
        DEMO_DIR.parents[1] / "config" / "connectors" / "csv_demo.yaml")
    config.data_directory = str(DEMO_DIR)
    assert run_ingestion(CsvConnector(config), e1_sessions, IngestionRequest()).counts.rejected == 0
    with e1_sessions.begin() as session:
        results = run_assessment(session, as_of=date(2026, 9, 18))
    return e1_sessions, {result.payload_hash: result.brief_id for result in results
                         if result.brief_id is not None}


def test_a_decision_on_meridians_real_brief(corpus):
    """Criterion 8 on M7's own payload: it re-hashes to e93c29cf..., and nothing of M7 changes."""
    sessions, briefs = corpus
    brief_id = briefs[MERIDIAN_PAYLOAD_HASH]
    before = all_counts(sessions)
    with sessions() as session:
        stored_brief = get_brief(session, brief_id)
    assert stored_brief is not None
    assert payload_hash(stored_brief.decision_payload) == MERIDIAN_PAYLOAD_HASH

    record = decide(sessions, brief_id, payload_hash=MERIDIAN_PAYLOAD_HASH,
                    decision=Decision.REJECTED)

    after = all_counts(sessions)
    assert after.pop("brief_decisions") == before.pop("brief_decisions") + 1
    assert after == before
    with sessions() as session:
        assert get_brief(session, brief_id) == stored_brief
    assert decision_status(history(sessions, brief_id)) is DecisionStatus.REJECTED
    assert record.payload_hash == MERIDIAN_PAYLOAD_HASH


def test_another_customers_hash_is_stale_for_meridians_brief(corpus, caplog):
    sessions, briefs = corpus
    brief_id = briefs[MERIDIAN_PAYLOAD_HASH]
    (other,) = [digest for digest in briefs if digest.startswith("08c99ced")]

    error = refused(sessions, caplog, PayloadHashConflictError, brief_id, payload_hash=other)

    assert error.reason is HashConflict.REQUEST_HASH_MISMATCH


# ---------------------------------------------------------------------------
# risk_queries: route 2's listing (§0.7.6, §0.7.8 OPEN-M8-13)
# ---------------------------------------------------------------------------


EARLIER, LATEST = date(2026, 9, 18), date(2026, 9, 19)


def assessment_values(identifier: uuid.UUID, **changes) -> dict[str, Any]:
    """One risk_assessments row as a Core insert writes it; its customer is NULL unless named."""
    values: dict[str, Any] = {
        "id": identifier, "customer_id": None, "as_of": EARLIER, "source_system": SOURCE_SYSTEM,
        "layer1_fingerprint": "a" * 64, "rules_version": 1, "linker_version": "1",
        "band": "WATCH", "executive_worthy": False, "signals": {"open_ticket_count": 1},
        "satisfied_rules": ["W1"], "ranking_key": [-1, 0, 0, "CUST-001"],
    }
    values.update(changes)
    return values


def core_assessments(sessions, rows: list[dict[str, Any]]) -> None:
    with sessions.begin() as session:
        session.execute(insert(RiskAssessment), rows)


def new_customer(sessions, source_id: str) -> uuid.UUID:
    identifier = uuid.uuid4()
    with sessions.begin() as session:
        session.add(Customer(
            id=identifier, source_system=SOURCE_SYSTEM, source_entity="customers",
            source_id=source_id, record_hash="d" * 64, ingestion_run_id=uuid.uuid4(),
            name=f"Customer {source_id}",
        ))
    return identifier


def listed(sessions, *, as_of: date | None = None, band: str | None = None,
           executive_worthy: bool | None = None, limit: int = 500, offset: int = 0):
    with read_snapshot(sessions) as session:
        return list_assessments(session, as_of=as_of, band=band,
                                executive_worthy=executive_worthy, limit=limit, offset=offset)


#: Route 2's keys above `id`, each with the value that sorts first and the one that sorts
#: second. A string pair is an upper-case value and a lower-case one: by code point, as
#: COLLATE "C" and Python compare, "B" (U+0042) precedes "a" (U+0061), and a locale collation
#: puts them the other way round. An integer pair is two negatives, whose text sorts the other
#: way round from their value ("-1" < "-3", but -3 < -1), as a ranking key's components are.
ORDER_KEYS: tuple[tuple[str, Any, Any], ...] = (
    ("as_of", LATEST, EARLIER),
    ("source_system", "B_source", "a_source"),
    ("layer1_fingerprint", "B" * 64, "a" * 64),
    ("rules_version", 2, 10),
    ("linker_version", "B1", "a1"),
    ("band_rank", -3, -1),
    ("s8", -4, -2),
    ("s4", -7, -5),
    ("source_id", "CUST-B07", "CUST-a07"),
)
ORDER_NAMES = tuple(name for name, _, _ in ORDER_KEYS)
#: The id tie: four rows equal on every other key, inserted out of id order.
TIED_IDS = tuple(uuid.UUID(int=900 + n) for n in (3, 1, 4, 2))


def ordering_row(identifier: uuid.UUID, keys: dict[str, Any]) -> dict[str, Any]:
    return assessment_values(
        identifier, as_of=keys["as_of"], source_system=keys["source_system"],
        layer1_fingerprint=keys["layer1_fingerprint"], rules_version=keys["rules_version"],
        linker_version=keys["linker_version"],
        ranking_key=[keys["band_rank"], keys["s8"], keys["s4"], keys["source_id"]],
    )


def pair_for(level: int) -> tuple[uuid.UUID, uuid.UUID, dict[str, Any], dict[str, Any]]:
    """
    Two rows that tie on every key before `level`, differ at it, and disagree after it.

    The row that sorts first at `level` sorts second at every later key, `id` included, so
    the pair is ordered by `level` alone: dropping it, reversing it or re-collating it
    reverses the pair.
    """
    first_keys, second_keys = {}, {}
    for index, (name, first, second) in enumerate(ORDER_KEYS):
        if index < level:
            first_keys[name] = second_keys[name] = first
        elif index == level:
            first_keys[name], second_keys[name] = first, second
        else:
            first_keys[name], second_keys[name] = second, first
    return uuid.UUID(int=2 * level + 2), uuid.UUID(int=2 * level + 1), first_keys, second_keys


def m6_order(row: dict[str, Any]) -> tuple:
    """Route 2's order in Python: as_of descending, then ascending, the ranking key as a tuple."""
    return (-row["as_of"].toordinal(), row["source_system"], row["layer1_fingerprint"],
            row["rules_version"], row["linker_version"], tuple(row["ranking_key"]), row["id"])


@pytest.fixture
def ordered(sessions) -> list[dict[str, Any]]:
    """One pair per ordering key and the four-way id tie, inserted in reverse."""
    rows = []
    for level in range(len(ORDER_KEYS)):
        first_id, second_id, first_keys, second_keys = pair_for(level)
        rows += [ordering_row(first_id, first_keys), ordering_row(second_id, second_keys)]
    last = {name: second for name, _, second in ORDER_KEYS}
    rows += [ordering_row(identifier, last) for identifier in TIED_IDS]
    core_assessments(sessions, list(reversed(rows)))
    return rows


def test_the_listing_is_route_2s_order_over_every_key(sessions, ordered):
    page = listed(sessions)

    assert [item.id for item in page.items] == [row["id"] for row in sorted(ordered, key=m6_order)]
    assert page.total == len(ordered) == 22


@pytest.mark.parametrize("level", range(len(ORDER_KEYS)), ids=ORDER_NAMES)
def test_each_key_decides_its_own_pair(sessions, ordered, level):
    first_id, second_id, first_keys, second_keys = pair_for(level)
    name, first, second = ORDER_KEYS[level]
    without_level = [key for key in ORDER_NAMES if key != name]

    ids = [item.id for item in listed(sessions).items]

    assert ids.index(first_id) < ids.index(second_id)
    # The fixture discriminates: every later key orders the pair the other way round.
    assert ((*(second_keys[key] for key in without_level[level:]), second_id)
            < (*(first_keys[key] for key in without_level[level:]), first_id))
    if isinstance(first, str):
        assert sorted([first, second]) == [first, second]
        assert sorted([first, second], key=str.casefold) == [second, first]
    if isinstance(first, int) and first < 0:
        assert sorted([str(first), str(second)]) == [str(second), str(first)]


def test_the_id_breaks_the_last_tie(sessions, ordered):
    ids = [item.id for item in listed(sessions).items]

    assert ids[-len(TIED_IDS):] == sorted(TIED_IDS)
    assert list(TIED_IDS) != sorted(TIED_IDS)


def test_the_order_is_the_same_on_every_read(sessions, ordered):
    assert len({tuple(item.id for item in listed(sessions).items) for _ in range(3)}) == 1


@pytest.mark.parametrize("limit", [1, 3, 7, 22, 500])
def test_pages_concatenate_to_the_whole_order_and_the_total_ignores_the_page(
        sessions, ordered, limit):
    whole = [item.id for item in listed(sessions).items]
    pages = [listed(sessions, limit=limit, offset=offset)
             for offset in range(0, len(whole) + limit, limit)]

    assert [item.id for page in pages for item in page.items] == whole
    assert {page.total for page in pages} == {len(whole)}
    assert all(len(page.items) <= limit for page in pages)
    assert pages[-1].items == []


def test_limit_and_offset_select_exactly_that_slice(sessions, ordered):
    whole = [item.id for item in listed(sessions).items]

    page = listed(sessions, limit=4, offset=5)

    assert [item.id for item in page.items] == whole[5:9]
    assert page.total == len(whole)
    assert listed(sessions, limit=4, offset=0).items == listed(sessions).items[:4]
    assert listed(sessions, limit=4, offset=len(whole)).items == []


BANDS = ("CRITICAL", "WATCH")


@pytest.fixture
def grid(sessions) -> list[dict[str, Any]]:
    """Every combination of two dates, two bands and both verdicts, one customer each."""
    rows = []
    for index, (as_of, band, worthy) in enumerate(
            (as_of, band, worthy) for as_of in (EARLIER, LATEST) for band in BANDS
            for worthy in (True, False)):
        rows.append(assessment_values(
            uuid.UUID(int=100 + index), as_of=as_of, band=band, executive_worthy=worthy,
            ranking_key=[-index, 0, 0, f"CUST-{index:03d}"]))
    core_assessments(sessions, rows)
    return rows


@pytest.mark.parametrize("filters", [
    {},
    {"as_of": EARLIER},
    {"as_of": LATEST},
    {"band": "CRITICAL"},
    {"band": "WATCH"},
    {"executive_worthy": True},
    {"executive_worthy": False},
    {"as_of": EARLIER, "executive_worthy": True},
    {"as_of": LATEST, "band": "WATCH"},
    {"band": "CRITICAL", "executive_worthy": False},
    {"as_of": LATEST, "band": "CRITICAL", "executive_worthy": True},
    {"band": "ELEVATED"},
    {"as_of": date(2026, 9, 17)},
], ids=lambda filters: "&".join(f"{key}={value}" for key, value in filters.items()) or "none")
def test_each_filter_is_an_exact_match_and_they_combine_with_and(sessions, grid, filters):
    expected = [row["id"] for row in sorted(grid, key=m6_order)
                if all(row[key] == value for key, value in filters.items())]

    page = listed(sessions, **filters)

    assert [item.id for item in page.items] == expected
    assert page.total == len(expected)


def test_the_total_counts_the_filtered_rows_not_the_page(sessions, grid):
    page = listed(sessions, as_of=LATEST, limit=1, offset=1)

    assert len(page.items) == 1
    assert page.total == 4


def test_a_listing_carries_every_column_as_stored_and_its_customers_source_id(sessions):
    customer_id = new_customer(sessions, "CUST-042")
    named, orphaned = uuid.UUID(int=1), uuid.UUID(int=2)
    core_assessments(sessions, [
        assessment_values(named, customer_id=customer_id, band="CRITICAL",
                          executive_worthy=True, ranking_key=[-3, -3, -5, "CUST-042"]),
        assessment_values(orphaned, ranking_key=[-1, 0, 0, "CUST-099"]),
    ])

    page = listed(sessions)

    assert page.total == 2
    assert [item._fields for item in page.items] == [AssessmentListing._fields] * 2
    assert AssessmentListing._fields == (
        "id", "customer_source_id", "as_of", "source_system", "layer1_fingerprint",
        "rules_version", "linker_version", "band", "executive_worthy", "ranking_key")
    assert [tuple(item) for item in page.items] == [
        (named, "CUST-042", EARLIER, SOURCE_SYSTEM, "a" * 64, 1, "1", "CRITICAL", True,
         [-3, -3, -5, "CUST-042"]),
        (orphaned, None, EARLIER, SOURCE_SYSTEM, "a" * 64, 1, "1", "WATCH", False,
         [-1, 0, 0, "CUST-099"]),
    ]


# ---------------------------------------------------------------------------
# risk_queries: one assessment, its positions and its briefs (§0.7.6)
# ---------------------------------------------------------------------------


SIGNALS = {"open_ticket_count": 3, "days_since_last_ticket": None}


def test_get_assessment_returns_the_listing_plus_the_rules_and_the_signals(sessions):
    customer_id = new_customer(sessions, "CUST-042")
    identifier = uuid.UUID(int=7)
    core_assessments(sessions, [assessment_values(
        identifier, customer_id=customer_id, as_of=LATEST, layer1_fingerprint="f" * 64,
        rules_version=3, linker_version="2", band="ELEVATED", executive_worthy=True,
        signals=SIGNALS, satisfied_rules=["E1", "W2"], ranking_key=[-2, -1, -4, "CUST-042"])])

    with read_snapshot(sessions) as session:
        row = get_assessment(session, identifier)
        missing = get_assessment(session, uuid.uuid4())

    assert missing is None
    assert row is not None
    assert row._fields == AssessmentListing._fields + ("satisfied_rules", "signals")
    assert row == StoredAssessment(
        identifier, "CUST-042", LATEST, SOURCE_SYSTEM, "f" * 64, 3, "2", "ELEVATED", True,
        [-2, -1, -4, "CUST-042"], ["E1", "W2"], SIGNALS)


def test_each_assessment_is_joined_to_its_own_customer_and_an_orphan_to_none(sessions):
    first, second = new_customer(sessions, "CUST-001"), new_customer(sessions, "CUST-002")
    ids = uuid.UUID(int=1), uuid.UUID(int=2), uuid.UUID(int=3)
    core_assessments(sessions, [
        assessment_values(ids[0], customer_id=second),
        assessment_values(ids[1], customer_id=first),
        assessment_values(ids[2]),
    ])

    with read_snapshot(sessions) as session:
        found = [get_assessment(session, identifier) for identifier in ids]

    assert [row.customer_source_id if row else "absent" for row in found] == [
        "CUST-002", "CUST-001", None]


def position_values(assessment_id: uuid.UUID, ordinal: int, identifier: uuid.UUID) -> dict:
    return {
        "id": identifier, "assessment_id": assessment_id, "ordinal": ordinal,
        "function": f"FUNCTION_{ordinal}", "stance": "OPPOSE" if ordinal % 2 else "SUPPORT",
        "proposed_action": f"ACTION_{ordinal}", "object_ref": f"DEAL-{ordinal:03d}",
        "rationale": f"rationale {ordinal}",
        "citations": [{"kind": "RECORD", "citation": {"source_id": f"TKT-{ordinal}"}}],
    }


def test_positions_for_returns_the_assessments_positions_by_ordinal(sessions, assessment_id):
    other = new_assessment(sessions, as_of=LATEST)
    # Written out of ordinal order, with ids that sort against it.
    ordinals = (3, 0, 5, 1, 4, 2)
    with sessions.begin() as session:
        session.execute(insert(RiskPosition), [
            position_values(assessment_id, ordinal, uuid.UUID(int=100 - ordinal))
            for ordinal in ordinals] + [position_values(other, 0, uuid.UUID(int=1))])

    with read_snapshot(sessions) as session:
        rows = positions_for(session, assessment_id)
        none = positions_for(session, uuid.uuid4())

    assert none == []
    assert StoredPosition._fields == (
        "ordinal", "function", "stance", "proposed_action", "object_ref", "rationale",
        "citations")
    expected = [position_values(assessment_id, ordinal, uuid.UUID(int=0))
                for ordinal in range(6)]
    assert rows == [StoredPosition(**{field: values[field] for field in StoredPosition._fields})
                    for values in expected]


def brief_values(assessment_id: uuid.UUID, identifier: uuid.UUID, policy_version: int,
                 digest: str) -> dict:
    return {
        "id": identifier, "assessment_id": assessment_id, "policy_version": policy_version,
        "template_version": f"t{policy_version}", "decision_payload": {"digest": digest},
        "payload_hash": digest, "narrative": "the narrative",
    }


@pytest.fixture
def briefed(sessions, assessment_id) -> tuple[uuid.UUID, list[uuid.UUID], uuid.UUID]:
    """
    Four briefs of one assessment, written against their order, and one of another.

    The order is policy_version, then payload_hash by code point ("B" before "a"),
    then id. The ids sort against it: by id alone, or by policy_version then id, the
    four come out in another order.
    """
    other = new_assessment(sessions, as_of=LATEST)
    specification = [(2, "0" * 64), (1, "a" * 64), (1, "B" * 64), (1, "1" * 64)]
    ids = [uuid.UUID(int=40 + index) for index in range(len(specification))]
    with sessions.begin() as session:
        session.execute(insert(RiskBrief), [
            brief_values(assessment_id, identifier, version, digest)
            for identifier, (version, digest) in zip(ids, specification, strict=True)]
            + [brief_values(other, uuid.UUID(int=1), 1, "0" * 64)])
    return assessment_id, [ids[3], ids[2], ids[1], ids[0]], other


def test_briefs_for_returns_every_brief_by_version_then_hash_by_code_point(sessions, briefed):
    assessment_id, expected, _ = briefed

    with read_snapshot(sessions) as session:
        rows = briefs_for(session, assessment_id)
        none = briefs_for(session, uuid.uuid4())

    assert none == []
    assert BriefReference._fields == ("id", "policy_version", "template_version", "payload_hash")
    assert rows == [
        BriefReference(expected[0], 1, "t1", "1" * 64),
        BriefReference(expected[1], 1, "t1", "B" * 64),
        BriefReference(expected[2], 1, "t1", "a" * 64),
        BriefReference(expected[3], 2, "t2", "0" * 64),
    ]
    assert sorted(["a" * 64, "B" * 64], key=str.casefold) == ["a" * 64, "B" * 64]
    assert sorted(expected) != expected
    assert sorted(expected[:3]) != expected[:3]


def test_brief_ids_for_groups_each_assessments_briefs_in_briefs_for_order(sessions, briefed):
    assessment_id, expected, other = briefed
    unbriefed = new_assessment(sessions, as_of=date(2026, 9, 17))

    with read_snapshot(sessions) as session:
        grouped = brief_ids_for(session, [assessment_id, other, unbriefed, uuid.uuid4()])
        each = {key: [row.id for row in briefs_for(session, key)] for key in grouped}
        only_one = brief_ids_for(session, [other])
        nothing = brief_ids_for(session, [])

    assert grouped == {assessment_id: expected, other: [uuid.UUID(int=1)]}
    assert grouped == each
    assert only_one == {other: [uuid.UUID(int=1)]}
    assert nothing == {}


def test_every_read_runs_in_a_read_only_snapshot_and_writes_nothing(sessions, briefed):
    assessment_id, _, _ = briefed
    before = all_counts(sessions)

    with read_snapshot(sessions) as session:
        list_assessments(session, as_of=EARLIER, band="CRITICAL", executive_worthy=True,
                         limit=10, offset=0)
        brief_ids_for(session, [assessment_id])
        get_assessment(session, assessment_id)
        positions_for(session, assessment_id)
        briefs_for(session, assessment_id)
        assert session.in_transaction()
        assert not (session.new or session.dirty or session.deleted)
        session.commit()

    assert all_counts(sessions) == before


# ---------------------------------------------------------------------------
# risk_queries over the corpus: the listing is M6's order (§0.7.8, §A15)
# ---------------------------------------------------------------------------


def test_the_corpus_listing_is_the_order_run_assessment_returns(corpus):
    """run_assessment returns order_reconciliations() order; route 2 must reproduce it."""
    sessions, _ = corpus
    with sessions.begin() as session:
        results = run_assessment(session, as_of=EARLIER)

    page = listed(sessions, as_of=EARLIER)

    assert [item.id for item in page.items] == [result.assessment_id for result in results]
    assert page.total == len(results) > 3
    assert [tuple(item.ranking_key) for item in page.items] == sorted(
        tuple(item.ranking_key) for item in page.items)
    assert [item.customer_source_id for item in page.items] == [
        item.ranking_key[3] for item in page.items]


def test_the_executive_worthy_corpus_listing_at_acceptance_is_exactly_meridian(corpus):
    sessions, briefs = corpus

    page = listed(sessions, as_of=EARLIER, executive_worthy=True)

    assert [(item.customer_source_id, item.band) for item in page.items] == [
        ("CUST-007", "CRITICAL")]
    assert page.total == 1
    with read_snapshot(sessions) as session:
        assert brief_ids_for(session, [page.items[0].id]) == {
            page.items[0].id: [briefs[MERIDIAN_PAYLOAD_HASH]]}


def test_meridians_detail_has_six_positions_by_ordinal_and_its_brief(corpus):
    sessions, briefs = corpus
    (listing,) = listed(sessions, as_of=EARLIER, executive_worthy=True).items

    with read_snapshot(sessions) as session:
        detail = get_assessment(session, listing.id)
        positions = positions_for(session, listing.id)
        references = briefs_for(session, listing.id)

    assert detail is not None
    assert tuple(detail)[:len(AssessmentListing._fields)] == tuple(listing)
    assert [position.ordinal for position in positions] == list(range(6))
    assert [(reference.id, reference.payload_hash) for reference in references] == [
        (briefs[MERIDIAN_PAYLOAD_HASH], MERIDIAN_PAYLOAD_HASH)]


# ---------------------------------------------------------------------------
# risk_queries: the SQL the reads emit is §0.7.8's, verbatim
# ---------------------------------------------------------------------------


#: §0.7.8's ordering tuple as PostgreSQL receives it. Pinned as text because this
#: database's default collation already orders by code point, so COLLATE "C" cannot be
#: shown by row order alone: a server with a locale default would need it.
ROUTE_2_ORDER = (
    'risk_assessments.as_of DESC, risk_assessments.source_system COLLATE "C", '
    'risk_assessments.layer1_fingerprint COLLATE "C", risk_assessments.rules_version, '
    'risk_assessments.linker_version COLLATE "C", '
    "CAST(risk_assessments.ranking_key ->> 0 AS INTEGER), "
    "CAST(risk_assessments.ranking_key ->> 1 AS INTEGER), "
    "CAST(risk_assessments.ranking_key ->> 2 AS INTEGER), "
    '(risk_assessments.ranking_key ->> 3) COLLATE "C", risk_assessments.id'
)
BRIEF_ORDER = 'risk_briefs.policy_version, risk_briefs.payload_hash COLLATE "C", risk_briefs.id'


def executed(engine, sessions, read: Callable[[Session], Any]) -> list[str]:
    """Every statement `read` sends, with its parameters bound by the driver."""
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(cursor.mogrify(statement, parameters).decode())

    with read_snapshot(sessions) as session:
        session.connection()
        event.listen(engine, "before_cursor_execute", capture)
        try:
            read(session)
        finally:
            event.remove(engine, "before_cursor_execute", capture)
    return statements


def test_the_listing_orders_by_route_2s_tuple_exactly(e1_engine, sessions):
    count, page = executed(e1_engine, sessions, lambda session: list_assessments(
        session, as_of=None, band=None, executive_worthy=None, limit=5, offset=10))

    assert "ORDER BY" not in count
    match = re.search(r" ORDER BY (.*?)\s+LIMIT 5 OFFSET 10$", page, re.DOTALL)
    assert match is not None and match.group(1) == ROUTE_2_ORDER
    assert "LEFT OUTER JOIN customers ON customers.id = risk_assessments.customer_id" in page


def test_brief_ids_for_is_one_grouped_query_in_the_brief_order(e1_engine, sessions):
    (statement,) = executed(e1_engine, sessions,
                            lambda session: brief_ids_for(session, [uuid.uuid4()]))

    assert f"array_agg(risk_briefs.id ORDER BY {BRIEF_ORDER})" in statement
    assert statement.endswith(" GROUP BY risk_briefs.assessment_id")
    assert executed(e1_engine, sessions, lambda session: brief_ids_for(session, [])) == []


def test_briefs_for_orders_by_the_brief_order_exactly(e1_engine, sessions):
    (statement,) = executed(e1_engine, sessions,
                            lambda session: briefs_for(session, uuid.uuid4()))

    assert statement.endswith(f" ORDER BY {BRIEF_ORDER}")
