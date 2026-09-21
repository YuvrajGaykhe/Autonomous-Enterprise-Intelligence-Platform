"""
M3 band decision table: what may drive a band, and what may never.

Two measured traps are what these tests exist to keep closed.

Strategy 4.3: a blended score demotes CUST-007 to roughly twelfth and
surfaces a customer with one open ticket, because CUST-007 is 22nd of the
23 customers holding active deals on weighted exposure. Money is therefore
not a permitted band input, and a table naming it is refused at load rather
than evaluated.

Strategy 4.4: TKT-010 and TKT-005 have been open since January. A band
driven by breach age ranks their customers above CUST-007. Chronic backlog
is therefore not a permitted band input either.

Both are asserted against the *shipped* table as well as against the
vocabulary, because a rule that cannot be written is only half the guard:
the other half is that nobody wrote one before the guard existed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.intelligence.bands import (
    BAND_INPUT_SIGNALS,
    BandAssignment,
    BandRule,
    Comparison,
    Condition,
    assign_band,
    band_rule_signals,
    parse_band_rules,
    ranking_key,
    rules_by_id,
)
from app.intelligence.config import default_risk_rules
from app.intelligence.contract import DealSignal, RiskBand, SignalSet
from app.intelligence.errors import IntelligenceConfigError
from app.intelligence.money import MoneyValue

NONE = str(RiskBand.NONE)
SHIPPED = default_risk_rules().band_rules

#: Signals plan A10 marks "band input: no" or "context". None of them may
#: appear in a rule, and each is named so a future edit fails by name.
FORBIDDEN_BAND_INPUTS = (
    "sla_breach_count",          # S7  - context, and strategy 4.4's trap
    "stale_open_ticket_count",   # S9  - chronic backlog, never a driver
    "dominant_ticket_category",  # S10 - context
    "active_deal_count",         # S11 - worthiness, not risk
    "exposure_by_currency",      # S12 - money, strategy 4.3's trap
    "active_project_count",      # S13 - worthiness, not risk
    "contract_document_ids",     # S14 - evidence, and M4's to populate
    "deal_under_pressure",       # S15 - a conflict input, not a band input
)


def signals(**overrides) -> SignalSet:
    """A signal set that satisfies no rule, with named fields overridden."""
    defaults = {
        "open_ticket_count": 0, "open_high_priority_count": 0, "high_priority_total": 0,
        "tickets_in_lookback": 0, "max_tickets_in_14d_window": 0,
        "policy_escalation_state": False, "days_since_last_ticket": None,
        "sla_breach_count": 0, "open_sla_breach_high_count": 0,
        "stale_open_ticket_count": 0, "dominant_ticket_category": None,
        "active_deals": (), "exposure_by_currency": {}, "active_project_count": 0,
        "contract_document_ids": (), "deal_under_pressure": False,
    }
    return SignalSet(**{**defaults, **overrides})


def meridian() -> SignalSet:
    """CUST-007 at the pinned as_of, exactly as plan A10 measures it."""
    return signals(
        open_ticket_count=4, open_high_priority_count=3, high_priority_total=4,
        tickets_in_lookback=5, max_tickets_in_14d_window=5, policy_escalation_state=True,
        days_since_last_ticket=22, sla_breach_count=5, open_sla_breach_high_count=3,
        dominant_ticket_category="performance",
        active_deals=(DealSignal(
            source_id="DEAL-001", stage="negotiation", probability=Decimal("90.00"),
            amount=MoneyValue(amount=Decimal("5361.44"), currency="USD"),
        ),),
        exposure_by_currency={"USD": MoneyValue(amount=Decimal("5361.44"), currency="USD")},
        deal_under_pressure=True,
    )


def band_of(signal_set: SignalSet) -> BandAssignment:
    return assign_band(signal_set, SHIPPED, floor=NONE)


# ---------------------------------------------------------------------------
# The vocabulary is closed
# ---------------------------------------------------------------------------


def test_exactly_the_seven_signals_plan_a10_marks_as_band_inputs_are_permitted():
    assert BAND_INPUT_SIGNALS == {
        "open_ticket_count", "open_high_priority_count", "tickets_in_lookback",
        "max_tickets_in_14d_window", "policy_escalation_state",
        "days_since_last_ticket", "open_sla_breach_high_count",
    }


@pytest.mark.parametrize("signal", FORBIDDEN_BAND_INPUTS)
def test_no_context_backlog_money_or_evidence_signal_is_a_band_input(signal):
    assert signal not in BAND_INPUT_SIGNALS


@pytest.mark.parametrize("signal", FORBIDDEN_BAND_INPUTS)
def test_the_shipped_table_names_no_forbidden_signal(signal):
    assert signal not in band_rule_signals(SHIPPED)


def test_every_signal_the_shipped_table_names_is_a_permitted_band_input():
    assert band_rule_signals(SHIPPED) <= BAND_INPUT_SIGNALS


def test_every_permitted_band_input_is_a_field_of_the_signal_set():
    """A rule naming a signal that does not exist would raise at evaluation, not load."""
    for name in BAND_INPUT_SIGNALS:
        assert hasattr(signals(), name), name


@pytest.mark.parametrize("signal", ["exposure_by_currency", "sla_breach_count",
                                    "stale_open_ticket_count"])
def test_a_table_reaching_for_a_forbidden_signal_is_refused_at_load_by_name(signal):
    with pytest.raises(IntelligenceConfigError, match=f"{signal!r} is not a counted band input"):
        parse_band_rules(
            [{"id": "R-X", "band": "CRITICAL", "when": {f"{signal}_at_least": 1}}], "bands"
        )


# ---------------------------------------------------------------------------
# Every row of the shipped table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id, satisfying, band", [
    ("R-CRIT-001", {"policy_escalation_state": True, "open_ticket_count": 2,
                    "open_high_priority_count": 2, "high_priority_total": 2,
                    "open_sla_breach_high_count": 2}, "CRITICAL"),
    ("R-ELEV-001", {"policy_escalation_state": True}, "ELEVATED"),
    ("R-ELEV-002", {"open_ticket_count": 2, "open_high_priority_count": 2,
                    "high_priority_total": 2, "open_sla_breach_high_count": 2}, "ELEVATED"),
    ("R-WATCH-001", {"open_ticket_count": 1, "open_high_priority_count": 1,
                     "high_priority_total": 1, "open_sla_breach_high_count": 1}, "WATCH"),
    ("R-WATCH-002", {"max_tickets_in_14d_window": 2, "days_since_last_ticket": 30}, "WATCH"),
    ("R-WATCH-003", {"open_ticket_count": 2}, "WATCH"),
])
def test_every_row_of_the_table_is_satisfiable_and_assigns_its_own_band(
    rule_id, satisfying, band
):
    assignment = band_of(signals(**satisfying))

    assert rule_id in assignment.satisfied_rules
    assert RiskBand(assignment.band).at_least(RiskBand(band))


def test_the_shipped_table_holds_exactly_the_rows_the_tests_enumerate():
    """A row added without a test would otherwise go unexercised."""
    assert tuple(rule.rule_id for rule in SHIPPED) == (
        "R-CRIT-001", "R-ELEV-001", "R-ELEV-002",
        "R-WATCH-001", "R-WATCH-002", "R-WATCH-003",
    )


def test_every_rule_id_is_unique():
    ids = [rule.rule_id for rule in SHIPPED]

    assert len(set(ids)) == len(ids)


def test_the_table_is_keyed_by_id_so_a_brief_can_quote_the_rule_it_satisfied():
    by_id = rules_by_id(SHIPPED)

    assert by_id["R-CRIT-001"].band == "CRITICAL"
    assert set(by_id) == {rule.rule_id for rule in SHIPPED}


@pytest.mark.parametrize("rule_id", ["R-CRIT-001", "R-ELEV-001", "R-WATCH-001"])
def test_every_policy_rule_names_the_document_it_came_from(rule_id):
    """Plan A13: policy citations are structural, because the rule names its source."""
    assert rules_by_id(SHIPPED)[rule_id].because_documents == ("DOC-003",)


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------


def test_meridian_is_critical_and_satisfies_every_rule_in_the_table():
    assignment = band_of(meridian())

    assert assignment.band == "CRITICAL"
    assert assignment.satisfied_rules == tuple(rule.rule_id for rule in SHIPPED)


def test_a_customer_no_rule_speaks_about_falls_to_the_floor():
    assignment = band_of(signals())

    assert assignment == BandAssignment(band=NONE, satisfied_rules=())


def test_a_ticketless_customer_collects_no_recency_rule():
    """
    days_since_last_ticket is None, not a large number.

    "At most 30 days since the last ticket" must be false for a customer who
    has no last ticket. Treating the absence as satisfying the bound is what
    would band all 15 ticketless customers.
    """
    assignment = band_of(signals(days_since_last_ticket=None, max_tickets_in_14d_window=2))

    assert assignment.satisfied_rules == ()
    assert assignment.band == NONE


def test_the_highest_satisfied_band_wins_rather_than_the_first_listed():
    """Bands are ordinal, so table order decides reporting order and nothing else."""
    reordered = tuple(reversed(SHIPPED))

    assert assign_band(meridian(), reordered, floor=NONE).band == "CRITICAL"


def test_the_satisfied_rules_are_reported_in_table_order():
    reordered = tuple(reversed(SHIPPED))

    assert assign_band(meridian(), reordered, floor=NONE).satisfied_rules == tuple(
        rule.rule_id for rule in reordered
    )


def test_the_escalation_rule_is_load_bearing_for_critical():
    """
    Plan A25 test 11, in band form.

    Raising DOC-003's threshold makes CUST-007 non-escalated; CRITICAL
    requires the escalation state, so the band must fall.
    """
    not_escalated = meridian()
    without = signals(**{
        **{field: getattr(not_escalated, field) for field in (
            "open_ticket_count", "open_high_priority_count", "high_priority_total",
            "tickets_in_lookback", "max_tickets_in_14d_window", "days_since_last_ticket",
            "sla_breach_count", "open_sla_breach_high_count",
        )},
        "policy_escalation_state": False,
    })

    assert band_of(without).band == "ELEVATED"
    assert "R-CRIT-001" not in band_of(without).satisfied_rules


def test_a_band_assignment_projects_its_band_and_its_reasons():
    assert band_of(signals()).to_payload() == {"band": NONE, "satisfied_rules": []}


# ---------------------------------------------------------------------------
# Money never reaches the band, and never reaches the order
# ---------------------------------------------------------------------------


def test_multiplying_every_deal_amount_leaves_the_band_unchanged():
    """Plan A25 test 5. Money is not an input, so this is invariance by construction."""
    inflated = meridian()
    scaled = signals(**{
        **{field: getattr(inflated, field) for field in (
            "open_ticket_count", "open_high_priority_count", "high_priority_total",
            "tickets_in_lookback", "max_tickets_in_14d_window", "policy_escalation_state",
            "days_since_last_ticket", "sla_breach_count", "open_sla_breach_high_count",
            "dominant_ticket_category",
        )},
        "active_deals": (DealSignal(
            source_id="DEAL-001", stage="negotiation", probability=Decimal("90.00"),
            amount=MoneyValue(amount=Decimal("5361440.00"), currency="USD"),
        ),),
        "exposure_by_currency": {
            "USD": MoneyValue(amount=Decimal("5361440.00"), currency="USD")},
        "deal_under_pressure": True,
    })

    assert band_of(scaled) == band_of(meridian())


def test_the_ranking_key_is_band_then_breaches_then_velocity_then_identity():
    assert ranking_key("CUST-007", band_of(meridian()), meridian()) == (
        -RiskBand.CRITICAL.rank, -3, -5, "CUST-007",
    )


def test_an_escalated_customer_outranks_a_chronically_backlogged_one():
    """
    Plan A25 test 6: CUST-048 and CUST-009 must not outrank CUST-007.

    Their signals at the pinned as_of, measured: a single open ticket each,
    stale since January, and no escalation.
    """
    backlog = signals(open_ticket_count=1, stale_open_ticket_count=1,
                      sla_breach_count=2, days_since_last_ticket=127)
    ranked = sorted(
        [("CUST-048", backlog), ("CUST-009", backlog), ("CUST-007", meridian())],
        key=lambda pair: ranking_key(pair[0], band_of(pair[1]), pair[1]),
    )

    assert [source_id for source_id, _ in ranked] == ["CUST-007", "CUST-009", "CUST-048"]


def test_a_larger_deal_does_not_move_a_customer_up_the_order():
    rich = signals(
        open_ticket_count=1,
        active_deals=(DealSignal(
            source_id="DEAL-999", stage="negotiation", probability=Decimal("90.00"),
            amount=MoneyValue(amount=Decimal("8960000.00"), currency="INR"),
        ),),
        exposure_by_currency={
            "INR": MoneyValue(amount=Decimal("8960000.00"), currency="INR")},
    )

    assert ranking_key("CUST-015", band_of(rich), rich) > ranking_key(
        "CUST-007", band_of(meridian()), meridian()
    )


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------


def test_a_boolean_condition_compares_identity_not_truthiness_of_a_count():
    condition = Condition("policy_escalation_state", Comparison.IS, False)

    assert condition.holds_for(signals()) is True
    assert condition.holds_for(signals(policy_escalation_state=True)) is False


@pytest.mark.parametrize("comparison, threshold, value, expected", [
    (Comparison.AT_LEAST, 2, 2, True),
    (Comparison.AT_LEAST, 2, 1, False),
    (Comparison.AT_MOST, 30, 30, True),
    (Comparison.AT_MOST, 30, 31, False),
])
def test_a_numeric_condition_is_inclusive_at_its_boundary(
    comparison, threshold, value, expected
):
    condition = Condition("days_since_last_ticket", comparison, threshold)

    assert condition.holds_for(signals(days_since_last_ticket=value)) is expected


@pytest.mark.parametrize("comparison", [Comparison.AT_LEAST, Comparison.AT_MOST])
def test_a_missing_value_satisfies_neither_bound(comparison):
    condition = Condition("days_since_last_ticket", comparison, 30)

    assert condition.holds_for(signals(days_since_last_ticket=None)) is False


def test_a_rule_holds_only_when_every_condition_holds():
    rule = rules_by_id(SHIPPED)["R-WATCH-002"]

    assert rule.holds_for(signals(max_tickets_in_14d_window=2, days_since_last_ticket=30))
    assert not rule.holds_for(signals(max_tickets_in_14d_window=2, days_since_last_ticket=31))


def test_a_condition_and_a_rule_project_deterministically():
    rule = BandRule(
        rule_id="R-X", band="WATCH",
        conditions=(Condition("open_ticket_count", Comparison.AT_LEAST, 2),),
        description="", because_documents=("DOC-003",),
    )

    assert rule.to_payload() == {
        "id": "R-X", "band": "WATCH",
        "conditions": [{"signal": "open_ticket_count", "comparison": "AT_LEAST",
                        "threshold": 2}],
        "because_documents": ["DOC-003"],
    }


# ---------------------------------------------------------------------------
# A broken table is refused at load, naming the broken rule (plan A23)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", [{}, [], "bands", None, 1])
def test_a_table_that_is_not_a_non_empty_list_is_refused(raw):
    with pytest.raises(IntelligenceConfigError, match="non-empty list of band rules"):
        parse_band_rules(raw, "bands")


def test_a_rule_that_is_not_a_mapping_is_refused_by_position():
    with pytest.raises(IntelligenceConfigError, match=r"bands\[0\]: expected a mapping"):
        parse_band_rules(["R-X"], "bands")


def test_a_rule_missing_a_required_key_is_refused_by_position_and_key():
    with pytest.raises(IntelligenceConfigError, match=r"bands\[0\]: missing keys \['when'\]"):
        parse_band_rules([{"id": "R-X", "band": "WATCH"}], "bands")


def test_a_rule_carrying_an_unknown_key_is_refused():
    with pytest.raises(IntelligenceConfigError, match=r"unknown keys \['weight'\]"):
        parse_band_rules(
            [{"id": "R-X", "band": "WATCH", "when": {"open_ticket_count_at_least": 1},
              "weight": 3}], "bands")


@pytest.mark.parametrize("rule_id", ["", "  ", 7, None])
def test_a_rule_without_an_id_is_refused(rule_id):
    with pytest.raises(IntelligenceConfigError, match="expected a non-empty string"):
        parse_band_rules(
            [{"id": rule_id, "band": "WATCH", "when": {"open_ticket_count_at_least": 1}}],
            "bands")


def test_two_rules_sharing_an_id_are_refused_because_the_explanation_would_be_ambiguous():
    rule = {"band": "WATCH", "when": {"open_ticket_count_at_least": 1}}

    with pytest.raises(IntelligenceConfigError, match="is already defined"):
        parse_band_rules([{"id": "R-X", **rule}, {"id": "R-X", **rule}], "bands")


@pytest.mark.parametrize("band", ["SEVERE", "critical", "", 3, None])
def test_a_rule_naming_a_band_the_vocabulary_lacks_is_refused_by_position(band):
    """Plan A23: refused at load, naming the broken rule rather than the value alone."""
    with pytest.raises(IntelligenceConfigError, match=r"bands\[0\]\.band:"):
        parse_band_rules(
            [{"id": "R-X", "band": band, "when": {"open_ticket_count_at_least": 1}}],
            "bands")


def test_the_scale_cannot_be_widened_by_adding_a_fifth_band():
    """Four ordinal bands are M1's vocabulary. A table may not invent a fifth."""
    with pytest.raises(IntelligenceConfigError, match="is not a risk band"):
        parse_band_rules(
            [{"id": "R-X", "band": "CATASTROPHIC",
              "when": {"open_ticket_count_at_least": 1}}], "bands")


