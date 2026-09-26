"""
Recording and reading decisions on risk briefs (VS-01 M8, §0.7.7).

A decision binds an asserted actor's APPROVED or REJECTED to one **immutable
stored brief**, identified by its id and its payload hash (OPEN-M8-7). The
request's hash must be the stored brief's, and the stored payload must still
re-hash to it, through M7's own `payload_hash`. Nothing here regenerates,
re-renders, re-resolves or mutates a brief, an assessment or a position, and
`risk_briefs.status` is never written: decision state is derived from the
history instead (OPEN-M8-8). Later-snapshot revalidation is deliberately not
performed (§0.7.17).

**One linear chain per brief** (OPEN-M8-6). A brief's first decision
supersedes nothing; every later one supersedes the current head of the same
brief. The database refuses a second first decision and a second successor
through its partial unique indexes; that a predecessor is on the same brief
and is the head is checked here, because a plain self-FK cannot express it
(§0.7.18 Q-M8-2). The chain, not `decided_at`, orders a brief's history.

**Impure, like the assessment run** (OPEN-M8-17). It reads and writes
through its two repositories only, and neither opens nor ends a transaction:
the caller owns both. It reads no clock -- `decided_at` is the caller's
argument (X7) -- generates no id, reaches no random source, speaks no HTTP,
and catches nothing. It is not re-exported by `app.decisions`; the one
module that imports it is the risk route.

**One event**, `vs01.decision_recorded` (§0.7.10), once per recorded
decision, after the row is inserted and before this returns, with exactly
`payload_hash`, `decision` and `supersedes`. A refused decision emits
nothing. The actor and the note are never logged, and no error message
carries them, the payload or an email address.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.decisions.payload import payload_hash as hash_payload
from app.intelligence.errors import ContractViolationError, IntelligenceError
from app.persistence.repositories.brief_decisions import NewDecision, insert_decision
from app.persistence.repositories.risk_queries import decisions_for, get_brief

logger = logging.getLogger(__name__)

#: OPEN-M8-9: the actor is 1-255 characters, the note at most 2000.
MAX_ACTOR_CHARS = 255
MAX_NOTE_CHARS = 2000


class Decision(StrEnum):
    """What a decision says about a brief (X6)."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DecisionStatus(StrEnum):
    """A brief's derived decision state: its head's decision, or PENDING (OPEN-M8-8)."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class HashConflict(StrEnum):
    """Why a decision's payload binding was refused."""

    REQUEST_HASH_MISMATCH = "REQUEST_HASH_MISMATCH"
    STORED_PAYLOAD_MISMATCH = "STORED_PAYLOAD_MISMATCH"


class DecisionConflict(StrEnum):
    """Why a decision does not extend the brief's history."""

    SUPERSEDES_REQUIRED = "SUPERSEDES_REQUIRED"
    PREDECESSOR_NOT_ON_BRIEF = "PREDECESSOR_NOT_ON_BRIEF"
    PREDECESSOR_NOT_HEAD = "PREDECESSOR_NOT_HEAD"
    CONCURRENT_DECISION = "CONCURRENT_DECISION"


@dataclass(frozen=True)
class DecisionRecord:
    """One recorded decision (§A30's reusable foundation)."""

    id: UUID
    brief_id: UUID
    payload_hash: str
    actor: str
    decision: Decision
    note: str | None
    decided_at: datetime
    supersedes_id: UUID | None


class ApprovalError(IntelligenceError):
    """A decision cannot be recorded or read."""


class UnknownBriefError(ApprovalError):
    """No brief has the id the decision names."""

    def __init__(self) -> None:
        super().__init__("risk brief does not exist")


_HASH_MESSAGES = {
    HashConflict.REQUEST_HASH_MISMATCH: "payload_hash is not the brief's payload hash",
    HashConflict.STORED_PAYLOAD_MISMATCH:
        "the brief's stored decision payload does not re-hash to its payload hash",
}

_DECISION_MESSAGES = {
    DecisionConflict.SUPERSEDES_REQUIRED:
        "the brief already has a decision, so supersedes_id must name its current head",
    DecisionConflict.PREDECESSOR_NOT_ON_BRIEF: "supersedes_id names no decision on this brief",
    DecisionConflict.PREDECESSOR_NOT_HEAD: "supersedes_id is not the brief's current head",
    DecisionConflict.CONCURRENT_DECISION:
        "a concurrent decision extended the brief's history first",
}


class PayloadHashConflictError(ApprovalError):
    """The decision's payload hash is not one the stored brief can be decided under."""

    def __init__(self, reason: HashConflict) -> None:
        super().__init__(_HASH_MESSAGES[reason])
        self.reason = reason


class DecisionConflictError(ApprovalError):
    """The decision does not extend the brief's one linear history."""

    def __init__(self, reason: DecisionConflict) -> None:
        super().__init__(_DECISION_MESSAGES[reason])
        self.reason = reason


