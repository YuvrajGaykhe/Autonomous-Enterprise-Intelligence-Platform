"""
The M5 context factory against a real database, and the six positions.

The demo dataset is ingested by the clean full-dataset path, so every number
asserted here is measured rather than remembered. Five kinds of test:

Acceptance: CUST-007's **six** positions, matching §0.4.1's table row for row
-- function, action, object_ref and stance -- and the corpus-wide expectation
of §0.4.8, so a position the analysts invent for any of the other 47 customers
fails the build.

The equivalence table of §0.4.2: M5's TicketFact derivation against M3's S1,
S2, S2b, S7 and S8 for **every** customer at **both** the acceptance date and
the 2026-08-27 fallback. Two implementations of one stated rule now exist, and
this is what makes their divergence a build failure rather than a latent
defect. It is the technique §A25 test 13b already uses: write the would-be-
wrong computation out and assert against it.

S14: the populated value reaches CommercialContext through documents_for() and
with_contract_documents() and by no other route, both DOC-006 evidence links
are still returned, a customer with links but no contract gets `()` without an
error, and -- the §0.4.3 hazard -- so does a run where nothing was derived at
all, which is why criterion 5 rather than a mock is what detects a broken
ordering.

Read-only: the whole table inventory is counted before and after, so a write
anywhere in the factory fails here and not in review.

Determinism: two builds in one session, and one more after the links are
reinserted in a different physical order, give equal contexts and equal
positions.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.analysts import (
    CommercialAnalyst,
    SupportRiskAnalyst,
    build_contexts,
    ticket_facts,
)
from app.connectors import CsvConnector, CsvConnectorConfig, SourceConnector
from app.core.database import Base
from app.evidence import documents_for
from app.evidence.linker import derive_and_persist
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence import Scope, resolve_scope
from app.intelligence.config import default_risk_rules
from app.intelligence.contract import ActionId, EntityRef, Function, Stance
from app.intelligence.signals import compute_signals, customers_in_scope
from app.persistence.models import SupportTicket
from app.persistence.models.document_customer_link import DocumentCustomerLink

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
SOURCE_SYSTEM = "csv_demo"

#: §A27. The max(created_at) fallback is 2026-08-27, and §0.4.2 requires the
#: equivalence table to hold at both.
ACCEPTANCE_AS_OF = date(2026, 9, 18)
FALLBACK_AS_OF = date(2026, 8, 27)

MERIDIAN = "CUST-007"
UNITY = "CUST-015"

#: §0.4.1's measured consequence: exactly six positions for CUST-007, as
#: (function, action, object_ref, stance). The table is the acceptance
#: criterion, so an implementer who measures a different set reports it
#: rather than adjusting this tuple (§0.3.8, §0.4.8).
CUST_007_POSITIONS = (
    ("SUPPORT", "ASSIGN_DEDICATED_SUPPORT_OWNER", "CUST-007", "NEUTRAL"),
    ("SUPPORT", "ESCALATE_TO_ACCOUNT_OWNER_PER_SLA", "CUST-007", "NEUTRAL"),
    ("SUPPORT", "SCHEDULE_EXECUTIVE_SPONSOR_CALL", "CUST-007", "NEUTRAL"),
    ("SUPPORT", "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED", "DEAL-001", "RESTRAIN"),
    ("SUPPORT", "REVIEW_INVOICE_DISPUTE", "TKT-079", "NEUTRAL"),
    ("SALES", "ACCELERATE_DEAL_CLOSE", "DEAL-001", "ADVANCE"),
)

#: §0.4.8's measured corpus expectation: the eight customers holding an active
#: negotiation deal at probability >= 80, counted from data/demo/ on
#: 2026-09-22. OBSERVED, not architecture -- a different measurement is
#: reported, not accommodated.
ACCELERATING_CUSTOMERS = {
    "CUST-003", "CUST-007", "CUST-019", "CUST-031",
    "CUST-042", "CUST-043", "CUST-046", "CUST-050",
}

#: §0.4.8 criterion 8: of the ticketless customers, the three with a
#: qualifying deal.
TICKETLESS_WITH_A_DEAL = {"CUST-019": "DEAL-011", "CUST-042": "DEAL-005", "CUST-043": "DEAL-029"}


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


@pytest.fixture
def fallback_scope(demo: sessionmaker[Session]) -> Scope:
    with demo() as session:
        return resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=FALLBACK_AS_OF)


@pytest.fixture
def linked(demo: sessionmaker[Session], scope: Scope) -> sessionmaker[Session]:
    """
    The demo dataset with every derived link persisted.

    The derivation is an explicit arrange step, exactly as §0.4.3 says M5's
    tests must do it: the production call belongs to the assessment run, which
    is M7's, and M5 is not independently runnable until it exists.
    """
    with demo.begin() as session:
        derive_and_persist(session, scope)
    return demo


def contexts_for(sessions, scope: Scope, customer: str):
    with sessions() as session:
        return build_contexts(session, scope, customer)


def positions_for(sessions, scope: Scope, customer: str):
    """Support's positions then Sales's, which is §0.4.1's table order."""
    contexts = contexts_for(sessions, scope, customer)
    return (
        SupportRiskAnalyst(context=contexts.support).positions()
        + CommercialAnalyst(context=contexts.commercial).positions()
    )


