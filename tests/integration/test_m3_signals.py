"""
M3 signal engine and band assignment against a real database.

The demo dataset is ingested by the clean full-dataset path, so every number
asserted here is the measured one rather than a remembered one. Three kinds
of test live in this file.

Behaviour: every signal hand-computed for CUST-007, for the two chronic
backlog accounts the plan names, for a ticketless customer and for an
inactive one; and the same signals again at the 2026-08-27 fallback date,
where the SLA-breach ranking genuinely differs.

Invariants: exactly one escalated and one CRITICAL customer; chronic backlog
never drives a band; money never moves the order; the DOC-003 threshold is
load-bearing; two runs over rows in a different physical order are
byte-identical; Layer 1 is neither written nor re-fingerprinted.

Plan A23: the three states stay distinct. Every source key in the demo
dataset resolves, so a missing key and an unresolved one cannot be shown
from it. They are written straight into the isolated test database, which is
also where a second source system comes from - the demo dataset holds one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.connectors import CsvConnector, CsvConnectorConfig, SourceConnector
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence import RiskBand, Scope, resolve_scope
from app.intelligence.bands import assign_band, ranking_key
from app.intelligence.config import default_risk_rules, load_risk_rules
from app.intelligence.scope import layer1_fingerprint
from app.intelligence.signals import (
    DataQualityState,
    compute_all_signals,
    compute_signals,
    customers_in_scope,
    data_quality_notes,
)
from app.persistence.models import Customer, Deal, Project, SupportTicket
from app.relationships import UnknownCustomerError, neighbourhood

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
PINNED = "1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00"
SOURCE_SYSTEM = "csv_demo"
OTHER_SOURCE_SYSTEM = "other_demo"

#: The acceptance date (plan A27). The max(created_at) fallback is 2026-08-27,
#: and plan defect 3 records that the two disagree about the breach ranking.
ACCEPTANCE_AS_OF = date(2026, 9, 18)
FALLBACK_AS_OF = date(2026, 8, 27)

MERIDIAN = "CUST-007"
NONE = str(RiskBand.NONE)

#: The two chronic backlog accounts of strategy 4.4: a single medium ticket
#: each, open since January, which a breach-age signal would rank first.
BACKLOG_ACCOUNTS = ("CUST-009", "CUST-048")
#: Ticketless, and inactive as well. All four inactive customers are ticketless.
INACTIVE_TICKETLESS = "CUST-002"
ACTIVE_TICKETLESS = "CUST-011"
TICKETLESS_COUNT = 15

REORDERABLE = ("support_tickets", "deals", "projects")


def _csv_connector() -> SourceConnector:
    config = CsvConnectorConfig.from_yaml(REPO / "config" / "connectors" / "csv_demo.yaml")
    config.data_directory = str(DEMO_DIR)
    return CsvConnector(config)


@pytest.fixture
def demo(e1_sessions: sessionmaker[Session]) -> sessionmaker[Session]:
    """The clean full-dataset path of plan A28: 233 rows, 7 entity types, 0 rejected."""
    counts = run_ingestion(_csv_connector(), e1_sessions, IngestionRequest()).counts
    assert counts.rejected == 0
    return e1_sessions


@pytest.fixture
def scope(demo: sessionmaker[Session]) -> Scope:
    with demo() as session:
        return resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=ACCEPTANCE_AS_OF)


def signals_for(sessions, scope: Scope, customer: str):
    with sessions() as session:
        return compute_signals(session, scope, customer)


def band_for(sessions, scope: Scope, customer: str):
    result = signals_for(sessions, scope, customer)
    return assign_band(result.signals, default_risk_rules().band_rules, floor=NONE)


def _provenance(entity_type: str, source_system: str = OTHER_SOURCE_SYSTEM) -> dict[str, object]:
    """Provenance columns a synthetic row needs. No FK constrains them."""
    return {
        "source_system": source_system,
        "source_entity": entity_type,
        "ingestion_run_id": uuid.uuid4(),
        "record_hash": "0" * 64,
        "ingested_at": datetime(2026, 1, 1, tzinfo=UTC),
    }


# ---------------------------------------------------------------------------
# Every signal, hand-computed, at the pinned as_of
# ---------------------------------------------------------------------------


def test_meridians_signals_are_the_values_plan_a10_measured(demo, scope):
    """
    S1-S15 for CUST-007 at 2026-09-18.

    S2 and S2b are the pair plan defect 2 was about: TKT-073 is high
    priority and resolved, so three high-priority tickets are open while
    four exist in total. Asserting both is what stops them collapsing back
    into one wrong number.
    """
    result = signals_for(demo, scope, MERIDIAN)
    s = result.signals

    assert s.open_ticket_count == 4
    assert s.open_high_priority_count == 3
    assert s.high_priority_total == 4
    assert s.tickets_in_lookback == 5
    assert s.max_tickets_in_14d_window == 5
    assert s.policy_escalation_state is True
    assert s.days_since_last_ticket == 22
    assert s.sla_breach_count == 5
    assert s.open_sla_breach_high_count == 3
    assert s.stale_open_ticket_count == 0
    assert s.dominant_ticket_category == "performance"
    assert s.active_project_count == 0
    assert s.deal_under_pressure is True


def test_meridians_open_high_priority_count_is_three_not_four(demo, scope):
    """Plan defect 2, pinned on its own because v1 got exactly this wrong."""
    s = signals_for(demo, scope, MERIDIAN).signals

    assert (s.open_high_priority_count, s.high_priority_total) == (3, 4)


def test_meridians_escalation_window_is_the_one_the_plan_measured(demo, scope):
    result = signals_for(demo, scope, MERIDIAN)

    assert result.escalation_window.start == date(2026, 8, 18)
    assert result.escalation_window.end == date(2026, 8, 31)
    assert result.escalation_window.count == 5


def test_meridians_only_deal_is_deal_001_in_negotiation_at_ninety_percent(demo, scope):
    s = signals_for(demo, scope, MERIDIAN).signals

    assert s.active_deal_count == 1
    deal = s.active_deals[0]
    assert (deal.source_id, deal.stage) == ("DEAL-001", "negotiation")
    assert deal.probability == Decimal("90.00")
    assert deal.amount.amount == Decimal("5361.44")
    assert deal.amount.currency == "USD"


def test_meridians_exposure_is_stated_per_currency_and_never_totalled(demo, scope):
    s = signals_for(demo, scope, MERIDIAN).signals

    assert set(s.exposure_by_currency) == {"USD"}
    assert str(s.exposure_by_currency["USD"]) == "USD 5361.44"


def test_a_multi_currency_customer_reports_every_currency_and_totals_none_of_them(
    demo, scope
):
    """
    Plan A25 test 14. CUST-042 holds two USD deals and two INR deals.

    Each currency is stated on its own, the per-currency totals are exact,
    and no figure spans the two: VS-01 has no FX rate set, so a portfolio
    number would be invented rather than computed.
    """
    s = signals_for(demo, scope, "CUST-042").signals

    assert s.active_deal_count == 4
    assert [deal.source_id for deal in s.active_deals] == [
        "DEAL-005", "DEAL-008", "DEAL-016", "DEAL-032"
    ]
    assert sorted(s.exposure_by_currency) == ["INR", "USD"]
    assert s.exposure_by_currency["USD"].amount == Decimal("107746.98")
    assert s.exposure_by_currency["INR"].amount == Decimal("9611500.00")


def test_two_currencies_of_one_customer_cannot_be_added_together(demo, scope):
    """The type refuses it, so no call site can produce a cross-currency total."""
    from app.intelligence.errors import CurrencyMismatchError

    s = signals_for(demo, scope, "CUST-042").signals

    with pytest.raises(CurrencyMismatchError):
        _ = s.exposure_by_currency["USD"] + s.exposure_by_currency["INR"]


def test_meridian_has_no_active_project_and_the_signal_says_so(demo, scope):
    """Plan A17: absence is stated, never omitted."""
    assert signals_for(demo, scope, MERIDIAN).signals.active_project_count == 0


def test_no_signal_names_a_contract_document_because_that_is_m4s(demo, scope):
    """Plan A11: S14 is evidence, and M4 owns every Document to Customer link."""
    for result in compute_all_signals_for(demo, scope):
        assert result.signals.contract_document_ids == ()


def compute_all_signals_for(sessions, scope: Scope):
    with sessions() as session:
        return compute_all_signals(session, scope)


# ---------------------------------------------------------------------------
# The chronic backlog accounts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("customer, days_since", [("CUST-009", 31), ("CUST-048", 127)])
def test_a_backlog_account_reports_its_stale_ticket_without_escalating(
    demo, scope, customer, days_since
):
    """
    Strategy 4.4: a January ticket is chronic backlog, not active deterioration.

    It is reported - the count is one, and the ticket is named - but the
    escalation state is false and the band is NONE.
    """
    result = signals_for(demo, scope, customer)

    assert result.signals.stale_open_ticket_count == 1
    assert len(result.backlog_ticket_ids) == 1
    assert result.signals.policy_escalation_state is False
    assert result.signals.days_since_last_ticket == days_since


@pytest.mark.parametrize("customer, ticket", [("CUST-009", "TKT-010"), ("CUST-048", "TKT-005")])
def test_the_backlog_ticket_is_named_so_a_brief_can_cite_it(demo, scope, customer, ticket):
    assert signals_for(demo, scope, customer).backlog_ticket_ids == (ticket,)


def test_meridian_has_no_chronic_backlog_at_all(demo, scope):
    """Its open tickets are three weeks old, not eight months."""
    result = signals_for(demo, scope, MERIDIAN)

    assert result.signals.stale_open_ticket_count == 0
    assert result.backlog_ticket_ids == ()


@pytest.mark.parametrize("customer", BACKLOG_ACCOUNTS)
def test_a_backlog_account_does_not_outrank_meridian(demo, scope, customer):
    """Plan A25 test 6, against the database rather than a constructed signal set."""
    meridian = signals_for(demo, scope, MERIDIAN)
    other = signals_for(demo, scope, customer)

    assert ranking_key(MERIDIAN, band_for(demo, scope, MERIDIAN), meridian.signals) < \
        ranking_key(customer, band_for(demo, scope, customer), other.signals)


# ---------------------------------------------------------------------------
# Negative cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("customer", [ACTIVE_TICKETLESS, INACTIVE_TICKETLESS])
def test_a_ticketless_customer_yields_zeros_and_an_absence_rather_than_an_error(
    demo, scope, customer
):
    """Plan A23: a ticketless customer is band NONE, not a failure."""
    s = signals_for(demo, scope, customer).signals

    assert s.open_ticket_count == 0
    assert s.tickets_in_lookback == 0
    assert s.max_tickets_in_14d_window == 0
    assert s.policy_escalation_state is False
    assert s.days_since_last_ticket is None
    assert s.dominant_ticket_category is None
    assert s.stale_open_ticket_count == 0


def test_a_ticketless_customer_has_no_escalation_window(demo, scope):
    assert signals_for(demo, scope, ACTIVE_TICKETLESS).escalation_window is None


@pytest.mark.parametrize("customer", [ACTIVE_TICKETLESS, INACTIVE_TICKETLESS])
def test_a_ticketless_customer_bands_none(demo, scope, customer):
    assignment = band_for(demo, scope, customer)

    assert (assignment.band, assignment.satisfied_rules) == (NONE, ())


def test_all_fifteen_ticketless_customers_band_none(demo, scope):
    """Plan A25 test 10: 15 in total, of which the 4 inactive ones are a subset."""
    ticketless = [
        result for result in compute_all_signals_for(demo, scope)
        if result.signals.days_since_last_ticket is None
    ]

    assert len(ticketless) == TICKETLESS_COUNT
    for result in ticketless:
        assignment = assign_band(result.signals, default_risk_rules().band_rules, floor=NONE)
        assert assignment.band == NONE, result.customer.source_id


# ---------------------------------------------------------------------------
# M3's acceptance: one escalated customer, one CRITICAL customer
# ---------------------------------------------------------------------------


def test_meridian_is_the_only_escalated_customer_in_the_whole_dataset(demo, scope):
    escalated = [
        result.customer.source_id for result in compute_all_signals_for(demo, scope)
        if result.signals.policy_escalation_state
    ]

    assert escalated == [MERIDIAN]


def test_meridian_is_the_only_critical_customer_in_the_whole_dataset(demo, scope):
    rules = default_risk_rules().band_rules
    critical = [
        result.customer.source_id for result in compute_all_signals_for(demo, scope)
        if assign_band(result.signals, rules, floor=NONE).band == "CRITICAL"
    ]

    assert critical == [MERIDIAN]


def test_the_band_distribution_over_the_whole_dataset_is_the_measured_one(demo, scope):
    rules = default_risk_rules().band_rules
    bands: dict[str, list[str]] = {}
    for result in compute_all_signals_for(demo, scope):
        band = assign_band(result.signals, rules, floor=NONE).band
        bands.setdefault(band, []).append(result.customer.source_id)

    assert bands["CRITICAL"] == [MERIDIAN]
    assert bands["WATCH"] == ["CUST-025", "CUST-036"]
    assert "ELEVATED" not in bands
    assert len(bands[NONE]) == 47


def test_meridian_ranks_first_over_the_whole_dataset(demo, scope):
    rules = default_risk_rules().band_rules
    ranked = sorted(
        compute_all_signals_for(demo, scope),
        key=lambda result: ranking_key(
            result.customer.source_id,
            assign_band(result.signals, rules, floor=NONE),
            result.signals,
        ),
    )

    assert ranked[0].customer.source_id == MERIDIAN


def test_every_customer_in_scope_gets_a_signal_set(demo, scope):
    results = compute_all_signals_for(demo, scope)

    assert len(results) == 50
    assert [r.customer.source_id for r in results] == sorted(
        r.customer.source_id for r in results
    )


# ---------------------------------------------------------------------------
# as_of sensitivity (plan defect 3)
# ---------------------------------------------------------------------------


@pytest.fixture
def fallback_scope(demo: sessionmaker[Session]) -> Scope:
    """The ad-hoc default: max(support_tickets.created_at), which is 2026-08-27."""
    with demo() as session:
        return resolve_scope(session, source_system=SOURCE_SYSTEM)


def test_the_ad_hoc_fallback_resolves_to_the_datasets_last_ticket_date(fallback_scope):
    assert fallback_scope.as_of == FALLBACK_AS_OF


def test_meridians_breach_counts_differ_between_the_two_evaluation_dates(
    demo, scope, fallback_scope
):
    """
    Plan defect 3: at 2026-08-27 CUST-007 has fewer breaches than at the
    pinned date, because three of its tickets have had less time to breach.
    The signal engine must report the position on the date it was asked
    about, not the latest one it can see.
    """
    pinned = signals_for(demo, scope, MERIDIAN).signals
    fallback = signals_for(demo, fallback_scope, MERIDIAN).signals

    assert (pinned.sla_breach_count, pinned.open_sla_breach_high_count) == (5, 3)
    assert (fallback.sla_breach_count, fallback.open_sla_breach_high_count) == (3, 2)


def test_meridian_is_escalated_at_both_evaluation_dates(demo, scope, fallback_scope):
    assert signals_for(demo, scope, MERIDIAN).signals.policy_escalation_state is True
    assert signals_for(demo, fallback_scope, MERIDIAN).signals.policy_escalation_state is True


def test_days_since_the_last_ticket_is_zero_on_the_day_it_was_raised(demo, fallback_scope):
    assert signals_for(demo, fallback_scope, MERIDIAN).signals.days_since_last_ticket == 0


def test_meridian_is_still_the_only_escalated_customer_at_the_fallback_date(
    demo, fallback_scope
):
    escalated = [
        result.customer.source_id
        for result in compute_all_signals_for(demo, fallback_scope)
        if result.signals.policy_escalation_state
    ]

    assert escalated == [MERIDIAN]


def test_an_as_of_before_all_data_yields_nothing_rather_than_failing(demo):
    """Plan A23: as_of before all data means every signal is empty, not an error."""
    with demo() as session:
        early = resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=date(2020, 1, 1))
        result = compute_signals(session, early, MERIDIAN)

    assert result.signals.open_ticket_count == 0
    assert result.signals.days_since_last_ticket is None
    assert result.escalation_window is None


def test_an_as_of_in_the_future_is_permitted_and_recency_decays(demo):
    """Plan A23: a future as_of is allowed; the account simply looks quieter."""
    with demo() as session:
        later = resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=date(2027, 6, 1))
        result = compute_signals(session, later, MERIDIAN)

    assert result.signals.policy_escalation_state is False
    assert result.signals.tickets_in_lookback == 0
    assert result.signals.open_ticket_count == 4


# ---------------------------------------------------------------------------
# Liveness: the configuration is load-bearing, not decorative
# ---------------------------------------------------------------------------


def test_raising_doc_003s_threshold_from_three_to_six_de_escalates_meridian(
    demo, scope, tmp_path
):
    """Plan A25 test 11. If this passes unchanged, the rule is not being read."""
    import yaml

    raw = yaml.safe_load(
        (REPO / "config" / "intelligence" / "risk_rules.yaml").read_text(encoding="utf-8")
    )
    raw["escalation"]["ticket_threshold"] = 6
    path = tmp_path / "risk_rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    stricter = load_risk_rules(path)

    with demo() as session:
        result = compute_signals(session, scope, MERIDIAN, config=stricter)

    assert result.signals.policy_escalation_state is False
    assert assign_band(result.signals, stricter.band_rules, floor=NONE).band == "ELEVATED"


def test_shrinking_the_lookback_de_escalates_meridian(demo, scope, tmp_path):
    """
    Strategy 4.4's constraint, exercised.

    With a 14-day lookback the August burst is out of view at 2026-09-18,
    so the escalation state falls even though the tickets are unchanged.
    """
    import yaml

    raw = yaml.safe_load(
        (REPO / "config" / "intelligence" / "risk_rules.yaml").read_text(encoding="utf-8")
    )
    raw["lookback_days"] = 14
    path = tmp_path / "risk_rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    narrow = load_risk_rules(path)

    with demo() as session:
        result = compute_signals(session, scope, MERIDIAN, config=narrow)

    assert result.signals.tickets_in_lookback == 0
    assert result.signals.policy_escalation_state is False


# ---------------------------------------------------------------------------
# Money never moves the band or the order (plan A25 test 5)
# ---------------------------------------------------------------------------


def test_multiplying_every_deal_amount_by_a_thousand_changes_no_band_and_no_order(
    demo, scope
):
    rules = default_risk_rules().band_rules

    def ranked():
        return [
            (result.customer.source_id,
             assign_band(result.signals, rules, floor=NONE).band)
            for result in sorted(
                compute_all_signals_for(demo, scope),
                key=lambda r: ranking_key(
                    r.customer.source_id,
                    assign_band(r.signals, rules, floor=NONE), r.signals),
            )
        ]

    before = ranked()
    with demo() as session:
        session.execute(text("UPDATE deals SET amount = amount * 1000"))
        session.commit()
    after = ranked()

    assert after == before


def test_the_inflated_amount_is_still_reported_per_currency(demo, scope):
    """The invariance above must not come from the engine ignoring deals."""
    with demo() as session:
        session.execute(text("UPDATE deals SET amount = amount * 1000"))
        session.commit()
    s = signals_for(demo, scope, MERIDIAN).signals

    assert s.exposure_by_currency["USD"].amount == Decimal("5361440.00")


# ---------------------------------------------------------------------------
# Plan A23: three states, kept distinct
# ---------------------------------------------------------------------------


def test_the_demo_dataset_holds_no_missing_and_no_unresolved_relationship(demo, scope):
    """The clean baseline, so the synthetic cases below are visibly the only ones."""
    with demo() as session:
        assert data_quality_notes(session, scope) == ()


def _orphan_ticket(session: Session, source_id: str, customer_source_id: str | None) -> None:
    """A ticket E1 could not attach to a customer, written straight in."""
    session.add(SupportTicket(
        source_id=source_id,
        customer_source_id=customer_source_id,
        customer_id=None,
        priority="high",
        status="open",
        category="performance",
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
        **_provenance("support_tickets", SOURCE_SYSTEM),
    ))
    session.commit()


def test_a_null_source_key_is_reported_as_a_missing_relationship(demo, scope):
    with demo() as session:
        _orphan_ticket(session, "TKT-NULL", None)
        notes = data_quality_notes(session, scope)

    assert len(notes) == 1
    assert notes[0].state is DataQualityState.MISSING_SOURCE_KEY
    assert notes[0].customer_source_id is None
    assert notes[0].carrier_field == "support_tickets.customer_source_id"


def test_a_non_null_unresolvable_source_key_is_reported_as_an_unresolved_relationship(
    demo, scope
):
    with demo() as session:
        _orphan_ticket(session, "TKT-GHOST", "CUST-DOES-NOT-EXIST")
        notes = data_quality_notes(session, scope)

    assert len(notes) == 1
    assert notes[0].state is DataQualityState.UNRESOLVED_SOURCE_KEY
    assert notes[0].customer_source_id == "CUST-DOES-NOT-EXIST"


def test_the_two_states_are_reported_separately_and_never_collapsed(demo, scope):
    """
    Both faults at once.

    A missing key means the source named no customer; an unresolved key
    means it named one Layer 1 could not find. The remedies differ, so
    reporting them as one number would hide which applies.
    """
    with demo() as session:
        _orphan_ticket(session, "TKT-NULL", None)
        _orphan_ticket(session, "TKT-GHOST", "CUST-DOES-NOT-EXIST")
        notes = data_quality_notes(session, scope)

    assert {note.source_id: note.state for note in notes} == {
        "TKT-NULL": DataQualityState.MISSING_SOURCE_KEY,
        "TKT-GHOST": DataQualityState.UNRESOLVED_SOURCE_KEY,
    }


def test_a_key_naming_a_customer_of_another_source_system_is_unresolved_not_missing(
    demo, scope
):
    """
    E1 resolves within one source system, so a cross-source key is unresolved.

    The customer exists - just not here. Reporting it as missing would say
    the source named nobody, which is false and points at the wrong fix.
    """
    with demo() as session:
        session.add(Customer(
            source_id="CUST-OTHER", name="Elsewhere Ltd",
            **_provenance("customers", OTHER_SOURCE_SYSTEM),
        ))
        session.commit()
        _orphan_ticket(session, "TKT-CROSS", "CUST-OTHER")
        notes = data_quality_notes(session, scope)

    assert [note.state for note in notes] == [DataQualityState.UNRESOLVED_SOURCE_KEY]


def test_an_unresolved_row_reaches_no_customers_signals(demo, scope):
    """
    Plan A23: excluded from signals *and* reported, never silently dropped.

    The orphan is a high-priority open ticket breaching its target. If it
    leaked into any customer it would move a band.
    """
    before = compute_all_signals_for(demo, scope)
    with demo() as session:
        _orphan_ticket(session, "TKT-GHOST", "CUST-DOES-NOT-EXIST")
    after = compute_all_signals_for(demo, scope)

    assert [r.to_payload() for r in after] == [r.to_payload() for r in before]


def test_a_data_quality_note_is_informational_and_moves_no_band(demo, scope):
    rules = default_risk_rules().band_rules

    def bands():
        return {
            r.customer.source_id: assign_band(r.signals, rules, floor=NONE).band
            for r in compute_all_signals_for(demo, scope)
        }

    before = bands()
    with demo() as session:
        _orphan_ticket(session, "TKT-NULL", None)
        _orphan_ticket(session, "TKT-GHOST", "CUST-DOES-NOT-EXIST")

    assert bands() == before


def test_notes_are_ordered_by_entity_then_source_identity(demo, scope):
    with demo() as session:
        session.add(Deal(
            source_id="DEAL-GHOST", name="Ghost deal", customer_source_id=None,
            customer_id=None, is_active=True, stage="negotiation",
            amount=Decimal("1.00"), currency="USD", probability=Decimal("50.00"),
            **_provenance("deals", SOURCE_SYSTEM),
        ))
        session.add(Project(
            source_id="PROJ-GHOST", name="Ghost project", customer_source_id="CUST-NOPE",
            customer_id=None, is_active=True, status="in_progress",
            **_provenance("projects", SOURCE_SYSTEM),
        ))
        session.commit()
        _orphan_ticket(session, "TKT-NULL", None)
        notes = data_quality_notes(session, scope)

    assert [(n.entity_type, n.source_id) for n in notes] == [
        ("deals", "DEAL-GHOST"), ("projects", "PROJ-GHOST"), ("support_tickets", "TKT-NULL"),
    ]


def test_a_note_projects_its_state_and_its_carrier_and_no_timestamp(demo, scope):
    with demo() as session:
        _orphan_ticket(session, "TKT-GHOST", "CUST-DOES-NOT-EXIST")
        notes = data_quality_notes(session, scope)

    assert notes[0].to_payload() == {
        "entity": "support_tickets", "id": "TKT-GHOST",
        "carrier_field": "support_tickets.customer_source_id",
        "state": "UNRESOLVED_SOURCE_KEY",
        "customer_source_id": "CUST-DOES-NOT-EXIST",
    }


# ---------------------------------------------------------------------------
# Scoping
# ---------------------------------------------------------------------------


def test_another_source_systems_rows_are_neither_signals_nor_notes(demo, scope):
    """Plan A29: one source system. Cross-source aggregation is not VS-01's."""
    with demo() as session:
        session.add(SupportTicket(
            source_id="TKT-ELSEWHERE", customer_source_id=None, customer_id=None,
            priority="high", status="open", created_at=datetime(2026, 9, 1, tzinfo=UTC),
            **_provenance("support_tickets"),
        ))
        session.commit()
        notes = data_quality_notes(session, scope)
        roster = customers_in_scope(session, scope)

    assert notes == ()
    assert "CUST-OTHER" not in roster