def test_ranking_a_band_outside_the_vocabulary_is_refused():
    """The order is over the ordinal scale, so an unknown band has no position."""
    with pytest.raises(IntelligenceConfigError, match="is not a risk band"):
        ranking_key("CUST-007", BandAssignment(band="SEVERE", satisfied_rules=()), signals())


@pytest.mark.parametrize("when", [{}, [], None, "always"])
def test_a_rule_with_no_condition_is_refused_because_it_would_band_everyone(when):
    with pytest.raises(IntelligenceConfigError, match="at least one condition"):
        parse_band_rules([{"id": "R-X", "band": "WATCH", "when": when}], "bands")


def test_a_condition_naming_no_known_signal_is_refused():
    with pytest.raises(IntelligenceConfigError, match="is not a boolean band input"):
        parse_band_rules(
            [{"id": "R-X", "band": "WATCH", "when": {"churn_probability": True}}], "bands")


@pytest.mark.parametrize("threshold", [-1, True, "2", 2.5, None])
def test_a_numeric_threshold_must_be_a_non_negative_integer(threshold):
    with pytest.raises(IntelligenceConfigError, match="threshold of at least 0"):
        parse_band_rules(
            [{"id": "R-X", "band": "WATCH",
              "when": {"open_ticket_count_at_least": threshold}}], "bands")


