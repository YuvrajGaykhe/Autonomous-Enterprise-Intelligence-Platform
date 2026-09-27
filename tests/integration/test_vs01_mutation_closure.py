"""
The tests M9's mutation audit found missing (plan §0.8.12, §0.8.10, M9 Phase 6).

The audit applied 274 mutants to its four targets: the signal engine, the
risk-band table, the conflict policy and the linker. Every one it did not kill
with the targets' own unit and integration files plus the §A25 corpus was
either proved equivalent, with written evidence recorded at closure, or is
killed here. Each test is named for the mutant or mutants it kills.

None of these mutants exposed a production defect. Each changes behaviour that
the committed contract specifies but that the committed demo data never
exercises: a closed-window boundary, a documented order, a configuration value
the data never sits next to, or a public function called with an argument no
production caller passes. The rows a test needs are made from the demo data
with one UPDATE, as tests/integration/test_m3_signals.py does, or are built
directly from the frozen contract types.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.analysts.base import canonical_fact
from app.connectors.registry import build_connector
from app.decisions.conflicts import detect_conflicts
from app.decisions.policy import default_conflict_policy
from app.evidence.linker import derive_and_persist, derive_links, find_exact_name, find_id_token
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence import Scope, resolve_scope
from app.intelligence.bands import assign_band, parse_band_rules
from app.intelligence.config import RiskRulesConfig, default_risk_rules, load_risk_rules
from app.intelligence.contract import ActionId, Function, Position, SignalSet, Stance
from app.intelligence.signals import (
    DataQualityNote,
    DataQualityState,
    compute_all_signals,
    compute_signals,
)
from app.intelligence.windows import max_window, sliding_windows
from app.persistence.models import DocumentCustomerLink
from tests.unit.m6_support import load_policy, policy_data

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
RISK_RULES = REPO / "config" / "intelligence" / "risk_rules.yaml"
SOURCE_SYSTEM = "csv_demo"
ACCEPTANCE_AS_OF = date(2026, 9, 18)
#: closed_window(2026-09-18, 90): the lookback's first date.
LOOKBACK_START = date(2026, 6, 21)
MERIDIAN = "CUST-007"
#: A backlog account: its one open medium ticket, TKT-005, dates from January.
BACKLOG = "CUST-048"
NONE = "NONE"


@pytest.fixture
def demo(e1_sessions: sessionmaker[Session]) -> sessionmaker[Session]:
    """The clean full-dataset path: 233 rows, 0 rejected."""
    summary = run_ingestion(build_connector(SOURCE_SYSTEM, data_directory=DEMO_DIR), e1_sessions,
                            IngestionRequest())
    assert summary.counts.rejected == 0
    return e1_sessions


@pytest.fixture
def scope(demo: sessionmaker[Session]) -> Scope:
    with demo() as session:
        return resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=ACCEPTANCE_AS_OF)


def signals_after(sessions: sessionmaker[Session], scope: Scope, customer: str,
                  *statements: str):
    """One customer's signals after the given UPDATEs, at the same scope."""
    with sessions() as session:
        for statement in statements:
            session.execute(text(statement))
        session.commit()
        return compute_signals(session, scope, customer)


def rules_with(tmp_path: Path, change) -> RiskRulesConfig:
    """The committed risk rules with one change applied, loaded through M1's validator."""
    raw = yaml.safe_load(RISK_RULES.read_text(encoding="utf-8"))
    change(raw)
    path = tmp_path / "risk_rules.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return load_risk_rules(path)


def signal_set(**overrides: object) -> SignalSet:
    """A signal set that satisfies no band rule, with named fields overridden."""
    defaults: dict[str, object] = {
        "open_ticket_count": 0, "open_high_priority_count": 0, "high_priority_total": 0,
        "tickets_in_lookback": 0, "max_tickets_in_14d_window": 0,
        "policy_escalation_state": False, "days_since_last_ticket": None,
        "sla_breach_count": 0, "open_sla_breach_high_count": 0,
        "stale_open_ticket_count": 0, "dominant_ticket_category": None,
        "active_deals": (), "exposure_by_currency": {}, "active_project_count": 0,
        "contract_document_ids": (), "deal_under_pressure": False,
    }
    return SignalSet(**{**defaults, **overrides})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The signal engine: app/intelligence/signals.py, windows.py, the signal inputs
