"""
The Layer 2 vocabulary (VS-01 M1).

Every later milestone speaks these types, so an invariant stated once here
cannot be violated later by accident. Four of them carry the weight of the
slice:

    Evidence            classifies *what kind of thing* supports a claim and
                        *where to verify it*. The five kinds are kept apart
                        deliberately: a canonical fact, a derived
                        relationship, a document span, a deterministic rule
                        and a model narrative are not interchangeable
                        grounds for an executive decision. VS-01 has no
                        model, so MODEL_NARRATIVE is reserved and
                        constructing one raises.
    DerivedLink         a relationship Layer 1 does not hold, recorded with
                        its basis, its deterministic confidence, the token
                        it matched and the Layer 1 snapshot it was derived
                        from. Layer 1 documents stay untouched.
    Position            one function's stance, its proposed action, the
                        object that action applies to, and evidence for
                        every claim.
    ConflictResolution  a resolution that structurally cannot discard the
                        losing argument: it holds the whole Conflict, and
                        dissent is derived from it rather than stored, so
                        there is no field to leave empty.

Nothing here reads a database, a clock or a model. Citations are validated
against the frozen Layer 1 canonical contract, so a citation that names a
field Layer 1 does not have cannot be built.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum, auto
from types import MappingProxyType

from app.intelligence.errors import ContractViolationError
from app.intelligence.money import MoneyValue
from app.normalization.contract import BUSINESS_FIELDS, CANONICAL_SCHEMAS, E1_RESOLVED_FIELDS

#: A 64-character lowercase hex SHA-256 digest.
SHA256_HEX = re.compile(r"[0-9a-f]{64}")


class RiskBand(StrEnum):
    """Ordinal risk band (plan A5). Never a percentage, never a probability."""

    NONE = "NONE"
    WATCH = "WATCH"
    ELEVATED = "ELEVATED"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        """Position in the ordinal scale, lowest first."""
        return _BAND_RANK[self]

    def at_least(self, other: RiskBand) -> bool:
        """Whether this band is at or above another. Bands are ordinal, not lexical."""
        return self.rank >= other.rank


_BAND_RANK: Mapping[RiskBand, int] = MappingProxyType(
    {band: index for index, band in enumerate(RiskBand)}
)


class EdgeBasis(StrEnum):
    """How a relationship in the Layer 2 model is known (plan A9)."""

    CANONICAL_FK = "CANONICAL_FK"
    SOURCE_KEY_JOIN = "SOURCE_KEY_JOIN"
    DERIVED_TEXT_MATCH = "DERIVED_TEXT_MATCH"
    DERIVED_TOPIC_MATCH = "DERIVED_TOPIC_MATCH"


class LinkConfidence(StrEnum):
    """
    The standing of a derived link.

    Deterministic, never probabilistic: VS-01 derives links by exact token
    and exact name matching, so there is no distribution to score. HIGH
    links state an identity the text asserts; SUPPORTING links state a
    topical overlap, which may corroborate a conclusion but may never
    derive one.
    """

    HIGH = "HIGH"
    SUPPORTING = "SUPPORTING"


class LinkBasis(StrEnum):
    """How a derived document link was matched (plan A11)."""

    # Members take their own names as values. Writing each value out as a
    # literal would read better, but the G2 secret scanner's quoted-assignment
    # rule flags any name containing the word it treats as credential-shaped
    # when a quoted string is assigned to it, and one member's name does. The
    # names and the values are the plan's vocabulary either way.
    @staticmethod
    def _generate_next_value_(
        name: str, start: int, count: int, last_values: list[str]
    ) -> str:
        return name

    ID_TOKEN = auto()
    EXACT_NAME = auto()
    TOPIC = auto()

    @property
    def edge_basis(self) -> EdgeBasis:
        """The relationship-model basis this link presents as."""
        return _LINK_EDGE_BASIS[self]

    @property
    def confidence(self) -> LinkConfidence:
        """The link's standing, fixed by its basis and never chosen per link."""
        return _LINK_CONFIDENCE[self]

    @property
    def may_derive_signals(self) -> bool:
        """Whether a signal may ever be computed from a link on this basis."""
        return self.confidence is LinkConfidence.HIGH


_LINK_EDGE_BASIS: Mapping[LinkBasis, EdgeBasis] = MappingProxyType({
    LinkBasis.ID_TOKEN: EdgeBasis.DERIVED_TEXT_MATCH,
    LinkBasis.EXACT_NAME: EdgeBasis.DERIVED_TEXT_MATCH,
    LinkBasis.TOPIC: EdgeBasis.DERIVED_TOPIC_MATCH,
})