def as_rows(positions) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        (
            str(position.function),
            str(position.proposed_action),
            position.object_ref,
            str(position.stance),
        )
        for position in positions
    )


def _table_counts(sessions) -> dict[str, int]:
    """Every row of every table, so no write anywhere goes unnoticed."""
    with sessions() as session:
        return {
            table.name: session.scalar(select(func.count()).select_from(table)) or 0
            for table in Base.metadata.sorted_tables
        }


# ---------------------------------------------------------------------------
# Criterion 1 and 2: action resolution, and nothing dropped
# ---------------------------------------------------------------------------


def test_cust_007_yields_exactly_the_six_measured_positions(linked, scope):
    """
    §0.4.8 criterion 1. Asserted as the whole ordered tuple rather than as a
    count and three spot checks, so a seventh position, a wrong object or a
    wrong stance all fail here.
    """
    assert as_rows(positions_for(linked, scope, MERIDIAN)) == CUST_007_POSITIONS


def test_all_five_support_entries_are_emitted_and_none_is_merged(linked, scope):
    """
    §0.4.8 criterion 2: five Support positions, nothing dropped, ranked or
    merged onto one proposed_action.
    """
    support = SupportRiskAnalyst(
        context=contexts_for(linked, scope, MERIDIAN).support
    ).positions()

    assert len(support) == 5
    assert len({position.proposed_action for position in support}) == 5


def test_exactly_one_support_and_one_sales_position_contest_deal_001(linked, scope):
    """
    §0.4.8 criterion 2's second half, and the property M6 depends on:
    Conflict's "at most one position per function" holds without M5 doing
    anything to make it hold.
    """
    contesting = [
        position for position in positions_for(linked, scope, MERIDIAN)
        if position.object_ref == "DEAL-001"
    ]

    assert [position.function for position in contesting] == [Function.SUPPORT, Function.SALES]
    assert [position.stance for position in contesting] == [Stance.RESTRAIN, Stance.ADVANCE]


def test_the_demo_dataset_contains_exactly_one_contested_object(linked, scope):
    """
    §A15's claim, asserted as a measured property of the data across all 50
    customers rather than for CUST-007 alone.
    """
    contested = {}
    with linked() as session:
        for customer in customers_in_scope(session, scope):
            contexts = build_contexts(session, scope, customer)
            support = SupportRiskAnalyst(context=contexts.support).positions()
            sales = CommercialAnalyst(context=contexts.commercial).positions()
            shared = {position.object_ref for position in support} & {
                position.object_ref for position in sales
            }
            if shared:
                contested[customer] = shared

    assert contested == {MERIDIAN: {"DEAL-001"}}


def test_exactly_the_eight_measured_customers_accelerate_a_deal(linked, scope):
    """
    §0.4.8's measured corpus-wide expectation. OBSERVED, not architecture: a
    different set is reported rather than pasted over this one.
    """
    accelerating = set()
    with linked() as session:
        for customer in customers_in_scope(session, scope):
            contexts = build_contexts(session, scope, customer)
            if CommercialAnalyst(context=contexts.commercial).positions():
                accelerating.add(customer)

    assert accelerating == ACCELERATING_CUSTOMERS


# ---------------------------------------------------------------------------
# Criterion 3 and 4: the ticket-level entry, and breach reporting
# ---------------------------------------------------------------------------


