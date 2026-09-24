"""
Conflict detection over M5's positions (VS-01 M6, §A15, §0.5.5, §0.5.10).

Detection is a statement of fact, separate from resolution: this module says
*that* two functions want incompatible things on one object, and returns the
frozen M1 Conflict that records it. Deciding between them is the reconciler's,
by policy.

**Three rules, and nothing else, make two positions a conflict:**

    one object      their Position.object_ref values are equal. Nothing is
                    compared across objects, so a customer whose functions
                    share no object has no conflict at all (§0.5.10).
    two functions   they are stated by different functions. Support's three
                    positions on its own customer are never compared with one
                    another.
    one declared    the policy names their pair of actions incompatible.
    pair            Two functions proposing different actions on one object
                    that no rule names do not conflict; both stand.

Because no two rules may name one pair, every conflict found here has exactly
one candidate rule. **More than one declared pair over one object is refused**
(§0.5.5): frozen Conflict admits one position per function, VS-01's policy
resolves pairs, and a three-way or cyclic conflict is VS-04's. The shipped
catalogue cannot produce one.

**Positions are checked against the catalogue before anything is compared**
(§0.5.2 D-M6-B2). A position must propose an action some function proposes,
and the catalogue's function and stance for that action must be the
position's own -- so drift between M5's code and the catalogue fails the run
rather than reaching a brief. No two positions may share an identity, which
§0.4.1 already guarantees and which is what makes every order below total.

Pure: no session, no clock, no randomness, no write. Every collection is put
in an explicit order before it is read, so nothing depends on the order the
positions arrive in.
"""

from __future__ import annotations

from collections.abc import Iterable
from itertools import combinations

from app.analysts.base import order_positions
from app.decisions.policy import ActionCatalogue, ConflictPolicy
from app.intelligence.contract import ActionId, Conflict, Function, Position
from app.intelligence.errors import IntelligenceError


class ReconciliationError(IntelligenceError):
    """
    A reconciliation's inputs are inconsistent, so no decision is safe to state.

    A runtime fault in what the decision layer was handed, not in its
    configuration: DecisionConfigError covers the files.
    """


class UnresolvableConflictError(ReconciliationError):
    """
    A conflict exists that the policy cannot resolve.

    Surfaced, never dropped (§0.5.5): no default winner is chosen, no partial
    result is returned, and the conflict is named in full so it can be read
    rather than inferred.
    """

    def __init__(
        self,
        message: str,
        *,
        object_ref: str,
        actions: tuple[ActionId, ...],
        rule_id: str | None,
    ) -> None:
        super().__init__(message)
        self.object_ref = object_ref
        self.actions = actions
        self.rule_id = rule_id


def position_identity(position: Position) -> tuple[Function, str, ActionId]:
    """
    Which function proposes which action on which object.

    At most one position per identity: §0.4.1 has an analyst emit one
    position per satisfied entry per contested object.
    """
    return position.function, position.object_ref, position.proposed_action


def checked_positions(
    positions: Iterable[Position], catalogue: ActionCatalogue
) -> tuple[Position, ...]:
    """
    The positions in §0.4.1's order, each agreeing with the catalogue, none repeated.

    The order is M5's own `order_positions`, reused rather than restated: a
    sort key for reproducibility, never a priority. Positions are returned
    unmodified -- the decision layer never edits a position, so it can never
    edit away a position's evidence.
    """
    ordered = order_positions(positions)
    for position in ordered:
        entry = catalogue.entry(position.proposed_action)
        where = f"{position.function} {position.proposed_action} on {position.object_ref}"
        if entry.function is None:
            raise ReconciliationError(
                f"{where}: the catalogue says no function proposes {position.proposed_action}"
            )
        if entry.function is not position.function:
            raise ReconciliationError(
                f"{where}: the catalogue gives {position.proposed_action} to {entry.function}"
            )
        if entry.stance is not position.stance:
            raise ReconciliationError(
                f"{where}: stance {position.stance} disagrees with the catalogue's "
                f"{entry.stance}"
            )
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        if position_identity(earlier) == position_identity(later):
            raise ReconciliationError(
                f"{later.function} states {later.proposed_action} on {later.object_ref} twice; "
                f"an analyst emits one position per entry per object"
            )
    return ordered


def detect_conflicts(
    positions: Iterable[Position], policy: ConflictPolicy
) -> tuple[Conflict, ...]:
    """
    Every conflict among one customer's positions, ascending by object.

    Each Conflict holds exactly the two positions whose pair the policy
    declares incompatible, in §0.4.1's position order. An object with no
    declared cross-function pair yields nothing.
    """
    ordered = checked_positions(positions, policy.catalogue)
    by_object: dict[str, list[Position]] = {}
    for position in ordered:
        by_object.setdefault(position.object_ref, []).append(position)
    conflicts = []
    for object_ref in sorted(by_object):
        pairs = [
            (first, second)
            for first, second in combinations(by_object[object_ref], 2)
            if first.function is not second.function
            and policy.declares_incompatible(first.proposed_action, second.proposed_action)
        ]
        if not pairs:
            continue
        if len(pairs) > 1:
            named = "; ".join(
                f"{first.proposed_action} vs {second.proposed_action}" for first, second in pairs
            )
            raise UnresolvableConflictError(
                f"{object_ref}: {len(pairs)} declared pairs conflict over one object ({named}). "
                f"VS-01 resolves one pair between two functions; a three-way or cyclic "
                f"conflict is VS-04's, and no winner is chosen for it",
                object_ref=object_ref,
                actions=tuple(
                    sorted({position.proposed_action for pair in pairs for position in pair},
                           key=str)
                ),
                rule_id=None,
            )
        conflicts.append(Conflict(object_ref=object_ref, positions=pairs[0]))
    return tuple(conflicts)
