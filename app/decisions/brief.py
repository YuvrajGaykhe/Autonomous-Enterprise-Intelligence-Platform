"""
The narrative: a view of the decision payload, rendered and never hashed (VS-01 M7, §0.6.10).

**Inputs, structurally.** The payload mapping and the resolved text of its
cited spans, and nothing else. This module holds no session, reads no clock,
imports only M1's errors and the standard library, and reads one file: its
own template. A database fact absent from the payload therefore cannot reach
the narrative, and nothing here queries, counts, filters or re-derives a fact
the payload does not already state. Formatting money and choosing an absence
line are presentation, not derivation.

**The engine** is the standard library's `string.Template`, rendered with
`substitute`, never `safe_substitute`, so a placeholder with no value fails
rather than leaving `$name` in the text (DR9). `string.Template` has no
conditionals, so every list join and every absence line is composed here, and
`TEMPLATE_VERSION` covers every fixed string the narrative can contain,
whether it lives in templates/brief.txt or in this module (DR23). A `null` or
empty value a section renders becomes a fixed absence line, and no section is
ever omitted (DR24).

**Quoting** (§0.6.13.4). Every document-derived string -- a cited span's
resolved text and a link's matched token -- passes through `quote_span`: at
most `MAX_QUOTED_SPAN_CHARS` code points of the unescaped text, escaped with
`json.dumps(..., ensure_ascii=False)`, then `TRUNCATION_MARKER` after the
closing quote, where the document cannot forge it. No other string is quoted
or capped. Offsets are printed from the payload's citation, which indexes the
original citable text, so a truncated quote still shows its full span.

**Failure** (§0.6.13.5). `BriefRenderError` is raised for four conditions and
no others: an unreadable template, a failed substitution, a payload value the
narrative needs that is missing or not of its stated JSON type, and span
texts that do not match the payload's targets. Where an underlying exception
exists -- a read error, a substitution error, a `Decimal` that cannot parse --
it is chained as the cause. A failed check has no underlying exception, so
none is manufactured. The message names the template and the placeholder or
the payload path, and never carries document text or a payload value.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from string import Template

from app.intelligence.errors import IntelligenceError

#: Bumped on any change to a fixed string the narrative can contain (DR23).
#: Stored with the brief, and never hashed.
TEMPLATE_VERSION = "1"

#: The one template, read-only, shipped beside this module.
TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "brief.txt"

#: §0.6.10 / §A22: code points of resolved, unescaped text a quote may hold.
MAX_QUOTED_SPAN_CHARS = 500

#: §0.6.13.4: appended after the closing quote of a capped quote.
TRUNCATION_MARKER = " [truncated]"

#: The S1-S15 signals the risk state lists, in §A10's order. S12 is rendered
#: per currency in the commercial section and S14 in the policy section.
RISK_SIGNALS = (
    ("S1", "open_ticket_count"),
    ("S2", "open_high_priority_count"),
    ("S2b", "high_priority_total"),
    ("S3", "tickets_in_lookback"),
    ("S4", "max_tickets_in_14d_window"),
    ("S5", "policy_escalation_state"),
    ("S6", "days_since_last_ticket"),
    ("S7", "sla_breach_count"),
    ("S8", "open_sla_breach_high_count"),
    ("S9", "stale_open_ticket_count"),
    ("S10", "dominant_ticket_category"),
    ("S11", "active_deal_count"),
    ("S13", "active_project_count"),
    ("S15", "deal_under_pressure"),
)


class BriefRenderError(IntelligenceError):
    """The narrative cannot be rendered from this payload, these span texts or this template."""


def quote_span(text: str) -> str:
    """One document-derived string, capped before it is escaped (§0.6.13.4)."""
    if len(text) <= MAX_QUOTED_SPAN_CHARS:
        return json.dumps(text, ensure_ascii=False)
    return json.dumps(text[:MAX_QUOTED_SPAN_CHARS], ensure_ascii=False) + TRUNCATION_MARKER


def render_brief(payload: Mapping[str, object], span_texts: Mapping[str, str]) -> str:
    """
    The narrative for one decision payload.

    `span_texts` maps each of the payload's cited-span targets to its resolved
    text, and must name exactly those targets. The output is a function of
    the payload, the span texts and TEMPLATE_VERSION alone.
    """
    template = _template()
    root = _Node(payload, "")
    spans = _spans(root, span_texts)
    sections = {
        "customer": root.get("customer").get("id").string(),
        "identity": _lines(_identity(root)),
        "risk_state": _lines(_risk_state(root)),
        "evidence": _lines(_evidence(root)),
        "commercial": _lines(_commercial(root)),
        "conflict": _lines(_conflict(root)),
        "dissent": _lines(_dissent(root)),
        "policy": _lines(_policy(root, spans)),
        "backlog": _lines(_backlog(root)),
        "actions": _lines(_actions(root)),
        "escalation": _lines(_escalation(root)),
    }
    try:
        return template.substitute(sections)
    except KeyError as exc:
        raise BriefRenderError(
            f"{TEMPLATE_PATH.name}: placeholder ${exc.args[0]} has no value"
        ) from exc
    except ValueError as exc:
        raise BriefRenderError(
            f"{TEMPLATE_PATH.name}: the template holds an invalid placeholder ({exc})"
        ) from exc


# ---------------------------------------------------------------------------
# Reading the payload: typed, and named by path when it fails
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Node:
    """One payload value and the path that reached it, e.g. `signals.active_deals[0]`."""

    value: object
    path: str

    def get(self, key: str) -> _Node:
        path = f"{self.path}.{key}" if self.path else key
        if not isinstance(self.value, Mapping) or key not in self.value:
            raise _unrenderable(path, "is missing")
        return _Node(self.value[key], path)

    def items(self) -> list[_Node]:
        if not isinstance(self.value, list):
            raise _unrenderable(self.path, "is not an array")
        return [_Node(item, f"{self.path}[{index}]") for index, item in enumerate(self.value)]

    def keys(self) -> list[str]:
        if not isinstance(self.value, Mapping):
            raise _unrenderable(self.path, "is not an object")
        return sorted(str(key) for key in self.value)

    def string(self) -> str:
        if not isinstance(self.value, str):
            raise _unrenderable(self.path, "is not a string")
        return self.value

    def count(self) -> int:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise _unrenderable(self.path, "is not an integer")
        return self.value

    def flag(self) -> bool:
        if not isinstance(self.value, bool):
            raise _unrenderable(self.path, "is not a boolean")
        return self.value

    @property
    def is_null(self) -> bool:
        return self.value is None


def _unrenderable(path: str, problem: str) -> BriefRenderError:
    return BriefRenderError(f"{TEMPLATE_PATH.name}: payload value {path} {problem}")


def _template() -> Template:
    try:
        return Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise BriefRenderError(
            f"{TEMPLATE_PATH.name}: the template cannot be read as UTF-8 text"
        ) from exc


def _spans(root: _Node, span_texts: Mapping[str, str]) -> dict[str, str]:
    """The span texts, checked against the payload's own targets (§0.6.13.5 condition 4)."""
    targets = [entry.get("target").string() for entry in root.get("cited_spans").items()]
    named = sorted(str(key) for key in span_texts)
    if named != sorted(targets):
        raise BriefRenderError(
            f"{TEMPLATE_PATH.name}: the span texts name {named}, but the payload's cited "
            f"spans are {sorted(targets)}"
        )
    for target in targets:
        if not isinstance(span_texts[target], str):
            raise BriefRenderError(
                f"{TEMPLATE_PATH.name}: the span text for {target} is not a string"
            )
    return dict(span_texts)


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------


