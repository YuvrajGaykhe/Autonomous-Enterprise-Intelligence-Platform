"""
Hand-built brief inputs for the M7 unit suite.

Not a test module. `meridian()` is CUST-007 at ACCEPTANCE_AS_OF, stated value
by value as the integration suite measures it on the committed dataset: five
visible tickets created 08-18 to 08-27, M3's window [08-18, 08-31] counting
five, DEAL-001 in negotiation at 90% for USD 5,361.44, six own-stamp links to
DOC-005, DOC-006 and DOC-009, and the three cited spans at their measured
offsets. The positions and the reconciliation are M5's and M6's own, built by
calling `reconcile` on the contexts, never restated.

Every builder returns fresh values, and `BriefInputs.replace` changes one
input and nothing else, so a test that perturbs a fact differs from CUST-007
in that fact alone.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from types import MappingProxyType

from app.analysts import AnalystContexts
from app.decisions import Reconciliation, reconcile
from app.decisions import payload as payloads
from app.evidence import derived_relationship_evidence
from app.intelligence import AsOfSource, RiskRulesConfig, Scope
from app.intelligence.config import default_risk_rules
from app.intelligence.contract import (
    DealSignal,
    DerivedLink,
    DocumentCitation,
    EntityRef,
    LinkBasis,
)
from app.persistence.repositories.canonical import ENTITY_MODELS
from tests.unit.m5_support import commercial_context, deal, support_context, ticket

MERIDIAN = "CUST-007"
FINGERPRINT = "1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00"
ACCEPTANCE_AS_OF = date(2026, 9, 18)

MERIDIAN_RULES = (
    "R-CRIT-001", "R-ELEV-001", "R-ELEV-002", "R-WATCH-001", "R-WATCH-002", "R-WATCH-003",
)

#: The five visible tickets, as M5 derives them at ACCEPTANCE_AS_OF.
MERIDIAN_TICKETS = (
    ticket("TKT-073", priority="high", category="performance", is_open=False,
           breaches_sla=True),
    ticket("TKT-075", priority="high", category="performance", is_open=True,
           breaches_sla=True),
    ticket("TKT-076", priority="high", category="integration", is_open=True,
           breaches_sla=True),
    ticket("TKT-079", priority="medium", category="billing", is_open=True,
           breaches_sla=True),
    ticket("TKT-080", priority="high", category="performance", is_open=True,
           breaches_sla=True),
)

MERIDIAN_DATES = MappingProxyType({
    "TKT-073": date(2026, 8, 18),
    "TKT-075": date(2026, 8, 20),
    "TKT-076": date(2026, 8, 23),
    "TKT-079": date(2026, 8, 25),
    "TKT-080": date(2026, 8, 27),
})

#: S1-S10 as M3 measures them for CUST-007.
MERIDIAN_SIGNALS = {
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
}

MERIDIAN_WINDOW = MappingProxyType({"start": "2026-08-18", "end": "2026-08-31", "count": 5})

#: The measured link spans in each document's citable text.
MERIDIAN_LINKS = (
    ("DOC-005", LinkBasis.EXACT_NAME, "Meridian Textiles", 171, 188),
    ("DOC-005", LinkBasis.ID_TOKEN, "CUST-007", 190, 198),
    ("DOC-006", LinkBasis.EXACT_NAME, "Meridian Textiles", 28, 45),
    ("DOC-006", LinkBasis.ID_TOKEN, "CUST-007", 113, 121),
    ("DOC-009", LinkBasis.EXACT_NAME, "Meridian Textiles", 23, 40),
    ("DOC-009", LinkBasis.ID_TOKEN, "CUST-007", 76, 84),
)

MERIDIAN_SPANS = MappingProxyType({
    "DOC_003_ESCALATION_RULE": DocumentCitation("DOC-003", 238, 330),
    "DOC_006_TERM_AND_NOTICE": DocumentCitation("DOC-006", 153, 238),
    "DOC_009_DEAL_LINKAGE": DocumentCitation("DOC-009", 238, 333),
})


def ref(entity: str, source_id: str) -> dict[str, object]:
    return {"entity": entity, "id": source_id}


def edge(kind: str, source: tuple[str, str], target: tuple[str, str], carrier: str) -> dict:
    return {
        "edge": kind, "source": ref(*source), "target": ref(*target),
        "basis": "SOURCE_KEY_JOIN", "carrier_field": carrier, "source_system": "csv_demo",
    }


#: M2's projection for CUST-007, in M2's own orders.
MERIDIAN_PATH = MappingProxyType({
    "customer": ref("customers", MERIDIAN),
    "account_owner": ref("employees", "EMP-007"),
    "account_owner_manager": ref("employees", "EMP-002"),
    "open_tickets": [ref("support_tickets", one) for one in
                     ("TKT-075", "TKT-076", "TKT-079", "TKT-080")],
    "assignees": [ref("employees", one) for one in ("EMP-018", "EMP-021", "EMP-017", "EMP-020")],
    "assignee_managers": [ref("employees", "EMP-004")],
    "edges": [
        edge("customer_owned_by", ("customers", MERIDIAN), ("employees", "EMP-007"),
             "customers.owner_source_id"),
        edge("employee_reports_to", ("employees", "EMP-007"), ("employees", "EMP-002"),
             "employees.manager_source_id"),
    ],
})


def scope(*, as_of: date = ACCEPTANCE_AS_OF, fingerprint: str = FINGERPRINT,
          source_system: str = "csv_demo") -> Scope:
    return Scope(
        source_system=source_system,
        as_of=as_of,
        layer1_fingerprint=fingerprint,
        as_of_source=AsOfSource.EXPLICIT,
        entity_counts=MappingProxyType(dict.fromkeys(ENTITY_MODELS, 1)),
    )


def meridian_deal(amount: str = "5361.44") -> DealSignal:
    return deal("DEAL-001", stage="negotiation", probability=90, amount=amount)


def contexts(
    *,
    customer: str = MERIDIAN,
    band: str = "CRITICAL",
    satisfied_rules: tuple[str, ...] = MERIDIAN_RULES,
    tickets: Sequence = MERIDIAN_TICKETS,
    deals: tuple[DealSignal, ...] | None = None,
    active_project_count: int = 0,
    contract_document_ids: tuple[str, ...] = ("DOC-006",),
    **signal_overrides: object,
) -> AnalystContexts:
    """Both contexts for one customer, agreeing on every shared fact."""
    deals = (meridian_deal(),) if deals is None else deals
    signals = {**MERIDIAN_SIGNALS, **signal_overrides}
    negotiating = sorted(one.source_id for one in deals if one.stage == "negotiation")
    return AnalystContexts(
        support=support_context(
            customer=customer,
            band=band,
            satisfied_rules=satisfied_rules,
            tickets=tuple(tickets),
            has_active_deal=bool(deals),
            contested_deal=EntityRef("deals", negotiating[0]) if negotiating else None,
            **signals,
        ),
        commercial=commercial_context(
            customer=customer,
            band=band,
            satisfied_rules=satisfied_rules,
            deals=deals,
            active_project_count=active_project_count,
            contract_document_ids=contract_document_ids,
            deal_under_pressure=bool(signals["policy_escalation_state"])
            and any(one.stage == "negotiation" for one in deals),
            **signals,
        ),
    )


def link(document: str, basis: LinkBasis, matched: str, start: int, end: int, *,
         customer: str = MERIDIAN, fingerprint: str = FINGERPRINT,
         linker_version: str = "1") -> DerivedLink:
    return DerivedLink(
        source=EntityRef("documents", document),
        target=EntityRef("customers", customer),
        basis=basis,
        confidence=basis.confidence,
        matched_token=matched,
        evidence=derived_relationship_evidence(document, start, end),
        source_system="csv_demo",
        layer1_fingerprint=fingerprint,
        linker_version=linker_version,
    )


def meridian_links() -> tuple[DerivedLink, ...]:
    return tuple(link(*row) for row in MERIDIAN_LINKS)


@dataclass(frozen=True)
class BriefInputs:
    """Everything build_payload takes, for one customer."""

    scope: Scope
    config: RiskRulesConfig
    contexts: AnalystContexts
    reconciliation: Reconciliation
    links: tuple[DerivedLink, ...]
    spans: Mapping[str, DocumentCitation]
    created_dates: Mapping[str, date]
    escalation_window: Mapping[str, object] | None
    backlog_ticket_ids: tuple[str, ...]
    escalation_path: Mapping[str, object] = field(default_factory=lambda: dict(MERIDIAN_PATH))

    def replace(self, **changes: object) -> BriefInputs:
        return replace(self, **changes)  # type: ignore[arg-type]

    def payload(self) -> dict[str, object]:
        return payloads.build_payload(
            scope=self.scope,
            config=self.config,
            contexts=self.contexts,
            reconciliation=self.reconciliation,
            links=self.links,
            spans=self.spans,
            created_dates=self.created_dates,
            escalation_window=self.escalation_window,
            backlog_ticket_ids=self.backlog_ticket_ids,
            escalation_path=self.escalation_path,
        )


def meridian(**context_changes: object) -> BriefInputs:
    """CUST-007's inputs at ACCEPTANCE_AS_OF, with any context fact changed."""
    built = contexts(**context_changes)  # type: ignore[arg-type]
    return BriefInputs(
        scope=scope(),
        config=default_risk_rules(),
        contexts=built,
        reconciliation=reconcile(built),
        links=meridian_links(),
        spans=dict(MERIDIAN_SPANS),
        created_dates=dict(MERIDIAN_DATES),
        escalation_window=dict(MERIDIAN_WINDOW),
        backlog_ticket_ids=(),
    )


