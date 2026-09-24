"""
Reconciliation: the winner, the dissent, the resolved set, worthiness and order.

Written against §0.5.7's table for CUST-007 and §0.5.8's and §0.5.9's truth
tables, on hand-built contexts, so every row can be reached -- including the
ones the demo dataset never shows: no ELEVATED customer exists, no two
customers share a band but differ in S8, and no detected conflict fails
CONF-001's `when`.

Three properties are asserted as equalities of whole results rather than as
spot checks, because a spot check is how a regression hides:

  * **Amount invariance.** Two customers that differ only in deal amounts
    reconcile to *equal* Reconciliations, and rank identically. Money is
    never an input (§A15, §0.5.8, §0.5.9).
  * **Liveness.** Flipping `resolve_to` flips the winner and the dissent, and
    nothing else about the result.
  * **Order independence.** Customers ranked in any arrival order come back in
    one order.
"""

from __future__ import annotations

import itertools
from dataclasses import FrozenInstanceError, replace

import pytest

from app.analysts import CommercialAnalyst, SupportRiskAnalyst
from app.decisions.conflicts import ReconciliationError, UnresolvableConflictError
from app.decisions.policy import default_conflict_policy
from app.decisions.reconciler import (
    DOCUMENTS,
    POLICY_TEXT_FIELD,
    Reconciliation,
    Worthiness,
    order_reconciliations,
    reconcile,
    resolution_evidence,
)
from app.intelligence.contract import (
    ActionId,
    EntityRef,
    Evidence,
    EvidenceKind,
    Function,
    Position,
    RecordCitation,
    RiskBand,
    Stance,
    canonical_json,
)
from app.intelligence.errors import ContractViolationError
from tests.unit.m5_support import deal
from tests.unit.m6_support import (
    contexts,
    flipped_policy,
    load_policy,
    meridian_contexts,
    policy_data,
    watch_conflict_contexts,
)

pytestmark = pytest.mark.unit

PAUSE = ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED
ACCELERATE = ActionId.ACCELERATE_DEAL_CLOSE

#: §0.5.7's ordered_positions for CUST-007: (function, action, object_ref).
MERIDIAN_ORDERED = (
    ("SALES", "ACCELERATE_DEAL_CLOSE", "DEAL-001"),
    ("SUPPORT", "ASSIGN_DEDICATED_SUPPORT_OWNER", "CUST-007"),
    ("SUPPORT", "ESCALATE_TO_ACCOUNT_OWNER_PER_SLA", "CUST-007"),
    ("SUPPORT", "SCHEDULE_EXECUTIVE_SPONSOR_CALL", "CUST-007"),
    ("SUPPORT", "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED", "DEAL-001"),
    ("SUPPORT", "REVIEW_INVOICE_DISPUTE", "TKT-900"),
)


def rows(positions) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (str(one.function), str(one.proposed_action), one.object_ref) for one in positions
    )


@pytest.fixture(scope="module")
def meridian() -> Reconciliation:
    return reconcile(meridian_contexts())


# ---------------------------------------------------------------------------
# CUST-007: §0.5.7's table
# ---------------------------------------------------------------------------


def test_every_emitted_position_is_kept_in_order(meridian):
    assert rows(meridian.ordered_positions) == MERIDIAN_ORDERED


def test_the_ordered_positions_are_the_analysts_own(meridian):
    """Unmodified: the decision layer never edits, copies or rebuilds a position."""
    analysts = meridian_contexts()
    emitted = (SupportRiskAnalyst(context=analysts.support).positions()
               + CommercialAnalyst(context=analysts.commercial).positions())

    assert sorted(meridian.ordered_positions, key=repr) == sorted(emitted, key=repr)


def test_one_conflict_over_deal_001(meridian):
    (conflict,) = meridian.conflicts

    assert conflict.object_ref == "DEAL-001"
    assert conflict.proposed_actions == (ACCELERATE, PAUSE)