def _lines(lines: Sequence[str]) -> str:
    return "\n".join(lines)


def _joined(values: Sequence[str], absent: str) -> str:
    return ", ".join(values) if values else absent


def _ids(node: _Node) -> list[str]:
    return [item.string() for item in node.items()]


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def _money(node: _Node) -> str:
    """`USD 5,361.44`: currency, a space, the stated amount comma-grouped, never rounded."""
    amount = node.get("amount")
    currency = node.get("currency").string()
    try:
        value = Decimal(amount.string())
    except InvalidOperation as exc:
        raise _unrenderable(amount.path, "is not a decimal amount") from exc
    if not value.is_finite():
        raise _unrenderable(amount.path, "is not a finite amount")
    return f"{currency} {format(value, ',f')}"


def _citation(node: _Node) -> str:
    kind = node.get("kind").string()
    if kind == "record":
        return (f"record {node.get('entity').string()} {node.get('id').string()} "
                f"{node.get('field').string()}")
    if kind == "document":
        return f"document {_span(node)}"
    raise _unrenderable(node.get("kind").path, "is not a citation kind")


def _span(node: _Node) -> str:
    """A document citation as `DOC-003 [238, 330)`: the full span, from the payload."""
    return (f"{node.get('document_id').string()} "
            f"[{node.get('start').count()}, {node.get('end').count()})")