def test_an_absent_customer_is_refused_rather_than_silently_zero(demo, scope):
    """
    M2's refusal propagates.

    A customer that is not in scope has no neighbourhood, and a signal set
    of zeros would read as a healthy account rather than as a bad question.
    """
    with demo() as session, pytest.raises(UnknownCustomerError):
        compute_signals(session, scope, "CUST-DOES-NOT-EXIST")


def test_the_roster_is_the_scopes_customers_in_source_identity_order(demo, scope):
    with demo() as session:
        roster = customers_in_scope(session, scope)

    assert len(roster) == 50
    assert list(roster) == sorted(roster)
    assert roster[0] == "CUST-001"


# ---------------------------------------------------------------------------
# Determinism (plan A24)
# ---------------------------------------------------------------------------


def test_physical_row_order_does_not_change_a_single_signal(demo, scope):
    """
    The same Layer 1 state, the same M2 state, a different physical order.

    PostgreSQL guarantees no row order without an ORDER BY, so a signal
    engine that reads unordered rows is reproducible only by luck.
    """
    before = [result.to_payload() for result in compute_all_signals_for(demo, scope)]
    with demo() as session:
        for table in REORDERABLE:
            session.execute(text(f"CREATE TEMP TABLE reorder AS SELECT * FROM {table}"))
            session.execute(text(f"DELETE FROM {table}"))
            session.execute(text(
                f"INSERT INTO {table} SELECT * FROM reorder ORDER BY source_id DESC"
            ))
            session.execute(text("DROP TABLE reorder"))
        session.commit()
    after = [result.to_payload() for result in compute_all_signals_for(demo, scope)]

    assert after == before


