"""
The hashed decision payload, and the cited-span targets (VS-01 M7, §0.6.7, §0.6.13.1-3).

The payload is what an approval binds to: twelve keys, every nested key, type
and list order fixed by §0.6.13.1, hashed as
`sha256(canonical_json(payload).encode("utf-8"))`. It is authoritative for
the narrative too: brief.py renders what is here and reads nothing else.

**Frozen projections are embedded as they emit.** `signals`, `reconciliation`,
`customer`, each `document_evidence` entry, `escalation_window`,
`escalation_path` and each ticket's and deal's own fields are the output of a
frozen M1-M6 `to_payload()`, and nothing inside them is added, removed,
renamed or reordered here.

**Derived facts carry their provenance** (§0.6.14 OPEN-M7-4). A stored field
is cited directly. A fact derived from records -- the four ticket counts, the
dominant category and the ticket span -- is stated with its rule, as fixed
ASCII text, and with the ids of the tickets that rule counts, never with a
citation to a field that does not store it. Every value is the context's,
which is authoritative (§0.6.4); a derivation whose tickets do not produce
that value raises ContractViolationError, because a payload may not state a
fact its own provenance contradicts.

**This module is pure.** It holds no session and reads no clock, and it
imports neither M2, M3 nor M4: the run reads the escalation window, the
backlog ids, the escalation path, the ticket dates and the links, and hands
them in as plain values. It states M3's 'high' literal itself, pinned to M3
by a test (DR22), and it imports no `datetime`: a ticket's creation date is
received as a value with a calendar date's ISO text and day number, which is
all the span arithmetic needs.

**The cited-span targets are declared here** (§0.6.8, §0.6.13.3). Locating a
phrase is a pure string search, and this module owns `cited_spans`. Refusing
a missing or repeated phrase is citation resolution, which is M4's error and
the run's to raise, so the search reports what it found and decides nothing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.analysts import AnalystContexts
from app.decisions import Reconciliation
from app.intelligence import RiskRulesConfig, Scope
from app.intelligence.contract import (
    Citation,
    DerivedLink,
    DocumentCitation,
    Evidence,
    EvidenceKind,
    RecordCitation,
    canonical_json,
)
from app.intelligence.errors import ContractViolationError
from app.intelligence.timeutil import closed_window

#: §0.6.13.1 item 12. Any change to this module's keys, shapes, orders, rule
#: texts or targets forces version 2.
PAYLOAD_VERSION = 1

#: M3's HIGH_PRIORITY, stated here because this module may not import M3
#: (DR22). Compared exactly and case-sensitively; a test pins the two.
HIGH_PRIORITY = "high"

#: Layer 1 entity types the payload's own citations address.
SUPPORT_TICKETS = "support_tickets"
DEALS = "deals"
DOCUMENTS = "documents"

#: Each ticket's and each deal's cited fields, in exactly this order (§0.6.13.1).
TICKET_EVIDENCE_FIELDS = ("created_at", "priority", "category", "resolved_at")
DEAL_EVIDENCE_FIELDS = ("is_active", "stage", "probability", "amount", "currency")

#: The rule texts, byte for byte (§0.6.13.1 item 6). ASCII, over the payload's
#: own field names, and hashed.
OPEN_TICKET_COUNT_RULE = "count of tickets where is_open"
OPEN_HIGH_PRIORITY_COUNT_RULE = "count of tickets where is_open and priority == 'high'"
HIGH_PRIORITY_TOTAL_RULE = "count of tickets where priority == 'high'"
OPEN_SLA_BREACH_HIGH_COUNT_RULE = (
    "count of tickets where is_open and priority == 'high' and breaches_sla"
)
DOMINANT_TICKET_CATEGORY_RULE = (
    "most frequent category among tickets where category is neither null nor empty and "
    "lookback.start <= created_date <= lookback.end; ties go to the smallest category name "
    "in code-point order"
)
TICKET_SPAN_RULE = (
    "tickets where escalation_window.start <= created_date <= escalation_window.end; "
    "ticket_span_days = (last_ticket_date - first_ticket_date).days"
)

#: The S10 derivation's fact name; it is always the last of the five.
DOMINANT_TICKET_CATEGORY = "dominant_ticket_category"


class CalendarDate(Protocol):
    """
    A ticket's UTC creation date, as this module needs one.

    Its ISO text is what the payload states and what every window comparison
    reads; its day number is what the elapsed-day arithmetic subtracts, which
    is exactly `(last - first).days` for a calendar date.
    """

    def isoformat(self) -> str: ...

    def toordinal(self) -> int: ...


@dataclass(frozen=True)
class SpanTarget:
    """One fixed statement located in one named document (§0.6.13.3)."""

    name: str
    document_id: str
    phrase: str


#: The three targets (§0.6.13.3), each the whole sentence stating its fact.
#: Every phrase is ASCII: DOC-006's apostrophe is U+0027 and DOC-009's dash
#: is U+002D. No offset appears here; the span is found in the text.
DOC_003_ESCALATION_RULE = SpanTarget(
    name="DOC_003_ESCALATION_RULE",
    document_id="DOC-003",
    phrase=(
        "Customers raising three or more tickets within 14 days are escalated to their "
        "account owner."
    ),
)
DOC_006_TERM_AND_NOTICE = SpanTarget(
    name="DOC_006_TERM_AND_NOTICE",
    document_id="DOC-006",
    phrase=(
        "Term: 36 months, renewing annually unless either party gives 90 days' written "
        "notice."
    ),
)
DOC_009_DEAL_LINKAGE = SpanTarget(
    name="DOC_009_DEAL_LINKAGE",
    document_id="DOC-009",
    phrase=(
        "The customer tied the Meridian Textiles - Seat Expansion decision (DEAL-001) to "
        "resolving them."
    ),
)

#: Every target, ascending by name.
SPAN_TARGETS = (DOC_003_ESCALATION_RULE, DOC_006_TERM_AND_NOTICE, DOC_009_DEAL_LINKAGE)


@dataclass(frozen=True)
class CountDerivation:
    """One ticket count, the rule that produces it, and the tickets it counts."""

    fact: str
    value: int
    rule: str
    ticket_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.value != len(self.ticket_ids):
            raise ContractViolationError(
                f"{self.fact} is {self.value}, but its rule counts {len(self.ticket_ids)} "
                f"tickets: the payload may not state a fact its provenance contradicts"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "fact": self.fact,
            "value": self.value,
            "rule": self.rule,
            "ticket_ids": list(self.ticket_ids),
        }


@dataclass(frozen=True)
class CategoryDerivation:
    """S10: the dominant category, the counts it is chosen from, and the tickets counted."""

    value: str | None
    lookback: tuple[str, str]
    category_counts: Mapping[str, int]
    ticket_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        counted = sum(self.category_counts.values())
        if counted != len(self.ticket_ids):
            raise ContractViolationError(
                f"{DOMINANT_TICKET_CATEGORY}'s category counts sum to {counted}, but it "
                f"counts {len(self.ticket_ids)} tickets"
            )
        winner = dominant_category(self.category_counts)
        if winner != self.value:
            raise ContractViolationError(
                f"{DOMINANT_TICKET_CATEGORY} is {self.value!r}, but its category counts "
                f"produce {winner!r}"
            )

    def to_payload(self) -> dict[str, object]:
        start, end = self.lookback
        return {
            "fact": DOMINANT_TICKET_CATEGORY,
            "value": self.value,
            "rule": DOMINANT_TICKET_CATEGORY_RULE,
            "lookback": {"start": start, "end": end},
            "category_counts": dict(sorted(self.category_counts.items())),
            "ticket_ids": list(self.ticket_ids),
        }


def dominant_category(category_counts: Mapping[str, int]) -> str | None:
    """
    The most frequent category, ties to the smallest name by code point; None when none.

    M3's S10 rule, stated over counts that are already filtered: the payload
    states the counts, so the winner is recomputed from them and checked.
    """
    if not category_counts:
        return None
    return min(category_counts, key=lambda name: (-category_counts[name], name))


def applicable_targets(
    reconciliation: Reconciliation, links: Sequence[DerivedLink]
) -> tuple[SpanTarget, ...]:
    """
    The targets whose document is cited under `reconciliation` or `document_evidence`.

    DR7, made exact in §0.6.13.3: a record citation of the document, whatever
    its field, or a document citation of it. A target whose document is not
    cited is neither searched for nor an error, which is what keeps another
    customer's documents out of this customer's brief (§A22).
    """
    cited = [
        document
        for value in _citation_values(
            [reconciliation.to_payload(), [link.to_payload() for link in links]]
        )
        for document in _cited_document(value)
    ]
    return tuple(target for target in SPAN_TARGETS if target.document_id in cited)


def first_occurrences(text: str, phrase: str) -> tuple[int, ...]:
    """
    Where a phrase starts in a text: none, one, or the first two (§0.6.13.3).

    The two-find algorithm, reported rather than judged. `()` is zero
    matches; one start means exactly one; two starts mean more than one. The
    second search begins one character after the first match, so an
    overlapping second occurrence is found too. Matching is exact and
    case-sensitive, with no normalisation of any kind.
    """
    start = text.find(phrase)
    if start == -1:
        return ()
    second = text.find(phrase, start + 1)
    return (start,) if second == -1 else (start, second)


def build_payload(
    *,
    scope: Scope,
    config: RiskRulesConfig,
    contexts: AnalystContexts,
    reconciliation: Reconciliation,
    links: Sequence[DerivedLink],
    spans: Mapping[str, DocumentCitation],
    created_dates: Mapping[str, CalendarDate],
    escalation_window: Mapping[str, object] | None,
    backlog_ticket_ids: Sequence[str],
    escalation_path: Mapping[str, object],
) -> dict[str, object]:
    """
    The decision payload of §0.6.13.1, exactly: twelve keys, none ever omitted.

    `links` are the customer's links under the assessment's own stamps;
    `spans` are the located cited spans by target name, and must name
    exactly the applicable targets. `created_dates` holds the UTC creation
    date of every visible ticket, `escalation_window` and `escalation_path`
    are M3's and M2's frozen projections, and `backlog_ticket_ids` is M3's
    tuple, all read by the run (§0.6.4).
    """
    expected = [target.name for target in applicable_targets(reconciliation, links)]
    if sorted(spans) != expected:
        raise ContractViolationError(
            f"cited spans {sorted(spans)} are not the applicable targets {expected}"
        )
    commercial = contexts.commercial
    return {
        "payload_version": PAYLOAD_VERSION,
        "scope": {
            "source_system": scope.source_system,
            "as_of": scope.as_of.isoformat(),
            "layer1_fingerprint": scope.layer1_fingerprint,
        },
        "versions": {
            "rules": config.rules_version,
            "linker": config.linker_version,
            "policy": reconciliation.policy_version,
        },
        "customer": reconciliation.customer.to_payload(),
        "band": commercial.band,
        "satisfied_rules": list(commercial.satisfied_rules),
        "signals": commercial.signals.to_payload(),
        "reconciliation": reconciliation.to_payload(),
        "document_evidence": [
            link.to_payload()
            for link in sorted(links, key=lambda link: (link.source.source_id, str(link.basis)))
        ],
        "cited_spans": [
            {"target": name, "citation": spans[name].to_payload()} for name in sorted(spans)
        ],
        "support_evidence": _support_evidence(
            scope, config, contexts, created_dates, escalation_window, backlog_ticket_ids,
            escalation_path,
        ),
        "commercial_evidence": {
            "deals": [
                {
                    **deal.to_payload(),
                    "evidence": [
                        _record_evidence(DEALS, deal.source_id, field)
                        for field in DEAL_EVIDENCE_FIELDS
                    ],
                }
                for deal in sorted(commercial.signals.active_deals, key=lambda deal: deal.source_id)
            ],
        },
    }


def payload_citations(payload: Mapping[str, object]) -> tuple[Citation, ...]:
    """
    Every distinct citation in a payload, ascending by canonical wire form (§0.6.9).

    A citation is every value under a key named `citation`, at any depth. Two
    are the same citation when their `canonical_json` is equal, so one that
    occurs in several sections counts once. The ascending order is what makes
    the first failure a resolver names deterministic.
    """
    found = {canonical_json(value): value for value in _citation_values(payload)}
    return tuple(_citation(found[wire]) for wire in sorted(found))


def payload_hash(payload: Mapping[str, object]) -> str:
    """§0.6.13.1 item 11: 64 lowercase hex characters over the canonical form."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _support_evidence(
    scope: Scope,
    config: RiskRulesConfig,
    contexts: AnalystContexts,
    created_dates: Mapping[str, CalendarDate],
    escalation_window: Mapping[str, object] | None,
    backlog_ticket_ids: Sequence[str],
    escalation_path: Mapping[str, object],
) -> dict[str, object]:
    """§0.6.13.1 item 6: exactly six keys."""
    facts = sorted(contexts.support.tickets, key=lambda fact: fact.source_id)
    created = {fact.source_id: created_dates[fact.source_id].isoformat() for fact in facts}
    return {
        "tickets": [
            {
                **fact.to_payload(),
                "created_date": created[fact.source_id],
                "evidence": [
                    _record_evidence(SUPPORT_TICKETS, fact.source_id, field)
                    for field in TICKET_EVIDENCE_FIELDS
                ],
            }
            for fact in facts
        ],
        "escalation_window": None if escalation_window is None else dict(escalation_window),
        "ticket_span": _ticket_span(contexts, created_dates, escalation_window),
        "backlog_ticket_ids": list(backlog_ticket_ids),
        "escalation_path": dict(escalation_path),
        "derivations": _derivations(scope, config, contexts, created),
    }


