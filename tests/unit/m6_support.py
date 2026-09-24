"""
Hand-built analyst contexts and configuration files for the M6 unit suite.

Not a test module. Two kinds of builder:

  * **Contexts.** `contexts()` builds one customer's AnalystContexts with
    every fact that decides a reconciliation stated explicitly -- band, S8,
    S4, deals, projects, tickets -- on top of M5's own builders. Nothing
    defaults to "whatever CUST-007 has": a default that happens to satisfy
    CONF-001's `when` is exactly how an unresolvable conflict stays hidden.
  * **Configuration.** `catalogue_data()` and `policy_data()` read the
    committed files rather than restating them, so a fixture that mutates
    one key differs from the shipped configuration in that key and no other.

`meridian_contexts()` is CUST-007's shape at ACCEPTANCE_AS_OF: the six
positions of §0.4.1, CRITICAL, S8 = 3, S4 = 5, one negotiation deal at 90%.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from app.analysts import AnalystContexts
from app.decisions.policy import (
    DEFAULT_CATALOGUE_PATH,
    DEFAULT_POLICY_PATH,
    ActionCatalogue,
    ConflictPolicy,
    load_action_catalogue,
    load_conflict_policy,
)
from app.intelligence.contract import DealSignal, EntityRef
from tests.unit.m5_support import commercial_context, deal, support_context, ticket

MERIDIAN = "CUST-007"
CONTESTED_DEAL = "DEAL-001"


def catalogue_data() -> dict:
    """The committed catalogue as plain data, safe to mutate."""
    return copy.deepcopy(yaml.safe_load(DEFAULT_CATALOGUE_PATH.read_text(encoding="utf-8")))


def policy_data() -> dict:
    """The committed policy as plain data, safe to mutate."""
    return copy.deepcopy(yaml.safe_load(DEFAULT_POLICY_PATH.read_text(encoding="utf-8")))


def write_yaml(path: Path, data: object) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def load_catalogue(tmp_path: Path, data: object) -> ActionCatalogue:
    return load_action_catalogue(write_yaml(tmp_path / "action_catalogue.yaml", data))


def load_policy(
    tmp_path: Path, data: object, *, catalogue: ActionCatalogue | None = None
) -> ConflictPolicy:
    if catalogue is None:
        catalogue = load_action_catalogue(DEFAULT_CATALOGUE_PATH)
    return load_conflict_policy(write_yaml(tmp_path / "conflict_policy.yaml", data),
                                catalogue=catalogue)


def flipped_policy(tmp_path: Path) -> ConflictPolicy:
    """The committed policy with CONF-001's `resolve_to` flipped, and nothing else changed."""
    data = policy_data()
    data["conflicts"][0]["resolve_to"] = "ACCELERATE_DEAL_CLOSE"
    return load_policy(tmp_path, data)


def breaching(count: int) -> tuple:
    """`count` open, high-priority, SLA-breaching tickets: the rows S8 counts."""
    return tuple(
        ticket(f"TKT-{index:03d}", priority="high", is_open=True, breaches_sla=True)
        for index in range(1, count + 1)
    )


def contexts(
    *,
    customer: str = "CUST-999",
    band: str = "NONE",
    s8: int = 0,
    s4: int = 0,
    s5: bool = False,
    deals: tuple[DealSignal, ...] = (),
    projects: int = 0,
    billing: bool = False,
) -> AnalystContexts:
    """
    One customer's two contexts, agreeing on every shared fact.

    `s8` open high-priority breaching tickets are placed in Support's ticket
    rows and counted identically on both sides; `contested_deal` and
    `has_active_deal` are derived from `deals` exactly as the M5 factory
    derives them, so Support and Sales can never disagree about the deal.
    """
    tickets = breaching(s8)
    if billing:
        tickets += (ticket("TKT-900", priority="medium", category="billing",
                           is_open=True, breaches_sla=True),)
    negotiating = sorted(one.source_id for one in deals if one.stage == "negotiation")
    signals = {
        "open_ticket_count": len(tickets),
        "open_high_priority_count": s8,
        "high_priority_total": s8,
        "max_tickets_in_14d_window": s4,
        "policy_escalation_state": s5,
        "sla_breach_count": len(tickets),
        "open_sla_breach_high_count": s8,
    }
    return AnalystContexts(
        support=support_context(
            customer=customer,
            band=band,
            tickets=tickets,
            has_active_deal=bool(deals),
            contested_deal=EntityRef("deals", negotiating[0]) if negotiating else None,
            **signals,
        ),
        commercial=commercial_context(
            customer=customer,
            band=band,
            deals=deals,
            active_project_count=projects,
            deal_under_pressure=s5 and bool(deals),
            **signals,
        ),
    )


def meridian_contexts(*, amount: str = "5361.44") -> AnalystContexts:
    """CUST-007 at ACCEPTANCE_AS_OF: CRITICAL, S8 = 3, S4 = 5, DEAL-001 at 90%."""
    return contexts(
        customer=MERIDIAN,
        band="CRITICAL",
        s8=3,
        s4=5,
        s5=True,
        deals=(deal(CONTESTED_DEAL, stage="negotiation", probability=90, amount=amount),),
        billing=True,
    )


def watch_conflict_contexts() -> AnalystContexts:
    """
    The shape §0.5.5 records as unresolvable: S8 = 1 without S5 bands WATCH,
    yet Support still pauses and Sales still accelerates one negotiation deal.
    """
    return contexts(
        customer="CUST-998",
        band="WATCH",
        s8=1,
        s4=1,
        deals=(deal("DEAL-998", stage="negotiation", probability=90),),
    )