def test_two_runs_over_the_same_scope_are_byte_identical(demo, scope):
    from app.intelligence.contract import canonical_json

    first = canonical_json([r.to_payload() for r in compute_all_signals_for(demo, scope)])
    second = canonical_json([r.to_payload() for r in compute_all_signals_for(demo, scope)])

    assert first == second


def test_no_signal_payload_carries_a_timestamp_or_a_run_id(demo, scope):
    from app.intelligence.contract import canonical_json

    payload = canonical_json([r.to_payload() for r in compute_all_signals_for(demo, scope)])

    for forbidden in ("ingested_at", "ingestion_run_id", "source_updated_at"):
        assert forbidden not in payload


# ---------------------------------------------------------------------------
# Layer 1 and M2 are untouched
# ---------------------------------------------------------------------------


def test_the_layer_1_fingerprint_is_unchanged_after_the_signal_engine_has_run(demo, scope):
    with demo() as session:
        compute_all_signals(session, scope)
        digest, _ = layer1_fingerprint(session, SOURCE_SYSTEM)

    assert digest == PINNED


def test_the_signal_engine_writes_no_row(demo, scope):
    def counts(session):
        return {
            table: session.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in ("customers", "support_tickets", "deals", "projects", "documents")
        }

    with demo() as session:
        before = counts(session)
        compute_all_signals(session, scope)
        data_quality_notes(session, scope)

        assert counts(session) == before


