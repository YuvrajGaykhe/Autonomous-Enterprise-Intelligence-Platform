"""
Functional analyst contexts and positions (VS-01 M5, plan §0.4).

Two enterprise functions reason over the same customer without being able to
see each other's data, and each states every action it wants on the record
with the object it contests. The isolation is **structural**: Support is not
asked to ignore commercial facts, it is handed a context that cannot hold
them, and neither analyst module can reach a database at all.

Public API:
    SupportSignals      an M5-owned projection of exactly the eleven S1-S10
                        fields. SupportContext never holds a SignalSet
                        (§0.4.9 D-M5-B7), so S11-S15 have no field to land in
                        and cannot reach Support even by mistake.
    support_signals     the projection, pure and total.
    TicketFact          the five-field ticket shape §A14's "Tickets" means,
                        derived under M3's stated rules and pinned to M3's
                        signals by an equivalence test (§0.4.2).
    SupportContext      what SupportRiskAnalyst is constructed with.
    CommercialContext   what CommercialAnalyst is constructed with: the full
                        populated SignalSet, S14 included.
    AnalystContexts     both, built together from one snapshot read.
    build_contexts      the one factory, and the only place in this package
                        permitted a Session or an ORM model (§0.4.7).
    SupportRiskAnalyst  five of §A16's entries, function=SUPPORT.
    CommercialAnalyst   ACCELERATE_DEAL_CLOSE, function=SALES.

**This package writes nothing.** It reads, projects and composes. The caller
owns the session and the transaction, exactly as every Layer 1 repository and
both earlier Layer 2 packages already require, and the production call to
derive_and_persist belongs to the assessment run, which is M7's (§0.4.3).
Boundary tests fail the build if any module here commits, flushes, adds,
deletes, opens or closes a session, reads a clock, reaches a random source,
invokes the linker, or imports the decision layer.

The import graph stays a DAG: app.intelligence (M1) is read by
app.relationships (M2) and app.evidence (M4), and all three are read here.
app.analysts is a leaf -- nothing imports it, and it imports nothing
downstream of itself (§0.4.5).
"""

from app.analysts.base import (
    ACCELERATE_PROBABILITY_THRESHOLD,
    DEDICATED_OWNER_BREACH_THRESHOLD,
    PAUSE_BREACH_THRESHOLD,
    Analyst,
)
from app.analysts.commercial import CommercialAnalyst, qualifying_deals
from app.analysts.context import (
    BILLING_CATEGORY,
    AnalystContexts,
    CommercialContext,
    SupportContext,
    SupportSignals,
    TicketFact,
    build_contexts,
    contested_deal,
    support_signals,
    ticket_facts,
)
from app.analysts.support_risk import SupportRiskAnalyst

__all__ = [
    "ACCELERATE_PROBABILITY_THRESHOLD",
    "BILLING_CATEGORY",
    "DEDICATED_OWNER_BREACH_THRESHOLD",
    "PAUSE_BREACH_THRESHOLD",
    "Analyst",
    "AnalystContexts",
    "CommercialAnalyst",
    "CommercialContext",
    "SupportContext",
    "SupportRiskAnalyst",
    "SupportSignals",
    "TicketFact",
    "build_contexts",
    "contested_deal",
    "qualifying_deals",
    "support_signals",
    "ticket_facts",
]
