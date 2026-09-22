"""
The two context shapes, and the field-scope rule that is their whole point.

§0.4.8 criterion 14 is asserted here by **field-type inspection**, recursively:
a type is forbidden not only when a context declares it directly but when it
can be reached through a member or an element. That recursion is what closes
§0.4.9 D-M5-B7's finding -- `signals: SignalSet` is not literally "a
DealSignal, MoneyValue or Decimal field", yet it carries all three, so a
shallow check passed an implementation that violated its own purpose.

The projection is tested against frozen SignalSet rather than against a list
written out here: `support_signals()` must agree with M1's declared names and
types, and a test that repeated them would drift with the implementation
rather than pin it.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal

import pytest

from app.analysts import context as context_module
from app.analysts.context import (
    BILLING_CATEGORY,
    AnalystContexts,
    CommercialContext,
    SupportContext,
    SupportSignals,
    TicketFact,
    contested_deal,
    support_signals,
)
from app.intelligence.contract import DealSignal, EntityRef, SignalSet
from app.intelligence.money import MoneyValue
from tests.unit.m5_support import (
    commercial_context,
    deal,
    signal_set,
    support_context,
    ticket,
)

pytestmark = pytest.mark.unit

#: §0.4.9 D-M5-B7. The eleven S1-S10 fields, in SignalSet's own order.
S1_TO_S10 = (
    "open_ticket_count",
    "open_high_priority_count",
    "high_priority_total",
    "tickets_in_lookback",
    "max_tickets_in_14d_window",
    "policy_escalation_state",
    "days_since_last_ticket",
    "sla_breach_count",
    "open_sla_breach_high_count",
    "stale_open_ticket_count",
    "dominant_ticket_category",
)

#: §A10 S11-S15, which SupportSignals must have no field for. S14 is named
#: explicitly because §0.4.9 D-M5-B8 corrected the column that skipped it.
S11_TO_S15 = (
    "active_deals",
    "exposure_by_currency",
    "active_project_count",
    "contract_document_ids",
    "deal_under_pressure",
)


def _reachable_types(annotation: object, seen: set[object] | None = None) -> set[object]:
    """
    Every type reachable from an annotation, through members and elements.

    A field typed `tuple[TicketFact, ...]` reaches TicketFact; a field typed
    SignalSet reaches DealSignal, MoneyValue and Decimal. Without the
    recursion the field-scope assertion would be satisfied by exactly the
    implementation §0.4.9 D-M5-B7 rejects.
    """
    seen = set() if seen is None else seen
    if annotation in seen:
        return set()
    found: set[object] = set()
    args = typing.get_args(annotation)
    if args:
        for arg in args:
            found |= _reachable_types(arg, seen)
        origin = typing.get_origin(annotation)
        if origin is not None:
            found.add(origin)
        return found
    found.add(annotation)
    if is_dataclass(annotation) and isinstance(annotation, type):
        seen.add(annotation)
        hints = typing.get_type_hints(annotation)
        for field in fields(annotation):
            found |= _reachable_types(hints[field.name], seen)
    return found


def reachable_from(target: type) -> set[object]:
    """Every type a dataclass can reach from any of its fields."""
    hints = typing.get_type_hints(target)
    found: set[object] = set()
    for field in fields(target):
        found |= _reachable_types(hints[field.name], {target})
    return found


# ---------------------------------------------------------------------------
# The walker itself, proved before it is trusted
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Hidden:
    """A type that hides money one level down, for the walker's own proof."""

    money: MoneyValue


@dataclass(frozen=True)
class _Outer:
    """Money behind a member and money behind an element, in one shape."""

    direct: int
    nested: _Hidden
    collected: tuple[_Hidden, ...]


@dataclass(frozen=True)
class _WouldBeWrong:
    """The implementation §0.4.9 D-M5-B7 rejects, written out so it can fail."""

    signals: SignalSet