def test_the_tickets_m3_measures_are_exactly_the_ones_m2_says_belong_to_the_customer(
    demo, scope
):
    """
    The one place M3 and M2 are compared directly.

    M3 does not resolve membership; it measures what M2 resolved. The
    counts are recomputed here from M2's own ticket ids, so if the two ever
    disagree about what a customer is connected to, this fails - which is
    the failure mode a second resolver inside M3 would produce.
    """
    with demo() as session:
        for customer in customers_in_scope(session, scope):
            around = neighbourhood(session, scope, customer)
            ticket_ids = [ref.source_id for ref in around.tickets]
            expected_open = _open_count(session, ticket_ids, scope.as_of)
            result = compute_signals(session, scope, customer)

            assert result.signals.open_ticket_count == expected_open, customer
            assert result.signals.active_deal_count <= len(around.deals), customer
            assert result.signals.active_project_count <= len(around.projects), customer


def _open_count(session: Session, ticket_ids: list[str], as_of: date) -> int:
    """Open at as_of, recomputed from M2's ticket ids without the signal engine."""
    if not ticket_ids:
        return 0
    rows = session.execute(
        select(SupportTicket.resolved_at)
        .where(SupportTicket.source_system == SOURCE_SYSTEM)
        .where(SupportTicket.source_entity == "support_tickets")
        .where(SupportTicket.source_id.in_(ticket_ids))
    ).all()
    return sum(
        1 for (resolved_at,) in rows
        if resolved_at is None or resolved_at.date() > as_of
    )