def test_conf_001_resolves_it_and_pause_prevails(meridian):
    (resolution,) = meridian.resolutions

    assert resolution.policy_id == "CONF-001"
    assert resolution.resolved_action is PAUSE
    assert resolution.prevailing.function is Function.SUPPORT
    assert resolution.rationale == default_conflict_policy().rules[0].rationale
    assert meridian.policy_ids == ("CONF-001",)


def test_the_resolution_cites_doc_003_and_doc_009_by_id(meridian):
    """§0.5.4: two canonical facts over the documents' body text, in id order, and nothing else."""
    (resolution,) = meridian.resolutions

    assert resolution.evidence == (
        Evidence(EvidenceKind.CANONICAL_FACT, RecordCitation("documents", "DOC-003", "body_text")),
        Evidence(EvidenceKind.CANONICAL_FACT, RecordCitation("documents", "DOC-009", "body_text")),
    )
    assert (DOCUMENTS, POLICY_TEXT_FIELD) == ("documents", "body_text")


def test_the_dissent_is_the_accelerate_position_whole_with_its_own_citations(meridian):
    """Losing discards nothing: the overruled position is the one Sales stated, evidence and all."""
    (dissent,) = meridian.dissent
    stated = CommercialAnalyst(context=meridian_contexts().commercial).positions()

    assert dissent.proposed_action is ACCELERATE
    assert dissent.stance is Stance.ADVANCE
    assert (dissent,) == stated
    assert [citation.field_name for citation in dissent.citations] == [
        "is_active", "stage", "probability"]
    assert meridian.resolutions[0].dissent == (dissent,)


def test_the_resolved_set_is_supports_five_positions(meridian):
    """§0.4.1 rows 1-5, as Position objects -- never bare action ids."""
    assert rows(meridian.resolved_positions) == MERIDIAN_ORDERED[1:]
    assert all(isinstance(one, Position) for one in meridian.resolved_positions)
    assert {one.function for one in meridian.resolved_positions} == {Function.SUPPORT}


def test_the_losing_position_leaves_only_the_resolved_view(meridian):
    """Removed from resolved_positions, kept in ordered_positions and in the dissent."""
    (dissent,) = meridian.dissent

    assert dissent not in meridian.resolved_positions
    assert dissent in meridian.ordered_positions
    assert len(meridian.resolved_positions) + len(meridian.dissent) == len(
        meridian.ordered_positions)


def test_cust_007_is_worthy_and_ranks_critical(meridian):
    assert meridian.worthiness == Worthiness(RiskBand.CRITICAL, 1, 0)
    assert meridian.worthiness.executive_worthy
    assert meridian.ranking_key == (-3, -3, -5, "CUST-007")
    assert meridian.customer == EntityRef("customers", "CUST-007")
    assert meridian.policy_version == 1


def test_the_policy_version_is_carried_from_the_policy(tmp_path):
    bumped = load_policy(tmp_path, {**policy_data(), "policy_version": 4})

    assert reconcile(meridian_contexts(), policy=bumped).policy_version == 4


def test_the_default_policy_is_the_committed_one(meridian):
    assert reconcile(meridian_contexts(), policy=default_conflict_policy()) == meridian


# ---------------------------------------------------------------------------
# Liveness: flip the policy, flip the outcome
# ---------------------------------------------------------------------------


def test_flipping_resolve_to_flips_the_winner_and_the_dissent(tmp_path, meridian):
    flipped = reconcile(meridian_contexts(), policy=flipped_policy(tmp_path))

    assert flipped.resolutions[0].resolved_action is ACCELERATE
    assert [one.proposed_action for one in flipped.dissent] == [PAUSE]
    assert ACCELERATE in [one.proposed_action for one in flipped.resolved_positions]
    assert PAUSE not in [one.proposed_action for one in flipped.resolved_positions]