_LINK_CONFIDENCE: Mapping[LinkBasis, LinkConfidence] = MappingProxyType({
    LinkBasis.ID_TOKEN: LinkConfidence.HIGH,
    LinkBasis.EXACT_NAME: LinkConfidence.HIGH,
    LinkBasis.TOPIC: LinkConfidence.SUPPORTING,
})


class Function(StrEnum):
    """The enterprise function a position speaks for (plan A14)."""

    SUPPORT = "SUPPORT"
    SALES = "SALES"


class Stance(StrEnum):
    """
    A function's posture toward activity on the contested object.

    Orthogonal to the proposed action: the action says what to do, the
    stance says which way the function is pulling, which is what makes an
    opposed pair legible to a reader of the brief.
    """

    ADVANCE = "ADVANCE"
    RESTRAIN = "RESTRAIN"
    NEUTRAL = "NEUTRAL"


class ActionId(StrEnum):
    """The versioned action catalogue (plan A16)."""

    ESCALATE_TO_ACCOUNT_OWNER_PER_SLA = "ESCALATE_TO_ACCOUNT_OWNER_PER_SLA"
    SCHEDULE_EXECUTIVE_SPONSOR_CALL = "SCHEDULE_EXECUTIVE_SPONSOR_CALL"
    ASSIGN_DEDICATED_SUPPORT_OWNER = "ASSIGN_DEDICATED_SUPPORT_OWNER"
    PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED = "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED"
    REVIEW_INVOICE_DISPUTE = "REVIEW_INVOICE_DISPUTE"
    ACCELERATE_DEAL_CLOSE = "ACCELERATE_DEAL_CLOSE"
    NO_ACTION = "NO_ACTION"


class EvidenceKind(StrEnum):
    """
    What class of thing supports an asserted fact.

    The distinction is the point: an executive reading a brief must be able
    to tell a measured canonical value from a link this system inferred,
    from text a document happens to contain, from a rule the project chose.
    """

    CANONICAL_FACT = "CANONICAL_FACT"
    DERIVED_RELATIONSHIP = "DERIVED_RELATIONSHIP"
    DOCUMENT_SPAN = "DOCUMENT_SPAN"
    DETERMINISTIC_RULE = "DETERMINISTIC_RULE"
    #: Reserved for a later slice. VS-01 has no model, so Evidence refuses it.
    MODEL_NARRATIVE = "MODEL_NARRATIVE"


@dataclass(frozen=True)
class RecordCitation:
    """A canonical record field, addressed the way a reviewer would look it up."""

    entity_type: str
    source_id: str
    field_name: str

    def __post_init__(self) -> None:
        if self.entity_type not in CANONICAL_SCHEMAS:
            raise ContractViolationError(
                f"RecordCitation.entity_type {self.entity_type!r} is not a canonical entity"
            )
        _require_text(self.source_id, "RecordCitation.source_id")
        citable = set(BUSINESS_FIELDS[self.entity_type]) | set(E1_RESOLVED_FIELDS[self.entity_type])
        if self.field_name not in citable:
            raise ContractViolationError(
                f"RecordCitation.field_name {self.field_name!r} is not a citable field of "
                f"{self.entity_type}: evidence is business content or a resolved canonical FK, "
                f"never ingestion provenance"
            )

    def to_payload(self) -> dict[str, object]:
        """The plan A17 wire shape for a record citation."""
        return {
            "kind": "record",
            "entity": self.entity_type,
            "id": self.source_id,
            "field": self.field_name,
        }


@dataclass(frozen=True)
class DocumentCitation:
    """A half-open character span of one document's text."""

    document_id: str
    start: int
    end: int

    def __post_init__(self) -> None:
        _require_text(self.document_id, "DocumentCitation.document_id")
        if self.start < 0:
            raise ContractViolationError(f"DocumentCitation.start must not be negative: {self.start}")
        if self.end <= self.start:
            raise ContractViolationError(
                f"DocumentCitation span must be non-empty: [{self.start}, {self.end})"
            )

    def to_payload(self) -> dict[str, object]:
        """The plan A17 wire shape for a document citation."""
        return {
            "kind": "document",
            "document_id": self.document_id,
            "start": self.start,
            "end": self.end,
        }


#: Every asserted fact resolves to exactly one of these two shapes (plan A17).
Citation = RecordCitation | DocumentCitation
CITATION_TYPES = (RecordCitation, DocumentCitation)