def test_the_invoice_dispute_names_the_one_open_billing_ticket(linked, scope):
    """§0.4.8 criterion 3: TKT-079, reached from the context's ticket rows."""
    support = contexts_for(linked, scope, MERIDIAN).support
    billing = [fact for fact in support.tickets if fact.is_billing and fact.is_open]

    assert [fact.source_id for fact in billing] == ["TKT-079"]
    assert ("SUPPORT", "REVIEW_INVOICE_DISPUTE", "TKT-079", "NEUTRAL") in as_rows(
        SupportRiskAnalyst(context=support).positions()
    )


def test_tkt_079_breaches_its_sla_yet_is_absent_from_s8(linked, scope):
    """
    §0.4.8 criterion 4's second half: S8 counts open **high**-priority
    breaches, and TKT-079 is medium. A derivation that conflated the two would
    pass the counts and fail here.
    """
    support = contexts_for(linked, scope, MERIDIAN).support
    tkt_079 = next(fact for fact in support.tickets if fact.source_id == "TKT-079")

    assert tkt_079.breaches_sla is True
    assert tkt_079.priority == "medium"
    assert support.signals.open_sla_breach_high_count == 3


def test_a_priority_the_policy_does_not_name_cannot_breach(demo, scope):
    """
    §0.4.2: a NULL priority and an unnamed priority have no target, so
    inventing one would manufacture breaches DOC-003 never states. Written as
    a fixture because the demo dataset's priorities are all named.
    """
    with demo.begin() as session:
        session.execute(
            SupportTicket.__table__.update()
            .where(SupportTicket.source_id == "TKT-075")
            .values(priority=None)
        )
    with demo() as session:
        facts = ticket_facts(session, scope, MERIDIAN, config=default_risk_rules())
    altered = next(fact for fact in facts if fact.source_id == "TKT-075")

    assert altered.priority is None
    assert altered.breaches_sla is False


def test_a_ticket_with_no_created_at_is_excluded_entirely(demo, scope):
    """
    §0.4.2 and §0.2.2: it cannot be placed in any window, so it is visible at
    no evaluation date -- and it produces no note, matching M3 exactly.
    """
    with demo.begin() as session:
        session.execute(
            SupportTicket.__table__.update()
            .where(SupportTicket.source_id == "TKT-075")
            .values(created_at=None)
        )
    with demo() as session:
        facts = ticket_facts(session, scope, MERIDIAN, config=default_risk_rules())

    assert "TKT-075" not in {fact.source_id for fact in facts}


def test_a_ticket_created_after_as_of_is_not_yet_visible(demo, scope):
    """
    §0.4.2: a ticket whose created_at date is after as_of is excluded, so an
    assessment names only what had happened by the date it names. The row
    stays in Layer 1 and simply does not reach this evaluation date.
    """
    with demo.begin() as session:
        session.execute(
            SupportTicket.__table__.update()
            .where(SupportTicket.source_id == "TKT-075")
            .values(created_at=datetime(2026, 9, 19, 12, 0, tzinfo=UTC))
        )
    with demo() as session:
        facts = ticket_facts(session, scope, MERIDIAN, config=default_risk_rules())
        later = resolve_scope(
            session, source_system=SOURCE_SYSTEM, as_of=date(2026, 9, 20)
        )
        visible_later = ticket_facts(session, later, MERIDIAN, config=default_risk_rules())

    assert "TKT-075" not in {fact.source_id for fact in facts}
    assert "TKT-075" in {fact.source_id for fact in visible_later}


def test_the_derivation_reads_the_resolution_date_and_never_the_status(demo, scope):
    """
    §0.4.2: M3's rule, not M2's. `status` is flipped to 'resolved' while
    `resolved_at` stays NULL; M3's rule still calls the ticket open, and a
    derivation that consulted status as a fallback would disagree.
    """
    with demo.begin() as session:
        session.execute(
            SupportTicket.__table__.update()
            .where(SupportTicket.source_id == "TKT-075")
            .values(status="resolved", resolved_at=None)
        )
    with demo() as session:
        facts = ticket_facts(session, scope, MERIDIAN, config=default_risk_rules())
    altered = next(fact for fact in facts if fact.source_id == "TKT-075")

    assert altered.is_open is True