def test_flipping_resolve_to_changes_nothing_else(tmp_path, meridian):
    flipped = reconcile(meridian_contexts(), policy=flipped_policy(tmp_path))

    assert flipped.ordered_positions == meridian.ordered_positions
    assert flipped.conflicts == meridian.conflicts
    assert flipped.worthiness == meridian.worthiness
    assert flipped.ranking_key == meridian.ranking_key
    assert flipped.resolutions[0].evidence == meridian.resolutions[0].evidence


# ---------------------------------------------------------------------------
# No shared object: no conflict, no dissent, no resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", ["no deal", "ticketless with a deal", "nothing at all"])
def test_a_customer_whose_functions_share_no_object_keeps_every_position(shape):
    analyst_contexts = {
        "no deal": contexts(band="CRITICAL", s8=3, s4=5, s5=True),
        "ticketless with a deal": contexts(
            deals=(deal("DEAL-011", stage="negotiation", probability=90),)),
        "nothing at all": contexts(),
    }[shape]

    result = reconcile(analyst_contexts)

    assert result.conflicts == ()
    assert result.resolutions == ()
    assert result.dissent == ()
    assert result.policy_ids == ()
    assert result.resolved_positions == result.ordered_positions


# ---------------------------------------------------------------------------
# Unresolvable: §0.5.5
# ---------------------------------------------------------------------------


def test_a_conflict_conf_001_does_not_apply_to_raises():
    """WATCH, S8 = 1: Support pauses, Sales accelerates, and CONF-001's band condition fails."""
    with pytest.raises(UnresolvableConflictError) as raised:
        reconcile(watch_conflict_contexts())

    message = str(raised.value)
    assert "CUST-998" in message and "DEAL-998" in message
    assert "CONF-001 does not apply" in message
    assert "support_band_at_least ELEVATED does not hold: the band is WATCH" in message
    assert "No default winner is chosen" in message
    assert raised.value.rule_id == "CONF-001"
    assert raised.value.object_ref == "DEAL-998"
    assert raised.value.actions == (ACCELERATE, PAUSE)


def test_every_failing_condition_is_named(tmp_path):
    stricter = policy_data()
    stricter["conflicts"][0]["when"]["open_sla_breach_high_count_at_least"] = 2

    with pytest.raises(UnresolvableConflictError, match="band is WATCH; "
                                                        ".*S8 is 1"):
        reconcile(watch_conflict_contexts(), policy=load_policy(tmp_path, stricter))


@pytest.mark.parametrize("s8, s4, resolves", [(1, 6, False), (2, 0, True)])
def test_the_breach_condition_reads_s8_and_nothing_else(tmp_path, s8, s4, resolves):
    """
    `open_sla_breach_high_count_at_least` is Support's S8. A wide 14-day window
    (S4) does not satisfy it, and an empty one does not defeat it.
    """
    stricter = policy_data()
    stricter["conflicts"][0]["when"]["open_sla_breach_high_count_at_least"] = 2
    analyst_contexts = contexts(customer="CUST-997", band="ELEVATED", s8=s8, s4=s4,
                                deals=(deal("DEAL-997", stage="negotiation", probability=90),))
    policy = load_policy(tmp_path, stricter)

    if resolves:
        assert reconcile(analyst_contexts, policy=policy).policy_ids == ("CONF-001",)
    else:
        with pytest.raises(UnresolvableConflictError, match="S8 is 1"):
            reconcile(analyst_contexts, policy=policy)


def test_the_same_shape_resolves_once_its_band_meets_the_rule():
    """The control: only the `when` is failing, not the detection."""
    elevated = watch_conflict_contexts()
    elevated = type(elevated)(
        support=replace(elevated.support, band="ELEVATED"),
        commercial=replace(elevated.commercial, band="ELEVATED"),
    )

    assert reconcile(elevated).policy_ids == ("CONF-001",)


def test_contexts_naming_different_customers_are_refused():
    mixed = type(meridian_contexts())(support=meridian_contexts().support,
                                      commercial=contexts(customer="CUST-001").commercial)

    with pytest.raises(ReconciliationError, match="the two contexts disagree"):
        reconcile(mixed)