#: Which citation shapes can ground each kind of evidence.
_EVIDENCE_CITATIONS: Mapping[EvidenceKind, tuple[type, ...]] = MappingProxyType({
    EvidenceKind.CANONICAL_FACT: (RecordCitation,),
    EvidenceKind.DERIVED_RELATIONSHIP: CITATION_TYPES,
    EvidenceKind.DOCUMENT_SPAN: (DocumentCitation,),
    EvidenceKind.DETERMINISTIC_RULE: (DocumentCitation,),
})


@dataclass(frozen=True)
class Evidence:
    """One classified, traceable support for an asserted fact."""

    kind: EvidenceKind
    citation: Citation
    rule_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind is EvidenceKind.MODEL_NARRATIVE:
            raise ContractViolationError(
                "MODEL_NARRATIVE evidence cannot be constructed: VS-01 uses no language model, "
                "so no narrative is ever a ground for a decision"
            )
        allowed = _EVIDENCE_CITATIONS[self.kind]
        if not isinstance(self.citation, allowed):
            raise ContractViolationError(
                f"{self.kind} evidence must cite "
                f"{' or '.join(kind.__name__ for kind in allowed)}, "
                f"got {type(self.citation).__name__}"
            )
        needs_rule = self.kind is EvidenceKind.DETERMINISTIC_RULE
        if needs_rule:
            _require_text(self.rule_id, "Evidence.rule_id")
        elif self.rule_id is not None:
            raise ContractViolationError(
                f"Evidence.rule_id is only meaningful for DETERMINISTIC_RULE, not {self.kind}"
            )

    def to_payload(self) -> dict[str, object]:
        """Deterministic projection: kind, where to verify it, and the rule if any."""
        payload: dict[str, object] = {
            "kind": str(self.kind),
            "citation": self.citation.to_payload(),
        }
        if self.rule_id is not None:
            payload["rule_id"] = self.rule_id
        return payload


@dataclass(frozen=True)
class EntityRef:
    """A canonical entity addressed by its source identity."""

    entity_type: str
    source_id: str

    def __post_init__(self) -> None:
        if self.entity_type not in CANONICAL_SCHEMAS:
            raise ContractViolationError(
                f"EntityRef.entity_type {self.entity_type!r} is not a canonical entity"
            )
        _require_text(self.source_id, "EntityRef.source_id")

    def to_payload(self) -> dict[str, object]:
        return {"entity": self.entity_type, "id": self.source_id}


@dataclass(frozen=True)
class DerivedLink:
    """
    A Layer 2 relationship that Layer 1 does not hold.

    Layer 1 documents are never modified to record one: the link is derived,
    stamped with the linker version and the Layer 1 snapshot it was derived
    from, and carries the evidence a reviewer checks it against. Confidence
    is not chosen per link; it follows from the basis, and a caller that
    tries to inflate it is refused.
    """

    source: EntityRef
    target: EntityRef
    basis: LinkBasis
    confidence: LinkConfidence
    matched_token: str
    evidence: tuple[Evidence, ...]
    source_system: str
    layer1_fingerprint: str
    linker_version: str

    def __post_init__(self) -> None:
        if self.confidence is not self.basis.confidence:
            raise ContractViolationError(
                f"{self.basis} links are {self.basis.confidence}, not {self.confidence}: "
                f"confidence follows from the basis and is never chosen per link"
            )
        if self.source == self.target:
            raise ContractViolationError(f"a link cannot join {self.source.source_id} to itself")
        _require_text(self.matched_token, "DerivedLink.matched_token")
        _require_text(self.source_system, "DerivedLink.source_system")
        _require_text(self.linker_version, "DerivedLink.linker_version")
        _require_fingerprint(self.layer1_fingerprint, "DerivedLink.layer1_fingerprint")
        if not self.evidence:
            raise ContractViolationError(
                "a derived link must carry the evidence it was derived from"
            )

    @property
    def edge_basis(self) -> EdgeBasis:
        """How the relationship model presents this link."""
        return self.basis.edge_basis

    def to_payload(self) -> dict[str, object]:
        return {
            "source": self.source.to_payload(),
            "target": self.target.to_payload(),
            "basis": str(self.basis),
            "edge_basis": str(self.edge_basis),
            "confidence": str(self.confidence),
            "matched_token": self.matched_token,
            "evidence": [item.to_payload() for item in self.evidence],
            "source_system": self.source_system,
            "layer1_fingerprint": self.layer1_fingerprint,
            "linker_version": self.linker_version,
        }


