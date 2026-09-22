"""
§A16's preconditions, evaluated literally, and the divergences that hid.

Two of Support's preconditions carry a commercial term, and §0.4 rejected a
shortcut for each:

  * `SCHEDULE_EXECUTIVE_SPONSOR_CALL` is `S5 and S11 > 0` -- **any stage**.
    The first §0.4 pass narrowed it to a negotiation deal, and §0.4.9 D-M5-B9
    restored it. On the demo dataset the narrowing is **unobservable**,
    because S5 is true for CUST-007 alone and CUST-007 holds a negotiation
    deal, so only a fixture that walks off the dataset can tell the two apart.
  * `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` needs an active **negotiation**
    deal, not `S15 deal_under_pressure`, which adds an S5 term the rule does
    not carry and could not supply an `object_ref` in any case (§0.4.6).

Both are exercised here at the exact combination that separates them: S5 true
with an active deal that is **not** in negotiation. Under the frozen rules the
sponsor call is proposed and the pause is not; under either rejected shortcut
one of those two flips. That is the whole reason this file exists, and the
assertions are written so a regression to either shortcut fails loudly.
"""

from __future__ import annotations

import pytest

from app.analysts.base import (
    ACCELERATE_PROBABILITY_THRESHOLD,
    DEDICATED_OWNER_BREACH_THRESHOLD,
    PAUSE_BREACH_THRESHOLD,
    order_positions,
)
from app.analysts.commercial import CommercialAnalyst, qualifying_deals
from app.analysts.support_risk import SupportRiskAnalyst
from app.intelligence.contract import ActionId, EntityRef, EvidenceKind, Function, Stance
from tests.unit.m5_support import commercial_context, deal, support_context, ticket

pytestmark = pytest.mark.unit

CONTESTED = EntityRef("deals", "DEAL-999")

#: Three high-priority breaching tickets: enough for every S8 threshold.
BREACHING = (
    ticket("TKT-001", priority="high", breaches_sla=True, is_open=True),
    ticket("TKT-002", priority="high", breaches_sla=True, is_open=True),
    ticket("TKT-003", priority="high", breaches_sla=True, is_open=True),
)
ESCALATING = (
    ticket("TKT-010", breaches_sla=False),
    ticket("TKT-011", breaches_sla=False),
    ticket("TKT-012", breaches_sla=False),
)


def support_actions(**kwargs) -> tuple[ActionId, ...]:
    """The actions Support proposes for one context, in the order it returns them."""
    return tuple(
        position.proposed_action
        for position in SupportRiskAnalyst(context=support_context(**kwargs)).positions()
    )


def commercial_actions(**kwargs) -> tuple[ActionId, ...]:
    return tuple(
        position.proposed_action
        for position in CommercialAnalyst(context=commercial_context(**kwargs)).positions()
    )


# ---------------------------------------------------------------------------
# The divergence that escaped review: S5 and S11 > 0, any stage
# ---------------------------------------------------------------------------


def test_the_sponsor_call_qualifies_on_an_active_deal_that_is_not_in_negotiation():
    """
    §0.4.9 D-M5-B9, the case the demo dataset cannot show. S5 is true and the
    customer's only active deal is in qualification: `S5 and S11 > 0` holds,
    so the sponsor call is proposed. An implementation that read
    `contested_deal is not None` here would silently drop it.
    """
    actions = support_actions(
        tickets=ESCALATING,
        policy_escalation_state=True,
        max_tickets_in_14d_window=3,
        has_active_deal=True,
        contested_deal=None,
    )

    assert ActionId.SCHEDULE_EXECUTIVE_SPONSOR_CALL in actions


def test_the_pause_does_not_qualify_on_an_active_deal_that_is_not_in_negotiation():
    """
    The other half of the same fixture: the pause needs a **negotiation**
    deal, so it is not proposed however many breaches there are. Together
    with the test above this separates the two predicates, so neither can
    become a proxy for the other.
    """
    actions = support_actions(
        tickets=BREACHING,
        policy_escalation_state=True,
        max_tickets_in_14d_window=3,
        open_sla_breach_high_count=3,
        has_active_deal=True,
        contested_deal=None,
    )

    assert ActionId.SCHEDULE_EXECUTIVE_SPONSOR_CALL in actions
    assert ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED not in actions