def _derivations(
    scope: Scope,
    config: RiskRulesConfig,
    contexts: AnalystContexts,
    created: Mapping[str, str],
) -> list[dict[str, object]]:
    """The five records, in §0.6.13.1's order, each value the context's."""
    facts = sorted(contexts.support.tickets, key=lambda fact: fact.source_id)
    signals = contexts.commercial.signals
    counts = (
        CountDerivation(
            fact="open_ticket_count",
            value=signals.open_ticket_count,
            rule=OPEN_TICKET_COUNT_RULE,
            ticket_ids=tuple(fact.source_id for fact in facts if fact.is_open),
        ),
        CountDerivation(
            fact="open_high_priority_count",
            value=signals.open_high_priority_count,
            rule=OPEN_HIGH_PRIORITY_COUNT_RULE,
            ticket_ids=tuple(
                fact.source_id for fact in facts
                if fact.is_open and fact.priority == HIGH_PRIORITY
            ),
        ),
        CountDerivation(
            fact="high_priority_total",
            value=signals.high_priority_total,
            rule=HIGH_PRIORITY_TOTAL_RULE,
            ticket_ids=tuple(
                fact.source_id for fact in facts if fact.priority == HIGH_PRIORITY
            ),
        ),
        CountDerivation(
            fact="open_sla_breach_high_count",
            value=signals.open_sla_breach_high_count,
            rule=OPEN_SLA_BREACH_HIGH_COUNT_RULE,
            ticket_ids=tuple(
                fact.source_id for fact in facts
                if fact.is_open and fact.priority == HIGH_PRIORITY and fact.breaches_sla
            ),
        ),
    )
    start, end = (day.isoformat() for day in closed_window(scope.as_of, config.lookback_days))
    counted = [
        fact for fact in facts
        if fact.category and start <= created[fact.source_id] <= end
    ]
    category_counts: dict[str, int] = {}
    for fact in counted:
        category = str(fact.category)
        category_counts[category] = category_counts.get(category, 0) + 1
    dominant = CategoryDerivation(
        value=signals.dominant_ticket_category,
        lookback=(start, end),
        category_counts=category_counts,
        ticket_ids=tuple(fact.source_id for fact in counted),
    )
    return [*(count.to_payload() for count in counts), dominant.to_payload()]


