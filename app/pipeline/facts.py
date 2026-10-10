"""
Deal facts (VS-02 plan A8, A13.2): what VS-02 reads of each deal, how each
deal is classified, and the notes it draws.

DealFact is VS-02's own value type. VS-01's DealSignal cannot represent an
incomplete deal, and a deal that cannot be valued is counted and reported
here, never dropped (plan A13.2 item 1).

    open        is_active is true. VS-01's own definition of an active deal;
                a deal is never reclassified by its stage (A8.2).
    valued      an open deal whose stage, amount, currency and probability
                are all present and whose amount is not negative (A8.3).
    owner       the employee the deal's deal_owned_by edge resolves to, or
                UNASSIGNED when the deal names none, or UNRESOLVED when the
                key it carries names no employee in the scope. The last two
                never collapse (A10.3).
    customer    the customer the deal's customer_has_deal edge resolves to.

This is one of the two modules of app/pipeline that accept a session (plan
A19 item 5). read_deal_facts reads through exactly three calls: deal_rows,
and edges_of_type with the two edge types of plan A5. It follows no
relationship beyond one edge, reads no document and no ticket, and writes
nothing: the session and its transaction are the caller's.

Everything below the reader is pure.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy.orm import Session

from app.intelligence import Scope
from app.persistence.repositories.pipeline_queries import deal_rows
from app.relationships import EdgeBasis, EdgeType, edges_of_type

#: The Layer 1 entity every deal-level note names.
DEALS = "deals"
#: How an owner is known (plan A10.3 item 1): the deal_owned_by edge is a
#: source-key join over this column. A test pins both to the frozen edge.
OWNER_BASIS = EdgeBasis.SOURCE_KEY_JOIN
OWNER_CARRIER_FIELD = "deals.owner_source_id"

#: Plan A8.3: the four fields a valued deal holds, ascending by name.
_VALUED_FIELDS = ("amount", "currency", "probability", "stage")


@dataclass(frozen=True)
class DealFact:
    """One deal in scope: nine stored values and its two resolved references (plan A8.1)."""

    source_id: str
    stage: str | None
    is_active: bool
    amount: Decimal | None
    currency: str | None
    probability: Decimal | None
    expected_close_date: date | None
    owner_source_id: str | None
    customer_source_id: str | None
    owner: str | None
    customer: str | None


@dataclass(frozen=True)
class ValuedDeal:
    """An open valued deal, with the four values that make it one (plan A8.3)."""

    fact: DealFact
    stage: str
    amount: Decimal
    currency: str
    probability: Decimal


class DealState(StrEnum):
    """Plan A8.2, A8.3: every deal is in exactly one."""

    OPEN_VALUED = "OPEN_VALUED"
    OPEN_UNVALUED = "OPEN_UNVALUED"
    CLOSED = "CLOSED"


class OwnerKind(StrEnum):
    """Plan A10.3: how a deal's owner stands. UNASSIGNED and UNRESOLVED never collapse."""

    EMPLOYEE = "EMPLOYEE"
    UNASSIGNED = "UNASSIGNED"
    UNRESOLVED = "UNRESOLVED"


class NoteCode(StrEnum):
    """The deal-level data-quality codes of plan A13.2."""

    CUSTOMER_KEY_MISSING = "CUSTOMER_KEY_MISSING"
    CUSTOMER_KEY_UNRESOLVED = "CUSTOMER_KEY_UNRESOLVED"
    EXPECTED_CLOSE_MISSING = "EXPECTED_CLOSE_MISSING"
    INCOMPLETE_DEAL = "INCOMPLETE_DEAL"
    NEGATIVE_AMOUNT = "NEGATIVE_AMOUNT"
    OWNER_KEY_MISSING = "OWNER_KEY_MISSING"
    OWNER_KEY_UNRESOLVED = "OWNER_KEY_UNRESOLVED"
    STAGE_ACTIVITY_MISMATCH = "STAGE_ACTIVITY_MISMATCH"


@dataclass(frozen=True)
class DealNote:
    """One deal-level data-quality note, in the shape of plan A14.9."""

    code: NoteCode
    entity: str
    id: str
    fields: tuple[str, ...]
    key: str | None