def test_meridians_measured_ticket_set_is_m2s_five_tickets(demo, scope):
    """Four open plus the one resolved high-priority ticket, which is plan A10's S2b."""
    with demo() as session:
        around = neighbourhood(session, scope, MERIDIAN)
        result = compute_signals(session, scope, MERIDIAN)

    assert [ref.source_id for ref in around.tickets] == [
        "TKT-073", "TKT-075", "TKT-076", "TKT-079", "TKT-080"
    ]
    assert result.signals.open_ticket_count == 4
    assert result.signals.tickets_in_lookback == len(around.tickets)


# ---------------------------------------------------------------------------
# Rows a signal cannot describe
# ---------------------------------------------------------------------------


def test_a_ticket_with_no_created_at_is_visible_at_no_evaluation_date(demo, scope):
    """It cannot be placed in any window, so it contributes to nothing."""
    with demo() as session:
        session.execute(text(
            "UPDATE support_tickets SET created_at = NULL WHERE source_id = 'TKT-075'"
        ))
        session.commit()
        result = compute_signals(session, scope, MERIDIAN)

    assert result.signals.open_ticket_count == 3
    assert result.signals.tickets_in_lookback == 4


def test_a_ticket_resolved_after_as_of_was_open_at_as_of(demo, scope):
    """
    The evaluation date decides, not the status column.

    An assessment states the position on the date it names. A ticket closed
    a week after that date was open then, and counting it as resolved would
    report a position nobody held. TKT-073 is the dataset's one resolved
    high-priority Meridian ticket, so moving its resolution past as_of
    turns it back into the fourth open high-priority breach.
    """
    with demo() as session:
        session.execute(text(
            "UPDATE support_tickets SET resolved_at = '2026-09-25T00:00:00+00' "
            "WHERE source_id = 'TKT-073'"
        ))
        session.commit()
        result = compute_signals(session, scope, MERIDIAN)

    assert result.signals.open_ticket_count == 5
    assert result.signals.open_high_priority_count == 4
    assert result.signals.open_sla_breach_high_count == 4
    assert result.signals.high_priority_total == 4