def _ticket_span(
    contexts: AnalystContexts,
    created_dates: Mapping[str, CalendarDate],
    escalation_window: Mapping[str, object] | None,
) -> dict[str, object] | None:
    """
    The burst the escalation window counts (§0.6.13.2), or None when there is no window.

    The tickets are M3's own window population: those created within
    `[start, end]`. ISO date text compares chronologically, so the window's
    bounds are compared as the payload states them. The span is elapsed days,
    not an inclusive count of dates: 08-18 to 08-27 is 9.
    """
    if escalation_window is None:
        return None
    start, end = str(escalation_window["start"]), str(escalation_window["end"])
    selected = [
        fact for fact in sorted(contexts.support.tickets, key=lambda fact: fact.source_id)
        if start <= created_dates[fact.source_id].isoformat() <= end
    ]
    if len(selected) != escalation_window["count"]:
        raise ContractViolationError(
            f"the escalation window counts {escalation_window['count']} tickets, but "
            f"{len(selected)} were created within it (DR16)"
        )
    dates = [created_dates[fact.source_id] for fact in selected]
    first = min(dates, key=lambda day: day.toordinal())
    last = max(dates, key=lambda day: day.toordinal())
    return {
        "ticket_ids": [fact.source_id for fact in selected],
        "ticket_count": len(selected),
        "first_ticket_date": first.isoformat(),
        "last_ticket_date": last.isoformat(),
        "ticket_span_days": last.toordinal() - first.toordinal(),
        "rule": TICKET_SPAN_RULE,
    }


