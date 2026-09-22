"""
The Support function's reading of a customer (VS-01 M5, §A16).

Five of §A16's six non-`NO_ACTION` entries are Support's, and this module
evaluates each precondition **literally**, in the words §A16 states it:

    ESCALATE_TO_ACCOUNT_OWNER_PER_SLA        S5
    SCHEDULE_EXECUTIVE_SPONSOR_CALL          S5 and S11 > 0
    ASSIGN_DEDICATED_SUPPORT_OWNER           S8 >= 2
    PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED   S8 >= 1 and an active negotiation deal
    REVIEW_INVOICE_DISPUTE                   an open `billing` ticket

**Two of those terms are commercial, and neither is a proxy.** `S11 > 0` is
read as `context.has_active_deal` -- any stage -- and "an active negotiation
deal" as `context.contested_deal is not None`. Swapping them is the exact
defect §0.4.9 D-M5-B9 corrected: a customer with `S5` true and an active
`qualification` deal satisfies the sponsor rule and not the pause rule, and on
the demo dataset that divergence is invisible because `S5` is true for
CUST-007 alone. `S15 deal_under_pressure` is rejected for the same reason
(§0.4.6): it is a different predicate and, being a boolean, could not supply
`object_ref` anyway.

**This module imports neither Session nor any ORM model.** It reads the
context it was constructed with and nothing else, so there is no route by
which it could widen its scope, and none by which it could learn a deal's
amount, stage or probability.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from app.analysts.base import (
    DEALS,
    DEDICATED_OWNER_BREACH_THRESHOLD,
    PAUSE_BREACH_THRESHOLD,
    SUPPORT_TICKETS,
    Analyst,
    canonical_fact,
)
from app.analysts.context import SupportContext, TicketFact
from app.intelligence.contract import ActionId, Evidence, Function, Position, Stance
from app.intelligence.signals import HIGH_PRIORITY


@dataclass(frozen=True)
class SupportRiskAnalyst(Analyst):
    """
    Support's position on every §A16 entry it satisfies, with citations.

    Constructed with a SupportContext and given nothing else (§A14). The
    result is `tuple[Position, ...]` -- five entries can be satisfied at once,
    and §0.4.1 keeps all of them rather than choosing one.
    """

    FUNCTION: ClassVar[Function] = Function.SUPPORT

    context: SupportContext

    def _proposals(self) -> Iterable[Position]:
        yield from self._escalation_positions()
        yield from self._breach_positions()
        yield from self._billing_positions()

    # -- S5: the policy escalation state ------------------------------------

    def _escalation_positions(self) -> Iterable[Position]:
        """
        The two entries whose first term is S5, both contesting the customer.

        Both are grounded in the creation dates the escalation window counts,
        which is what S5 is computed from. The sponsor call's second term is
        `has_active_deal`, a boolean with no identity, so there is no deal row
        to cite -- see base.py on why citing `contested_deal` instead would be
        wrong rather than merely generous.
        """
        context = self.context
        if not context.signals.policy_escalation_state:
            return
        window = context.escalation
        evidence = [
            canonical_fact(SUPPORT_TICKETS, fact.source_id, "created_at")
            for fact in context.tickets
        ]
        customer = context.customer.source_id
        yield self._position(
            ActionId.ESCALATE_TO_ACCOUNT_OWNER_PER_SLA,
            customer,
            f"{customer} is in the policy escalation state: "
            f"{context.signals.max_tickets_in_14d_window} tickets in a "
            f"{window.window_days}-day window meets the threshold of "
            f"{window.ticket_threshold}.",
            evidence,
        )
        if context.has_active_deal:
            yield self._position(
                ActionId.SCHEDULE_EXECUTIVE_SPONSOR_CALL,
                customer,
                f"{customer} is in the policy escalation state and has at least one "
                f"active deal, so the account warrants an executive sponsor.",
                evidence,
            )

    # -- S8: open high-priority SLA breaches --------------------------------

    def _breach_positions(self) -> Iterable[Position]:
        """
        The two entries whose first term is S8, contesting customer then deal.

        The predicate reads the signal, as §A16 words it; the evidence reads
        the rows behind it, which §0.4.2's equivalence test pins to the same
        number. The pause position is the one Support states on the deal, and
        it is what makes §A15's conflict over DEAL-001 expressible at all.
        """
        context = self.context
        breaches = context.signals.open_sla_breach_high_count
        if breaches < PAUSE_BREACH_THRESHOLD:
            return
        breaching = _open_high_priority_breaches(context.tickets)
        evidence = [
            citation
            for fact in breaching
            for citation in (
                canonical_fact(SUPPORT_TICKETS, fact.source_id, "created_at"),
                canonical_fact(SUPPORT_TICKETS, fact.source_id, "priority"),
                canonical_fact(SUPPORT_TICKETS, fact.source_id, "resolved_at"),
            )
        ]
        customer = context.customer.source_id
        if breaches >= DEDICATED_OWNER_BREACH_THRESHOLD:
            yield self._position(
                ActionId.ASSIGN_DEDICATED_SUPPORT_OWNER,
                customer,
                f"{customer} has {breaches} open high-priority tickets past their "
                f"SLA target, at or above the threshold of "
                f"{DEDICATED_OWNER_BREACH_THRESHOLD} for a dedicated owner.",
                evidence,
            )
        contested = context.contested_deal
        if contested is not None:
            yield self._position(
                ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED,
                contested.source_id,
                f"{contested.source_id} is in negotiation while {customer} has "
                f"{breaches} open high-priority SLA breaches, so the deal push "
                f"should pause until they are resolved.",
                [*evidence, canonical_fact(DEALS, contested.source_id, "stage")],
                stance=Stance.RESTRAIN,
            )

    # -- The ticket-level entry ---------------------------------------------

    def _billing_positions(self) -> Iterable[Position]:
        """
        One position per open `billing` ticket, each contesting that ticket.

        Category equality is exact and case-sensitive (§0.4.2), so "Billing",
        "BILLING", " billing" and NULL qualify nothing, and open-ness is the
        resolution date's answer rather than `status`'s.
        """
        for fact in self.context.tickets:
            if not (fact.is_open and fact.is_billing):
                continue
            yield self._position(
                ActionId.REVIEW_INVOICE_DISPUTE,
                fact.source_id,
                f"{fact.source_id} is an open ticket categorised "
                f"{fact.category!r} for {self.context.customer.source_id}, so the "
                f"invoice dispute needs review.",
                _ticket_evidence(fact),
            )


def _open_high_priority_breaches(tickets: Iterable[TicketFact]) -> tuple[TicketFact, ...]:
    """The rows S8 counts: open, high priority, past their SLA target."""
    return tuple(
        fact for fact in tickets
        if fact.is_open and fact.priority == HIGH_PRIORITY and fact.breaches_sla
    )


def _ticket_evidence(fact: TicketFact) -> list[Evidence]:
    """The two fields an open-`billing` claim rests on: its category and its openness."""
    return [
        canonical_fact(SUPPORT_TICKETS, fact.source_id, "category"),
        canonical_fact(SUPPORT_TICKETS, fact.source_id, "resolved_at"),
    ]