def test_a_ticket_resolved_on_as_of_itself_is_not_open(demo, scope):
    """The window is closed at as_of, so a resolution on the day counts."""
    with demo() as session:
        session.execute(text(
            "UPDATE support_tickets SET resolved_at = '2026-09-18T00:00:00+00' "
            "WHERE source_id = 'TKT-075'"
        ))
        session.commit()
        result = compute_signals(session, scope, MERIDIAN)

    assert result.signals.open_ticket_count == 3
    assert result.signals.open_high_priority_count == 2


def test_an_open_ticket_is_measured_to_as_of_and_not_to_its_later_resolution(demo, scope):
    """
    The clock stops at as_of for a ticket still open then.

    TKT-080 moved to the evaluation date itself and resolved twelve days
    later: nothing has elapsed at as_of, so it has not breached. Measuring
    it to its eventual resolution would report a breach that had not
    happened on the date the assessment names.
    """
    with demo() as session:
        session.execute(text(
            "UPDATE support_tickets SET created_at = '2026-09-18T00:00:00+00', "
            "resolved_at = '2026-09-30T00:00:00+00' WHERE source_id = 'TKT-080'"
        ))
        session.commit()
        result = compute_signals(session, scope, MERIDIAN)

    assert result.signals.open_high_priority_count == 3
    assert result.signals.open_sla_breach_high_count == 2


