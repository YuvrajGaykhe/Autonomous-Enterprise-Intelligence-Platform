"""
The shared analyst abstraction and §A16's precondition thresholds (VS-01 M5).

**This module imports neither Session nor any ORM model**, and neither does
either analyst module. An analyst is constructed with a pre-built, typed
context and is never given a database, so scope is enforced by construction
rather than by convention (§A14, §0.4.5).

**One Position per satisfied catalogue entry.** §0.4.1 settles the shape that
earlier drafts read as a contradiction: `Position` is one per function *per
contested object*, not one per function. An analyst emits every entry it
satisfies, each carrying that entry's contested object in `object_ref`.
Nothing is discarded, nothing is ranked and no action is selected over
another -- choosing is M6's, by policy, and only between positions sharing an
object. `NO_ACTION` is emitted by neither analyst: §A16 leaves its *Proposed
by* column empty, so a function with no satisfied entry emits the empty
tuple, which is the representation of "this function has nothing to say".

**Ordering is a sort key, never a priority.** `order_positions` sorts ascending
by `(function, object_ref, proposed_action)`, all three compared as strings.
§A24 requires the determinism; the key itself expresses no precedence, and no
rule in M5 reads it to choose a winner. It mirrors the discipline already
frozen for S14 (§0.3.6) and M2's queries.

**Thresholds are named constants, not configuration.** §A16 is a *versioned
config* catalogue, but `action_catalogue.yaml` is M6's and M5 may add no
configuration key (§0.4.8). Until M6 loads the catalogue, the three numbers
§A16 states live here as named constants so no literal is buried in a
predicate, and each one's docstring says which entry reads it.

**Evidence: canonical facts, cited field by field.** §0.4.8 criterion 14
requires every Position to validate and carry at least one Evidence, and every
citation to resolve. The grounds M5 has are canonical rows -- the ticket and
deal values its preconditions actually read -- so every position here carries
`CANONICAL_FACT` evidence over `RecordCitation`s naming those exact fields,
which resolve against Layer 1 by construction. Two deliberate omissions, so
neither reads as an oversight:

  * **No DOCUMENT_SPAN or DETERMINISTIC_RULE evidence.** Both require a
    DocumentCitation, which is a character span, and a span can only come
    from reading a document's text. §0.4.7 fixes what the factory reads, and
    resolving a span is not among its steps; an analyst has no session at
    all. DOC-003 still reaches Support -- as `escalation.because_documents`
    and M2's `policy_documents()` -- so the milestone that renders and cites
    the policy structurally (§A13, §7.3) has what it needs.
  * **`SCHEDULE_EXECUTIVE_SPONSOR_CALL` cites tickets only.** Its second term
    is `has_active_deal`, a boolean carrying no identity, so there is no deal
    row for Support to cite. Citing `contested_deal` instead would ground the
    claim in a *negotiation* deal the rule does not ask about, reintroducing
    the narrowing §0.4.9 D-M5-B9 corrected.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from app.intelligence.contract import (
    ActionId,
    Evidence,
    EvidenceKind,
    Function,
    Position,
    RecordCitation,
    Stance,
)

#: §A16, ACCELERATE_DEAL_CLOSE: "probability >= 80". A Decimal because
#: DealSignal.probability is one, and comparing a Decimal to a float is the
#: kind of silent coercion a percentage threshold should not depend on.
ACCELERATE_PROBABILITY_THRESHOLD = Decimal(80)

#: §A16, ASSIGN_DEDICATED_SUPPORT_OWNER: "S8 >= 2".
DEDICATED_OWNER_BREACH_THRESHOLD = 2

#: §A16, PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED: "S8 >= 1".
PAUSE_BREACH_THRESHOLD = 1

#: The stance every entry carries but the contested pair, where stance is what
#: makes the opposition legible to a reader of the brief (§0.4.1).
DEFAULT_STANCE = Stance.NEUTRAL

#: Layer 1 entity types the citations below address.
CUSTOMERS = "customers"
SUPPORT_TICKETS = "support_tickets"
DEALS = "deals"


def canonical_fact(entity_type: str, source_id: str, field_name: str) -> Evidence:
    """
    One CANONICAL_FACT evidence over one citable field of one canonical row.

    M1 validates both halves: the entity type must be canonical and the field
    must be business content or a resolved canonical FK, never ingestion
    provenance. A citation naming a field a reviewer cannot look up therefore
    fails at construction rather than at rendering time.
    """
    return Evidence(
        kind=EvidenceKind.CANONICAL_FACT,
        citation=RecordCitation(
            entity_type=entity_type, source_id=source_id, field_name=field_name
        ),
    )


def order_positions(positions: Iterable[Position]) -> tuple[Position, ...]:
    """
    Positions ascending by (function, object_ref, proposed_action), as strings.

    Required by §A24 for reproducibility, and explicitly **not** a precedence:
    the order two positions come back in says nothing about which should win.
    """
    return tuple(
        sorted(
            positions,
            key=lambda position: (
                str(position.function),
                position.object_ref,
                str(position.proposed_action),
            ),
        )
    )


@dataclass(frozen=True)
class Analyst(ABC):
    """
    One enterprise function's reading of one pre-built context.

    Subclasses declare their `FUNCTION` and yield the entries they satisfy;
    the base stamps the function onto every position and applies §0.4.1's
    ordering, so neither analyst can disagree with the other about either.
    """

    FUNCTION: ClassVar[Function]

    def positions(self) -> tuple[Position, ...]:
        """
        Every §A16 entry this function satisfies, ordered and never ranked.

        An empty tuple is a complete answer: it means no entry was satisfied,
        not that evaluation failed and not that `NO_ACTION` was chosen.
        """
        return order_positions(self._proposals())

    @abstractmethod
    def _proposals(self) -> Iterable[Position]:
        """Yield one Position per satisfied entry, in any order."""

    def _position(
        self,
        action: ActionId,
        object_ref: str,
        rationale: str,
        evidence: Iterable[Evidence],
        *,
        stance: Stance = DEFAULT_STANCE,
    ) -> Position:
        """One position of this function's, with M1 validating every field."""
        return Position(
            function=self.FUNCTION,
            stance=stance,
            proposed_action=action,
            object_ref=object_ref,
            rationale=rationale,
            evidence=tuple(evidence),
        )