def record_decision(
    session: Session,
    *,
    brief_id: UUID,
    payload_hash: str,
    actor: str,
    decision: Decision,
    note: str | None,
    supersedes_id: UUID | None,
    decided_at: datetime,
) -> DecisionRecord:
    """
    Record one decision on a stored brief, in §0.7.7's order; the first failure raises.

    0. The arguments: `decided_at` timezone-aware, the actor 1-255
       characters, the note None or at most 2000, the decision APPROVED or
       REJECTED -- else ContractViolationError.
    1. The brief exists -- else UnknownBriefError.
    2. The request's hash is the brief's -- else REQUEST_HASH_MISMATCH.
    3. The stored payload re-hashes to it -- else STORED_PAYLOAD_MISMATCH.
    4. The brief's history is read; its head is the last decision.
    5. The first decision supersedes nothing, and every later one supersedes
       the head -- else SUPERSEDES_REQUIRED, PREDECESSOR_NOT_ON_BRIEF or
       PREDECESSOR_NOT_HEAD.
    6. The row is inserted -- a concurrent first decision or successor that
       committed first makes it CONCURRENT_DECISION.
    7. The event is emitted, and 8. the record returned.
    """
    chosen = _checked_arguments(actor=actor, decision=decision, note=note, decided_at=decided_at)
    brief = get_brief(session, brief_id)
    if brief is None:
        raise UnknownBriefError()
    if payload_hash != brief.payload_hash:
        raise PayloadHashConflictError(HashConflict.REQUEST_HASH_MISMATCH)
    if hash_payload(brief.decision_payload) != brief.payload_hash:
        raise PayloadHashConflictError(HashConflict.STORED_PAYLOAD_MISMATCH)
    history = decision_history(session, brief_id)
    _check_supersession(history, supersedes_id)
    identifier = insert_decision(session, NewDecision(
        brief_id=brief_id,
        payload_hash=payload_hash,
        actor=actor,
        decision=chosen.value,
        note=note,
        decided_at=decided_at,
        supersedes_id=supersedes_id,
    ))
    if identifier is None:
        raise DecisionConflictError(DecisionConflict.CONCURRENT_DECISION)
    log_event(
        logger, logging.INFO, "vs01.decision_recorded",
        payload_hash=payload_hash,
        decision=chosen.value,
        supersedes=supersedes_id is not None,
    )
    return DecisionRecord(
        id=identifier,
        brief_id=brief_id,
        payload_hash=payload_hash,
        actor=actor,
        decision=chosen,
        note=note,
        decided_at=decided_at,
        supersedes_id=supersedes_id,
    )


def decision_history(session: Session, brief_id: UUID) -> tuple[DecisionRecord, ...]:
    """
    The brief's decisions from its first to its head, following each one's successor.

    A missing brief raises UnknownBriefError. Rows that do not form one linear
    chain from one first decision raise ContractViolationError; the database
    constraints and `record_decision` make that unreachable, except by writing
    around this module.
    """
    if get_brief(session, brief_id) is None:
        raise UnknownBriefError()
    rows = decisions_for(session, brief_id)
    if not rows:
        return ()
    firsts = [row for row in rows if row.supersedes_id is None]
    if len(firsts) != 1:
        raise ContractViolationError("the brief's decisions do not form one linear chain")
    # Each row is keyed by its one predecessor, so the walk from the first
    # decision visits a row at most once; a fork or a detached row is left over.
    successors = {row.supersedes_id: row for row in rows}
    chain = [firsts[0]]
    while chain[-1].id in successors:
        chain.append(successors[chain[-1].id])
    if len(chain) != len(rows):
        raise ContractViolationError("the brief's decisions do not form one linear chain")
    if any(row.decision not in tuple(Decision) for row in chain):
        raise ContractViolationError("a stored decision is neither APPROVED nor REJECTED")
    return tuple(
        DecisionRecord(
            id=row.id,
            brief_id=row.brief_id,
            payload_hash=row.payload_hash,
            actor=row.actor,
            decision=Decision(row.decision),
            note=row.note,
            decided_at=row.decided_at,
            supersedes_id=row.supersedes_id,
        )
        for row in chain
    )


def decision_status(history: Sequence[DecisionRecord]) -> DecisionStatus:
    """PENDING for an empty history, otherwise the head's decision (OPEN-M8-8)."""
    if not history:
        return DecisionStatus.PENDING
    return DecisionStatus(history[-1].decision.value)


def _checked_arguments(
    *, actor: str, decision: Decision, note: str | None, decided_at: datetime
) -> Decision:
    """Step 0. The route's schema and clock guarantee all of it, so a failure here is a 500."""
    if decided_at.utcoffset() is None:
        raise ContractViolationError("decided_at must be timezone-aware")
    if not 1 <= len(actor) <= MAX_ACTOR_CHARS:
        raise ContractViolationError(f"actor must be 1 to {MAX_ACTOR_CHARS} characters")
    if note is not None and len(note) > MAX_NOTE_CHARS:
        raise ContractViolationError(f"note must be at most {MAX_NOTE_CHARS} characters")
    if decision not in tuple(Decision):
        raise ContractViolationError("decision must be APPROVED or REJECTED")
    return Decision(decision)


def _check_supersession(history: Sequence[DecisionRecord], supersedes_id: UUID | None) -> None:
    """Step 5: the first decision supersedes nothing; every later one supersedes the head."""
    if history and supersedes_id is None:
        raise DecisionConflictError(DecisionConflict.SUPERSEDES_REQUIRED)
    if supersedes_id is None:
        return
    if supersedes_id not in {record.id for record in history}:
        raise DecisionConflictError(DecisionConflict.PREDECESSOR_NOT_ON_BRIEF)
    if supersedes_id != history[-1].id:
        raise DecisionConflictError(DecisionConflict.PREDECESSOR_NOT_HEAD)