def test_the_type_walker_reaches_through_a_member_and_an_element():
    """
    A scan that cannot see through composition would pass the very
    implementation D-M5-B7 rejects, so it is proved on a type that does hide
    one before it is used to clear SupportContext.
    """
    reached = reachable_from(_Outer)

    assert MoneyValue in reached, "the walker missed a type behind a member"
    assert _Hidden in reached
    assert Decimal in reachable_from(_Hidden)


def test_the_walker_reaches_every_forbidden_type_through_a_signal_set():
    """
    The concrete form of the finding: a `signals: SignalSet` field carries
    DealSignal, MoneyValue and Decimal, which is why the criterion 14 clause
    naming SignalSet itself is load-bearing.
    """
    reached = reachable_from(_WouldBeWrong)

    assert {SignalSet, DealSignal, MoneyValue, Decimal} <= reached


# ---------------------------------------------------------------------------
# SupportSignals: exactly the eleven S1-S10 fields
# ---------------------------------------------------------------------------


def test_support_signals_has_exactly_the_eleven_s1_to_s10_fields():
    """§0.4.8 criterion 14: exactly these, and no other."""
    assert tuple(field.name for field in fields(SupportSignals)) == S1_TO_S10
    assert len(fields(SupportSignals)) == 11


def test_support_signals_names_and_types_are_signal_sets_own():
    """
    Same name, same type, so no second definition of any signal is created.
    Read off frozen SignalSet rather than repeated here, so a drift in either
    direction fails.
    """
    declared = typing.get_type_hints(SignalSet)
    projected = typing.get_type_hints(SupportSignals)

    assert projected == {name: declared[name] for name in S1_TO_S10}


def test_support_signals_has_no_field_for_any_of_s11_to_s15():
    """
    The exclusion is structural: S11-S15 have nowhere to land, so no
    commercial value reaches Support even by mistake. S14 included -- the
    column that skipped it is corrected by §0.4.9 D-M5-B8.
    """
    names = {field.name for field in fields(SupportSignals)}

    assert names.isdisjoint(S11_TO_S15)
    assert "contract_document_ids" not in names


def test_the_projection_copies_every_field_and_invents_none():
    """Pure and total: a field-by-field copy, no rounding and no defaulting."""
    full = signal_set(
        open_ticket_count=4,
        open_high_priority_count=3,
        high_priority_total=4,
        tickets_in_lookback=5,
        max_tickets_in_14d_window=5,
        policy_escalation_state=True,
        days_since_last_ticket=22,
        sla_breach_count=5,
        open_sla_breach_high_count=3,
        stale_open_ticket_count=1,
        dominant_ticket_category="performance",
        deals=(deal(),),
        contract_document_ids=("DOC-006",),
    )

    projected = support_signals(full)

    for name in S1_TO_S10:
        assert getattr(projected, name) == getattr(full, name), name


def test_the_projection_is_total_over_the_none_carrying_fields():
    """S6 and S10 are legitimately absent for a customer with no tickets."""
    projected = support_signals(signal_set())

    assert projected.days_since_last_ticket is None
    assert projected.dominant_ticket_category is None


def test_the_projection_returns_equal_values_for_equal_input():
    """Deterministic and side-effect-free: two calls, one answer."""
    full = signal_set(open_ticket_count=2, deals=(deal(),))

    assert support_signals(full) == support_signals(full)


# ---------------------------------------------------------------------------
# SupportContext field scope
# ---------------------------------------------------------------------------


def test_support_context_carries_exactly_the_specified_fields():
    """§0.4.9 D-M5-B7's list, in order, so an added field is a decision."""
    assert tuple(field.name for field in fields(SupportContext)) == (
        "customer",
        "signals",
        "band",
        "satisfied_rules",
        "tickets",
        "sla_targets",
        "escalation",
        "policy_documents",
        "has_active_deal",
        "contested_deal",
    )


