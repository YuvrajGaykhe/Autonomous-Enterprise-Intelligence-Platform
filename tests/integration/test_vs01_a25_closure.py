"""
§A25 proofs the mapped corpus did not assert (plan §0.8.6, M9 Phase 5).

Phase 5 re-read every test §0.8.6 maps to a §A25 criterion. One clause was
not asserted by any of them:

    10. Negative cases. The 15 ticketless customers, which include all 4
        inactive ones, yield NONE, not worthy.

tests/integration/test_m3_signals.py::test_all_fifteen_ticketless_customers_band_none
asserts that exactly 15 customers are ticketless and that each bands NONE,
and tests/integration/test_m6_reconciliation.py::test_only_cust_007_is_executive_worthy
that no one but CUST-007 is worthy. Neither asserts that the four inactive
customers are among the fifteen, so an inactive customer that acquired a
ticket would leave both green while the criterion's clause became false.
The proof below closes that clause over the stored assessments of one real,
pinned run, rather than over any one milestone's intermediate values.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.registry import build_connector
from app.decisions.assessment import run_assessment
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence.config import default_risk_rules
from app.persistence.models import Customer, RiskAssessment, SupportTicket

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
ACCEPTANCE_AS_OF = date(2026, 9, 18)
INACTIVE = {"CUST-002", "CUST-013", "CUST-027", "CUST-034"}
TICKETLESS_COUNT = 15


@pytest.fixture
def assessed(e1_sessions: sessionmaker[Session]) -> sessionmaker[Session]:
    """The clean full-dataset path, then one pinned run at the acceptance date."""
    summary = run_ingestion(build_connector("csv_demo", data_directory=DEMO_DIR), e1_sessions,
                            IngestionRequest())
    assert summary.counts.rejected == 0
    with e1_sessions.begin() as session:
        run_assessment(session, as_of=ACCEPTANCE_AS_OF, expected_fingerprint=default_risk_rules()
                       .pinned_fingerprint("csv_demo"))
    return e1_sessions


def test_the_four_inactive_customers_are_ticketless_and_yield_none_not_worthy(assessed):
    """§A25 test 10: the 15 ticketless customers include all 4 inactive ones, and none is worthy."""
    with assessed() as session:
        customers = session.execute(select(Customer.source_id, Customer.is_active)).all()
        ticketed = set(session.scalars(select(SupportTicket.customer_source_id)).all())
        assessments = {source_id: (band, worthy) for source_id, band, worthy in session.execute(
            select(Customer.source_id, RiskAssessment.band, RiskAssessment.executive_worthy)
            .join(Customer, RiskAssessment.customer_id == Customer.id)).all()}

    inactive = {source_id for source_id, is_active in customers if not is_active}
    ticketless = {source_id for source_id, _ in customers if source_id not in ticketed}

    assert inactive == INACTIVE
    assert len(ticketless) == TICKETLESS_COUNT
    assert inactive <= ticketless
    assert len(assessments) == 50
    for source_id in sorted(ticketless):
        assert assessments[source_id] == ("NONE", False), source_id