def test_the_facts_come_back_ascending_by_source_id(linked, scope):
    """§0.4.2's stated ordering, so two runs cannot disagree."""
    facts = contexts_for(linked, scope, MERIDIAN).support.tickets
    ids = [fact.source_id for fact in facts]

    assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# Criterion 4: the §0.4.2 equivalence table, every customer, both dates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("as_of", [ACCEPTANCE_AS_OF, FALLBACK_AS_OF])
def test_the_ticket_derivation_equals_m3s_signals_for_every_customer(demo, as_of):
    """
    §0.4.2's table, in full. Because two implementations of one stated rule
    exist, drift is made a build failure here rather than left as a latent
    defect. The comparison is per customer, so a compensating error in one
    direction for one customer cannot cancel another's.
    """
    rules = default_risk_rules()
    with demo() as session:
        run_scope = resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=as_of)
        customers = customers_in_scope(session, run_scope)
        assert len(customers) == 50, "the scan would be vacuous without the full roster"
        for customer in customers:
            facts = ticket_facts(session, run_scope, customer, config=rules)
            signals = compute_signals(session, run_scope, customer, config=rules).signals
            high = [fact for fact in facts if fact.priority == "high"]
            openz = [fact for fact in facts if fact.is_open]
            where = f"{customer} at {as_of}"

            assert sum(1 for f in openz) == signals.open_ticket_count, where
            assert sum(
                1 for f in openz if f.priority == "high"
            ) == signals.open_high_priority_count, where
            assert len(high) == signals.high_priority_total, where
            assert sum(
                1 for f in facts if f.breaches_sla
            ) == signals.sla_breach_count, where
            assert sum(
                1 for f in openz if f.priority == "high" and f.breaches_sla
            ) == signals.open_sla_breach_high_count, where


@pytest.mark.parametrize("as_of", [ACCEPTANCE_AS_OF, FALLBACK_AS_OF])
def test_the_derived_ids_are_the_neighbourhoods_minus_the_excluded(demo, as_of):
    """
    The table's last row. Membership is M2's; the only ids missing are the
    ones §0.4.2 excludes, so the derivation adds nothing and loses nothing
    else.
    """
    from app.relationships import neighbourhood

    rules = default_risk_rules()
    with demo() as session:
        run_scope = resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=as_of)
        for customer in customers_in_scope(session, run_scope):
            member_ids = {
                ref.source_id
                for ref in neighbourhood(session, run_scope, customer).tickets
            }
            derived = {
                fact.source_id
                for fact in ticket_facts(session, run_scope, customer, config=rules)
            }
            excluded = _excluded_ticket_ids(session, member_ids, run_scope.as_of)

            assert derived == member_ids - excluded, f"{customer} at {as_of}"


def _excluded_ticket_ids(session: Session, ids: set[str], as_of: date) -> set[str]:
    """
    The would-be-wrong computation, written out: which ids §0.4.2 drops.

    Recomputed from Layer 1 without the derivation under test, so the two
    cannot agree by sharing a bug.
    """
    if not ids:
        return set()
    rows = session.execute(
        select(SupportTicket.source_id, SupportTicket.created_at).where(
            SupportTicket.source_system == SOURCE_SYSTEM,
            SupportTicket.source_entity == "support_tickets",
            SupportTicket.source_id.in_(sorted(ids)),
        )
    ).all()
    return {
        source_id
        for source_id, created_at in rows
        if created_at is None or created_at.date() > as_of
    }


# ---------------------------------------------------------------------------
# Criteria 5, 6 and 7: S14 through M4, and the silent-empty hazard
# ---------------------------------------------------------------------------


def test_s14_reaches_the_commercial_context_as_the_one_contract_document(linked, scope):
    """
    §0.4.8 criterion 5, the production invocation of §0.3.6 B. This is also
    what detects criterion 7's hazard: if the run's ordering were wrong, S14
    would be () here and this assertion is what says so.
    """
    commercial = contexts_for(linked, scope, MERIDIAN).commercial

    assert commercial.signals.contract_document_ids == ("DOC-006",)