# ---------------------------------------------------------------------------


def test_sig_10_data_quality_notes_order_by_entity_type_then_source_id():
    """DataQualityNote.sort_key: "Total order: entity type, then source identity"."""
    ticket = DataQualityNote(entity_type="support_tickets", source_id="A-950",
                             carrier_field="support_tickets.customer_source_id",
                             state=DataQualityState.UNRESOLVED_SOURCE_KEY,
                             customer_source_id="CUST-950")
    deal = DataQualityNote(entity_type="deals", source_id="Z-951",
                           carrier_field="deals.customer_source_id",
                           state=DataQualityState.MISSING_SOURCE_KEY, customer_source_id=None)

    assert sorted([ticket, deal], key=lambda note: note.sort_key) == [deal, ticket]
    assert deal.sort_key == ("deals", "Z-951")


def test_sig_12_the_signal_projection_carries_the_backlog_tickets(demo, scope):
    with demo() as session:
        result = compute_signals(session, scope, BACKLOG)

    assert result.backlog_ticket_ids == ("TKT-005",)
    assert result.to_payload()["backlog_ticket_ids"] == ["TKT-005"]


def test_sig_20_compute_all_signals_applies_the_rules_it_is_given(demo, scope, tmp_path):
    """§A25 test 11's lever through the whole-scope entry point, not only the per-customer one."""
    stricter = rules_with(tmp_path, lambda raw: raw["escalation"].update(ticket_threshold=6))

    with demo() as session:
        results = {one.customer.source_id: one for one in
                   compute_all_signals(session, scope, config=stricter)}

    assert results[MERIDIAN].signals.policy_escalation_state is False
    assert [customer for customer, one in results.items()
            if one.signals.policy_escalation_state] == []


@pytest.mark.parametrize("created, backlog", [
    ("2026-06-20", ("TKT-005",)),
    ("2026-06-21", ()),
])
def test_sig_26_a_breaching_ticket_opened_on_the_lookback_start_is_not_backlog(
        demo, scope, created, backlog):
    """Backlog is an open, breaching ticket created *before* the closed lookback window."""
    result = signals_after(demo, scope, BACKLOG, f"UPDATE support_tickets SET created_at = "
                           f"'{created}T09:00:00+00' WHERE source_id = 'TKT-005'")

    assert result.backlog_ticket_ids == backlog
    assert result.signals.stale_open_ticket_count == len(backlog)


def test_sig_27_an_old_open_ticket_that_never_breaches_is_not_backlog(demo, scope):
    """A priority with no DOC-003 target never breaches, so it is never chronic backlog."""
    result = signals_after(demo, scope, BACKLOG,
                           "UPDATE support_tickets SET priority = 'low' WHERE source_id = 'TKT-005'")

    assert result.signals.open_ticket_count == 1
    assert result.backlog_ticket_ids == ()
    assert result.signals.stale_open_ticket_count == 0


def test_sig_35_and_sig_49_backlog_tickets_are_listed_in_ascending_id_order(demo, scope):
    """§0.6.13.1: backlog_ticket_ids in M3's order, which is ascending by ticket id."""
    result = signals_after(demo, scope, BACKLOG,
                           "UPDATE support_tickets SET resolved_at = NULL WHERE source_id = 'TKT-042'")

    assert result.backlog_ticket_ids == ("TKT-005", "TKT-042")
    assert result.signals.stale_open_ticket_count == 2


def test_sig_39_a_ticket_opened_on_the_lookback_start_counts_for_the_dominant_category(
        demo, scope):
    """CUST-033's TKT-058 was created on 2026-06-21, the lookback's first date: it is inside."""
    with demo() as session:
        result = compute_signals(session, scope, "CUST-033")

    assert result.signals.tickets_in_lookback == 1
    assert result.signals.dominant_ticket_category == "auth"