def test_a_ticket_that_exactly_meets_its_target_has_not_breached_it(demo, scope):
    """
    DOC-003 says the target is one business day, and one is not more than one.

    TKT-073 created on a Monday and resolved on the Tuesday elapses exactly
    one business day. A breach is *exceeding* the target, so an
    off-by-one here would manufacture a breach out of a ticket that met it.
    """
    with demo() as session:
        session.execute(text(
            "UPDATE support_tickets SET created_at = '2026-09-14T00:00:00+00', "
            "resolved_at = '2026-09-15T00:00:00+00' WHERE source_id = 'TKT-073'"
        ))
        session.commit()
        result = compute_signals(session, scope, MERIDIAN)

    assert result.signals.sla_breach_count == 4


def test_the_escalation_threshold_is_inclusive_at_its_boundary(demo, scope, tmp_path):
    """
    DOC-003: "three or more tickets within 14 days".

    Set the threshold to exactly the five CUST-007 raised. Five or more
    still escalates; a strict comparison here would silently need six.
    """
    import yaml

    raw = yaml.safe_load(
        (REPO / "config" / "intelligence" / "risk_rules.yaml").read_text(encoding="utf-8")
    )
    raw["escalation"]["ticket_threshold"] = 5
    path = tmp_path / "risk_rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    exactly_five = load_risk_rules(path)

    with demo() as session:
        result = compute_signals(session, scope, MERIDIAN, config=exactly_five)

    assert result.signals.max_tickets_in_14d_window == 5
    assert result.signals.policy_escalation_state is True