def read_deal_facts(session: Session, scope: Scope) -> tuple[DealFact, ...]:
    """
    Every deal of the scope's source system, ascending by source_id.

    The owner and the customer are filled from the two relationship edges of
    plan A5, both scoped to the same source system: a key naming an employee
    of another source system resolves to nothing. The order is sorted here
    and is not the order the rows arrived in.
    """
    owners = {edge.source.source_id: edge.target.source_id
              for edge in edges_of_type(EdgeType.DEAL_OWNED_BY, session, scope)}
    customers = {edge.target.source_id: edge.source.source_id
                 for edge in edges_of_type(EdgeType.CUSTOMER_HAS_DEAL, session, scope)}
    facts = [
        DealFact(
            source_id=row.source_id,
            stage=row.stage,
            is_active=row.is_active,
            amount=row.amount,
            currency=row.currency,
            probability=row.probability,
            expected_close_date=row.expected_close_date,
            owner_source_id=row.owner_source_id,
            customer_source_id=row.customer_source_id,
            owner=owners.get(row.source_id),
            customer=customers.get(row.source_id),
        )
        for row in deal_rows(session, scope.source_system)
    ]
    return tuple(sorted(facts, key=_by_source_id))


def valued_deal(fact: DealFact) -> ValuedDeal | None:
    """The deal as an open valued deal, or None when it is closed or cannot be valued."""
    if (not fact.is_active or fact.stage is None or fact.amount is None
            or fact.currency is None or fact.probability is None or _is_negative(fact.amount)):
        return None
    return ValuedDeal(fact=fact, stage=fact.stage, amount=fact.amount, currency=fact.currency,
                      probability=fact.probability)


def deal_state(fact: DealFact) -> DealState:
    """Open or closed by is_active alone (plan A8.2); valued by plan A8.3."""
    if not fact.is_active:
        return DealState.CLOSED
    return DealState.OPEN_UNVALUED if valued_deal(fact) is None else DealState.OPEN_VALUED


def owner_kind(fact: DealFact) -> OwnerKind:
    """Plan A10.3 item 2: a resolved employee, no key at all, or a key that names no one."""
    if fact.owner is not None:
        return OwnerKind.EMPLOYEE
    return OwnerKind.UNASSIGNED if fact.owner_source_id is None else OwnerKind.UNRESOLVED


def deal_notes(fact: DealFact, closed_stages: Collection[str]) -> tuple[DealNote, ...]:
    """
    Every deal-level note one deal draws (plan A13.2), ascending by code.

    Owner, customer and close-date notes are drawn by valued deals only,
    because only they sit in the partitions those notes explain. A deal with
    a null stage draws no mismatch note.
    """
    notes = []
    if fact.is_active:
        missing = tuple(name for name in _VALUED_FIELDS if getattr(fact, name) is None)
        if missing:
            notes.append(_note(NoteCode.INCOMPLETE_DEAL, fact, missing))
        elif valued_deal(fact) is None:
            notes.append(_note(NoteCode.NEGATIVE_AMOUNT, fact, ("amount",)))
    if fact.stage is not None and fact.is_active == (fact.stage in closed_stages):
        notes.append(_note(NoteCode.STAGE_ACTIVITY_MISMATCH, fact, ("is_active", "stage")))
    if valued_deal(fact) is not None:
        owner = owner_kind(fact)
        if owner is OwnerKind.UNASSIGNED:
            notes.append(_note(NoteCode.OWNER_KEY_MISSING, fact, ("owner_source_id",)))
        elif owner is OwnerKind.UNRESOLVED:
            notes.append(_note(NoteCode.OWNER_KEY_UNRESOLVED, fact, ("owner_source_id",),
                               fact.owner_source_id))
        if fact.customer is None and fact.customer_source_id is None:
            notes.append(_note(NoteCode.CUSTOMER_KEY_MISSING, fact, ("customer_source_id",)))
        elif fact.customer is None:
            notes.append(_note(NoteCode.CUSTOMER_KEY_UNRESOLVED, fact, ("customer_source_id",),
                               fact.customer_source_id))
        if fact.expected_close_date is None:
            notes.append(_note(NoteCode.EXPECTED_CLOSE_MISSING, fact, ("expected_close_date",)))
    return tuple(sorted(notes, key=_by_code))


def _note(code: NoteCode, fact: DealFact, fields: tuple[str, ...],
          key: str | None = None) -> DealNote:
    return DealNote(code=code, entity=DEALS, id=fact.source_id, fields=fields, key=key)


def _is_negative(amount: Decimal) -> bool:
    """
    Below zero, for a number. What is not a number is not negative.

    Comparing a NaN signals or not according to the Decimal context in force,
    so none is compared: a NaN or an infinity is left for the frozen
    MoneyValue, which refuses it (plan A10.5, stage 1).
    """
    return amount.is_finite() and amount < 0


def _by_source_id(fact: DealFact) -> str:
    return fact.source_id


def _by_code(note: DealNote) -> str:
    return note.code.value
