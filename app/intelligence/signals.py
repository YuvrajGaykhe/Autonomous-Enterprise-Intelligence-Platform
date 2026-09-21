"""
The signal engine: S1-S15 computed as of a scope date (VS-01 M3).

This module measures. It does not decide what a customer is connected to,
and that separation is the point.

    Membership comes from M2.   Which tickets, deals and projects belong to
                                a customer is a relationship question, and
                                app/relationships answers it once, with a
                                basis on every edge. This module calls
                                neighbourhood() and reads the attributes of
                                the rows it names. It joins nothing, so it
                                cannot become a second resolver: a
                                relationship engine has to join, and a
                                boundary test asserts there is no join here.
    Documents are unreachable.  No signal is derived from a document link
                                (plan A11). S14 stays empty until M4, which
                                owns every Document to Customer association;
                                this module imports neither app.evidence nor
                                the Document model, so a document-derived
                                signal cannot be written here even by
                                accident.
    Data quality is separate.   Plan A23 requires three states to stay
                                distinct: a NULL source key is a *missing*
                                relationship, a non-NULL source key with no
                                resolvable target is an *unresolved* one, and
                                a resolved key is a valid relationship. The
                                first two are reported as observations and
                                drive no signal and no band. They are read
                                straight from two frozen Layer 1 columns of
                                one table at a time - the one place this
                                module looks past M2, and the only thing it
                                looks for.

What "open" means, stated once. A ticket is open at as_of when it carries no
resolution date on or before as_of. The date decides, not the status column:
status records the row's state today, while an assessment states the state on
its evaluation date, and a ticket resolved after as_of was open then. Where
the two disagree the date is the field with the evidence.

A ticket with no created_at cannot be placed in time, so it is visible at no
as_of and contributes to nothing. A deal that cannot state its stage, amount,
currency and probability cannot be built into M1's DealSignal, so it is not a
commercial signal; M1's frozen contract decides that, not this module.

Nothing here writes, commits, logs or reads a clock. The caller owns the
session, matching the repository convention.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.config import RiskRulesConfig, default_risk_rules
from app.intelligence.contract import DealSignal, EntityRef, SignalSet
from app.intelligence.errors import ContractViolationError
from app.intelligence.money import MoneyValue
from app.intelligence.scope import Scope
from app.intelligence.timeutil import business_days_between, utc_date
from app.intelligence.windows import (
    WindowCount,
    dates_in_lookback,
    lookback_window,
    max_window,
)
from app.persistence.models import Customer, Deal, Project, SupportTicket
from app.relationships import neighbourhood

#: Canonical entity types this module reads. A test pins each one against
#: Layer 1's ENTITY_MODELS, so a rename cannot leave a literal behind.
CUSTOMERS = "customers"
SUPPORT_TICKETS = "support_tickets"
DEALS = "deals"
PROJECTS = "projects"

#: The deal stage that makes an escalation a conflict (plan A10, S15; A16).
NEGOTIATION_STAGE = "negotiation"

#: The priority whose open breaches drive the band (plan A10, S2, S8).
HIGH_PRIORITY = "high"

#: The three entities carrying a customer source key that E1 resolves.
#: Plan A9.1 row 2: these are the only CANONICAL_FK edges VS-01 can emit,
#: so they are also the only places a customer relationship can go missing.
CUSTOMER_CARRIERS: Mapping[str, str] = MappingProxyType({
    SUPPORT_TICKETS: "support_tickets.customer_source_id",
    DEALS: "deals.customer_source_id",
    PROJECTS: "projects.customer_source_id",
})

_CARRIER_MODELS: Mapping[str, Any] = MappingProxyType({
    SUPPORT_TICKETS: SupportTicket, DEALS: Deal, PROJECTS: Project,
})


class DataQualityState(StrEnum):
    """
    Why a row has no customer, kept as two states rather than one.

    Plan A23 separates them because the remedies differ and collapsing them
    hides which one applies. A missing key means the source never stated a
    customer. An unresolved key means the source stated one and Layer 1
    could not find it - a different fault, in a different system, needing a
    different fix.
    """

    #: The carrier column is NULL: the source named no customer at all.
    MISSING_SOURCE_KEY = "MISSING_SOURCE_KEY"
    #: The carrier column holds a key E1 could not resolve in this scope.
    UNRESOLVED_SOURCE_KEY = "UNRESOLVED_SOURCE_KEY"


@dataclass(frozen=True)
class DataQualityNote:
    """
    One row excluded from a customer's signals, and why.

    Informational only. A note never contributes to a signal, a band or a
    ranking: plan A23 requires such a row to be reported rather than
    silently dropped, not to be counted as though it were resolved.
    """

    entity_type: str
    source_id: str
    carrier_field: str
    state: DataQualityState
    customer_source_id: str | None

    def __post_init__(self) -> None:
        missing = self.state is DataQualityState.MISSING_SOURCE_KEY
        if missing != (self.customer_source_id is None):
            raise ContractViolationError(
                f"{self.state} does not describe customer_source_id="
                f"{self.customer_source_id!r}: a missing key is NULL and an unresolved one "
                f"is not, and collapsing the two is what plan A23 forbids"
            )

    @property
    def sort_key(self) -> tuple[str, str]:
        """Total order: entity type, then source identity."""
        return (self.entity_type, self.source_id)

    def to_payload(self) -> dict[str, object]:
        """Deterministic projection. Carries no timestamp and no run id."""
        return {
            "entity": self.entity_type,
            "id": self.source_id,
            "carrier_field": self.carrier_field,
            "state": str(self.state),
            "customer_source_id": self.customer_source_id,
        }


@dataclass(frozen=True)
class CustomerSignals:
    """Every signal for one customer at one scope, with what explains them."""

    customer: EntityRef
    signals: SignalSet
    escalation_window: WindowCount | None
    backlog_ticket_ids: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "customer": self.customer.to_payload(),
            "signals": self.signals.to_payload(),
            "escalation_window": (
                None if self.escalation_window is None else self.escalation_window.to_payload()
            ),
            "backlog_ticket_ids": list(self.backlog_ticket_ids),
        }


@dataclass(frozen=True)
class _Ticket:
    """One ticket as the signal engine sees it, already placed in time."""

    source_id: str
    priority: str | None
    category: str | None
    created: date
    resolved: date | None

    def is_open_at(self, as_of: date) -> bool:
        """Open when no resolution date falls on or before the evaluation date."""
        return self.resolved is None or self.resolved > as_of

    def breaches(self, as_of: date, targets: Mapping[str, int]) -> bool:
        """
        Whether elapsed business days exceed DOC-003's target for the priority.

        A priority the policy does not name has no target, so it cannot
        breach: inventing one would manufacture breaches the document never
        states. Resolved tickets are measured created to resolved, open ones
        created to as_of (plan A5).
        """
        target = targets.get(self.priority or "")
        if target is None:
            return False
        resolved = self.resolved
        end = resolved if (resolved is not None and resolved <= as_of) else as_of
        return business_days_between(self.created, end) > target


def data_quality_notes(session: Session, scope: Scope) -> tuple[DataQualityNote, ...]:
    """
    Every row in scope whose customer relationship is missing or unresolved.

    Read one table at a time from two frozen Layer 1 columns: the carrier
    key the source supplied, and the canonical FK E1 either resolved or did
    not. No join is needed and none is performed - resolving a relationship
    is M2's job, and this is the complement of that job, which M2's queries
    cannot express because an edge that does not exist has nothing to carry
    a basis.

    A cross-source key falls out of the same read: E1 resolves within one
    source system, so a key naming a customer of another system leaves the
    FK NULL and is reported as unresolved, which is exactly what it is.
    """
    notes: list[DataQualityNote] = []
    for entity_type, carrier_field in sorted(CUSTOMER_CARRIERS.items()):
        model = _CARRIER_MODELS[entity_type]
        rows = session.execute(
            select(model.source_id, model.customer_source_id)
            .where(
                model.source_system == scope.source_system,
                model.source_entity == entity_type,
                model.customer_id.is_(None),
            )
            .order_by(model.source_id)
        ).all()
        notes.extend(
            DataQualityNote(
                entity_type=entity_type,
                source_id=source_id,
                carrier_field=carrier_field,
                state=(
                    DataQualityState.MISSING_SOURCE_KEY
                    if customer_source_id is None
                    else DataQualityState.UNRESOLVED_SOURCE_KEY
                ),
                customer_source_id=customer_source_id,
            )
            for source_id, customer_source_id in rows
        )
    return tuple(sorted(notes, key=lambda note: note.sort_key))


def customers_in_scope(session: Session, scope: Scope) -> tuple[str, ...]:
    """
    Every customer source id in scope, in source-identity order.

    A roster, not a relationship: one column of one table, explicitly
    ordered because PostgreSQL guarantees no row order without it.
    """
    rows = session.scalars(
        select(Customer.source_id)
        .where(
            Customer.source_system == scope.source_system,
            Customer.source_entity == CUSTOMERS,
        )
        .order_by(Customer.source_id)
    ).all()
    return tuple(rows)


def compute_signals(
    session: Session,
    scope: Scope,
    customer_source_id: str,
    *,
    config: RiskRulesConfig | None = None,
) -> CustomerSignals:
    """
    S1-S15 for one customer, as of the scope's evaluation date.

    The customer's tickets, deals and projects are whatever M2's
    neighbourhood says they are. This function reads their attributes and
    counts; it never decides membership, and an unresolved row is invisible
    to it by construction because no edge reaches it.
    """
    rules = config if config is not None else default_risk_rules()
    around = neighbourhood(session, scope, customer_source_id)
    tickets = _tickets(session, scope, [ref.source_id for ref in around.tickets])
    deals = _active_deals(session, scope, [ref.source_id for ref in around.deals])
    projects = _active_project_count(session, scope, [ref.source_id for ref in around.projects])
    return _assemble(around.customer, tickets, deals, projects, scope.as_of, rules)


def compute_all_signals(
    session: Session, scope: Scope, *, config: RiskRulesConfig | None = None
) -> tuple[CustomerSignals, ...]:
    """Signals for every customer in scope, in source-identity order."""
    rules = config if config is not None else default_risk_rules()
    return tuple(
        compute_signals(session, scope, source_id, config=rules)
        for source_id in customers_in_scope(session, scope)
    )


def _assemble(
    customer: EntityRef,
    tickets: Sequence[_Ticket],
    deals: Sequence[DealSignal],
    active_project_count: int,
    as_of: date,
    rules: RiskRulesConfig,
) -> CustomerSignals:
    """Turn the rows M2 named into the signal set plan A10 defines."""
    lookback = rules.lookback_days
    targets = rules.sla_resolution_targets
    open_tickets = [ticket for ticket in tickets if ticket.is_open_at(as_of)]
    high = [ticket for ticket in tickets if ticket.priority == HIGH_PRIORITY]
    open_high = [ticket for ticket in open_tickets if ticket.priority == HIGH_PRIORITY]
    in_lookback = dates_in_lookback((t.created for t in tickets), as_of, lookback)
    window = max_window(
        [ticket.created for ticket in tickets],
        as_of,
        window_days=rules.escalation.window_days,
        lookback_days=lookback,
    )
    escalated = window is not None and window.count >= rules.escalation.ticket_threshold
    lookback_start, _ = lookback_window(as_of, lookback)
    backlog = [
        ticket for ticket in open_tickets
        if ticket.breaches(as_of, targets) and ticket.created < lookback_start
    ]
    negotiating = any(deal.stage == NEGOTIATION_STAGE for deal in deals)
    signals = SignalSet(
        open_ticket_count=len(open_tickets),
        open_high_priority_count=len(open_high),
        high_priority_total=len(high),
        tickets_in_lookback=len(in_lookback),
        max_tickets_in_14d_window=0 if window is None else window.count,
        policy_escalation_state=escalated,
        days_since_last_ticket=_days_since_last_ticket(tickets, as_of),
        sla_breach_count=sum(1 for t in tickets if t.breaches(as_of, targets)),
        open_sla_breach_high_count=sum(1 for t in open_high if t.breaches(as_of, targets)),
        stale_open_ticket_count=len(backlog),
        dominant_ticket_category=_dominant_category(tickets, as_of, lookback),
        active_deals=tuple(deals),
        exposure_by_currency=_exposure(deals),
        active_project_count=active_project_count,
        # S14 is evidence, and every Document to Customer association is M4's
        # (plan A11). M3 cannot name one, so it states none.
        contract_document_ids=(),
        deal_under_pressure=escalated and negotiating,
    )
    return CustomerSignals(
        customer=customer,
        signals=signals,
        escalation_window=window,
        backlog_ticket_ids=tuple(ticket.source_id for ticket in backlog),
    )


def _days_since_last_ticket(tickets: Sequence[_Ticket], as_of: date) -> int | None:
    """None when the customer has never raised a ticket - an absence, not a zero."""
    if not tickets:
        return None
    return (as_of - max(ticket.created for ticket in tickets)).days


def _dominant_category(
    tickets: Sequence[_Ticket], as_of: date, lookback_days: int
) -> str | None:
    """
    The most common category among tickets in the lookback window.

    Ties break on the lexicographically smallest name, so the answer does
    not depend on the order rows arrived in. Uncategorised tickets are not
    a category and are not counted.
    """
    start, end = lookback_window(as_of, lookback_days)
    counts: dict[str, int] = {}
    for ticket in tickets:
        if ticket.category and start <= ticket.created <= end:
            counts[ticket.category] = counts.get(ticket.category, 0) + 1
    if not counts:
        return None
    return min(counts, key=lambda name: (-counts[name], name))


def _exposure(deals: Sequence[DealSignal]) -> Mapping[str, MoneyValue]:
    """
    Active deal value per currency. Never a total across currencies.

    MoneyValue.total states the currency it is totalling and raises on any
    other, so a cross-currency sum cannot be written here even by mistake
    (plan A12). VS-01 publishes no FX rate set, so no portfolio figure
    exists to publish.
    """
    currencies = sorted({deal.amount.currency for deal in deals})
    return MappingProxyType({
        currency: MoneyValue.total(
            currency, [d.amount for d in deals if d.amount.currency == currency]
        )
        for currency in currencies
    })


def _tickets(
    session: Session, scope: Scope, source_ids: Sequence[str]
) -> tuple[_Ticket, ...]:
    """
    The named tickets, in source-identity order, placed in UTC time.

    A ticket with no created_at is dropped: it cannot be placed in any
    window, so it is visible at no evaluation date. A ticket created after
    as_of is not yet visible to an assessment that names that date.
    """
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
            SupportTicket.source_id.in_(sorted(set(source_ids))),
        )
        .order_by(SupportTicket.source_id)
    ).all()
    tickets = []
    for source_id, priority, category, created_at, resolved_at in rows:
        if created_at is None:
            continue
        created = utc_date(created_at)
        if created > scope.as_of:
            continue
        tickets.append(_Ticket(
            source_id=source_id,
            priority=priority,
            category=category,
            created=created,
            resolved=_resolved_date(resolved_at),
        ))
    return tuple(tickets)


def _resolved_date(resolved_at: datetime | None) -> date | None:
    return None if resolved_at is None else utc_date(resolved_at)


def _active_deals(
    session: Session, scope: Scope, source_ids: Sequence[str]
) -> tuple[DealSignal, ...]:
    """
    The customer's active deals as M1's DealSignal, in source-identity order.

    A deal missing its stage, amount, currency or probability cannot be
    built into a DealSignal at all - M1's contract requires every one of
    them - so it is not a commercial signal. That is M1's frozen decision
    about what a describable deal is, not a rule invented here.
    """
    if not source_ids:
        return ()
    rows = session.execute(
        select(Deal.source_id, Deal.stage, Deal.amount, Deal.currency, Deal.probability)
        .where(
            Deal.source_system == scope.source_system,
            Deal.source_entity == DEALS,
            Deal.is_active.is_(True),
            Deal.source_id.in_(sorted(set(source_ids))),
        )
        .order_by(Deal.source_id)
    ).all()
    deals = []
    for source_id, stage, amount, currency, probability in rows:
        if stage is None or amount is None or currency is None or probability is None:
            continue
        deals.append(DealSignal(
            source_id=source_id,
            stage=stage,
            probability=Decimal(probability),
            amount=MoneyValue(amount=Decimal(amount), currency=currency),
        ))
    return tuple(deals)


def _active_project_count(
    session: Session, scope: Scope, source_ids: Sequence[str]
) -> int:
    """How many of the named projects are active. is_active is NOT NULL in Layer 1."""
    if not source_ids:
        return 0
    rows = session.scalars(
        select(Project.source_id)
        .where(
            Project.source_system == scope.source_system,
            Project.source_entity == PROJECTS,
            Project.is_active.is_(True),
            Project.source_id.in_(sorted(set(source_ids))),
        )
        .order_by(Project.source_id)
    ).all()
    return len(rows)