def _record_evidence(entity_type: str, source_id: str, field_name: str) -> dict[str, object]:
    """One canonical fact, cited to the stored field that states it."""
    return Evidence(
        kind=EvidenceKind.CANONICAL_FACT,
        citation=RecordCitation(
            entity_type=entity_type, source_id=source_id, field_name=field_name
        ),
    ).to_payload()


def _citation_values(node: object) -> Iterator[Any]:
    """Every value under a key named `citation`, at any depth, in document order."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "citation":
                yield value
            else:
                yield from _citation_values(value)
    elif isinstance(node, list | tuple):
        for item in node:
            yield from _citation_values(item)


def _cited_document(value: Mapping[str, Any]) -> tuple[str, ...]:
    """The document a citation names, if it names one."""
    if value["kind"] == "document":
        return (value["document_id"],)
    if value["entity"] == DOCUMENTS:
        return (value["id"],)
    return ()


def _citation(value: Mapping[str, Any]) -> Citation:
    """Rebuild the M1 citation a wire form states; M1 validates it again on the way."""
    if value["kind"] == "record":
        return RecordCitation(
            entity_type=value["entity"], source_id=value["id"], field_name=value["field"]
        )
    return DocumentCitation(
        document_id=value["document_id"], start=value["start"], end=value["end"]
    )