def test_an_inactive_project_is_not_an_active_project(demo, scope):
    """Every project in the demo dataset is active, so the exclusion needs showing."""
    with demo() as session:
        before = compute_signals(session, scope, "CUST-021").signals.active_project_count
        session.execute(text(
            "UPDATE projects SET is_active = false WHERE source_id = 'PROJ-001'"
        ))
        session.commit()
        after = compute_signals(session, scope, "CUST-021").signals.active_project_count

    assert before == 1
    assert after == 0


def test_a_colliding_source_id_in_another_source_system_is_not_measured(demo, scope):
    """
    The same ticket id in two source systems must not be counted twice.

    M2 hands over source ids, which are unique only within a source system.
    Reading their attributes without re-applying the scope would let another
    connector's TKT-075 inflate this customer's counts.
    """
    before = signals_for(demo, scope, MERIDIAN).signals.to_payload()
    with demo() as session:
        session.add(SupportTicket(
            source_id="TKT-075", customer_source_id="CUST-007", customer_id=None,
            priority="high", status="open", category="performance",
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
            **_provenance("support_tickets"),
        ))
        session.commit()
    after = signals_for(demo, scope, MERIDIAN).signals.to_payload()

    assert after == before


def test_a_deal_that_cannot_state_its_amount_is_not_a_commercial_signal(demo, scope):
    """
    M1's DealSignal requires stage, amount, currency and probability.

    A deal missing one cannot be described, so it is not reported as
    exposure. That is M1's frozen contract deciding, not the signal engine.
    """
    with demo() as session:
        session.execute(text("UPDATE deals SET amount = NULL WHERE source_id = 'DEAL-001'"))
        session.commit()
        result = compute_signals(session, scope, MERIDIAN)

    assert result.signals.active_deal_count == 0
    assert result.signals.exposure_by_currency == {}
    assert result.signals.deal_under_pressure is False


def test_an_inactive_deal_is_not_counted(demo, scope):
    with demo() as session:
        session.execute(text("UPDATE deals SET is_active = false WHERE source_id = 'DEAL-001'"))
        session.commit()
        result = compute_signals(session, scope, MERIDIAN)

    assert result.signals.active_deal_count == 0


def test_a_ticket_of_an_unmapped_priority_never_breaches(demo, scope):
    """DOC-003 names high and medium. A priority it does not name has no target."""
    with demo() as session:
        session.execute(text(
            "UPDATE support_tickets SET priority = NULL WHERE source_id = 'TKT-079'"
        ))
        session.commit()
        result = compute_signals(session, scope, MERIDIAN)

    assert result.signals.sla_breach_count == 4
    assert result.signals.open_ticket_count == 4


def test_an_uncategorised_ticket_is_not_a_dominant_category(demo, scope):
    with demo() as session:
        session.execute(text(
            "UPDATE support_tickets SET category = NULL WHERE customer_source_id = 'CUST-007'"
        ))
        session.commit()
        result = compute_signals(session, scope, MERIDIAN)

    assert result.signals.dominant_ticket_category is None


def test_a_category_tie_breaks_on_the_lexicographically_smallest_name(demo, scope):
    """Otherwise the answer would depend on the order the rows arrived in."""
    with demo() as session:
        session.execute(text(
            "UPDATE support_tickets SET category = 'zeta' "
            "WHERE source_id IN ('TKT-075', 'TKT-076')"
        ))
        session.execute(text(
            "UPDATE support_tickets SET category = 'alpha' "
            "WHERE source_id IN ('TKT-073', 'TKT-079')"
        ))
        session.commit()
        result = compute_signals(session, scope, MERIDIAN)

    assert result.signals.dominant_ticket_category == "alpha"
