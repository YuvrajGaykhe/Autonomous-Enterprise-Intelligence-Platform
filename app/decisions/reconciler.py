"""
Reconciliation: the winning action, the preserved dissent, worthiness and order (VS-01 M6).

**The M6 result is `Reconciliation`, one per customer** -- the seam M7 builds
the risk brief from (§0.5.7 D-M6-B7). It stores what was decided and derives
everything that follows from it, in the discipline M1's ConflictResolution
set: dissent there is derived from the conflict rather than stored, "so there
is no field a future change can leave empty". Here `conflicts`, `dissent`,
`resolved_positions` and `policy_ids` are derived the same way, so none of
them can disagree with the decisions they come from.

**`reconcile()` invokes the two M5 analysts itself**, on the contexts it is
given, so the positions and the facts they are reconciled against cannot come
from different customers. Every position either analyst emits is kept,
unmodified, in `ordered_positions`. A conflict's losing position is removed
only from the derived `resolved_positions` view; it stays whole, with its own
evidence, in `ordered_positions` and in its resolution's dissent. Nothing is
averaged and nothing is deleted.

**An unresolvable conflict raises** (§0.5.5 D-M6-B5). A detected conflict has
exactly one candidate rule, and the rule applies only when every `when`
condition holds. When one does not, there is no default winner and no partial
result: UnresolvableConflictError names the conflict, the rule and each
failing condition, and no Reconciliation is returned for the customer.

**Resolution evidence cites documents by id** (§0.5.4 D-M6-B4): one
CANONICAL_FACT over RecordCitation("documents", id, "body_text") per document
the rule names. No session, no span, no derived link -- a policy citation is
structural (§A13), and M4 alone builds links.

**Worthiness is §A15 verbatim** (D-M6-B8): band >= ELEVATED and an active deal
or an active project. **Two orders, both total, neither reading money**
(D-M6-B9): positions by M5's `order_positions`, customers by M3's
`ranking_key` -- band desc, S8 desc, S4 desc, source_id asc. Both are called,
not restated, so the codebase holds one definition of each.

Pure: a function of (AnalystContexts, ConflictPolicy). No session, no clock,
no randomness, no write, no log -- §A21's conflict events are the assessment
run's to emit from the result (§0.5.1).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.analysts import AnalystContexts, CommercialAnalyst, SupportRiskAnalyst
from app.analysts.base import order_positions
from app.decisions.conflicts import (
    ReconciliationError,
    UnresolvableConflictError,
    checked_positions,
    detect_conflicts,
    position_identity,
)
from app.decisions.policy import ConflictPolicy, ConflictRule, default_conflict_policy
from app.intelligence.bands import BandAssignment, ranking_key
from app.intelligence.contract import (
    Conflict,
    ConflictResolution,
    EntityRef,
    Evidence,
    EvidenceKind,
    Position,
    RecordCitation,
    RiskBand,
)
from app.intelligence.errors import ContractViolationError

#: Layer 1 entity type a policy document is cited as.
DOCUMENTS = "documents"

#: The citable field of a policy document that states what the rule relies on.
POLICY_TEXT_FIELD = "body_text"

#: §A15: an executive-worthy customer's band is at least this.
WORTHINESS_BAND = RiskBand.ELEVATED

#: §A15's order as M3's ranking_key states it: (-band rank, -S8, -S4, source_id).
RankingKey = tuple[int, int, int, str]


@dataclass(frozen=True)
class Worthiness:
    """
    Whether a customer requires executive attention, and the three facts that decide it.

    Derived, never chosen: `executive_worthy` is a property of the band and
    the two counts, so it cannot disagree with them. S11 counts active deals
    of **any** stage and S13 active projects; no amount, currency,
    probability, stage or derived document count is an input (§0 defect 7).
    """

    band: RiskBand
    active_deal_count: int
    active_project_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.band, RiskBand):
            raise ContractViolationError(f"Worthiness.band must be a RiskBand, got {self.band!r}")
        for name in ("active_deal_count", "active_project_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ContractViolationError(
                    f"Worthiness.{name} must be a count of at least 0, got {value!r}"
                )

    @property
    def executive_worthy(self) -> bool:
        """§A15: band >= ELEVATED and (S11 > 0 or S13 > 0)."""
        return self.band.at_least(WORTHINESS_BAND) and (
            self.active_deal_count > 0 or self.active_project_count > 0
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "band": str(self.band),
            "active_deal_count": self.active_deal_count,
            "active_project_count": self.active_project_count,
            "executive_worthy": self.executive_worthy,
        }


@dataclass(frozen=True)
class Reconciliation:
    """
    One customer's reconciled decision: the M6 -> M7 seam.

    Stored: what was decided. Derived: everything that follows from it.

        customer            the customer both contexts name
        policy_version      the decision configuration's one version
        ordered_positions   every position both analysts emitted, each once
                            and unmodified, in §0.4.1's order -- prevailing,
                            uncontested and overruled alike
        resolutions         one per detected conflict, ascending by object
        worthiness          §A15's executive-worthiness and its inputs
        ranking_key         §A15's order for this customer
        conflicts           (derived) the conflict each resolution resolved
        dissent             (derived) every overruled position, whole
        resolved_positions  (derived) ordered_positions minus the dissent:
                            §A17's "resolved action set", as positions
        policy_ids          (derived) the rules applied, in resolution order
    """

    customer: EntityRef
    policy_version: int
    ordered_positions: tuple[Position, ...]
    resolutions: tuple[ConflictResolution, ...]
    worthiness: Worthiness
    ranking_key: RankingKey

    def __post_init__(self) -> None:
        for name in ("ordered_positions", "resolutions", "ranking_key"):
            if not isinstance(getattr(self, name), tuple):
                raise ContractViolationError(f"Reconciliation.{name} must be a tuple")
        if (isinstance(self.policy_version, bool) or not isinstance(self.policy_version, int)
                or self.policy_version < 1):
            raise ContractViolationError(
                f"Reconciliation.policy_version must be an integer of at least 1, "
                f"got {self.policy_version!r}"
            )
        identities = [position_identity(position) for position in self.ordered_positions]
        if (self.ordered_positions != order_positions(self.ordered_positions)
                or len(set(identities)) != len(identities)):
            raise ContractViolationError(
                "Reconciliation.ordered_positions must be in §0.4.1's order with no position "
                "stated twice"
            )
        objects = [resolution.conflict.object_ref for resolution in self.resolutions]
        if objects != sorted(set(objects)):
            raise ContractViolationError(
                "Reconciliation.resolutions must be one per object, ascending by object_ref"
            )
        for resolution in self.resolutions:
            for position in resolution.conflict.positions:
                if position not in self.ordered_positions:
                    raise ContractViolationError(
                        f"{resolution.policy_id} resolved a {position.function} position on "
                        f"{position.object_ref} that this customer's analysts did not state"
                    )
        if (len(self.ranking_key) != 4 or self.ranking_key[3] != self.customer.source_id
                or self.ranking_key[0] != -self.worthiness.band.rank):
            raise ContractViolationError(
                f"Reconciliation.ranking_key {self.ranking_key!r} does not rank "
                f"{self.customer.source_id} at band {self.worthiness.band}"
            )

    @property
    def conflicts(self) -> tuple[Conflict, ...]:
        """Every detected conflict. Each is resolved, or no Reconciliation would exist."""
        return tuple(resolution.conflict for resolution in self.resolutions)

    @property
    def dissent(self) -> tuple[Position, ...]:
        """Every overruled position, preserved whole with its own evidence, in position order."""
        overruled = tuple(
            position for resolution in self.resolutions for position in resolution.dissent
        )
        return tuple(position for position in self.ordered_positions if position in overruled)

    @property
    def resolved_positions(self) -> tuple[Position, ...]:
        """
        The positions that survive reconciliation: every one emitted, minus the dissent.

        Positions, not action ids -- an action id alone loses the object it
        contests. Every position that took part in no conflict remains.
        """
        overruled = self.dissent
        return tuple(
            position for position in self.ordered_positions if position not in overruled
        )

    @property
    def policy_ids(self) -> tuple[str, ...]:
        """The rules applied, in resolution order. Empty when nothing conflicted."""
        return tuple(resolution.policy_id for resolution in self.resolutions)

    def to_payload(self) -> dict[str, object]:
        """
        A deterministic projection through the frozen M1 payloads.

        Not §A17's hashed decision payload, which is M7's to assemble.
        """
        return {
            "customer": self.customer.to_payload(),
            "policy_version": self.policy_version,
            "ordered_positions": [position.to_payload() for position in self.ordered_positions],
            "conflicts": [conflict.to_payload() for conflict in self.conflicts],
            "resolutions": [resolution.to_payload() for resolution in self.resolutions],
            "resolved_positions": [
                position.to_payload() for position in self.resolved_positions
            ],
            "dissent": [position.to_payload() for position in self.dissent],
            "worthiness": self.worthiness.to_payload(),
            "ranking_key": list(self.ranking_key),
        }


def reconcile(
    contexts: AnalystContexts, *, policy: ConflictPolicy | None = None
) -> Reconciliation:
    """
    One customer's positions, conflicts, resolutions, worthiness and rank.

    The policy defaults to the repository's, matching how build_contexts and
    compute_signals default their configuration.
    """
    rules = policy if policy is not None else default_conflict_policy()
    support, commercial = contexts.support, contexts.commercial
    if support.customer != commercial.customer or support.band != commercial.band:
        raise ReconciliationError(
            f"the two contexts disagree: Support sees {support.customer.source_id} at "
            f"{support.band}, Sales sees {commercial.customer.source_id} at {commercial.band}"
        )
    customer = support.customer
    band = RiskBand(support.band)
    positions = checked_positions(
        SupportRiskAnalyst(context=support).positions()
        + CommercialAnalyst(context=commercial).positions(),
        rules.catalogue,
    )
    resolutions = tuple(
        _resolve(
            conflict,
            rules,
            customer=customer.source_id,
            band=band,
            open_sla_breach_high_count=support.signals.open_sla_breach_high_count,
        )
        for conflict in detect_conflicts(positions, rules)
    )
    return Reconciliation(
        customer=customer,
        policy_version=rules.policy_version,
        ordered_positions=positions,
        resolutions=resolutions,
        worthiness=Worthiness(
            band=band,
            active_deal_count=commercial.signals.active_deal_count,
            active_project_count=commercial.signals.active_project_count,
        ),
        ranking_key=ranking_key(
            customer.source_id,
            BandAssignment(band=support.band, satisfied_rules=support.satisfied_rules),
            commercial.signals,
        ),
    )


def resolution_evidence(rule: ConflictRule) -> tuple[Evidence, ...]:
    """
    The grounds a rule is cited from: one canonical fact per document, by id.

    M1 validates both halves at construction -- `documents` is a canonical
    entity and `body_text` a citable business field of it -- so a citation a
    reviewer could not look up cannot be built. The ids are already ascending.
    """
    return tuple(
        Evidence(
            kind=EvidenceKind.CANONICAL_FACT,
            citation=RecordCitation(
                entity_type=DOCUMENTS, source_id=document, field_name=POLICY_TEXT_FIELD
            ),
        )
        for document in rule.because_documents
    )


def order_reconciliations(
    reconciliations: Iterable[Reconciliation],
) -> tuple[Reconciliation, ...]:
    """
    Customers in §A15's order: band desc, S8 desc, S4 desc, source_id asc.

    Total, because source_id is the last term and a customer may appear only
    once. Money is never a term, and neither is the order the results arrive
    in. Results reconciled under different policy versions are not one run
    and are not ranked together.
    """
    results = tuple(reconciliations)
    customers = [result.customer.source_id for result in results]
    repeated = sorted({customer for customer in customers if customers.count(customer) > 1})
    if repeated:
        raise ReconciliationError(f"customers reconciled more than once: {repeated}")
    versions = sorted({result.policy_version for result in results})
    if len(versions) > 1:
        raise ReconciliationError(
            f"reconciliations from policy versions {versions} cannot be ranked as one run"
        )
    return tuple(sorted(results, key=lambda result: result.ranking_key))


def _resolve(
    conflict: Conflict,
    policy: ConflictPolicy,
    *,
    customer: str,
    band: RiskBand,
    open_sla_breach_high_count: int,
) -> ConflictResolution:
    """
    The conflict's one candidate rule, applied -- or an UnresolvableConflictError.

    The prevailing position is the conflict's own position proposing the
    rule's `resolve_to`; the other is dissent, which ConflictResolution
    derives rather than stores.
    """
    first, second = conflict.proposed_actions
    rule = policy.rule_for(first, second)
    failures = rule.when.failures(
        band=band, open_sla_breach_high_count=open_sla_breach_high_count
    )
    if failures:
        raise UnresolvableConflictError(
            f"{customer}: the conflict over {conflict.object_ref} between {first} and "
            f"{second} is unresolvable -- {rule.rule_id} does not apply: "
            f"{'; '.join(failures)}. No default winner is chosen and no partial result is "
            f"returned",
            object_ref=conflict.object_ref,
            actions=(first, second),
            rule_id=rule.rule_id,
        )
    prevailing = next(
        position for position in conflict.positions
        if position.proposed_action is rule.resolve_to
    )
    return ConflictResolution(
        policy_id=rule.rule_id,
        conflict=conflict,
        prevailing=prevailing,
        rationale=rule.rationale,
        evidence=resolution_evidence(rule),
    )