@pytest.mark.parametrize("forbidden", [SignalSet, DealSignal, MoneyValue, Decimal])
def test_support_context_cannot_reach_a_forbidden_type(forbidden):
    """
    §0.4.8 criterion 14, by field-type inspection and through composition.
    The SignalSet clause is the one that closes D-M5-B7.
    """
    assert forbidden not in reachable_from(SupportContext)


def test_support_context_holds_support_signals_and_not_a_signal_set():
    """The positive half: it does carry S1-S10, through the projection."""
    hints = typing.get_type_hints(SupportContext)

    assert hints["signals"] is SupportSignals


def test_support_context_carries_no_deal_or_project_attribute():
    """
    §0.4.6's explicit list, asserted by name rather than by the phrase "any
    deal field", which was too coarse to implement.
    """
    names = {field.name for field in fields(SupportContext)}
    forbidden = {
        "amount", "currency", "stage", "probability", "expected_close_date",
        "active_deals", "active_deal_count", "deal_count", "project_count",
        "active_project_count", "exposure_by_currency", "deal_under_pressure",
        "contract_document_ids",
    }

    assert names.isdisjoint(forbidden)


def test_the_two_commercial_scalars_carry_nothing_more_than_they_claim():
    """
    has_active_deal is a boolean and contested_deal is an identity pair: no
    amount, currency, stage, probability or count reaches Support through
    either (§0.4.6, §0.4.9 D-M5-B9).
    """
    hints = typing.get_type_hints(SupportContext)

    assert hints["has_active_deal"] is bool
    assert hints["contested_deal"] == EntityRef | None
    assert tuple(field.name for field in fields(EntityRef)) == ("entity_type", "source_id")


# ---------------------------------------------------------------------------
# CommercialContext field scope
# ---------------------------------------------------------------------------


def test_commercial_context_carries_exactly_the_specified_fields():
    assert tuple(field.name for field in fields(CommercialContext)) == (
        "customer",
        "signals",
        "band",
        "satisfied_rules",
    )


def test_commercial_context_holds_the_full_signal_set():
    """No projection: S11-S15 are exactly what §A14 grants this function."""
    hints = typing.get_type_hints(CommercialContext)

    assert hints["signals"] is SignalSet
    assert {SignalSet, DealSignal, MoneyValue, Decimal} <= reachable_from(CommercialContext)


def test_commercial_context_holds_no_ticket_record():
    """
    §A14's prohibition on this side is on **rows**, not on values: TicketFact
    is absent, while the S1-S10 aggregates ride along on the SignalSet
    (§0.4.9 D-M5-B7).
    """
    reached = reachable_from(CommercialContext)

    assert TicketFact not in reached
    assert SupportSignals not in reached


def test_commercial_context_still_carries_the_ticket_aggregates():
    """The asymmetry stated positively, so it reads as deliberate."""
    commercial = commercial_context(open_ticket_count=4, dominant_ticket_category="billing")

    assert commercial.signals.open_ticket_count == 4
    assert commercial.signals.dominant_ticket_category == "billing"


# ---------------------------------------------------------------------------
# AnalystContexts, TicketFact and the contested-deal rule
# ---------------------------------------------------------------------------


def test_analyst_contexts_pairs_one_of_each():
    hints = typing.get_type_hints(AnalystContexts)

    assert hints == {"support": SupportContext, "commercial": CommercialContext}


def test_ticket_fact_carries_five_fields_and_nothing_else():
    """
    §0.4.2: no subject, description, assignee, customer key, deal, project or
    monetary field.
    """
    assert tuple(field.name for field in fields(TicketFact)) == (
        "source_id",
        "priority",
        "category",
        "is_open",
        "breaches_sla",
    )
    assert {Decimal, MoneyValue}.isdisjoint(reachable_from(TicketFact))