def _evidence_lines(node: _Node, indent: str) -> list[str]:
    lines = [f"{indent}evidence:"]
    for item in node.items():
        line = f"{indent}- {item.get('kind').string()} {_citation(item.get('citation'))}"
        if isinstance(item.value, Mapping) and "rule_id" in item.value:
            line += f" (rule {item.get('rule_id').string()})"
        lines.append(line)
    if len(lines) == 1:
        lines.append(f"{indent}- none stated")
    return lines


def _position(node: _Node, lead: str) -> list[str]:
    return [
        f"{lead}{node.get('function').string()} {node.get('stance').string()} "
        f"{node.get('proposed_action').string()} on {node.get('object_ref').string()}",
        f"  Rationale: {node.get('rationale').string()}",
        *_evidence_lines(node.get("evidence"), "  "),
    ]


# ---------------------------------------------------------------------------
# The sections, in §A17's order
# ---------------------------------------------------------------------------


def _identity(root: _Node) -> list[str]:
    scope = root.get("scope")
    versions = root.get("versions")
    return [
        f"Customer: {root.get('customer').get('id').string()}",
        f"Source system: {scope.get('source_system').string()}",
        f"As of: {scope.get('as_of').string()}",
        f"Layer 1 fingerprint: {scope.get('layer1_fingerprint').string()}",
        f"Versions: payload {root.get('payload_version').count()}, "
        f"rules {versions.get('rules').count()}, linker {versions.get('linker').string()}, "
        f"policy {versions.get('policy').count()}",
    ]


def _signal_value(node: _Node) -> str:
    if node.is_null:
        return "none"
    if isinstance(node.value, bool):
        return "true" if node.flag() else "false"
    if isinstance(node.value, int):
        return str(node.count())
    return node.string()