def test_the_sponsor_call_does_not_qualify_without_any_active_deal():
    """
    `S5 and S11 > 0` with S11 == 0. The escalation entry still fires, because
    its precondition is S5 alone, so this proves the second term is read
    rather than that the whole branch was skipped.
    """
    actions = support_actions(
        tickets=ESCALATING,
        policy_escalation_state=True,
        max_tickets_in_14d_window=3,
        has_active_deal=False,
        contested_deal=None,
    )

    assert ActionId.ESCALATE_TO_ACCOUNT_OWNER_PER_SLA in actions
    assert ActionId.SCHEDULE_EXECUTIVE_SPONSOR_CALL not in actions


def test_the_sponsor_call_does_not_qualify_without_the_escalation_state():
    """The first term, read on its own: a deal without S5 proposes neither entry."""
    actions = support_actions(
        tickets=(ticket(),),
        policy_escalation_state=False,
        has_active_deal=True,
        contested_deal=CONTESTED,
    )

    assert ActionId.ESCALATE_TO_ACCOUNT_OWNER_PER_SLA not in actions
    assert ActionId.SCHEDULE_EXECUTIVE_SPONSOR_CALL not in actions


def test_a_negotiation_deal_satisfies_both_commercial_terms():
    """
    The demo dataset's own case, where the two predicates agree. Asserted so
    the tests above read as a separation rather than as a claim that the
    frozen rules disagree in general.
    """
    actions = support_actions(
        tickets=BREACHING,
        policy_escalation_state=True,
        max_tickets_in_14d_window=3,
        open_sla_breach_high_count=3,
        has_active_deal=True,
        contested_deal=CONTESTED,
    )

    assert ActionId.SCHEDULE_EXECUTIVE_SPONSOR_CALL in actions
    assert ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED in actions


# ---------------------------------------------------------------------------
# S8's two thresholds
# ---------------------------------------------------------------------------


def test_one_breach_pauses_the_deal_but_does_not_assign_a_dedicated_owner():
    """§A16: the pause reads `S8 >= 1`, the dedicated owner `S8 >= 2`."""
    actions = support_actions(
        tickets=BREACHING[:1],
        open_sla_breach_high_count=PAUSE_BREACH_THRESHOLD,
        has_active_deal=True,
        contested_deal=CONTESTED,
    )

    assert ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED in actions
    assert ActionId.ASSIGN_DEDICATED_SUPPORT_OWNER not in actions


def test_two_breaches_assign_a_dedicated_owner():
    actions = support_actions(
        tickets=BREACHING[:2],
        open_sla_breach_high_count=DEDICATED_OWNER_BREACH_THRESHOLD,
    )

    assert ActionId.ASSIGN_DEDICATED_SUPPORT_OWNER in actions


def test_no_breach_proposes_neither_s8_entry():
    actions = support_actions(tickets=BREACHING, open_sla_breach_high_count=0,
                              has_active_deal=True, contested_deal=CONTESTED)

    assert ActionId.ASSIGN_DEDICATED_SUPPORT_OWNER not in actions
    assert ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED not in actions


def test_the_pause_contests_the_deal_and_restrains_it():
    """
    §0.4.1's Object and Stance columns. The object is what makes §A15's
    conflict over one identity expressible; the stance is what makes the
    opposition legible.
    """
    positions = SupportRiskAnalyst(context=support_context(
        tickets=BREACHING,
        open_sla_breach_high_count=3,
        has_active_deal=True,
        contested_deal=CONTESTED,
    )).positions()
    pause = next(
        position for position in positions
        if position.proposed_action is ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED
    )

    assert pause.object_ref == CONTESTED.source_id
    assert pause.stance is Stance.RESTRAIN


# ---------------------------------------------------------------------------
# The ticket-level entry
# ---------------------------------------------------------------------------


def test_one_review_position_is_proposed_per_open_billing_ticket():
    """§0.4.1's multiplicity: one per qualifying ticket, each naming that ticket."""
    positions = SupportRiskAnalyst(context=support_context(tickets=(
        ticket("TKT-050", category="billing", is_open=True),
        ticket("TKT-051", category="billing", is_open=True),
        ticket("TKT-052", category="performance", is_open=True),
    ))).positions()
    reviews = [
        position for position in positions
        if position.proposed_action is ActionId.REVIEW_INVOICE_DISPUTE
    ]

    assert [position.object_ref for position in reviews] == ["TKT-050", "TKT-051"]


