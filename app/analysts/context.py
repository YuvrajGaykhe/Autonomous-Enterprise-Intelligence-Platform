"""
The two analyst contexts, and the one factory that builds them (VS-01 M5).

**This is the only module in app/analysts/ permitted a Session or an ORM
model** (§0.4.7). The analysts receive a context and nothing else, so scope is
enforced by construction rather than by convention: support_risk.py and
commercial.py cannot widen what they see, because they have nothing to widen
it with.

**SupportContext never holds a SignalSet** (§0.4.9 D-M5-B7). Frozen SignalSet
is one dataclass carrying all sixteen signal fields, so a `signals: SignalSet`
field would hand Support active_deals, exposure_by_currency,
active_project_count, contract_document_ids and deal_under_pressure -- every
value §A14 forbids it -- while still passing a purity test that only looks for
a DealSignal, MoneyValue or Decimal field. SupportSignals is the projection
that closes that: the eleven S1-S10 fields, same names, same types, same
values, and **no field for S11-S15 to land in**. The exclusion is structural,
not documented.

**TicketFact is an M5-owned derivation pinned to M3's signals** (§0.4.2). M3's
_Ticket is private to a frozen module and CustomerSignals carries no ticket
attributes, so the rows §A14 calls "Tickets" have to be derived here. No rule
is re-authored: open-ness, the created_at exclusions and the breach arithmetic
are M3's, restated from their statement in the plan and computed with M1's
public timeutil and the policy's own sla_resolution_targets. Because two
implementations of one stated rule now exist, an equivalence test binds this
derivation to S1, S2, S2b, S7 and S8 for every customer at two dates, so
drift is a build failure rather than a latent defect.

**M2's open-ticket rule is deliberately not used.** escalation_path() reports
`status == 'open'` with no as_of; M3's rule ignores status and tests the
resolution date against as_of (§0.2.1: "The resolution *date* decides, not
`status`"). S1, S2, S8 and therefore the band are built on M3's, so this
module uses M3's and reads `status` nowhere at all.

**Contexts are data, not behaviour.** Evaluating §A16's preconditions is the
analysts' work and lives in base.py and the two analyst modules, so nothing
here reads a catalogue threshold. That also keeps the import direction
one-way: base.py reads this module, and this module reads no part of it.

**Nothing here writes.** The factory receives a session and never opens,
commits, rolls back or closes one; it derives no link and persists nothing.
Deriving links is the assessment run's, which is M7's (§0.4.3), so a run that
forgets to derive hands S14 an empty tuple -- which is why M5's acceptance
asserts ("DOC-006",) reaches CommercialContext rather than merely asserting
that the call happened.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evidence import documents_for, with_contract_documents
from app.intelligence import EntityRef, Scope, business_days_between, utc_date
from app.intelligence.bands import assign_band
from app.intelligence.config import EscalationPolicy, RiskRulesConfig, default_risk_rules
from app.intelligence.contract import DealSignal, RiskBand, SignalSet
from app.intelligence.signals import (
    DEALS,
    NEGOTIATION_STAGE,
    SUPPORT_TICKETS,
    compute_signals,
)
from app.persistence.models import SupportTicket
from app.relationships import neighbourhood, policy_documents

#: The one Layer 1 ticket category M5 reads, for §A16's REVIEW_INVOICE_DISPUTE.
#: Exact, case-sensitive equality and nothing else: "Billing", "BILLING",
#: " billing" and NULL are not this category, and there is no normalization,
#: case folding, stripping, substring, prefix or synonym rule. This is the
#: discipline §0.3.6 fixed for CONTRACT_DOCUMENT_TYPE and M2 fixed for
#: POLICY_DOCUMENT_TYPE, applied to the one category string M5 reads.
BILLING_CATEGORY = "billing"


@dataclass(frozen=True)
class SupportSignals:
    """
    S1-S10 for one customer: eleven fields, and nothing commercial.

    A projection of frozen SignalSet, not a replacement for it. Every field
    carries SignalSet's own name, type and value, so no second definition of
    any signal exists and nothing needs pinning to M3 the way TicketFact
    does. What makes it worth having is what it leaves out: S11 active_deals,
    S12 exposure_by_currency, S13 active_project_count, S14
    contract_document_ids and S15 deal_under_pressure have no field here, so
    no commercial value can reach a Support analyst by any route.
    """

    open_ticket_count: int
    open_high_priority_count: int
    high_priority_total: int
    tickets_in_lookback: int
    max_tickets_in_14d_window: int
    policy_escalation_state: bool
    days_since_last_ticket: int | None
    sla_breach_count: int
    open_sla_breach_high_count: int
    stale_open_ticket_count: int
    dominant_ticket_category: str | None

    def to_payload(self) -> dict[str, object]:
        return {
            "open_ticket_count": self.open_ticket_count,
            "open_high_priority_count": self.open_high_priority_count,
            "high_priority_total": self.high_priority_total,
            "tickets_in_lookback": self.tickets_in_lookback,
            "max_tickets_in_14d_window": self.max_tickets_in_14d_window,
            "policy_escalation_state": self.policy_escalation_state,
            "days_since_last_ticket": self.days_since_last_ticket,
            "sla_breach_count": self.sla_breach_count,
            "open_sla_breach_high_count": self.open_sla_breach_high_count,
            "stale_open_ticket_count": self.stale_open_ticket_count,
            "dominant_ticket_category": self.dominant_ticket_category,
        }


def support_signals(signals: SignalSet) -> SupportSignals:
    """
    The S1-S10 projection of a SignalSet.

    Pure and total: a field-by-field copy with no session, no clock, no
    derivation, no rounding and no defaulting. It narrows by construction
    rather than by filtering, so there is no branch here that could admit a
    commercial field by mistake.
    """
    return SupportSignals(
        open_ticket_count=signals.open_ticket_count,
        open_high_priority_count=signals.open_high_priority_count,
        high_priority_total=signals.high_priority_total,
        tickets_in_lookback=signals.tickets_in_lookback,
        max_tickets_in_14d_window=signals.max_tickets_in_14d_window,
        policy_escalation_state=signals.policy_escalation_state,
        days_since_last_ticket=signals.days_since_last_ticket,
        sla_breach_count=signals.sla_breach_count,
        open_sla_breach_high_count=signals.open_sla_breach_high_count,
        stale_open_ticket_count=signals.stale_open_ticket_count,
        dominant_ticket_category=signals.dominant_ticket_category,
    )


@dataclass(frozen=True)
class TicketFact:
    """
    One ticket as a Support analyst sees it, already placed in time.

    The smallest shape that answers §A16's ticket-level preconditions and
    grounds a RecordCitation: no subject, no description, no assignee, no
    customer key, no deal, no project and no monetary field. `is_open` and
    `breaches_sla` are evaluated at the scope's as_of, so the tuple is a
    statement about one evaluation date and not a mutable view of a row.
    """

    source_id: str
    priority: str | None
    category: str | None
    is_open: bool
    breaches_sla: bool

    @property
    def is_billing(self) -> bool:
        """Whether §A16's REVIEW_INVOICE_DISPUTE counts this ticket's category."""
        return self.category == BILLING_CATEGORY

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.source_id,
            "priority": self.priority,
            "category": self.category,
            "is_open": self.is_open,
            "breaches_sla": self.breaches_sla,
        }


def ticket_facts(
    session: Session,
    scope: Scope,
    customer_source_id: str,
    *,
    config: RiskRulesConfig,
) -> tuple[TicketFact, ...]:
    """
    The customer's tickets as TicketFact rows, ascending by source_id.

    Membership is M2's, exactly as M3 obtains it: whatever neighbourhood()
    says the customer's tickets are, and nothing else. This function reads
    their attributes and places them in time; it decides no relationship, so
    an unresolved row is invisible to it by construction.

    Placement in time is M3's rule verbatim (§0.2.1, §0.4.2). A ticket with
    no created_at is excluded entirely and produces no note -- it cannot be
    placed in any window, so it is visible at no evaluation date -- and a
    ticket created after as_of is not yet visible.
    """
    around = neighbourhood(session, scope, customer_source_id)
    source_ids = sorted({ref.source_id for ref in around.tickets})
    if not source_ids:
        return ()
    rows = session.execute(
        select(
            SupportTicket.source_id,
            SupportTicket.priority,
            SupportTicket.category,
            SupportTicket.created_at,
            SupportTicket.resolved_at,
        )
        .where(
            SupportTicket.source_system == scope.source_system,
            SupportTicket.source_entity == SUPPORT_TICKETS,
            SupportTicket.source_id.in_(source_ids),
        )
        .order_by(SupportTicket.source_id)
    ).all()
    targets = config.sla_resolution_targets
    facts = []
    for source_id, priority, category, created_at, resolved_at in rows:
        if created_at is None:
            continue
        created = utc_date(created_at)
        if created > scope.as_of:
            continue
        resolved = None if resolved_at is None else utc_date(resolved_at)
        facts.append(TicketFact(
            source_id=source_id,
            priority=priority,
            category=category,
            is_open=_is_open(resolved, scope.as_of),
            breaches_sla=_breaches_sla(created, resolved, scope.as_of, priority, targets),
        ))
    return tuple(facts)


def _is_open(resolved: date | None, as_of: date) -> bool:
    """
    Open when no resolution date falls on or before the evaluation date.

    M3's rule verbatim. `status` is not read, is not consulted as a fallback
    and does not break a tie, and M2's status-based definition is
    deliberately not used here (§0.4.2).
    """
    return resolved is None or resolved > as_of


def _breaches_sla(
    created: date,
    resolved: date | None,
    as_of: date,
    priority: str | None,
    targets: Mapping[str, int],
) -> bool:
    """
    Whether elapsed business days exceed DOC-003's target for the priority.

    A priority the policy does not name, and a NULL priority, have no target
    and therefore cannot breach: inventing one would manufacture breaches
    DOC-003 never states. Resolved tickets are measured created to resolved,
    open ones created to as_of (§A5).
    """
    target = targets.get(priority or "")
    if target is None:
        return False
    end = resolved if (resolved is not None and resolved <= as_of) else as_of
    return business_days_between(created, end) > target


@dataclass(frozen=True)
class SupportContext:
    """
    Everything SupportRiskAnalyst may see, and nothing it may not.

    The two commercial scalars are the whole of Support's commercial
    visibility, and each exists because §A16 requires it:

    `has_active_deal` carries S11 > 0 -- **any stage** -- so
    SCHEDULE_EXECUTIVE_SPONSOR_CALL can be evaluated as the frozen `S5 and
    S11 > 0` rather than narrowed to negotiation deals (§0.4.9 D-M5-B9). It
    is a boolean, not a count: no amount, no currency, no stage, no
    probability, no identity, not even how many.

    `contested_deal` carries the active negotiation deal's identity and
    nothing about it, so PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED can name the
    object it contests. §A15's conflict is "over the same object identity",
    and Position.object_ref is a required non-empty field of M1's frozen
    contract, so without an identity the slice's central conflict would be
    structurally inexpressible (§0.4.6). An (entity_type, source_id) pair
    supports no commercial reasoning: exposure, ranking and every §A15
    ordering term need attributes this context does not have.

    **The two are not interchangeable.** has_active_deal is true for a
    customer whose only active deal is in qualification, where contested_deal
    is None; substituting either for the other silently narrows or widens a
    frozen §A16 rule, which is the defect §0.4.9 D-M5-B9 corrected.
    """

    customer: EntityRef
    signals: SupportSignals
    band: str
    satisfied_rules: tuple[str, ...]
    tickets: tuple[TicketFact, ...]
    sla_targets: Mapping[str, int]
    escalation: EscalationPolicy
    policy_documents: tuple[EntityRef, ...]
    has_active_deal: bool
    contested_deal: EntityRef | None


@dataclass(frozen=True)
class CommercialContext:
    """
    Everything CommercialAnalyst may see: the full SignalSet, S14 populated.

    No projection is needed. S11, S12, S13, S14 and S15 are exactly what §A14
    grants this function, and they live on the SignalSet that
    with_contract_documents() returns. S1-S10 come along as a by-product of
    holding that set, which is deliberate and not an oversight: §A14's two
    prohibitions are not the same kind -- Support may hold no deal, project or
    monetary **field**, a prohibition on values, while Commercial may hold no
    ticket **record**, a prohibition on rows. TicketFact is a record and is
    absent here; S1-S10 are aggregates. S15 is itself defined in terms of S5,
    so denying Commercial every ticket aggregate would make its own signal
    unexplainable (§0.4.9 D-M5-B7).
    """

    customer: EntityRef
    signals: SignalSet
    band: str
    satisfied_rules: tuple[str, ...]


@dataclass(frozen=True)
class AnalystContexts:
    """Both contexts, built together from one snapshot at one evaluation date."""

    support: SupportContext
    commercial: CommercialContext


def build_contexts(
    session: Session,
    scope: Scope,
    customer_source_id: str,
    *,
    config: RiskRulesConfig | None = None,
) -> AnalystContexts:
    """
    Both analyst contexts for one customer, at one scope.

    Deterministic, side-effect-free and read-only, and **not functionally
    pure**: it performs database reads, and it does not claim otherwise.
    Same database state and same scope give the same output; no clock, no
    randomness, no write, no log. Determinism and purity are independent
    properties (§0.4.7), and both are independent of the *field-scope* rule
    that governs what a context may hold.

    The caller owns the session, exactly as every Layer 1 repository and both
    earlier Layer 2 packages require. This function receives one and never
    creates, opens, commits, rolls back or closes it.

    **S14 is populated here, through M4 and only through M4** -- this is the
    production invocation §0.3.6 B assigned to M5. documents_for() reads the
    links the assessment run persisted and with_contract_documents() composes
    them onto a new SignalSet. Nothing is re-derived, no DerivedLink or
    LinkedDocument is constructed, and the link table is never queried from
    here. A run that never derived leaves S14 an empty tuple, which is
    indistinguishable from a customer with no contract -- the hazard §0.4.3
    records, and the reason the ordering belongs to M7.

    The band is assigned once and shared by both contexts. It is computed
    from the S14-populated set, which changes nothing: no band rule reads
    contract_document_ids, and §A10 classifies S14 as evidence only.
    """
    rules = config if config is not None else default_risk_rules()
    computed = compute_signals(session, scope, customer_source_id, config=rules)
    links = documents_for(session, scope, customer_source_id)
    commercial_signals = with_contract_documents(computed.signals, links)
    policies = policy_documents(session, scope)
    facts = ticket_facts(session, scope, customer_source_id, config=rules)
    band = assign_band(commercial_signals, rules.band_rules, floor=str(RiskBand.NONE))
    active_deals = computed.signals.active_deals
    return AnalystContexts(
        support=SupportContext(
            customer=computed.customer,
            signals=support_signals(computed.signals),
            band=band.band,
            satisfied_rules=band.satisfied_rules,
            tickets=facts,
            sla_targets=rules.sla_resolution_targets,
            escalation=rules.escalation,
            policy_documents=policies,
            has_active_deal=len(active_deals) > 0,
            contested_deal=contested_deal(active_deals),
        ),
        commercial=CommercialContext(
            customer=computed.customer,
            signals=commercial_signals,
            band=band.band,
            satisfied_rules=band.satisfied_rules,
        ),
    )


def contested_deal(deals: Sequence[DealSignal]) -> EntityRef | None:
    """
    The active negotiation deal Support may name, or None.

    Pure. Where more than one exists the lexicographically smallest source_id
    is contested, and §0.4.1's "one per qualifying deal" multiplicity for
    PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED is bounded to that single deal. No
    customer in the demo dataset has two, so the tiebreak is exercised only by
    a fixture and is recorded as a known limitation (§A29) rather than a
    behaviour the dataset proves.

    Only the identity crosses into SupportContext: stage, probability and
    amount are read to choose the deal and are then left behind.
    """
    negotiating = sorted(
        deal.source_id for deal in deals if deal.stage == NEGOTIATION_STAGE
    )
    if not negotiating:
        return None
    return EntityRef(DEALS, negotiating[0])