@pytest.mark.parametrize("category", ["Billing", "BILLING", " billing", "billings", None])
def test_only_exact_lowercase_billing_is_the_billing_category(category):
    """
    §0.4.2: exact, case-sensitive equality, with no normalization, folding,
    stripping, substring, prefix or synonym rule.
    """
    assert ticket(category=category).is_billing is False
    assert ticket(category=BILLING_CATEGORY).is_billing is True


def test_contested_deal_is_none_when_no_deal_is_in_negotiation():
    """
    The rejected proxy, made visible: an active deal exists, so S11 > 0, yet
    there is no negotiation deal to contest.
    """
    assert contested_deal((deal(stage="qualification"),)) is None


def test_contested_deal_names_the_negotiation_deal_and_only_its_identity():
    contested = contested_deal((deal(stage="qualification", source_id="DEAL-002"),
                                deal(stage="negotiation", source_id="DEAL-001")))

    assert contested == EntityRef("deals", "DEAL-001")


def test_two_negotiation_deals_contest_the_lexicographically_smallest():
    """
    §0.4.6's tiebreak and §A29's known limitation. No demo customer has two,
    so this is exercised only here.
    """
    contested = contested_deal((
        deal(stage="negotiation", source_id="DEAL-050"),
        deal(stage="negotiation", source_id="DEAL-004"),
        deal(stage="negotiation", source_id="DEAL-031"),
    ))

    assert contested == EntityRef("deals", "DEAL-004")


def test_contested_deal_ignores_the_order_the_deals_arrive_in():
    """Determinism is structural, not an artefact of row order."""
    deals = (deal(stage="negotiation", source_id="DEAL-009"),
             deal(stage="negotiation", source_id="DEAL-002"))

    assert contested_deal(deals) == contested_deal(tuple(reversed(deals)))


def test_contested_deal_is_none_without_any_deal():
    assert contested_deal(()) is None


# ---------------------------------------------------------------------------
# The context module's own boundaries
# ---------------------------------------------------------------------------


def test_the_factory_module_reads_m3s_constants_rather_than_redeclaring_them():
    """
    §0.4.6: M5 reuses M3's NEGOTIATION_STAGE rather than repeating the
    literal, so the two cannot drift apart.
    """
    from app.intelligence import signals as m3

    assert context_module.NEGOTIATION_STAGE is m3.NEGOTIATION_STAGE
    assert context_module.SUPPORT_TICKETS is m3.SUPPORT_TICKETS
    assert context_module.DEALS is m3.DEALS


def test_a_support_context_can_be_built_without_any_commercial_visibility():
    """The ordinary case: most customers have neither scalar set."""
    support = support_context(tickets=(ticket(),))

    assert support.has_active_deal is False
    assert support.contested_deal is None


# ---------------------------------------------------------------------------
# The wire shapes, which §0.4.8 criterion 10 asserts determinism over
# ---------------------------------------------------------------------------


def test_the_support_signals_payload_carries_the_eleven_fields_and_no_more():
    """
    The payload is the same projection again, so a commercial value cannot
    reach a serialised Support context either. Keys are the S1-S10 names.
    """
    payload = support_signals(signal_set(
        open_ticket_count=4, dominant_ticket_category="billing", deals=(deal(),),
        contract_document_ids=("DOC-006",),
    )).to_payload()

    assert tuple(payload) == S1_TO_S10
    assert payload["open_ticket_count"] == 4
    assert payload["dominant_ticket_category"] == "billing"


def test_the_ticket_fact_payload_carries_its_five_values():
    payload = ticket("TKT-079", priority="medium", category="billing",
                     is_open=True, breaches_sla=True).to_payload()

    assert payload == {
        "id": "TKT-079",
        "priority": "medium",
        "category": "billing",
        "is_open": True,
        "breaches_sla": True,
    }


def test_equal_signals_render_equal_payloads():
    """Determinism at the wire boundary, not only at the dataclass."""
    full = signal_set(open_ticket_count=2, deals=(deal(),))

    assert support_signals(full).to_payload() == support_signals(full).to_payload()