def quiet(**context_changes: object) -> BriefInputs:
    """
    A WATCH customer with one ticket and no deal, link, span or position.

    Its only ticket is TKT-078, created 08-24 and still open, as CUST-036's is,
    so the window counts one and the span is 0 days (§0.6.13.2's one-ticket
    case). Everything a brief can state as absent is absent.
    """
    tickets = (ticket("TKT-078", priority="medium", category="performance", is_open=True,
                      breaches_sla=True),)
    changes: dict[str, object] = {
        "customer": "CUST-036", "band": "WATCH", "satisfied_rules": ("R-WATCH-003",),
        "tickets": tickets, "deals": (), "contract_document_ids": (),
        "open_ticket_count": 1, "open_high_priority_count": 0, "high_priority_total": 0,
        "tickets_in_lookback": 1, "max_tickets_in_14d_window": 1,
        "policy_escalation_state": False, "days_since_last_ticket": 25,
        "sla_breach_count": 1, "open_sla_breach_high_count": 0,
        "dominant_ticket_category": "performance",
        **context_changes,
    }
    built = contexts(**changes)  # type: ignore[arg-type]
    return BriefInputs(
        scope=scope(),
        config=default_risk_rules(),
        contexts=built,
        reconciliation=reconcile(built),
        links=(),
        spans={},
        created_dates={"TKT-078": date(2026, 8, 24)},
        escalation_window={"start": "2026-08-24", "end": "2026-09-06", "count": 1},
        backlog_ticket_ids=(),
        escalation_path={
            "customer": ref("customers", "CUST-036"), "account_owner": None,
            "account_owner_manager": None, "open_tickets": [], "assignees": [],
            "assignee_managers": [], "edges": [],
        },
    )