def _risk_state(root: _Node) -> list[str]:
    signals = root.get("signals")
    worthiness = root.get("reconciliation").get("worthiness")
    support = root.get("support_evidence")
    lines = [
        f"Band: {root.get('band').string()}",
        f"Satisfied band rules: {_joined(_ids(root.get('satisfied_rules')), 'none')}",
        f"Executive-worthy: {_yes(worthiness.get('executive_worthy').flag())} (band "
        f"{worthiness.get('band').string()}, active deal count "
        f"{worthiness.get('active_deal_count').count()}, active project count "
        f"{worthiness.get('active_project_count').count()})",
        "Signals:",
        *(f"- {label} {name}: {_signal_value(signals.get(name))}"
          for label, name in RISK_SIGNALS),
    ]
    window = support.get("escalation_window")
    if window.is_null:
        lines.append("Escalation window: none, because no ticket was created in the lookback")
    else:
        lines.append(
            f"Escalation window: {window.get('start').string()} to {window.get('end').string()}, "
            f"ticket count {window.get('count').count()}"
        )
    span = support.get("ticket_span")
    if span.is_null:
        lines.append("Ticket span: none, because there is no escalation window")
    else:
        lines += [
            f"Ticket span: a {span.get('ticket_span_days').count()}-day span from "
            f"{span.get('first_ticket_date').string()} to {span.get('last_ticket_date').string()}, "
            f"ticket count {span.get('ticket_count').count()}: "
            f"{_joined(_ids(span.get('ticket_ids')), 'no ticket')}",
            f"  rule: {span.get('rule').string()}",
        ]
    lines.append("Derivations:")
    for record in support.get("derivations").items():
        line = (f"- {record.get('fact').string()} = {_signal_value(record.get('value'))}, counting "
                f"{_joined(_ids(record.get('ticket_ids')), 'no ticket')}")
        if isinstance(record.value, Mapping) and "category_counts" in record.value:
            counts = record.get("category_counts")
            lookback = record.get("lookback")
            stated_counts = [f"{name} {counts.get(name).count()}" for name in counts.keys()]
            line += (f"; category counts {_joined(stated_counts, 'none')}; lookback "
                     f"{lookback.get('start').string()} to {lookback.get('end').string()}")
        lines += [line, f"  rule: {record.get('rule').string()}"]
    return lines


def _evidence(root: _Node) -> list[str]:
    lines = ["Tickets:"]
    tickets = root.get("support_evidence").get("tickets").items()
    for ticket in tickets:
        priority, category = ticket.get("priority"), ticket.get("category")
        lines += [
            f"- {ticket.get('id').string()}: created {ticket.get('created_date').string()}, "
            f"priority {'none stated' if priority.is_null else priority.string()}, "
            f"category {'none stated' if category.is_null else category.string()}, "
            f"open {_yes(ticket.get('is_open').flag())}, "
            f"breaches SLA {_yes(ticket.get('breaches_sla').flag())}",
            *_evidence_lines(ticket.get("evidence"), "  "),
        ]
    if not tickets:
        lines.append("- none visible at this date")
    lines.append("Document links (this snapshot and linker version only):")
    links = root.get("document_evidence").items()
    for link in links:
        lines += [
            f"- {link.get('source').get('id').string()} names {link.get('target').get('id').string()}"
            f" by {link.get('basis').string()}, {link.get('confidence').string()} confidence, "
            f"matching {quote_span(link.get('matched_token').string())}",
            *_evidence_lines(link.get("evidence"), "  "),
        ]
    if not links:
        lines.append("- none under this snapshot and linker version")
    lines.append("Cited spans:")
    spans = root.get("cited_spans").items()
    lines += [
        f"- {entry.get('target').string()}: {_span(entry.get('citation'))}, quoted in section 7"
        for entry in spans
    ]
    if not spans:
        lines.append("- none, because no targeted document is cited in this payload")
    return lines


def _commercial(root: _Node) -> list[str]:
    signals = root.get("signals")
    lines = ["Active deals:"]
    deals = root.get("commercial_evidence").get("deals").items()
    for deal in deals:
        lines += [
            f"- {deal.get('id').string()}: stage {deal.get('stage').string()}, probability "
            f"{deal.get('probability').string()}%, amount {_money(deal.get('amount'))}",
            *_evidence_lines(deal.get("evidence"), "  "),
        ]
    if not deals:
        lines.append("- none")
    exposure = signals.get("exposure_by_currency")
    currencies = exposure.keys()
    lines.append("Exposure by currency (S12):")
    lines += [f"- {_money(exposure.get(currency))}" for currency in currencies]
    if not currencies:
        lines.append("- none, because there is no active deal")
    projects = signals.get("active_project_count").count()
    if projects == 0:
        customer = root.get("customer").get("id").string()
        lines.append(f"Active projects (S13): none. {customer} has no active project.")
    else:
        lines.append(f"Active projects (S13): {projects}")
    return lines


