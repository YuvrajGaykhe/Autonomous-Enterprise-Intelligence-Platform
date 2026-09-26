"""
Every M8 read of the risk tables (VS-01 M8, §0.7.6, OPEN-M8-16).

This module is **persistence only**, on the boundary M4 drew (§0.3.11 D-M4-B1,
D-M4-B2) and M7 kept (§0.6.5): it imports no app.intelligence, app.evidence,
app.analysts or app.decisions module, names no domain type, and decides
nothing. Each function returns plain NamedTuple rows or scalars; giving them
meaning is the caller's.

It reads and never writes. Every function takes a caller-owned session and
builds its query from SQLAlchemy expressions only: nothing here commits,
rolls back, begins, closes or flushes, nothing uses textual SQL, and nothing
logs. Stored values are returned exactly as stored: a brief's payload and
narrative are never re-hashed, re-rendered or re-resolved here.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any, NamedTuple

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session

from app.persistence.models import (
    BriefDecision,
    Customer,
    RiskAssessment,
    RiskBrief,
    RiskPosition,
)
from app.persistence.repositories.run_queries import QueryPage


class StoredBrief(NamedTuple):
    """Every `risk_briefs` column, as stored."""

    id: uuid.UUID
    assessment_id: uuid.UUID
    policy_version: int
    template_version: str
    decision_payload: Any
    payload_hash: str
    narrative: str
    status: str


class StoredDecision(NamedTuple):
    """Every `brief_decisions` column, as stored."""

    id: uuid.UUID
    brief_id: uuid.UUID
    payload_hash: str
    actor: str
    decision: str
    note: str | None
    decided_at: datetime
    supersedes_id: uuid.UUID | None


class AssessmentListing(NamedTuple):
    """One `risk_assessments` row as route 2 lists it, with its customer's source id."""

    id: uuid.UUID
    customer_source_id: str | None
    as_of: date
    source_system: str
    layer1_fingerprint: str
    rules_version: int
    linker_version: str
    band: str
    executive_worthy: bool
    ranking_key: Any


class StoredAssessment(NamedTuple):
    """A listing's columns plus the satisfied rules and the signals, as stored."""

    id: uuid.UUID
    customer_source_id: str | None
    as_of: date
    source_system: str
    layer1_fingerprint: str
    rules_version: int
    linker_version: str
    band: str
    executive_worthy: bool
    ranking_key: Any
    satisfied_rules: Any
    signals: Any


class StoredPosition(NamedTuple):
    """One `risk_positions` row, without its keys."""

    ordinal: int
    function: str
    stance: str
    proposed_action: str
    object_ref: str
    rationale: str
    citations: Any


class BriefReference(NamedTuple):
    """What identifies one brief of an assessment, without its payload or narrative."""

    id: uuid.UUID
    policy_version: int
    template_version: str
    payload_hash: str


#: The customer's source id, or NULL when `customer_id` was set NULL: an outer join.
_LISTING_COLUMNS = (
    RiskAssessment.id,
    Customer.source_id,
    RiskAssessment.as_of,
    RiskAssessment.source_system,
    RiskAssessment.layer1_fingerprint,
    RiskAssessment.rules_version,
    RiskAssessment.linker_version,
    RiskAssessment.band,
    RiskAssessment.executive_worthy,
    RiskAssessment.ranking_key,
)
_CUSTOMER = Customer.id == RiskAssessment.customer_id

#: Route 2's order (§0.7.8, OPEN-M8-13). The first five keys group the rows by
#: scope and versions; within a group, the ranking key's four components
#: reproduce order_reconciliations(): `(-band rank, -S8, -S4, source_id)`,
#: compared as integers and, for the source id, by code point. `id` breaks
#: every remaining tie.
_LISTING_ORDER = (
    RiskAssessment.as_of.desc(),
    RiskAssessment.source_system.collate("C"),
    RiskAssessment.layer1_fingerprint.collate("C"),
    RiskAssessment.rules_version,
    RiskAssessment.linker_version.collate("C"),
    cast(RiskAssessment.ranking_key[0].astext, Integer),
    cast(RiskAssessment.ranking_key[1].astext, Integer),
    cast(RiskAssessment.ranking_key[2].astext, Integer),
    RiskAssessment.ranking_key[3].astext.collate("C"),
    RiskAssessment.id,
)

#: The order of an assessment's briefs (§0.7.6). It is only deterministic:
#: no brief is current, and none supersedes another.
_BRIEF_ORDER = (RiskBrief.policy_version, RiskBrief.payload_hash.collate("C"), RiskBrief.id)


