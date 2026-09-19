"""
M1 contract vocabulary: bands, bases, evidence, links, signals, conflict.

These are the types every later VS-01 milestone speaks, so an invariant
stated here is one no later milestone can violate by accident. The tests
that matter most are the ones asserting something is *impossible*: model
narrative as evidence, a link whose confidence was talked up, a resolution
that has forgotten what it overruled.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.intelligence.contract import (
    ActionId,
    Conflict,
    ConflictResolution,
    DealSignal,
    DerivedLink,
    DocumentCitation,
    EdgeBasis,
    EntityRef,
    Evidence,
    EvidenceKind,
    Function,
    LinkBasis,
    LinkConfidence,
    Position,
    RecordCitation,
    RiskBand,
    SignalSet,
    Stance,
    canonical_json,
    decimal_text,
    money_payload,
)
from app.intelligence.errors import ContractViolationError
from app.intelligence.money import MoneyValue
from app.normalization.identifiers import _canonical_value

MERIDIAN_ID = "CUST-007"
TOPIC_MATCH = "performance"
FINGERPRINT = "1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00"

TICKET_FACT = Evidence(
    kind=EvidenceKind.CANONICAL_FACT,
    citation=RecordCitation("support_tickets", "TKT-075", "priority"),
)
POLICY_RULE = Evidence(
    kind=EvidenceKind.DETERMINISTIC_RULE,
    citation=DocumentCitation("DOC-003", 100, 180),
    rule_id="ESCALATION_THRESHOLD",
)
DEAL_FACT = Evidence(
    kind=EvidenceKind.CANONICAL_FACT,
    citation=RecordCitation("deals", "DEAL-001", "stage"),
)


def support_position(action=ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED) -> Position:
    return Position(
        function=Function.SUPPORT,
        stance=Stance.RESTRAIN,
        proposed_action=action,
        object_ref="DEAL-001",
        rationale="Three open high-priority tickets are past their SLA resolution target.",
        evidence=(TICKET_FACT, POLICY_RULE),
    )


def sales_position(action=ActionId.ACCELERATE_DEAL_CLOSE) -> Position:
    return Position(
        function=Function.SALES,
        stance=Stance.ADVANCE,
        proposed_action=action,
        object_ref="DEAL-001",
        rationale="DEAL-001 is in negotiation at 90 percent probability.",
        evidence=(DEAL_FACT,),
    )


# ---------------------------------------------------------------------------
# Risk band
# ---------------------------------------------------------------------------


def test_bands_are_ordinal_not_lexical():
    """CRITICAL sorts before ELEVATED as a string, which is why rank exists."""
    assert "CRITICAL" < "ELEVATED"
    assert RiskBand.CRITICAL.at_least(RiskBand.ELEVATED)
    assert not RiskBand.WATCH.at_least(RiskBand.ELEVATED)


def test_the_band_scale_runs_from_none_to_critical():
    assert [band.rank for band in RiskBand] == [0, 1, 2, 3]
    assert RiskBand.NONE.at_least(RiskBand.NONE)


# ---------------------------------------------------------------------------
# Link bases and confidence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("basis", "edge_basis", "confidence", "may_derive"),
    [
        (LinkBasis.ID_TOKEN, EdgeBasis.DERIVED_TEXT_MATCH, LinkConfidence.HIGH, True),
        (LinkBasis.EXACT_NAME, EdgeBasis.DERIVED_TEXT_MATCH, LinkConfidence.HIGH, True),
        (LinkBasis.TOPIC, EdgeBasis.DERIVED_TOPIC_MATCH, LinkConfidence.SUPPORTING, False),
    ],
)
def test_each_link_basis_fixes_its_edge_basis_confidence_and_standing(
    basis, edge_basis, confidence, may_derive
):
    assert basis.edge_basis is edge_basis
    assert basis.confidence is confidence
    assert basis.may_derive_signals is may_derive


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


def test_a_record_citation_addresses_a_canonical_business_field():
    citation = RecordCitation("support_tickets", "TKT-075", "priority")

    assert citation.to_payload() == {
        "kind": "record", "entity": "support_tickets", "id": "TKT-075", "field": "priority"}


def test_a_record_citation_may_address_a_resolved_canonical_fk():
    assert RecordCitation("deals", "DEAL-001", "customer_id").field_name == "customer_id"


def test_a_record_citation_cannot_name_an_unknown_entity():
    with pytest.raises(ContractViolationError, match="not a canonical entity"):
        RecordCitation("tickets", "TKT-075", "priority")


def test_a_record_citation_cannot_name_a_field_layer_1_does_not_have():
    with pytest.raises(ContractViolationError, match="not a citable field"):
        RecordCitation("support_tickets", "TKT-075", "severity")


@pytest.mark.parametrize("provenance", ["ingested_at", "ingestion_run_id", "record_hash", "id"])
def test_ingestion_provenance_is_never_evidence(provenance):
    """Evidence is business content or a resolved FK, never when a row was ingested."""
    with pytest.raises(ContractViolationError, match="never ingestion provenance"):
        RecordCitation("support_tickets", "TKT-075", provenance)


@pytest.mark.parametrize("source_id", ["", "   "])
def test_a_record_citation_needs_a_source_id(source_id):
    with pytest.raises(ContractViolationError, match="source_id must be a non-empty string"):
        RecordCitation("support_tickets", source_id, "priority")


def test_a_document_citation_is_a_non_empty_span():
    assert DocumentCitation("DOC-003", 100, 180).to_payload() == {
        "kind": "document", "document_id": "DOC-003", "start": 100, "end": 180}


def test_a_document_citation_needs_a_document_id():
    with pytest.raises(ContractViolationError, match="document_id must be a non-empty string"):
        DocumentCitation("", 0, 10)


def test_a_document_span_cannot_start_before_the_text():
    with pytest.raises(ContractViolationError, match="must not be negative"):
        DocumentCitation("DOC-003", -1, 10)


@pytest.mark.parametrize(("start", "end"), [(10, 10), (10, 9)])
def test_a_document_span_cannot_be_empty_or_inverted(start, end):
    with pytest.raises(ContractViolationError, match="must be non-empty"):
        DocumentCitation("DOC-003", start, end)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def test_model_narrative_evidence_cannot_be_constructed():
    """VS-01 uses no language model, so no narrative is ever a ground for a decision."""
    with pytest.raises(ContractViolationError, match="uses no language model"):
        Evidence(kind=EvidenceKind.MODEL_NARRATIVE,
                 citation=DocumentCitation("DOC-005", 0, 10))


def test_a_canonical_fact_must_cite_a_record_not_a_document():
    with pytest.raises(ContractViolationError, match="must cite RecordCitation"):
        Evidence(kind=EvidenceKind.CANONICAL_FACT,
                 citation=DocumentCitation("DOC-005", 0, 10))


def test_a_document_span_must_cite_a_document_not_a_record():
    with pytest.raises(ContractViolationError, match="must cite DocumentCitation"):
        Evidence(kind=EvidenceKind.DOCUMENT_SPAN,
                 citation=RecordCitation("documents", "DOC-005", "title"))


def test_a_derived_relationship_may_cite_either_shape():
    record = Evidence(kind=EvidenceKind.DERIVED_RELATIONSHIP,
                      citation=RecordCitation("deals", "DEAL-001", "customer_id"))
    document = Evidence(kind=EvidenceKind.DERIVED_RELATIONSHIP,
                        citation=DocumentCitation("DOC-005", 12, 20))

    assert record.kind is document.kind is EvidenceKind.DERIVED_RELATIONSHIP


def test_a_deterministic_rule_names_the_rule_and_the_document_it_came_from():
    """The citation cannot drift from the rule, because the rule carries the citation."""
    assert POLICY_RULE.to_payload() == {
        "kind": "DETERMINISTIC_RULE",
        "citation": {"kind": "document", "document_id": "DOC-003", "start": 100, "end": 180},
        "rule_id": "ESCALATION_THRESHOLD",
    }


def test_a_deterministic_rule_without_a_rule_id_is_refused():
    with pytest.raises(ContractViolationError, match="rule_id must be a non-empty string"):
        Evidence(kind=EvidenceKind.DETERMINISTIC_RULE,
                 citation=DocumentCitation("DOC-003", 100, 180))


def test_only_a_deterministic_rule_carries_a_rule_id():
    with pytest.raises(ContractViolationError, match="only meaningful for DETERMINISTIC_RULE"):
        Evidence(kind=EvidenceKind.CANONICAL_FACT,
                 citation=RecordCitation("support_tickets", "TKT-075", "priority"),
                 rule_id="ESCALATION_THRESHOLD")


def test_evidence_without_a_rule_omits_the_key_rather_than_carrying_a_null():
    assert TICKET_FACT.to_payload() == {
        "kind": "CANONICAL_FACT",
        "citation": {"kind": "record", "entity": "support_tickets", "id": "TKT-075",
                     "field": "priority"},
    }


# ---------------------------------------------------------------------------
# Entity references and derived links
# ---------------------------------------------------------------------------


def test_an_entity_reference_addresses_a_canonical_entity_by_source_identity():
    assert EntityRef("customers", "CUST-007").to_payload() == {
        "entity": "customers", "id": "CUST-007"}


def test_an_entity_reference_cannot_name_an_unknown_entity():
    with pytest.raises(ContractViolationError, match="not a canonical entity"):
        EntityRef("accounts", "CUST-007")


def test_an_entity_reference_needs_a_source_id():
    with pytest.raises(ContractViolationError, match="source_id must be a non-empty string"):
        EntityRef("customers", "")


def make_link(**overrides) -> DerivedLink:
    arguments = {
        "source": EntityRef("documents", "DOC-009"),
        "target": EntityRef("customers", "CUST-007"),
        "basis": LinkBasis.ID_TOKEN,
        "confidence": LinkConfidence.HIGH,
        "matched_token": MERIDIAN_ID,
        "evidence": (Evidence(kind=EvidenceKind.DERIVED_RELATIONSHIP,
                              citation=DocumentCitation("DOC-009", 42, 50)),),
        "source_system": "csv_demo",
        "layer1_fingerprint": FINGERPRINT,
        "linker_version": "1",
    }
    arguments.update(overrides)
    return DerivedLink(**arguments)


def test_a_derived_link_records_both_ends_its_basis_and_its_provenance():
    link = make_link()

    assert link.source.source_id == "DOC-009"
    assert link.target.source_id == "CUST-007"
    assert link.basis is LinkBasis.ID_TOKEN
    assert link.edge_basis is EdgeBasis.DERIVED_TEXT_MATCH
    assert link.confidence is LinkConfidence.HIGH
    assert link.layer1_fingerprint == FINGERPRINT
    assert link.linker_version == "1"


def test_a_derived_links_confidence_cannot_be_talked_up():
    """Confidence follows from the basis, so a topical link stays supporting."""
    with pytest.raises(ContractViolationError, match="never chosen per link"):
        make_link(basis=LinkBasis.TOPIC, confidence=LinkConfidence.HIGH)


def test_a_topical_link_is_supporting_and_may_not_derive_a_signal():
    link = make_link(basis=LinkBasis.TOPIC, confidence=LinkConfidence.SUPPORTING,
                     matched_token=TOPIC_MATCH, source=EntityRef("documents", "DOC-010"),
                     evidence=(Evidence(kind=EvidenceKind.DERIVED_RELATIONSHIP,
                                        citation=DocumentCitation("DOC-010", 0, 11)),))

    assert link.confidence is LinkConfidence.SUPPORTING
    assert link.basis.may_derive_signals is False


def test_a_link_cannot_join_an_entity_to_itself():
    with pytest.raises(ContractViolationError, match="cannot join"):
        make_link(source=EntityRef("customers", "CUST-007"))


def test_a_derived_link_must_record_the_token_it_matched():
    with pytest.raises(ContractViolationError, match="matched_token must be a non-empty string"):
        make_link(matched_token="")


def test_a_derived_link_must_name_its_source_system_and_linker_version():
    with pytest.raises(ContractViolationError, match="source_system must be"):
        make_link(source_system="")
    with pytest.raises(ContractViolationError, match="linker_version must be"):
        make_link(linker_version="")


@pytest.mark.parametrize("fingerprint", ["", "not-a-digest", FINGERPRINT[:-1], FINGERPRINT.upper()])
def test_a_derived_link_must_be_stamped_with_a_real_layer_1_snapshot(fingerprint):
    with pytest.raises(ContractViolationError, match="64-character hex SHA-256"):
        make_link(layer1_fingerprint=fingerprint)


def test_a_derived_link_must_carry_the_evidence_it_was_derived_from():
    with pytest.raises(ContractViolationError, match="must carry the evidence"):
        make_link(evidence=())


def test_a_derived_link_serialises_both_ends_and_its_whole_provenance():
    assert make_link().to_payload() == {
        "source": {"entity": "documents", "id": "DOC-009"},
        "target": {"entity": "customers", "id": "CUST-007"},
        "basis": "ID_TOKEN",
        "edge_basis": "DERIVED_TEXT_MATCH",
        "confidence": "HIGH",
        "matched_token": MERIDIAN_ID,
        "evidence": [{"kind": "DERIVED_RELATIONSHIP",
                      "citation": {"kind": "document", "document_id": "DOC-009",
                                   "start": 42, "end": 50}}],
        "source_system": "csv_demo",
        "layer1_fingerprint": FINGERPRINT,
        "linker_version": "1",
    }


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


DEAL_001 = DealSignal(
    source_id="DEAL-001",
    stage="negotiation",
    probability=Decimal("90.00"),
    amount=MoneyValue(Decimal("5361.44"), "USD"),
)


def make_signals(**overrides) -> SignalSet:
    arguments = {
        "open_ticket_count": 4,
        "open_high_priority_count": 3,
        "high_priority_total": 4,
        "tickets_in_lookback": 5,
        "max_tickets_in_14d_window": 5,
        "policy_escalation_state": True,
        "days_since_last_ticket": 22,
        "sla_breach_count": 5,
        "open_sla_breach_high_count": 3,
        "stale_open_ticket_count": 0,
        "dominant_ticket_category": "performance",
        "active_deals": (DEAL_001,),
        "exposure_by_currency": {"USD": MoneyValue(Decimal("4825.30"), "USD")},
        "active_project_count": 0,
        "contract_document_ids": ("DOC-006",),
        "deal_under_pressure": True,
    }
    arguments.update(overrides)
    return SignalSet(**arguments)


def test_a_deal_signal_keeps_stage_probability_and_currency_qualified_amount():
    assert DEAL_001.to_payload() == {
        "id": "DEAL-001", "stage": "negotiation", "probability": "90",
        "amount": {"amount": "5361.44", "currency": "USD"}}


def test_a_deal_signal_probability_must_be_a_decimal_percentage():
    with pytest.raises(ContractViolationError, match="must be a Decimal"):
        DealSignal("DEAL-001", "negotiation", 90.0, MoneyValue(Decimal("1"), "USD"))


@pytest.mark.parametrize("probability", ["-0.01", "100.01"])
def test_a_deal_signal_probability_must_be_within_zero_and_one_hundred(probability):
    with pytest.raises(ContractViolationError, match=r"percentage in \[0, 100\]"):
        DealSignal("DEAL-001", "negotiation", Decimal(probability),
                   MoneyValue(Decimal("1"), "USD"))


@pytest.mark.parametrize("blank", ["source_id", "stage"])
def test_a_deal_signal_needs_its_identity_and_stage(blank):
    arguments = {"source_id": "DEAL-001", "stage": "negotiation",
                 "probability": Decimal("90"), "amount": MoneyValue(Decimal("1"), "USD")}
    arguments[blank] = ""

    with pytest.raises(ContractViolationError, match="non-empty string"):
        DealSignal(**arguments)


def test_the_open_high_priority_count_is_three_and_the_total_is_four():
    """The v1 plan asserted four open high-priority tickets. It is three; TKT-073 is resolved."""
    signals = make_signals()

    assert signals.open_high_priority_count == 3
    assert signals.high_priority_total == 4


def test_the_active_deal_count_is_derived_so_it_cannot_disagree_with_the_deals():
    assert make_signals().active_deal_count == 1
    assert make_signals(active_deals=(), deal_under_pressure=False).active_deal_count == 0


@pytest.mark.parametrize("count", [
    "open_ticket_count", "open_high_priority_count", "high_priority_total",
    "tickets_in_lookback", "max_tickets_in_14d_window", "sla_breach_count",
    "open_sla_breach_high_count", "stale_open_ticket_count", "active_project_count",
])
def test_no_count_may_be_negative(count):
    with pytest.raises(ContractViolationError, match="must not be negative"):
        make_signals(**{count: -1})


def test_days_since_the_last_ticket_may_be_absent_but_never_negative():
    assert make_signals(days_since_last_ticket=None).days_since_last_ticket is None

    with pytest.raises(ContractViolationError, match="days_since_last_ticket must not be negative"):
        make_signals(days_since_last_ticket=-1)


def test_open_high_priority_tickets_cannot_outnumber_open_tickets():
    with pytest.raises(ContractViolationError, match="cannot exceed open_ticket_count"):
        make_signals(open_ticket_count=2)


def test_open_high_priority_tickets_cannot_outnumber_all_high_priority_tickets():
    with pytest.raises(ContractViolationError, match="cannot exceed high_priority_total"):
        make_signals(high_priority_total=2)


def test_open_high_priority_breaches_cannot_outnumber_open_high_priority_tickets():
    with pytest.raises(ContractViolationError, match="cannot exceed open_high_priority_count"):
        make_signals(open_sla_breach_high_count=4)


def test_exposure_is_filed_under_its_own_currency():
    with pytest.raises(ContractViolationError, match=r"exposure_by_currency\['INR'\] holds USD"):
        make_signals(exposure_by_currency={"INR": MoneyValue(Decimal("1"), "USD")})


def test_a_deal_is_only_under_pressure_when_an_escalation_and_a_deal_both_exist():
    with pytest.raises(ContractViolationError, match="requires an escalation state"):
        make_signals(policy_escalation_state=False)
    with pytest.raises(ContractViolationError, match="requires an escalation state"):
        make_signals(active_deals=())


def test_the_signal_payload_carries_every_value_with_money_still_qualified():
    payload = make_signals().to_payload()

    assert payload["open_high_priority_count"] == 3
    assert payload["high_priority_total"] == 4
    assert payload["policy_escalation_state"] is True
    assert payload["days_since_last_ticket"] == 22
    assert payload["dominant_ticket_category"] == "performance"
    assert payload["active_deal_count"] == 1
    assert payload["active_deals"] == [DEAL_001.to_payload()]
    # Trailing zeros are insignificant under Layer 1's hashing discipline.
    assert payload["exposure_by_currency"] == {"USD": {"amount": "4825.3", "currency": "USD"}}
    assert payload["contract_document_ids"] == ["DOC-006"]
    assert payload["deal_under_pressure"] is True


def test_the_signal_payload_orders_currencies_so_two_runs_serialise_alike():
    exposure = {"USD": MoneyValue(Decimal("1"), "USD"), "INR": MoneyValue(Decimal("2"), "INR")}
    reversed_exposure = {"INR": MoneyValue(Decimal("2"), "INR"),
                         "USD": MoneyValue(Decimal("1"), "USD")}

    assert canonical_json(make_signals(exposure_by_currency=exposure).to_payload()) == \
        canonical_json(make_signals(exposure_by_currency=reversed_exposure).to_payload())


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


def test_a_position_states_a_function_a_stance_an_action_and_its_object():
    position = support_position()

    assert position.function is Function.SUPPORT
    assert position.stance is Stance.RESTRAIN
    assert position.proposed_action is ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED
    assert position.object_ref == "DEAL-001"


def test_a_position_exposes_where_each_of_its_claims_is_verified():
    assert support_position().citations == (TICKET_FACT.citation, POLICY_RULE.citation)


def test_a_position_without_evidence_is_refused():
    with pytest.raises(ContractViolationError, match="with no evidence"):
        Position(function=Function.SALES, stance=Stance.ADVANCE,
                 proposed_action=ActionId.ACCELERATE_DEAL_CLOSE, object_ref="DEAL-001",
                 rationale="Because.", evidence=())


@pytest.mark.parametrize("blank", ["object_ref", "rationale"])
def test_a_position_needs_an_object_and_a_reason(blank):
    arguments = {"function": Function.SALES, "stance": Stance.ADVANCE,
                 "proposed_action": ActionId.ACCELERATE_DEAL_CLOSE, "object_ref": "DEAL-001",
                 "rationale": "Because.", "evidence": (DEAL_FACT,)}
    arguments[blank] = "  "

    with pytest.raises(ContractViolationError, match="non-empty string"):
        Position(**arguments)


def test_a_position_serialises_its_stance_action_and_evidence():
    payload = sales_position().to_payload()

    assert payload["function"] == "SALES"
    assert payload["stance"] == "ADVANCE"
    assert payload["proposed_action"] == "ACCELERATE_DEAL_CLOSE"
    assert payload["object_ref"] == "DEAL-001"
    assert payload["evidence"] == [DEAL_FACT.to_payload()]


# ---------------------------------------------------------------------------
# Conflict
# ---------------------------------------------------------------------------


def test_a_conflict_holds_both_competing_actions_over_one_object():
    conflict = Conflict("DEAL-001", (support_position(), sales_position()))

    assert conflict.proposed_actions == (
        ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED, ActionId.ACCELERATE_DEAL_CLOSE)


def test_a_conflict_needs_at_least_two_positions():
    with pytest.raises(ContractViolationError, match="at least two positions"):
        Conflict("DEAL-001", (support_position(),))


def test_a_conflict_needs_an_object():
    with pytest.raises(ContractViolationError, match="object_ref must be a non-empty string"):
        Conflict("", (support_position(), sales_position()))


def test_one_function_states_one_position_per_conflict():
    with pytest.raises(ContractViolationError, match="at most one position"):
        Conflict("DEAL-001", (support_position(),
                              support_position(ActionId.ESCALATE_TO_ACCOUNT_OWNER_PER_SLA)))


def test_positions_on_different_objects_are_not_one_conflict():
    elsewhere = Position(
        function=Function.SALES, stance=Stance.ADVANCE,
        proposed_action=ActionId.ACCELERATE_DEAL_CLOSE, object_ref="DEAL-002",
        rationale="A different deal entirely.", evidence=(DEAL_FACT,))

    with pytest.raises(ContractViolationError, match="does not belong to the conflict"):
        Conflict("DEAL-001", (support_position(), elsewhere))


def test_two_functions_wanting_the_same_thing_is_agreement_not_conflict():
    with pytest.raises(ContractViolationError, match="agreement, not conflict"):
        Conflict("DEAL-001", (support_position(ActionId.ACCELERATE_DEAL_CLOSE),
                              sales_position()))


def test_a_conflict_serialises_every_competing_position():
    payload = Conflict("DEAL-001", (support_position(), sales_position())).to_payload()

    assert payload["object_ref"] == "DEAL-001"
    assert [position["function"] for position in payload["positions"]] == ["SUPPORT", "SALES"]


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------


def make_resolution(**overrides) -> ConflictResolution:
    support, sales = support_position(), sales_position()
    arguments = {
        "policy_id": "CONF-001",
        "conflict": Conflict("DEAL-001", (support, sales)),
        "prevailing": support,
        "rationale": "An active support-policy escalation outranks deal acceleration.",
        "evidence": (POLICY_RULE,),
    }
    arguments.update(overrides)
    return ConflictResolution(**arguments)


def test_a_resolution_names_the_policy_and_the_action_that_prevailed():
    resolution = make_resolution()

    assert resolution.policy_id == "CONF-001"
    assert resolution.resolved_action is ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED


def test_the_losing_position_is_preserved_whole_with_its_own_evidence():
    resolution = make_resolution()

    assert len(resolution.dissent) == 1
    dissent = resolution.dissent[0]
    assert dissent.function is Function.SALES
    assert dissent.proposed_action is ActionId.ACCELERATE_DEAL_CLOSE
    assert dissent.evidence == (DEAL_FACT,)
    assert dissent.rationale


def test_dissent_is_derived_from_the_conflict_so_there_is_no_field_to_leave_empty():
    resolution = make_resolution()

    assert set(resolution.dissent) | {resolution.prevailing} == set(
        resolution.conflict.positions)
    assert resolution.dissent


def test_a_resolution_must_choose_one_of_the_conflicting_positions():
    outsider = Position(
        function=Function.SALES, stance=Stance.NEUTRAL, proposed_action=ActionId.NO_ACTION,
        object_ref="DEAL-001", rationale="Nothing to do.", evidence=(DEAL_FACT,))

    with pytest.raises(ContractViolationError, match="is not one of the conflicting positions"):
        make_resolution(prevailing=outsider)


def test_a_resolution_must_cite_why_it_resolved_the_way_it_did():
    with pytest.raises(ContractViolationError, match="without citing why"):
        make_resolution(evidence=())


@pytest.mark.parametrize("blank", ["policy_id", "rationale"])
def test_a_resolution_needs_a_named_policy_and_a_reason(blank):
    with pytest.raises(ContractViolationError, match="non-empty string"):
        make_resolution(**{blank: ""})


def test_a_resolution_serialises_the_winner_and_the_dissent_side_by_side():
    payload = make_resolution().to_payload()

    assert payload["policy_id"] == "CONF-001"
    assert payload["resolved_action"] == "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED"
    assert payload["prevailing"]["function"] == "SUPPORT"
    assert [position["proposed_action"] for position in payload["dissent"]] == [
        "ACCELERATE_DEAL_CLOSE"]
    assert payload["evidence"] == [POLICY_RULE.to_payload()]
    assert payload["conflict"]["object_ref"] == "DEAL-001"


# ---------------------------------------------------------------------------
# Serialisation discipline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["0", "0.00", "-0", "5361.44", "90.00", "1E+3", "0.10"])
def test_decimal_text_agrees_with_layer_1s_record_hash_discipline(text):
    """A Layer 2 payload hash and a Layer 1 record_hash must never disagree on a number."""
    value = Decimal(text)

    assert decimal_text(value) == _canonical_value("amount", value)


def test_a_non_finite_decimal_cannot_be_serialised():
    with pytest.raises(ContractViolationError, match="non-finite Decimal"):
        decimal_text(Decimal("NaN"))


def test_money_is_serialised_as_an_amount_and_its_currency_never_a_bare_number():
    assert money_payload(MoneyValue(Decimal("5361.4400"), "USD")) == {
        "amount": "5361.44", "currency": "USD"}


def test_canonical_json_is_insensitive_to_insertion_order():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1}) == '{"a":2,"b":1}'