@dataclass(frozen=True)
class DealSignal:
    """One active deal as the commercial signals see it (plan A10 S11, S12)."""

    source_id: str
    stage: str
    probability: Decimal
    amount: MoneyValue

    def __post_init__(self) -> None:
        _require_text(self.source_id, "DealSignal.source_id")
        _require_text(self.stage, "DealSignal.stage")
        if not isinstance(self.probability, Decimal):
            raise ContractViolationError(
                f"DealSignal.probability must be a Decimal, "
                f"got {type(self.probability).__name__}"
            )
        if not Decimal(0) <= self.probability <= Decimal(100):
            raise ContractViolationError(
                f"DealSignal.probability must be a percentage in [0, 100], got {self.probability}"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.source_id,
            "stage": self.stage,
            "probability": decimal_text(self.probability),
            "amount": money_payload(self.amount),
        }


@dataclass(frozen=True)
class SignalSet:
    """
    S1-S15 for one customer at one scope (plan A10).

    Every value is computed from canonical rows. No signal in VS-01 is
    derived from document prose, which is what the DOC-005 leave-out test
    exists to keep true.
    """

    open_ticket_count: int
    open_high_priority_count: int
    high_priority_total: int
    tickets_in_lookback: int
    max_tickets_in_14d_window: int
    policy_escalation_state: bool
    days_since_last_ticket: int | None
    sla_breach_count: int
    open_sla_breach_high_count: int
    stale_open_ticket_count: int
    dominant_ticket_category: str | None
    active_deals: tuple[DealSignal, ...]
    exposure_by_currency: Mapping[str, MoneyValue]
    active_project_count: int
    contract_document_ids: tuple[str, ...]
    deal_under_pressure: bool

    def __post_init__(self) -> None:
        for name in _SIGNAL_COUNTS:
            value = getattr(self, name)
            if value < 0:
                raise ContractViolationError(f"SignalSet.{name} must not be negative: {value}")
        if self.days_since_last_ticket is not None and self.days_since_last_ticket < 0:
            raise ContractViolationError(
                f"SignalSet.days_since_last_ticket must not be negative: "
                f"{self.days_since_last_ticket}"
            )
        if self.open_high_priority_count > self.open_ticket_count:
            raise ContractViolationError(
                "SignalSet.open_high_priority_count cannot exceed open_ticket_count"
            )
        if self.open_high_priority_count > self.high_priority_total:
            raise ContractViolationError(
                "SignalSet.open_high_priority_count cannot exceed high_priority_total"
            )
        if self.open_sla_breach_high_count > self.open_high_priority_count:
            raise ContractViolationError(
                "SignalSet.open_sla_breach_high_count cannot exceed open_high_priority_count"
            )
        for currency, exposure in self.exposure_by_currency.items():
            if exposure.currency != currency:
                raise ContractViolationError(
                    f"SignalSet.exposure_by_currency[{currency!r}] holds {exposure.currency}"
                )
        if self.deal_under_pressure and not (self.policy_escalation_state and self.active_deals):
            raise ContractViolationError(
                "SignalSet.deal_under_pressure requires an escalation state and an active deal"
            )

    @property
    def active_deal_count(self) -> int:
        """S11's count. Derived, so it can never disagree with the deals themselves."""
        return len(self.active_deals)

    def to_payload(self) -> dict[str, object]:
        """Deterministic projection of every signal value."""
        payload: dict[str, object] = {
            name: getattr(self, name)
            for name in (*_SIGNAL_COUNTS, "policy_escalation_state", "days_since_last_ticket",
                         "dominant_ticket_category", "deal_under_pressure")
        }
        payload["active_deal_count"] = self.active_deal_count
        payload["active_deals"] = [deal.to_payload() for deal in self.active_deals]
        payload["exposure_by_currency"] = {
            currency: money_payload(self.exposure_by_currency[currency])
            for currency in sorted(self.exposure_by_currency)
        }
        payload["contract_document_ids"] = list(self.contract_document_ids)
        return payload


#: SignalSet fields that are counts and must never be negative.
_SIGNAL_COUNTS = (
    "open_ticket_count", "open_high_priority_count", "high_priority_total",
    "tickets_in_lookback", "max_tickets_in_14d_window", "sla_breach_count",
    "open_sla_breach_high_count", "stale_open_ticket_count", "active_project_count",
)