@pytest.mark.parametrize("value", [1, "true", None])
def test_a_boolean_condition_must_be_true_or_false(value):
    with pytest.raises(IntelligenceConfigError, match="expected true or false"):
        parse_band_rules(
            [{"id": "R-X", "band": "WATCH", "when": {"policy_escalation_state": value}}],
            "bands")


@pytest.mark.parametrize("documents", ["DOC-003", 3, {"a": 1}])
def test_a_citation_list_that_is_not_a_list_is_refused(documents):
    with pytest.raises(IntelligenceConfigError, match="expected a list of document ids"):
        parse_band_rules(
            [{"id": "R-X", "band": "WATCH", "when": {"open_ticket_count_at_least": 1},
              "because_documents": documents}], "bands")


@pytest.mark.parametrize("document", ["", "   ", 3, None])
def test_a_citation_that_is_not_a_document_id_is_refused_by_position(document):
    with pytest.raises(IntelligenceConfigError,
                       match=r"because_documents\[0\]: expected a document id"):
        parse_band_rules(
            [{"id": "R-X", "band": "WATCH", "when": {"open_ticket_count_at_least": 1},
              "because_documents": [document]}], "bands")


def test_a_rule_may_omit_its_description_and_its_citations():
    rules = parse_band_rules(
        [{"id": "R-X", "band": "WATCH", "when": {"open_ticket_count_at_least": 1}}], "bands")

    assert rules[0].description == ""
    assert rules[0].because_documents == ()