def test_both_doc_006_evidence_links_are_still_returned(linked, scope):
    """
    §0.4.8 criterion 5's second half: the composition projects evidence grain
    onto document grain, and does not discard a link to do it.
    """
    with linked() as session:
        links = documents_for(session, scope, MERIDIAN)
    doc_006 = [link for link in links if link.document_source_id == "DOC-006"]

    assert len(doc_006) == 2
    assert {str(link.link.basis) for link in doc_006} == {"EXACT_NAME", "ID_TOKEN"}


def test_a_customer_with_links_but_no_contract_document_gets_an_empty_tuple(linked, scope):
    """§0.4.8 criterion 6, and §0.3.6: zero contract links yield (), not an error."""
    with linked() as session:
        links = documents_for(session, scope, UNITY)
        commercial = build_contexts(session, scope, UNITY).commercial

    assert links, "the case is only meaningful for a customer that does have links"
    assert not any(link.is_contract for link in links)
    assert commercial.signals.contract_document_ids == ()


def test_with_no_links_persisted_at_all_both_contexts_still_build(demo, scope):
    """
    §0.4.8 criterion 7, the §0.4.3 hazard stated directly: an undertived run
    is indistinguishable from a customer with no contract, so the factory must
    not raise and S14 must be ().
    """
    with demo() as session:
        assert session.scalar(select(func.count()).select_from(DocumentCustomerLink)) == 0
        contexts = build_contexts(session, scope, MERIDIAN)

    assert contexts.commercial.signals.contract_document_ids == ()
    assert contexts.support.tickets, "the rest of the context is unaffected"


def test_the_support_context_is_never_given_s14(linked, scope):
    """
    §0.4.9 D-M5-B8, asserted on a built context as well as on the type: the
    exclusion is structural, so there is no attribute to read.
    """
    support = contexts_for(linked, scope, MERIDIAN).support

    assert not hasattr(support.signals, "contract_document_ids")
    assert not hasattr(support, "contract_document_ids")


def test_support_reaches_doc_003_as_a_policy_document_instead(linked, scope):
    """
    D-M5-B8's positive half: Support's document evidence is DOC-003, through
    escalation.because_documents and M2's policy_documents() -- a policy
    document, structurally cited, never a derived contract link.
    """
    support = contexts_for(linked, scope, MERIDIAN).support

    assert support.escalation.because_documents == ("DOC-003",)
    assert EntityRef("documents", "DOC-003") in support.policy_documents


# ---------------------------------------------------------------------------
# Criterion 8 and 9: silence, and the case the rejected proxy got wrong
# ---------------------------------------------------------------------------


def test_a_ticketless_customer_gets_band_none_and_no_support_position(linked, scope):
    """§0.4.8 criterion 8: the empty tuple, and not a NO_ACTION position."""
    ticketless = _ticketless_customers(linked, scope)
    assert ticketless, "the scan would be vacuous without at least one"

    with linked() as session:
        for customer in ticketless:
            contexts = build_contexts(session, scope, customer)
            support = SupportRiskAnalyst(context=contexts.support).positions()

            assert contexts.support.band == "NONE", customer
            assert contexts.support.tickets == (), customer
            assert support == (), customer


def test_exactly_three_ticketless_customers_still_speak_commercially(linked, scope):
    """
    §0.4.8 criterion 8's second half, measured: ACCELERATE_DEAL_CLOSE carries
    no band term, so three of the ticketless customers emit one SALES position
    and the rest emit nothing.
    """
    speaking = {}
    with linked() as session:
        for customer in _ticketless_customers(linked, scope):
            contexts = build_contexts(session, scope, customer)
            sales = CommercialAnalyst(context=contexts.commercial).positions()
            if sales:
                speaking[customer] = tuple(position.object_ref for position in sales)

    assert speaking == {
        customer: (deal,) for customer, deal in TICKETLESS_WITH_A_DEAL.items()
    }


def test_the_watch_customers_propose_no_pause_because_neither_negotiates(linked, scope):
    """
    §0.4.8 criterion 9 -- the case that would have been wrong under §0.4.6's
    rejected S15 proxy. CUST-025 has no deal and CUST-036's DEAL-037 is in
    qualification, so neither contests a deal however many breaches it has.
    """
    with linked() as session:
        for customer in ("CUST-025", "CUST-036"):
            contexts = build_contexts(session, scope, customer)
            actions = {
                position.proposed_action
                for position in SupportRiskAnalyst(context=contexts.support).positions()
            }

            assert contexts.support.contested_deal is None, customer
            assert ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED not in actions, customer
            assert ActionId.NO_ACTION not in actions, customer