def _conflict(root: _Node) -> list[str]:
    reconciliation = root.get("reconciliation")
    policy_version = reconciliation.get("policy_version").count()
    lines: list[str] = []
    for resolution in reconciliation.get("resolutions").items():
        conflict = resolution.get("conflict")
        prevailing = resolution.get("prevailing")
        lines += [
            f"- Conflict over {conflict.get('object_ref').string()}:",
            *(f"  - {one.get('function').string()} {one.get('stance').string()} "
              f"{one.get('proposed_action').string()}"
              for one in conflict.get("positions").items()),
            f"  Resolved by policy {resolution.get('policy_id').string()} (policy version "
            f"{policy_version}): {resolution.get('resolved_action').string()} prevails, as "
            f"{prevailing.get('function').string()} proposed",
            f"  Rationale: {resolution.get('rationale').string()}",
            *_evidence_lines(resolution.get("evidence"), "  "),
        ]
    if not lines:
        lines.append("No conflict was detected between the functions' positions.")
    return lines


def _dissent(root: _Node) -> list[str]:
    lines: list[str] = []
    for resolution in root.get("reconciliation").get("resolutions").items():
        policy_id = resolution.get("policy_id").string()
        for position in resolution.get("dissent").items():
            lines += _position(position, f"- Overruled by {policy_id}: ")
    if not lines:
        lines.append("No position was overruled, so no dissent is recorded.")
    return lines


def _policy(root: _Node, spans: Mapping[str, str]) -> list[str]:
    lines = ["Cited spans:"]
    entries = root.get("cited_spans").items()
    for entry in entries:
        target = entry.get("target").string()
        lines.append(f"- {target}, {_span(entry.get('citation'))}: {quote_span(spans[target])}")
    if not entries:
        lines.append("- none, because no targeted document is cited in this payload")
    documents = _ids(root.get("signals").get("contract_document_ids"))
    lines.append(f"Contract documents (S14): {_joined(documents, 'none')}")
    return lines


def _backlog(root: _Node) -> list[str]:
    backlog = _ids(root.get("support_evidence").get("backlog_ticket_ids"))
    return [
        f"Chronic backlog tickets: {_joined(backlog, 'none')}",
        "A chronic backlog ticket is reported here and never drives the band.",
    ]


def _actions(root: _Node) -> list[str]:
    lines: list[str] = []
    for position in root.get("reconciliation").get("resolved_positions").items():
        lines += _position(position, "- ")
    if not lines:
        lines.append("No action is recommended, because no function stated a position.")
    return lines


def _escalation(root: _Node) -> list[str]:
    path = root.get("support_evidence").get("escalation_path")
    owner, manager = path.get("account_owner"), path.get("account_owner_manager")
    open_tickets = [one.get("id").string() for one in path.get("open_tickets").items()]
    assignees = [one.get("id").string() for one in path.get("assignees").items()]
    managers = [one.get("id").string() for one in path.get("assignee_managers").items()]
    lines = [
        f"Account owner: {'none stated' if owner.is_null else owner.get('id').string()}",
        "Account owner's manager: "
        f"{'none stated' if manager.is_null else manager.get('id').string()}",
        f"Open tickets (by status): {_joined(open_tickets, 'none')}",
        f"Assignees of open tickets: {_joined(assignees, 'none')}",
        f"Assignees' managers: {_joined(managers, 'none')}",
        "Edges:",
    ]
    edges = path.get("edges").items()
    lines += [
        f"- {edge.get('edge').string()}: {edge.get('source').get('id').string()} -> "
        f"{edge.get('target').get('id').string()} ({edge.get('basis').string()}, "
        f"{edge.get('carrier_field').string()})"
        for edge in edges
    ]
    if not edges:
        lines.append("- none")
    return lines