def test_sig_40_a_ticket_opened_on_as_of_counts_for_the_dominant_category(demo, scope):
    """The lookback is closed at as_of: CUST-012's only ticket, moved to as_of, still counts."""
    result = signals_after(demo, scope, "CUST-012", "UPDATE support_tickets SET created_at = "
                           "'2026-09-18T09:00:00+00' WHERE source_id = 'TKT-077'")

    assert result.signals.tickets_in_lookback == 1
    assert result.signals.dominant_ticket_category == "onboarding"


def test_sig_41_an_uncategorised_ticket_is_never_the_dominant_category(demo, scope):
    """Three uncategorised performance tickets leave billing and integration tied at one."""
    result = signals_after(demo, scope, MERIDIAN,
                           "UPDATE support_tickets SET category = NULL "
                           "WHERE source_id IN ('TKT-073', 'TKT-075', 'TKT-080')")

    assert result.signals.dominant_ticket_category == "billing"


def test_win_10_a_one_day_window_is_a_valid_window():
    """A window must span at least one day, so a one-day window is legal."""
    days = [date(2026, 9, 1), date(2026, 9, 1), date(2026, 9, 2)]

    windows = sliding_windows(days, ACCEPTANCE_AS_OF, window_days=1, lookback_days=90)

    assert [(one.start, one.end, one.count) for one in windows] == [
        (date(2026, 9, 1), date(2026, 9, 1), 2), (date(2026, 9, 2), date(2026, 9, 2), 1)]
    fullest = max_window(days, ACCEPTANCE_AS_OF, window_days=1, lookback_days=90)
    assert fullest is not None and (fullest.start, fullest.count) == (date(2026, 9, 1), 2)


@pytest.mark.parametrize("created, elapsed, breaches", [
    ("2026-09-11", 5, 0),
    ("2026-09-10", 6, 1),
])
def test_cfg_05_and_cfg_06_a_medium_ticket_breaches_after_five_business_days(
        demo, scope, created, elapsed, breaches):
    """DOC-003's medium target is 5 business days: 5 elapsed is on target, 6 is a breach."""
    from app.intelligence.timeutil import business_days_between

    assert business_days_between(date.fromisoformat(created), ACCEPTANCE_AS_OF) == elapsed
    result = signals_after(demo, scope, "CUST-012", f"UPDATE support_tickets SET created_at = "
                           f"'{created}T09:00:00+00' WHERE source_id = 'TKT-077'")

    assert result.signals.sla_breach_count == breaches


def test_cfg_10_three_tickets_within_fourteen_days_escalate(demo, scope):
    """DOC-003: three or more tickets within 14 days escalate. Exactly three is enough."""
    result = signals_after(
        demo, scope, MERIDIAN,
        "UPDATE support_tickets SET created_at = '2026-07-01T09:00:00+00' "
        "WHERE source_id = 'TKT-079'",
        "UPDATE support_tickets SET created_at = '2026-07-20T09:00:00+00' "
        "WHERE source_id = 'TKT-080'")

    assert result.signals.max_tickets_in_14d_window == 3
    assert result.signals.policy_escalation_state is True


# ---------------------------------------------------------------------------
# The risk-band table: config/intelligence/risk_rules.yaml's bands, bands.py
# ---------------------------------------------------------------------------


def _band(signals: SignalSet):
    return assign_band(signals, default_risk_rules().band_rules, floor=NONE)


def _escalated_with_one_high_breach() -> SignalSet:
    """Escalated, one open high-priority ticket, and it is past its target."""
    return signal_set(policy_escalation_state=True, open_ticket_count=1,
                      open_high_priority_count=1, high_priority_total=1, sla_breach_count=1,
                      open_sla_breach_high_count=1)


