"""
Conflict detection and reconciliation (VS-01 M6, plan §0.5).

The heart of the slice: detect that two functions want incompatible things on
one object, resolve it by a stated, versioned policy, and keep the losing
argument whole. Worthiness and ordering are decided here too, and M7 persists
them without recomputing either (§0.5.1 D-M6-B1).

Public API:
    ActionCatalogue / CatalogueEntry
                        the declarative action vocabulary: who proposes each
                        action, what it contests, which way it pulls. No
                        precondition and no threshold -- those stay M5's.
    ConflictPolicy / ConflictRule / ResolutionCondition
                        which pairs are incompatible and which action
                        prevails, when.
    load_action_catalogue / default_action_catalogue
    load_conflict_policy / default_conflict_policy
                        strict loaders; a broken entry is refused by name
                        and nothing half-loads.
    detect_conflicts    one object, two functions, one declared pair.
    reconcile           one customer's Reconciliation, from its
                        AnalystContexts.
    order_reconciliations
                        customers in §A15's order: band, S8, S4, source_id.
    Reconciliation / Worthiness
                        the M6 -> M7 seam.
    DecisionConfigError / ReconciliationError / UnresolvableConflictError

**This package is pure.** It reads no database, holds no session, reads no
clock, reaches no random source, writes nothing and logs nothing. It imports
M1's contract, M3's ranking key and M5's analysts, and never M2, M4 or
persistence: a policy document is cited by id, and membership was resolved
before the contexts were built. Boundary tests fail the build on any of it.
"""

from app.decisions.conflicts import (
    ReconciliationError,
    UnresolvableConflictError,
    detect_conflicts,
)
from app.decisions.policy import (
    ActionCatalogue,
    CatalogueEntry,
    ConflictPolicy,
    ConflictRule,
    DecisionConfigError,
    ResolutionCondition,
    default_action_catalogue,
    default_conflict_policy,
    load_action_catalogue,
    load_conflict_policy,
)
from app.decisions.reconciler import (
    Reconciliation,
    Worthiness,
    order_reconciliations,
    reconcile,
)

__all__ = [
    "ActionCatalogue",
    "CatalogueEntry",
    "ConflictPolicy",
    "ConflictRule",
    "DecisionConfigError",
    "Reconciliation",
    "ReconciliationError",
    "ResolutionCondition",
    "UnresolvableConflictError",
    "Worthiness",
    "default_action_catalogue",
    "default_conflict_policy",
    "detect_conflicts",
    "load_action_catalogue",
    "load_conflict_policy",
    "order_reconciliations",
    "reconcile",
]