def test_contexts_disagreeing_on_the_band_are_refused():
    analyst_contexts = meridian_contexts()
    mixed = type(analyst_contexts)(
        support=analyst_contexts.support,
        commercial=replace(analyst_contexts.commercial, band="WATCH"),
    )

    with pytest.raises(ReconciliationError, match="at CRITICAL, Sales sees CUST-007 at WATCH"):
        reconcile(mixed)


# ---------------------------------------------------------------------------
# Worthiness: §0.5.8's truth table, all sixteen combinations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("band", list(RiskBand))
@pytest.mark.parametrize("deals", [0, 1])
@pytest.mark.parametrize("projects", [0, 1])
def test_the_worthiness_truth_table(band, deals, projects):
    expected = band in (RiskBand.ELEVATED, RiskBand.CRITICAL) and (deals > 0 or projects > 0)

    assert Worthiness(band, deals, projects).executive_worthy is expected


@pytest.mark.parametrize("band", list(RiskBand))
@pytest.mark.parametrize("deals", [0, 2])
@pytest.mark.parametrize("projects", [0, 3])
def test_reconcile_reads_worthiness_from_s11_and_s13(band, deals, projects):
    """Any stage counts for S11: two qualification deals make a customer as linked as one."""
    analyst_contexts = contexts(
        band=str(band),
        deals=tuple(deal(f"DEAL-{index}", stage="qualification", probability=10)
                    for index in range(deals)),
        projects=projects,
    )

    worthiness = reconcile(analyst_contexts).worthiness

    assert worthiness == Worthiness(band, deals, projects)
    assert worthiness.executive_worthy is (
        band.at_least(RiskBand.ELEVATED) and (deals > 0 or projects > 0))


def test_worthiness_projects_its_inputs_and_its_verdict():
    assert Worthiness(RiskBand.ELEVATED, 0, 1).to_payload() == {
        "band": "ELEVATED", "active_deal_count": 0, "active_project_count": 1,
        "executive_worthy": True,
    }


@pytest.mark.parametrize("band, deals, projects", [
    ("CRITICAL", 1, 0), (RiskBand.CRITICAL, -1, 0), (RiskBand.CRITICAL, 0, -1),
    (RiskBand.CRITICAL, True, 0), (RiskBand.CRITICAL, 1.0, 0),
])
def test_worthiness_refuses_what_is_not_a_band_and_two_counts(band, deals, projects):
    with pytest.raises(ContractViolationError):
        Worthiness(band, deals, projects)


# ---------------------------------------------------------------------------
# Ordering: §0.5.9's truth table
# ---------------------------------------------------------------------------


def ranked(**shape) -> Reconciliation:
    return reconcile(contexts(**shape))


def order_of(*results: Reconciliation) -> list[str]:
    return [result.customer.source_id for result in order_reconciliations(results)]


def test_band_decides_first():
    """A lower band loses even with more breaches, a larger window and an earlier id."""
    watch = ranked(customer="CUST-001", band="WATCH", s8=3, s4=9)
    critical = ranked(customer="CUST-900", band="CRITICAL", s8=1, s4=1)

    assert order_of(watch, critical) == ["CUST-900", "CUST-001"]


def test_s8_decides_between_equal_bands():
    fewer = ranked(customer="CUST-001", band="WATCH", s8=1, s4=9)
    more = ranked(customer="CUST-900", band="WATCH", s8=2, s4=1)

    assert order_of(fewer, more) == ["CUST-900", "CUST-001"]


def test_s4_decides_between_equal_bands_and_s8():
    narrower = ranked(customer="CUST-001", band="WATCH", s8=1, s4=1)
    wider = ranked(customer="CUST-900", band="WATCH", s8=1, s4=4)

    assert order_of(narrower, wider) == ["CUST-900", "CUST-001"]


