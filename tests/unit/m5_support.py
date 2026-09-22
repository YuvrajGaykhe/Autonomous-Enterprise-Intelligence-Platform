"""
Hand-built analyst contexts for the M5 unit suite.

Not a test module. These builders exist so a precondition can be exercised at
a combination of signals the demo dataset does not contain -- which is the
whole point of §0.4.6's and §0.4.9 D-M5-B9's rejected shortcuts: both were
invisible on this dataset, and only a fixture that walks off it can tell the
frozen rule from the narrowed one.

Every value here is explicit. Nothing defaults to "whatever CUST-007 has",
because a default that happens to satisfy a precondition is exactly how a
divergence stays hidden.
"""

from __future__ import annotations

from decimal import Decimal
from types import MappingProxyType

from app.analysts.context import (
    CommercialContext,
    SupportContext,
    SupportSignals,
    TicketFact,
)
from app.intelligence.config import EscalationPolicy
from app.intelligence.contract import DealSignal, EntityRef, SignalSet
from app.intelligence.money import MoneyValue

CUSTOMER = "CUST-999"
SLA_TARGETS = MappingProxyType({"high": 1, "medium": 5})
ESCALATION = EscalationPolicy(
    window_days=14, ticket_threshold=3, because_documents=("DOC-003",)
)
POLICY_DOCUMENTS = (EntityRef("documents", "DOC-003"),)

#: The eleven S1-S10 values a customer with nothing to report has.
QUIET_SIGNALS = {
    "open_ticket_count": 0,
    "open_high_priority_count": 0,
    "high_priority_total": 0,
    "tickets_in_lookback": 0,
    "max_tickets_in_14d_window": 0,
    "policy_escalation_state": False,
    "days_since_last_ticket": None,
    "sla_breach_count": 0,
    "open_sla_breach_high_count": 0,
    "stale_open_ticket_count": 0,
    "dominant_ticket_category": None,
}


def support_signal_values(**overrides: object) -> dict[str, object]:
    """The quiet S1-S10 values with named fields replaced."""
    unknown = set(overrides) - set(QUIET_SIGNALS)
    if unknown:
        raise AssertionError(f"not an S1-S10 field: {sorted(unknown)}")
    return {**QUIET_SIGNALS, **overrides}


def deal(
    source_id: str = "DEAL-999",
    stage: str = "negotiation",
    probability: int = 90,
    amount: str = "1000.00",
    currency: str = "USD",
) -> DealSignal:
    """One active deal, with every commercial attribute named rather than defaulted."""
    return DealSignal(
        source_id=source_id,
        stage=stage,
        probability=Decimal(probability),
        amount=MoneyValue(amount=Decimal(amount), currency=currency),
    )


def ticket(
    source_id: str = "TKT-999",
    *,
    priority: str | None = "high",
    category: str | None = "performance",
    is_open: bool = True,
    breaches_sla: bool = True,
) -> TicketFact:
    """One TicketFact, already placed in time by the caller's choice."""
    return TicketFact(
        source_id=source_id,
        priority=priority,
        category=category,
        is_open=is_open,
        breaches_sla=breaches_sla,
    )


def support_context(
    *,
    customer: str = CUSTOMER,
    tickets: tuple[TicketFact, ...] = (),
    band: str = "NONE",
    satisfied_rules: tuple[str, ...] = (),
    has_active_deal: bool = False,
    contested_deal: EntityRef | None = None,
    **signal_overrides: object,
) -> SupportContext:
    """A SupportContext whose commercial visibility is stated, never inferred."""
    return SupportContext(
        customer=EntityRef("customers", customer),
        signals=SupportSignals(**support_signal_values(**signal_overrides)),  # type: ignore[arg-type]
        band=band,
        satisfied_rules=satisfied_rules,
        tickets=tickets,
        sla_targets=SLA_TARGETS,
        escalation=ESCALATION,
        policy_documents=POLICY_DOCUMENTS,
        has_active_deal=has_active_deal,
        contested_deal=contested_deal,
    )


def signal_set(
    *,
    deals: tuple[DealSignal, ...] = (),
    contract_document_ids: tuple[str, ...] = (),
    active_project_count: int = 0,
    deal_under_pressure: bool = False,
    **signal_overrides: object,
) -> SignalSet:
    """A full sixteen-field SignalSet: the S1-S10 values plus S11-S15."""
    currencies = sorted({one.amount.currency for one in deals})
    return SignalSet(
        **support_signal_values(**signal_overrides),  # type: ignore[arg-type]
        active_deals=deals,
        exposure_by_currency=MappingProxyType({
            currency: MoneyValue.total(
                currency, [one.amount for one in deals if one.amount.currency == currency]
            )
            for currency in currencies
        }),
        active_project_count=active_project_count,
        contract_document_ids=contract_document_ids,
        deal_under_pressure=deal_under_pressure,
    )


def commercial_context(
    *,
    customer: str = CUSTOMER,
    band: str = "NONE",
    satisfied_rules: tuple[str, ...] = (),
    signals: SignalSet | None = None,
    **signal_overrides: object,
) -> CommercialContext:
    """A CommercialContext over a full SignalSet."""
    return CommercialContext(
        customer=EntityRef("customers", customer),
        signals=signal_set(**signal_overrides) if signals is None else signals,
        band=band,
        satisfied_rules=satisfied_rules,
    )
