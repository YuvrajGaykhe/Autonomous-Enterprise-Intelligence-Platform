"""
Persistence for risk assessments, their positions and their briefs (VS-01 M7, §0.6.5).

This module is **persistence only**, on the boundary M4 drew (§0.3.11 D-M4-B1,
D-M4-B2): it writes rows and reads back the ids of rows it could not write.
It imports no app.intelligence, app.evidence, app.analysts or app.decisions
module, names no domain type, and decides nothing. The three row types below
are row projections: every field is plain data, and none validates anything.

Every write is append-or-read, never update (§0.6.6). Each insert runs ON
CONFLICT ON CONSTRAINT ... DO NOTHING against the table's named identity, so
the database, not an application pre-existence check, decides whether a row
is new. That is what makes an identical re-run, or a concurrent identical
run, a read rather than a race. A key collision is trusted: the existing row
is neither compared, nor updated, nor rejected.

Session and transaction are the caller's, matching every Layer 1 repository:
nothing here commits, rolls back, begins, closes or flushes, and nothing logs.

Customer identity crosses this seam as a source id, as in M4's link
repository, and is resolved to the `customers.id` surrogate key here, within
the row's own source system.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any, NamedTuple, cast

from sqlalchemy import CursorResult, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.persistence.models import Customer, RiskAssessment, RiskBrief, RiskPosition
from app.persistence.models.risk_assessment import IDENTITY_CONSTRAINT as ASSESSMENT_IDENTITY
from app.persistence.models.risk_brief import IDENTITY_CONSTRAINT as BRIEF_IDENTITY
from app.persistence.models.risk_position import IDENTITY_CONSTRAINT as POSITION_IDENTITY

#: Layer 1 source_entity value the customer lookup is constrained to.
CUSTOMERS = "customers"


class AssessmentRow(NamedTuple):
    """One assessment to write, keyed by the customer's source id."""

    customer_source_id: str
    as_of: date
    source_system: str
    layer1_fingerprint: str
    rules_version: int
    linker_version: str
    band: str
    executive_worthy: bool
    signals: Any
    satisfied_rules: Any
    ranking_key: Any


class PositionRow(NamedTuple):
    """One position to write under an assessment. Ordering is by `ordinal`."""

    ordinal: int
    function: str
    stance: str
    proposed_action: str
    object_ref: str
    rationale: str
    citations: Any


class BriefRow(NamedTuple):
    """One brief to write under an assessment. `status` is the table's default."""

    assessment_id: uuid.UUID
    policy_version: int
    template_version: str
    decision_payload: Any
    payload_hash: str
    narrative: str


def insert_assessment(session: Session, row: AssessmentRow) -> tuple[uuid.UUID, bool]:
    """
    Write an assessment, or read back the one its identity already names.

    Returns the row's id and whether this call created it. When the identity
    already exists nothing is written, the existing id is re-selected by the
    six identity columns, and `created` is False.
    """
    customer_id = session.execute(
        select(Customer.id).where(
            Customer.source_system == row.source_system,
            Customer.source_entity == CUSTOMERS,
            Customer.source_id == row.customer_source_id,
        )
    ).scalar_one()
    identity = {
        "customer_id": customer_id,
        "as_of": row.as_of,
        "source_system": row.source_system,
        "layer1_fingerprint": row.layer1_fingerprint,
        "rules_version": row.rules_version,
        "linker_version": row.linker_version,
    }
    statement = (
        insert(RiskAssessment)
        .values(
            id=uuid.uuid4(),
            band=row.band,
            executive_worthy=row.executive_worthy,
            signals=row.signals,
            satisfied_rules=row.satisfied_rules,
            ranking_key=row.ranking_key,
            **identity,
        )
        .on_conflict_do_nothing(constraint=ASSESSMENT_IDENTITY)
        .returning(RiskAssessment.id)
    )
    inserted = session.execute(statement).scalar_one_or_none()
    if inserted is not None:
        return inserted, True
    existing = session.execute(
        select(RiskAssessment.id).where(
            *(getattr(RiskAssessment, name) == value for name, value in identity.items())
        )
    ).scalar_one()
    return existing, False


def insert_positions(
    session: Session, assessment_id: uuid.UUID, rows: Sequence[PositionRow]
) -> int:
    """
    Write an assessment's positions in `ordinal` order, returning how many were inserted.

    A position whose identity already exists under the assessment is skipped
    by the database, not by a pre-check, so the count is the rows actually
    written.
    """
    if not rows:
        return 0
    values = [
        {
            "id": uuid.uuid4(),
            "assessment_id": assessment_id,
            "ordinal": row.ordinal,
            "function": row.function,
            "stance": row.stance,
            "proposed_action": row.proposed_action,
            "object_ref": row.object_ref,
            "rationale": row.rationale,
            "citations": row.citations,
        }
        for row in sorted(rows, key=lambda row: row.ordinal)
    ]
    statement = insert(RiskPosition).values(values).on_conflict_do_nothing(
        constraint=POSITION_IDENTITY
    )
    # A DML execute returns a CursorResult, whose rowcount is the number of
    # rows ON CONFLICT DO NOTHING did not skip. Session.execute is typed as
    # returning the wider Result.
    result = cast("CursorResult[Any]", session.execute(statement))
    return int(result.rowcount)


def insert_brief(session: Session, row: BriefRow) -> tuple[uuid.UUID, bool]:
    """
    Write a brief, or read back the one `(assessment_id, payload_hash)` already names.

    Returns the row's id and whether this call created it. An existing brief
    is never updated: its narrative and template_version stay as first
    written, whatever this call carries.
    """
    statement = (
        insert(RiskBrief)
        .values(
            id=uuid.uuid4(),
            assessment_id=row.assessment_id,
            policy_version=row.policy_version,
            template_version=row.template_version,
            decision_payload=row.decision_payload,
            payload_hash=row.payload_hash,
            narrative=row.narrative,
        )
        .on_conflict_do_nothing(constraint=BRIEF_IDENTITY)
        .returning(RiskBrief.id)
    )
    inserted = session.execute(statement).scalar_one_or_none()
    if inserted is not None:
        return inserted, True
    existing = session.execute(
        select(RiskBrief.id).where(
            RiskBrief.assessment_id == row.assessment_id,
            RiskBrief.payload_hash == row.payload_hash,
        )
    ).scalar_one()
    return existing, False