def get_brief(session: Session, brief_id: uuid.UUID) -> StoredBrief | None:
    """The brief with this id, or None when there is none."""
    row = session.execute(
        select(
            RiskBrief.id,
            RiskBrief.assessment_id,
            RiskBrief.policy_version,
            RiskBrief.template_version,
            RiskBrief.decision_payload,
            RiskBrief.payload_hash,
            RiskBrief.narrative,
            RiskBrief.status,
        ).where(RiskBrief.id == brief_id)
    ).one_or_none()
    return None if row is None else StoredBrief(*row)


def decisions_for(session: Session, brief_id: uuid.UUID) -> list[StoredDecision]:
    """
    Every decision recorded on the brief, ordered by id.

    The order is only deterministic, not meaningful: a brief's history is its
    supersession chain, which the caller rebuilds (§0.7.7).
    """
    rows = session.execute(
        select(
            BriefDecision.id,
            BriefDecision.brief_id,
            BriefDecision.payload_hash,
            BriefDecision.actor,
            BriefDecision.decision,
            BriefDecision.note,
            BriefDecision.decided_at,
            BriefDecision.supersedes_id,
        )
        .where(BriefDecision.brief_id == brief_id)
        .order_by(BriefDecision.id)
    ).all()
    return [StoredDecision(*row) for row in rows]


def list_assessments(
    session: Session,
    *,
    as_of: date | None,
    band: str | None,
    executive_worthy: bool | None,
    limit: int,
    offset: int,
) -> QueryPage[AssessmentListing]:
    """
    Assessments matching every given filter, in route 2's order, one page at a time.

    A filter left None is not applied. `total` counts every matching row,
    whatever the page.
    """
    conditions = []
    if as_of is not None:
        conditions.append(RiskAssessment.as_of == as_of)
    if band is not None:
        conditions.append(RiskAssessment.band == band)
    if executive_worthy is not None:
        conditions.append(RiskAssessment.executive_worthy == executive_worthy)
    total = session.execute(
        select(func.count()).select_from(RiskAssessment).where(*conditions)
    ).scalar_one()
    rows = session.execute(
        select(*_LISTING_COLUMNS)
        .outerjoin(Customer, _CUSTOMER)
        .where(*conditions)
        .order_by(*_LISTING_ORDER)
        .limit(limit)
        .offset(offset)
    ).all()
    return QueryPage(items=[AssessmentListing(*row) for row in rows], total=total)


def brief_ids_for(
    session: Session, assessment_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """
    Each assessment's brief ids, in `briefs_for` order, from one grouped query.

    An assessment with no brief is absent, as is an id naming no assessment.
    """
    if not assessment_ids:
        return {}
    rows = session.execute(
        select(
            RiskBrief.assessment_id,
            func.array_agg(aggregate_order_by(RiskBrief.id, *_BRIEF_ORDER)),
        )
        .where(RiskBrief.assessment_id.in_(assessment_ids))
        .group_by(RiskBrief.assessment_id)
    ).all()
    return {assessment_id: list(brief_ids) for assessment_id, brief_ids in rows}


def get_assessment(session: Session, assessment_id: uuid.UUID) -> StoredAssessment | None:
    """The assessment with this id, or None when there is none."""
    row = session.execute(
        select(*_LISTING_COLUMNS, RiskAssessment.satisfied_rules, RiskAssessment.signals)
        .outerjoin(Customer, _CUSTOMER)
        .where(RiskAssessment.id == assessment_id)
    ).one_or_none()
    return None if row is None else StoredAssessment(*row)


def positions_for(session: Session, assessment_id: uuid.UUID) -> list[StoredPosition]:
    """Every position of the assessment, by `ordinal`; empty for an unknown assessment."""
    rows = session.execute(
        select(
            RiskPosition.ordinal,
            RiskPosition.function,
            RiskPosition.stance,
            RiskPosition.proposed_action,
            RiskPosition.object_ref,
            RiskPosition.rationale,
            RiskPosition.citations,
        )
        .where(RiskPosition.assessment_id == assessment_id)
        .order_by(RiskPosition.ordinal)
    ).all()
    return [StoredPosition(*row) for row in rows]


def briefs_for(session: Session, assessment_id: uuid.UUID) -> list[BriefReference]:
    """
    Every brief of the assessment, by `policy_version`, `payload_hash` and `id`.

    All of them: none is selected as current (OPEN-M8-14). Empty for an
    unknown assessment.
    """
    rows = session.execute(
        select(
            RiskBrief.id,
            RiskBrief.policy_version,
            RiskBrief.template_version,
            RiskBrief.payload_hash,
        )
        .where(RiskBrief.assessment_id == assessment_id)
        .order_by(*_BRIEF_ORDER)
    ).all()
    return [BriefReference(*row) for row in rows]