def test_no_customer_anywhere_draws_a_no_action_position(linked, scope):
    """§A16 leaves NO_ACTION's *Proposed by* column empty, across all 50 customers."""
    with linked() as session:
        for customer in customers_in_scope(session, scope):
            for position in (
                SupportRiskAnalyst(
                    context=build_contexts(session, scope, customer).support
                ).positions()
            ):
                assert position.proposed_action is not ActionId.NO_ACTION, customer


def _ticketless_customers(sessions, scope: Scope) -> tuple[str, ...]:
    with sessions() as session:
        return tuple(
            customer for customer in customers_in_scope(session, scope)
            if not ticket_facts(session, scope, customer, config=default_risk_rules())
        )


# ---------------------------------------------------------------------------
# Criterion 10 and 11: determinism, and the read-only guarantee
# ---------------------------------------------------------------------------


def test_two_builds_in_one_session_are_equal(linked, scope):
    """§0.4.8 criterion 10, first half: equal contexts and equal payloads."""
    with linked() as session:
        first = build_contexts(session, scope, MERIDIAN)
        second = build_contexts(session, scope, MERIDIAN)

    assert first == second
    assert first.support.signals.to_payload() == second.support.signals.to_payload()
    assert [fact.to_payload() for fact in first.support.tickets] == [
        fact.to_payload() for fact in second.support.tickets
    ]


def test_two_readings_render_identical_position_payloads(linked, scope):
    """
    §0.4.8 criterion 10 names `to_payload()` explicitly, because the payload
    is what M7 hashes: two runs that agreed as objects but not as payloads
    would still produce two different assessments.
    """
    first = [position.to_payload() for position in positions_for(linked, scope, MERIDIAN)]
    second = [position.to_payload() for position in positions_for(linked, scope, MERIDIAN)]

    assert first == second


def test_rebuilding_after_reinsertion_in_a_different_order_is_equal(linked, scope):
    """
    §0.4.8 criterion 10's third clause: physical row order must not reach the
    output. The links are deleted and reinserted in reverse, which is a
    fixture manipulation and not something M5 does.
    """
    before = contexts_for(linked, scope, MERIDIAN)
    before_positions = as_rows(positions_for(linked, scope, MERIDIAN))
    with linked.begin() as session:
        rows = session.execute(select(DocumentCustomerLink)).scalars().all()
        payload = [
            {
                column.name: getattr(row, column.name)
                for column in DocumentCustomerLink.__table__.columns
            }
            for row in rows
        ]
        session.execute(DocumentCustomerLink.__table__.delete())
    with linked.begin() as session:
        session.execute(DocumentCustomerLink.__table__.insert(), list(reversed(payload)))

    assert contexts_for(linked, scope, MERIDIAN) == before
    assert as_rows(positions_for(linked, scope, MERIDIAN)) == before_positions


def test_building_every_context_writes_no_row_anywhere(linked, scope):
    """
    §0.4.8 criterion 11, and §0.4.3's "M5 never persists", proved rather than
    promised. Every table is counted, not only the link table, so a write to
    any of them fails here.
    """
    before = _table_counts(linked)

    with linked() as session:
        for customer in customers_in_scope(session, scope):
            contexts = build_contexts(session, scope, customer)
            SupportRiskAnalyst(context=contexts.support).positions()
            CommercialAnalyst(context=contexts.commercial).positions()

    assert _table_counts(linked) == before


def test_the_factory_does_not_derive_the_links_it_reads(demo, scope):
    """
    §0.4.3: deriving is the assessment run's, which is M7's. Building contexts
    over an underived snapshot must leave the link table empty rather than
    quietly filling it.
    """
    with demo() as session:
        build_contexts(session, scope, MERIDIAN)

    with demo() as session:
        assert session.scalar(select(func.count()).select_from(DocumentCustomerLink)) == 0


def test_the_factory_leaves_the_session_usable_and_untouched(linked, scope):
    """
    §0.4.7: it never closes, commits or rolls back. A session the factory had
    closed would fail the next read, and an in-progress transaction it had
    committed would not still be in one.
    """
    with linked() as session:
        build_contexts(session, scope, MERIDIAN)
        assert session.is_active
        assert compute_signals(session, scope, MERIDIAN).customer.source_id == MERIDIAN