def test_a_resolved_billing_ticket_proposes_no_review():
    """The precondition is an **open** billing ticket."""
    actions = support_actions(tickets=(ticket("TKT-050", category="billing", is_open=False),))

    assert actions == ()


@pytest.mark.parametrize("category", ["Billing", "BILLING", " billing", None])
def test_a_near_miss_category_proposes_no_review(category):
    """
    §0.4.8 criterion 3. Exact, case-sensitive equality: a normalising
    implementation would manufacture a position here.
    """
    actions = support_actions(tickets=(ticket("TKT-050", category=category, is_open=True),))

    assert ActionId.REVIEW_INVOICE_DISPUTE not in actions


# ---------------------------------------------------------------------------
# Silence, and what it is not
# ---------------------------------------------------------------------------


def test_a_quiet_customer_draws_no_support_position_at_all():
    """
    §0.4.8 criterion 8: the empty tuple, **not** a NO_ACTION position. §A16
    leaves NO_ACTION's *Proposed by* column empty, so neither analyst emits it.
    """
    assert support_actions(tickets=()) == ()


def test_neither_analyst_ever_emits_no_action():
    """Asserted across a satisfied context too, not only across an empty one."""
    support = support_actions(
        tickets=BREACHING, policy_escalation_state=True, max_tickets_in_14d_window=3,
        open_sla_breach_high_count=3, has_active_deal=True, contested_deal=CONTESTED,
    )
    commercial = commercial_actions(deals=(deal(),))

    assert ActionId.NO_ACTION not in support + commercial


def test_a_ticketless_customer_is_not_silent_commercially():
    """
    §0.4.8 criterion 8's second half: ACCELERATE_DEAL_CLOSE carries no band
    term, so a customer with no tickets and a qualifying deal still speaks.
    """
    assert support_actions(tickets=()) == ()
    assert commercial_actions(deals=(deal(),)) == (ActionId.ACCELERATE_DEAL_CLOSE,)


# ---------------------------------------------------------------------------
# The commercial entry
# ---------------------------------------------------------------------------


def test_the_accelerate_entry_reads_stage_and_probability():
    positions = CommercialAnalyst(
        context=commercial_context(deals=(deal(source_id="DEAL-001"),))
    ).positions()

    assert len(positions) == 1
    assert positions[0].function is Function.SALES
    assert positions[0].object_ref == "DEAL-001"
    assert positions[0].stance is Stance.ADVANCE


@pytest.mark.parametrize("probability", [80, 81, 100])
def test_a_probability_at_or_above_the_threshold_qualifies(probability):
    """"at or above", so the boundary itself qualifies."""
    assert commercial_actions(deals=(deal(probability=probability),)) == (
        ActionId.ACCELERATE_DEAL_CLOSE,
    )


@pytest.mark.parametrize("probability", [0, 79])
def test_a_probability_below_the_threshold_does_not_qualify(probability):
    assert commercial_actions(deals=(deal(probability=probability),)) == ()


@pytest.mark.parametrize("stage", ["qualification", "proposal", "closed_won", "Negotiation"])
def test_a_deal_outside_negotiation_does_not_qualify(stage):
    """Stage equality is exact, matching the constant M3 declares."""
    assert commercial_actions(deals=(deal(stage=stage),)) == ()


def test_two_qualifying_deals_state_two_positions():
    """§0.4.1: one per qualifying deal, nothing merged and nothing ranked."""
    positions = CommercialAnalyst(context=commercial_context(deals=(
        deal(source_id="DEAL-031"),
        deal(source_id="DEAL-004"),
        deal(source_id="DEAL-020", stage="qualification"),
    ))).positions()

    assert [position.object_ref for position in positions] == ["DEAL-004", "DEAL-031"]


def test_qualifying_deals_is_order_independent():
    deals = (deal(source_id="DEAL-009"), deal(source_id="DEAL-002"))

    assert qualifying_deals(deals) == qualifying_deals(tuple(reversed(deals)))


def test_the_threshold_is_a_decimal_so_the_comparison_is_exact():
    """DealSignal.probability is a Decimal; comparing it to a float would coerce."""
    from decimal import Decimal

    assert isinstance(ACCELERATE_PROBABILITY_THRESHOLD, Decimal)


# ---------------------------------------------------------------------------
# Ordering, evidence and determinism
# ---------------------------------------------------------------------------