def test_source_id_decides_last_ascending():
    """The CUST-025 / CUST-036 case the demo dataset holds: equal in every term but the id."""
    later = ranked(customer="CUST-036", band="WATCH", s8=1, s4=1)
    earlier = ranked(customer="CUST-025", band="WATCH", s8=1, s4=1)

    assert order_of(later, earlier) == ["CUST-025", "CUST-036"]


def test_worthiness_is_not_an_ordering_term():
    """S11 and S13 decide worthiness, never rank."""
    worthy = ranked(customer="CUST-900", band="ELEVATED", s8=1, s4=1,
                    deals=(deal("DEAL-1", stage="qualification", probability=10),))
    unworthy = ranked(customer="CUST-001", band="ELEVATED", s8=1, s4=1)

    assert worthy.worthiness.executive_worthy and not unworthy.worthiness.executive_worthy
    assert order_of(worthy, unworthy) == ["CUST-001", "CUST-900"]


def test_the_order_is_independent_of_arrival_order():
    results = [
        ranked(customer="CUST-004", band="NONE"),
        ranked(customer="CUST-003", band="WATCH", s8=1, s4=1),
        reconcile(meridian_contexts()),
        ranked(customer="CUST-002", band="WATCH", s8=1, s4=1),
        ranked(customer="CUST-001", band="NONE", s4=2),
    ]
    expected = ["CUST-007", "CUST-002", "CUST-003", "CUST-001", "CUST-004"]

    for permutation in itertools.permutations(results):
        assert order_of(*permutation) == expected


def test_an_empty_run_orders_to_nothing():
    assert order_reconciliations([]) == ()


def test_a_customer_ranked_twice_is_refused(meridian):
    with pytest.raises(ReconciliationError, match=r"reconciled more than once: \['CUST-007'\]"):
        order_reconciliations([meridian, reconcile(meridian_contexts())])


def test_results_of_two_policy_versions_are_not_one_run(tmp_path, meridian):
    other = reconcile(contexts(customer="CUST-001"),
                      policy=load_policy(tmp_path, {**policy_data(), "policy_version": 2}))

    with pytest.raises(ReconciliationError, match=r"policy versions \[1, 2\]"):
        order_reconciliations([meridian, other])


# ---------------------------------------------------------------------------
# Money is never an input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("amount", ["5.36", "5361440.00", "0.01", "999999999.99"])
def test_the_amount_changes_nothing_reconciled(meridian, amount):
    """§A25 test 5 at M6's grain: the whole result is equal, not merely the winner."""
    perturbed = reconcile(meridian_contexts(amount=amount))

    assert perturbed == meridian
    assert canonical_json(perturbed.to_payload()) == canonical_json(meridian.to_payload())


def test_two_customers_differing_only_in_amount_keep_their_order():
    """
    Equal in every ranking term, each with one accelerating deal: only the
    id orders them, whichever of the two holds the larger amount.
    """
    def pair(first_amount: str, second_amount: str) -> list[str]:
        return order_of(
            ranked(customer="CUST-001", s4=1, deals=(deal("DEAL-1", amount=first_amount),)),
            ranked(customer="CUST-002", s4=1, deals=(deal("DEAL-2", amount=second_amount),)),
        )

    assert pair("1.00", "1000000000.00") == pair("1000000000.00", "1.00") == [
        "CUST-001", "CUST-002"]


def test_the_currency_changes_nothing_reconciled(meridian):
    analyst_contexts = contexts(
        customer="CUST-007", band="CRITICAL", s8=3, s4=5, s5=True, billing=True,
        deals=(deal("DEAL-001", stage="negotiation", probability=90, currency="INR"),),
    )

    assert reconcile(analyst_contexts) == meridian


# ---------------------------------------------------------------------------
# Determinism, serialisation and immutability
# ---------------------------------------------------------------------------


def test_two_runs_are_equal_and_serialise_identically(meridian):
    again = reconcile(meridian_contexts())

    assert again == meridian
    assert canonical_json(again.to_payload()) == canonical_json(meridian.to_payload())