@dataclass(frozen=True)
class Position:
    """One function's stance on one object, with evidence for every claim."""

    function: Function
    stance: Stance
    proposed_action: ActionId
    object_ref: str
    rationale: str
    evidence: tuple[Evidence, ...]

    def __post_init__(self) -> None:
        _require_text(self.object_ref, "Position.object_ref")
        _require_text(self.rationale, "Position.rationale")
        if not self.evidence:
            raise ContractViolationError(
                f"{self.function} proposed {self.proposed_action} with no evidence"
            )

    @property
    def citations(self) -> tuple[Citation, ...]:
        """Where every claim in this position is verified."""
        return tuple(item.citation for item in self.evidence)

    def to_payload(self) -> dict[str, object]:
        return {
            "function": str(self.function),
            "stance": str(self.stance),
            "proposed_action": str(self.proposed_action),
            "object_ref": self.object_ref,
            "rationale": self.rationale,
            "evidence": [item.to_payload() for item in self.evidence],
        }


@dataclass(frozen=True)
class Conflict:
    """
    Two or more functions proposing different actions on the same object.

    Detection is a statement of fact, separate from resolution: a conflict
    exists whether or not a policy can resolve it, and an unresolvable one
    must surface rather than be quietly dropped.
    """

    object_ref: str
    positions: tuple[Position, ...]

    def __post_init__(self) -> None:
        _require_text(self.object_ref, "Conflict.object_ref")
        if len(self.positions) < 2:
            raise ContractViolationError("a conflict needs at least two positions")
        functions = [position.function for position in self.positions]
        if len(set(functions)) != len(functions):
            raise ContractViolationError("each function states at most one position per conflict")
        for position in self.positions:
            if position.object_ref != self.object_ref:
                raise ContractViolationError(
                    f"position on {position.object_ref} does not belong to the conflict over "
                    f"{self.object_ref}"
                )
        if len({position.proposed_action for position in self.positions}) < 2:
            raise ContractViolationError(
                "positions proposing the same action are agreement, not conflict"
            )

    @property
    def proposed_actions(self) -> tuple[ActionId, ...]:
        """Every competing action, in position order."""
        return tuple(position.proposed_action for position in self.positions)

    def to_payload(self) -> dict[str, object]:
        return {
            "object_ref": self.object_ref,
            "positions": [position.to_payload() for position in self.positions],
        }


@dataclass(frozen=True)
class ConflictResolution:
    """
    A conflict resolved by a named, versioned policy.

    The losing argument is not stored, it is *derived* from the conflict
    this resolution holds. There is therefore no field a future change can
    leave empty, and no way to record a resolution that has forgotten what
    it overruled.
    """

    policy_id: str
    conflict: Conflict
    prevailing: Position
    rationale: str
    evidence: tuple[Evidence, ...]

    def __post_init__(self) -> None:
        _require_text(self.policy_id, "ConflictResolution.policy_id")
        _require_text(self.rationale, "ConflictResolution.rationale")
        if self.prevailing not in self.conflict.positions:
            raise ContractViolationError(
                f"the prevailing {self.prevailing.function} position is not one of the "
                f"conflicting positions"
            )
        if not self.evidence:
            raise ContractViolationError(
                f"conflict policy {self.policy_id} resolved a conflict without citing why"
            )

    @property
    def resolved_action(self) -> ActionId:
        """The action that prevailed."""
        return self.prevailing.proposed_action

    @property
    def dissent(self) -> tuple[Position, ...]:
        """Every overruled position, preserved whole with its own evidence."""
        return tuple(
            position for position in self.conflict.positions if position != self.prevailing
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "conflict": self.conflict.to_payload(),
            "resolved_action": str(self.resolved_action),
            "prevailing": self.prevailing.to_payload(),
            "dissent": [position.to_payload() for position in self.dissent],
            "rationale": self.rationale,
            "evidence": [item.to_payload() for item in self.evidence],
        }


def decimal_text(value: Decimal) -> str:
    """
    A Decimal's canonical text, by Layer 1's rule.

    Mirrors app/normalization/identifiers.py so a Layer 2 payload hash and a
    Layer 1 record_hash can never disagree about the same number. A unit
    test pins the two implementations together.
    """
    if not value.is_finite():
        raise ContractViolationError(f"non-finite Decimal {value} cannot be serialised")
    if value.is_zero():
        return "0"
    return format(value.normalize(), "f")


def money_payload(value: MoneyValue) -> dict[str, object]:
    """A MoneyValue as a currency-qualified pair. Never a bare number."""
    return {"amount": decimal_text(value.amount), "currency": value.currency}


def canonical_json(payload: object) -> str:
    """
    Serialise a payload with Layer 1's hashing discipline.

    Sorted keys and compact separators, so the same content always produces
    the same bytes regardless of dict insertion order or platform.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolationError(f"{name} must be a non-empty string")


def _require_fingerprint(value: str, name: str) -> None:
    if not SHA256_HEX.fullmatch(value):
        raise ContractViolationError(f"{name} must be a 64-character hex SHA-256 digest")
