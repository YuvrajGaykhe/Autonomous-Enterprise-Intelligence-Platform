"""
Conflict detection: one object, two functions, one declared pair (§0.5.10).

Each of the three conditions is taken away in turn, and each time the
conflict must disappear -- so no one of them is doing the others' work. The
positions are M5's own, from its analysts wherever the shape allows, so what
is detected here is what the real pipeline would detect.

Positions are checked against the catalogue before they are compared
(§0.5.2): a position whose function or stance disagrees with the declared
vocabulary, a NO_ACTION position and a position stated twice are refused
rather than reconciled. A multi-way conflict -- more than one declared pair
over one object -- is refused as VS-04's (§0.5.5); the shipped catalogue
cannot produce one, so a fixture catalogue does.
"""

from __future__ import annotations

import itertools

import pytest

from app.analysts import CommercialAnalyst, SupportRiskAnalyst
from app.analysts.base import canonical_fact
from app.decisions.conflicts import (
    ReconciliationError,
    UnresolvableConflictError,
    checked_positions,
    detect_conflicts,
    position_identity,
)
from app.decisions.policy import default_action_catalogue, default_conflict_policy
from app.intelligence.contract import (
    ActionId,
    Conflict,
    Function,
    Position,
    Stance,
)
from app.intelligence.errors import IntelligenceError
from tests.unit.m5_support import deal
from tests.unit.m6_support import (
    catalogue_data,
    contexts,
    load_catalogue,
    load_policy,
    meridian_contexts,
    policy_data,
)

pytestmark = pytest.mark.unit

PAUSE = ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED
ACCELERATE = ActionId.ACCELERATE_DEAL_CLOSE


def positions_of(analyst_contexts) -> tuple[Position, ...]:
    """Support's positions then Sales's, straight from the M5 analysts."""
    return (
        SupportRiskAnalyst(context=analyst_contexts.support).positions()
        + CommercialAnalyst(context=analyst_contexts.commercial).positions()
    )


def position(function: Function, action: ActionId, object_ref: str, stance: Stance,
             *, rationale: str = "stated for the test") -> Position:
    """A hand-built position, for the shapes M5 never emits."""
    return Position(
        function=function, stance=stance, proposed_action=action, object_ref=object_ref,
        rationale=rationale, evidence=(canonical_fact("deals", "DEAL-900", "stage"),),
    )


# ---------------------------------------------------------------------------
# The conflict
# ---------------------------------------------------------------------------


def test_cust_007s_shape_yields_exactly_one_conflict_over_the_deal():
    (conflict,) = detect_conflicts(positions_of(meridian_contexts()), default_conflict_policy())

    assert isinstance(conflict, Conflict)
    assert conflict.object_ref == "DEAL-001"
    assert [(p.function, p.proposed_action, p.stance) for p in conflict.positions] == [
        (Function.SALES, ACCELERATE, Stance.ADVANCE),
        (Function.SUPPORT, PAUSE, Stance.RESTRAIN),
    ]


def test_the_conflict_holds_the_analysts_own_positions_unmodified():
    emitted = positions_of(meridian_contexts())
    (conflict,) = detect_conflicts(emitted, default_conflict_policy())

    for held in conflict.positions:
        assert held in emitted
        assert any(held is original for original in emitted)


def test_detection_does_not_depend_on_the_order_positions_arrive_in():
    emitted = positions_of(meridian_contexts())
    expected = detect_conflicts(emitted, default_conflict_policy())

    for permutation in itertools.islice(itertools.permutations(emitted), 0, 720, 37):
        assert detect_conflicts(permutation, default_conflict_policy()) == expected


# ---------------------------------------------------------------------------
# Take each condition away, and the conflict goes
# ---------------------------------------------------------------------------


def test_no_shared_object_means_no_conflict():
    """Support pauses DEAL-001 and Sales accelerates DEAL-002: two objects, nothing to reconcile."""
    support = position(Function.SUPPORT, PAUSE, "DEAL-001", Stance.RESTRAIN)
    sales = position(Function.SALES, ACCELERATE, "DEAL-002", Stance.ADVANCE)

    assert detect_conflicts((support, sales), default_conflict_policy()) == ()


def test_positions_of_one_function_are_never_compared():
    """CUST-007's three Support positions share the customer, and none conflicts with another."""
    customer_positions = [
        one for one in positions_of(meridian_contexts()) if one.object_ref == "CUST-007"
    ]

    assert len(customer_positions) == 3
    assert {one.function for one in customer_positions} == {Function.SUPPORT}
    assert detect_conflicts(customer_positions, default_conflict_policy()) == ()


def test_an_undeclared_pair_on_one_object_is_not_a_conflict():
    """Two functions, one object, different actions -- but no rule names the pair, so both stand."""
    support = position(Function.SUPPORT, ActionId.ESCALATE_TO_ACCOUNT_OWNER_PER_SLA,
                       "OBJ-1", Stance.NEUTRAL)
    sales = position(Function.SALES, ACCELERATE, "OBJ-1", Stance.ADVANCE)

    assert detect_conflicts((support, sales), default_conflict_policy()) == ()


def test_a_customer_with_no_deal_has_no_conflict():
    breaching_only = contexts(band="CRITICAL", s8=3, s4=5, s5=True)

    assert positions_of(breaching_only)
    assert detect_conflicts(positions_of(breaching_only), default_conflict_policy()) == ()


def test_a_sales_position_alone_has_no_conflict():
    """CUST-019's shape: ticketless, one qualifying deal, one SALES position, no conflict."""
    ticketless = contexts(deals=(deal("DEAL-011", stage="negotiation", probability=90),))

    assert [one.function for one in positions_of(ticketless)] == [Function.SALES]
    assert detect_conflicts(positions_of(ticketless), default_conflict_policy()) == ()