def test_the_projection_carries_every_field(meridian):
    payload = meridian.to_payload()

    assert list(payload) == [
        "customer", "policy_version", "ordered_positions", "conflicts", "resolutions",
        "resolved_positions", "dissent", "worthiness", "ranking_key",
    ]
    assert payload["policy_version"] == 1
    assert payload["ranking_key"] == [-3, -3, -5, "CUST-007"]
    assert payload["resolutions"][0]["policy_id"] == "CONF-001"
    assert [one["proposed_action"] for one in payload["dissent"]] == ["ACCELERATE_DEAL_CLOSE"]
    assert len(payload["resolved_positions"]) == 5


def test_the_result_is_immutable(meridian):
    with pytest.raises(FrozenInstanceError):
        meridian.policy_version = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        meridian.worthiness.band = RiskBand.NONE  # type: ignore[misc]
    for name in ("ordered_positions", "resolutions", "ranking_key"):
        assert isinstance(getattr(meridian, name), tuple)
    for derived in (meridian.conflicts, meridian.dissent, meridian.resolved_positions,
                    meridian.policy_ids):
        assert isinstance(derived, tuple)


def test_resolution_evidence_follows_the_rule(tmp_path):
    rule = load_policy(tmp_path, {**policy_data(), "conflicts": [
        {**policy_data()["conflicts"][0], "because_documents": ["DOC-011", "DOC-003"]}]}).rules[0]

    assert [item.citation.source_id for item in resolution_evidence(rule)] == [
        "DOC-003", "DOC-011"]


# ---------------------------------------------------------------------------
# The result's own invariants
# ---------------------------------------------------------------------------


def rebuilt(meridian: Reconciliation, **changes) -> Reconciliation:
    return replace(meridian, **changes)


def test_a_rebuild_with_nothing_changed_is_equal(meridian):
    assert rebuilt(meridian) == meridian


@pytest.mark.parametrize("name", ["ordered_positions", "resolutions", "ranking_key"])
def test_a_collection_field_must_be_a_tuple(meridian, name):
    with pytest.raises(ContractViolationError, match=f"{name} must be a tuple"):
        rebuilt(meridian, **{name: list(getattr(meridian, name))})


@pytest.mark.parametrize("version", [0, -1, True, "1"])
def test_the_policy_version_must_be_positive(meridian, version):
    with pytest.raises(ContractViolationError, match="policy_version must be an integer"):
        rebuilt(meridian, policy_version=version)


def test_positions_out_of_order_are_refused(meridian):
    with pytest.raises(ContractViolationError, match="§0.4.1's order"):
        rebuilt(meridian, ordered_positions=tuple(reversed(meridian.ordered_positions)))


def test_a_position_stated_twice_is_refused(meridian):
    twice = meridian.ordered_positions[:1] + meridian.ordered_positions

    with pytest.raises(ContractViolationError, match="no position stated twice"):
        rebuilt(meridian, ordered_positions=twice)


def test_two_resolutions_of_one_object_are_refused(meridian):
    with pytest.raises(ContractViolationError, match="one per object"):
        rebuilt(meridian, resolutions=meridian.resolutions * 2)


def test_a_resolution_of_positions_the_customer_did_not_state_is_refused(meridian):
    without_the_deal = tuple(
        one for one in meridian.ordered_positions if one.object_ref != "DEAL-001")

    with pytest.raises(ContractViolationError, match="did not state"):
        rebuilt(meridian, ordered_positions=without_the_deal)


@pytest.mark.parametrize("key", [
    (-3, -3, -5, "CUST-008"), (-1, -3, -5, "CUST-007"), (-3, -3, -5),
])
def test_a_ranking_key_for_another_customer_or_band_is_refused(meridian, key):
    with pytest.raises(ContractViolationError, match="does not rank CUST-007"):
        rebuilt(meridian, ranking_key=key)