def test_positions_come_back_ordered_by_function_object_then_action():
    """
    §0.4.1's sort key, and explicitly not a priority: no rule in M5 reads it
    to choose a winner.
    """
    positions = SupportRiskAnalyst(context=support_context(
        customer="CUST-007",
        tickets=(*BREACHING, ticket("TKT-079", priority="medium", category="billing")),
        policy_escalation_state=True,
        max_tickets_in_14d_window=5,
        open_sla_breach_high_count=3,
        has_active_deal=True,
        contested_deal=EntityRef("deals", "DEAL-001"),
    )).positions()

    keys = [
        (str(position.function), position.object_ref, str(position.proposed_action))
        for position in positions
    ]

    assert keys == sorted(keys)


def test_the_ordering_helper_is_stable_against_input_order():
    positions = SupportRiskAnalyst(context=support_context(
        tickets=(ticket("TKT-050", category="billing"), ticket("TKT-049", category="billing")),
    )).positions()

    assert order_positions(reversed(positions)) == positions


def test_every_position_validates_and_carries_at_least_one_canonical_citation():
    """
    §0.4.8 criterion 14. M1 refuses a Position with empty evidence, so this
    asserts the kind and the shape rather than merely that construction
    succeeded.
    """
    support = SupportRiskAnalyst(context=support_context(
        customer="CUST-007",
        tickets=(*BREACHING, ticket("TKT-079", priority="medium", category="billing")),
        policy_escalation_state=True,
        max_tickets_in_14d_window=5,
        open_sla_breach_high_count=3,
        has_active_deal=True,
        contested_deal=EntityRef("deals", "DEAL-001"),
    )).positions()
    commercial = CommercialAnalyst(
        context=commercial_context(deals=(deal(source_id="DEAL-001"),))
    ).positions()

    for position in support + commercial:
        assert position.evidence, position.proposed_action
        assert position.rationale.strip()
        for item in position.evidence:
            assert item.kind is EvidenceKind.CANONICAL_FACT
            assert item.citation.source_id


def test_the_pause_cites_the_deal_it_contests():
    """The contested object is grounded, not merely named."""
    positions = SupportRiskAnalyst(context=support_context(
        tickets=BREACHING,
        open_sla_breach_high_count=3,
        has_active_deal=True,
        contested_deal=CONTESTED,
    )).positions()
    pause = next(
        position for position in positions
        if position.proposed_action is ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED
    )

    assert any(
        item.citation.entity_type == "deals"
        and item.citation.source_id == CONTESTED.source_id
        for item in pause.evidence
    )


def test_the_sponsor_call_cites_no_deal():
    """
    Its second term is a boolean with no identity, so there is no deal row to
    cite. Citing `contested_deal` instead would ground the claim in a
    negotiation deal the frozen rule does not ask about (base.py).
    """
    positions = SupportRiskAnalyst(context=support_context(
        tickets=ESCALATING,
        policy_escalation_state=True,
        max_tickets_in_14d_window=3,
        has_active_deal=True,
        contested_deal=CONTESTED,
    )).positions()
    sponsor = next(
        position for position in positions
        if position.proposed_action is ActionId.SCHEDULE_EXECUTIVE_SPONSOR_CALL
    )

    assert all(item.citation.entity_type == "support_tickets" for item in sponsor.evidence)


def test_two_readings_of_one_context_are_equal():
    """Deterministic: no clock, no randomness, no accumulated state."""
    context = support_context(
        tickets=BREACHING,
        policy_escalation_state=True,
        max_tickets_in_14d_window=3,
        open_sla_breach_high_count=3,
        has_active_deal=True,
        contested_deal=CONTESTED,
    )
    analyst = SupportRiskAnalyst(context=context)

    assert analyst.positions() == analyst.positions()
    assert SupportRiskAnalyst(context=context).positions() == analyst.positions()


def test_each_analyst_speaks_only_for_its_own_function():
    support = SupportRiskAnalyst(context=support_context(
        tickets=BREACHING, open_sla_breach_high_count=3,
        has_active_deal=True, contested_deal=CONTESTED,
    )).positions()
    commercial = CommercialAnalyst(
        context=commercial_context(deals=(deal(),))
    ).positions()

    assert {position.function for position in support} == {Function.SUPPORT}
    assert {position.function for position in commercial} == {Function.SALES}