def test_bt_02_an_escalated_account_with_one_high_breach_is_elevated_not_critical():
    """R-CRIT-001 needs *more than one* open high-priority breach (at least 2)."""
    assignment = _band(_escalated_with_one_high_breach())

    assert assignment.band == "ELEVATED"
    assert assignment.satisfied_rules == ("R-ELEV-001", "R-WATCH-001")


def test_bt_19_recent_ticket_velocity_alone_is_watch():
    """R-WATCH-002: two tickets in one 14-day window, the last within 30 days."""
    assignment = _band(signal_set(max_tickets_in_14d_window=2, days_since_last_ticket=10))

    assert (assignment.band, assignment.satisfied_rules) == ("WATCH", ("R-WATCH-002",))


def test_bd_23_a_zero_threshold_is_a_valid_band_condition():
    """_condition refuses a threshold below 0, not 0 itself."""
    (rule,) = parse_band_rules(
        [{"id": "R-ZERO", "band": "WATCH", "when": {"open_ticket_count_at_least": 0}}], "rules")

    assert rule.conditions[0].threshold == 0
    assert rule.holds_for(signal_set())


def test_bd_31_a_band_assignment_projects_its_satisfied_rules():
    assignment = _band(_escalated_with_one_high_breach())

    assert assignment.to_payload() == {"band": "ELEVATED",
                                       "satisfied_rules": ["R-ELEV-001", "R-WATCH-001"]}


# ---------------------------------------------------------------------------
# The conflict policy: conflict_policy.yaml, policy.py, conflicts.py, reconciler.py
# ---------------------------------------------------------------------------


def test_pl_24_a_zero_breach_threshold_is_a_valid_resolution_condition(tmp_path):
    """_count refuses a count below 0, not 0 itself."""
    data = policy_data()
    data["conflicts"][0]["when"]["open_sla_breach_high_count_at_least"] = 0

    (rule,) = load_policy(tmp_path, data).rules

    assert rule.when.open_sla_breach_high_count_at_least == 0
    assert rule.when.to_payload()["open_sla_breach_high_count_at_least"] == 0


def _position(function: Function, action: ActionId, deal: str, stance: Stance) -> Position:
    return Position(function=function, stance=stance, proposed_action=action, object_ref=deal,
                    rationale="stated for the test",
                    evidence=(canonical_fact("deals", deal, "stage"),))


def test_cf_06_conflicts_over_two_objects_are_ascending_by_object():
    """detect_conflicts: "Every conflict among one customer's positions, ascending by object"."""
    accelerate, pause = ActionId.ACCELERATE_DEAL_CLOSE, ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED
    positions = [
        _position(Function.SALES, accelerate, "DEAL-902", Stance.ADVANCE),
        _position(Function.SUPPORT, pause, "DEAL-902", Stance.RESTRAIN),
        _position(Function.SALES, accelerate, "DEAL-901", Stance.ADVANCE),
        _position(Function.SUPPORT, pause, "DEAL-901", Stance.RESTRAIN),
    ]

    conflicts = detect_conflicts(positions, default_conflict_policy())

    assert [conflict.object_ref for conflict in conflicts] == ["DEAL-901", "DEAL-902"]


# ---------------------------------------------------------------------------
# The linker: app/evidence/linker.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("find", [find_id_token, find_exact_name])
def test_lk_08_an_empty_needle_matches_nowhere(find):
    """An empty id or name has no occurrence, even where an empty span would be bounded."""
    assert find("Quarterly review.", "") is None


def test_lk_27_and_lk_30_links_carry_the_given_configurations_linker_version(
        demo, scope, tmp_path):
    """derive_links and derive_and_persist stamp the linker version of the config they are given."""
    second = rules_with(tmp_path, lambda raw: raw.update(linker_version="2"))

    with demo() as session:
        derived = derive_links(session, scope, config=second)
    with demo.begin() as session:
        inserted = derive_and_persist(session, scope, config=second)
    with demo() as session:
        persisted = set(session.scalars(select(DocumentCustomerLink.linker_version)).all())

    assert derived and {link.linker_version for link in derived} == {"2"}
    assert inserted == len(derived)
    assert persisted == {"2"}