def test_no_positions_have_no_conflict():
    assert detect_conflicts((), default_conflict_policy()) == ()


# ---------------------------------------------------------------------------
# Multi-way: VS-04's, refused
# ---------------------------------------------------------------------------


def multi_way_policy(tmp_path):
    """A catalogue giving Support a second deal action, and a rule pairing it with Sales."""
    catalogue = catalogue_data()
    catalogue["actions"][4]["object"] = "deals"  # REVIEW_INVOICE_DISPUTE, now on a deal
    policy = policy_data()
    policy["conflicts"].append({
        **policy["conflicts"][0],
        "id": "CONF-002",
        "between": ["REVIEW_INVOICE_DISPUTE", "ACCELERATE_DEAL_CLOSE"],
        "resolve_to": "REVIEW_INVOICE_DISPUTE",
    })
    return load_policy(tmp_path, policy, catalogue=load_catalogue(tmp_path, catalogue))


def test_two_declared_pairs_over_one_object_are_refused_as_multi_way(tmp_path):
    positions = (
        position(Function.SUPPORT, PAUSE, "DEAL-7", Stance.RESTRAIN),
        position(Function.SUPPORT, ActionId.REVIEW_INVOICE_DISPUTE, "DEAL-7", Stance.NEUTRAL),
        position(Function.SALES, ACCELERATE, "DEAL-7", Stance.ADVANCE),
    )

    with pytest.raises(UnresolvableConflictError, match="2 declared pairs conflict over one "
                                                        "object") as raised:
        detect_conflicts(positions, multi_way_policy(tmp_path))

    assert raised.value.object_ref == "DEAL-7"
    assert raised.value.rule_id is None
    assert raised.value.actions == (ACCELERATE, PAUSE, ActionId.REVIEW_INVOICE_DISPUTE)


def test_the_same_catalogue_with_one_pair_per_object_still_detects(tmp_path):
    """The refusal is for two pairs on ONE object, not for a policy with two rules."""
    positions = (
        position(Function.SUPPORT, PAUSE, "DEAL-7", Stance.RESTRAIN),
        position(Function.SALES, ACCELERATE, "DEAL-7", Stance.ADVANCE),
        position(Function.SUPPORT, ActionId.REVIEW_INVOICE_DISPUTE, "DEAL-8", Stance.NEUTRAL),
    )

    (conflict,) = detect_conflicts(positions, multi_way_policy(tmp_path))

    assert conflict.object_ref == "DEAL-7"


# ---------------------------------------------------------------------------
# Positions are checked against the catalogue
# ---------------------------------------------------------------------------


def test_the_analysts_positions_agree_with_the_committed_catalogue():
    emitted = positions_of(meridian_contexts())

    assert checked_positions(emitted, default_action_catalogue()) == tuple(
        sorted(emitted, key=lambda one: (str(one.function), one.object_ref,
                                         str(one.proposed_action)))
    )


def test_a_position_for_the_wrong_function_is_refused():
    wrong = position(Function.SALES, PAUSE, "DEAL-001", Stance.RESTRAIN)

    with pytest.raises(ReconciliationError, match="gives PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED "
                                                  "to SUPPORT"):
        checked_positions((wrong,), default_action_catalogue())


def test_a_position_whose_stance_disagrees_with_the_catalogue_is_refused():
    wrong = position(Function.SUPPORT, PAUSE, "DEAL-001", Stance.NEUTRAL)

    with pytest.raises(ReconciliationError, match="stance NEUTRAL disagrees with the "
                                                  "catalogue's RESTRAIN"):
        checked_positions((wrong,), default_action_catalogue())


def test_a_no_action_position_is_refused():
    """§A16: NO_ACTION is proposed by no function, so no position may carry it."""
    wrong = position(Function.SUPPORT, ActionId.NO_ACTION, "CUST-007", Stance.NEUTRAL)

    with pytest.raises(ReconciliationError, match="no function proposes NO_ACTION"):
        checked_positions((wrong,), default_action_catalogue())


def test_a_position_stated_twice_is_refused():
    first = position(Function.SUPPORT, PAUSE, "DEAL-001", Stance.RESTRAIN)
    second = position(Function.SUPPORT, PAUSE, "DEAL-001", Stance.RESTRAIN, rationale="again")

    with pytest.raises(ReconciliationError, match="states PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED "
                                                  "on DEAL-001 twice"):
        checked_positions((first, second), default_action_catalogue())


def test_a_catalogue_that_drifts_from_m5_fails_the_run(tmp_path):
    """The catalogue is load-bearing: M5 pauses with RESTRAIN, and a NEUTRAL entry is refused."""
    data = catalogue_data()
    data["actions"][3]["stance"] = "NEUTRAL"
    drifted = load_catalogue(tmp_path, data)

    with pytest.raises(ReconciliationError, match="disagrees with the catalogue"):
        checked_positions(positions_of(meridian_contexts()), drifted)


def test_detection_checks_positions_before_comparing_them():
    wrong = position(Function.SALES, PAUSE, "DEAL-001", Stance.RESTRAIN)

    with pytest.raises(ReconciliationError):
        detect_conflicts((wrong,), default_conflict_policy())


def test_position_identity_is_function_object_and_action():
    one = position(Function.SUPPORT, PAUSE, "DEAL-001", Stance.RESTRAIN)

    assert position_identity(one) == (Function.SUPPORT, "DEAL-001", PAUSE)


def test_the_errors_are_runtime_decision_failures():
    assert issubclass(ReconciliationError, IntelligenceError)
    assert issubclass(UnresolvableConflictError, ReconciliationError)