# ---------------------------------------------------------------------------
# Criterion 14 and 15: grounded positions, and money per currency
# ---------------------------------------------------------------------------


def test_every_citation_of_every_position_resolves_to_a_layer_1_row(linked, scope):
    """
    §0.4.8 criterion 14's last clause, over all 50 customers. A citation is
    resolved by looking the row up the way a reviewer would, so a position
    naming a ticket or deal that is not in scope fails here.
    """
    resolved = 0
    with linked() as session:
        for customer in customers_in_scope(session, scope):
            contexts = build_contexts(session, scope, customer)
            positions = (
                SupportRiskAnalyst(context=contexts.support).positions()
                + CommercialAnalyst(context=contexts.commercial).positions()
            )
            for position in positions:
                assert position.evidence, position.proposed_action
                for citation in position.citations:
                    assert _row_exists(session, citation), (customer, citation)
                    resolved += 1

    assert resolved > 0, "the scan would pass vacuously with no citations at all"


def _row_exists(session: Session, citation) -> bool:
    """Whether a RecordCitation names a row that is actually in scope."""
    from app.persistence.models import Customer, Deal

    model = {"customers": Customer, "deals": Deal, "support_tickets": SupportTicket}[
        citation.entity_type
    ]
    return session.scalar(
        select(func.count()).select_from(model).where(
            model.source_system == SOURCE_SYSTEM,
            model.source_entity == citation.entity_type,
            model.source_id == citation.source_id,
        )
    ) == 1


def test_the_commercial_context_renders_exposure_per_currency(linked, scope):
    """
    §0.4.8 criterion 15 and §A12: exposure is per currency, and CUST-007's is
    the USD figure §A27.3 requires the brief to cite.
    """
    commercial = contexts_for(linked, scope, MERIDIAN).commercial
    exposure = commercial.signals.exposure_by_currency

    assert set(exposure) == {"USD"}
    assert str(exposure["USD"].amount) == "5361.44"


def test_summing_two_currencies_raises_rather_than_inventing_a_rate(linked, scope):
    """
    §A12, on a real context: VS-01 publishes no FX rate set, so no
    cross-currency total exists to publish. The second currency is a fixture,
    because the demo dataset's deals for one customer share a currency.
    """
    from app.intelligence.errors import CurrencyMismatchError
    from app.intelligence.money import MoneyValue

    commercial = contexts_for(linked, scope, MERIDIAN).commercial
    usd = commercial.signals.exposure_by_currency["USD"]

    with pytest.raises(CurrencyMismatchError):
        MoneyValue.total("USD", [usd, MoneyValue(amount=usd.amount, currency="EUR")])


# ---------------------------------------------------------------------------
# Criterion 13: the M4 handoff is unchanged
# ---------------------------------------------------------------------------


def test_the_band_and_satisfied_rules_are_m3s_and_are_shared(linked, scope):
    """
    Both contexts carry the same assignment, and it is the one M3 computes:
    the factory assigns no band of its own.
    """
    from app.intelligence.bands import assign_band

    contexts = contexts_for(linked, scope, MERIDIAN)
    with linked() as session:
        signals = compute_signals(session, scope, MERIDIAN).signals
    expected = assign_band(signals, default_risk_rules().band_rules, floor="NONE")

    assert contexts.support.band == contexts.commercial.band == expected.band == "CRITICAL"
    assert contexts.support.satisfied_rules == expected.satisfied_rules


def test_s14_does_not_change_the_band(linked, demo, scope):
    """
    The band is assigned from the S14-populated set, which changes nothing: no
    band rule reads contract_document_ids, and §A10 classifies S14 as evidence
    only. Asserted by comparing a derived run with an underived one.
    """
    with linked() as session:
        with_links = build_contexts(session, scope, MERIDIAN)
    with linked.begin() as session:
        session.execute(DocumentCustomerLink.__table__.delete())
    with demo() as session:
        without_links = build_contexts(session, scope, MERIDIAN)

    assert with_links.commercial.signals.contract_document_ids == ("DOC-006",)
    assert without_links.commercial.signals.contract_document_ids == ()
    assert with_links.support.band == without_links.support.band
    assert with_links.support.signals == without_links.support.signals
