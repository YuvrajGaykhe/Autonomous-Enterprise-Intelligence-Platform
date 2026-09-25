"""
The decision payload, exactly as §0.6.13.1 and §0.6.13.2 state it.

§0.6.13.1 fixes every key, nested key, JSON type, list order and rule text,
so each is asserted literally here: a drifted frozen projection, a reordered
list or a reworded rule fails a test instead of silently changing every
payload_hash and every approval bound to one.

The inputs are tests/unit/m7_support.py's CUST-007, value by value as the
integration suite measures it; the integration suite asserts the same
payload over the real rows.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from app.decisions import payload as payloads
from app.decisions.payload import (
    SPAN_TARGETS,
    CategoryDerivation,
    CountDerivation,
    applicable_targets,
    dominant_category,
    first_occurrences,
    payload_citations,
    payload_hash,
)
from app.intelligence.contract import (
    DocumentCitation,
    LinkBasis,
    RecordCitation,
    canonical_json,
)
from app.intelligence.errors import ContractViolationError
from tests.unit.m5_support import deal, ticket
from tests.unit.m7_support import (
    FINGERPRINT,
    MERIDIAN_DATES,
    MERIDIAN_TICKETS,
    link,
    meridian,
    meridian_links,
    quiet,
    scope,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]

TOP_LEVEL_KEYS = {
    "payload_version", "scope", "versions", "customer", "band", "satisfied_rules", "signals",
    "reconciliation", "document_evidence", "cited_spans", "support_evidence",
    "commercial_evidence",
}

#: §0.6.13.1 item 3: the frozen projections' key sets at 6919fe5.
SIGNAL_KEYS = {
    "open_ticket_count", "open_high_priority_count", "high_priority_total",
    "tickets_in_lookback", "max_tickets_in_14d_window", "sla_breach_count",
    "open_sla_breach_high_count", "stale_open_ticket_count", "active_project_count",
    "policy_escalation_state", "days_since_last_ticket", "dominant_ticket_category",
    "deal_under_pressure", "active_deal_count", "active_deals", "exposure_by_currency",
    "contract_document_ids",
}
RECONCILIATION_KEYS = {
    "customer", "policy_version", "ordered_positions", "conflicts", "resolutions",
    "resolved_positions", "dissent", "worthiness", "ranking_key",
}
POSITION_KEYS = {"function", "stance", "proposed_action", "object_ref", "rationale", "evidence"}
CONFLICT_KEYS = {"object_ref", "positions"}
RESOLUTION_KEYS = {
    "policy_id", "conflict", "resolved_action", "prevailing", "dissent", "rationale", "evidence",
}
WORTHINESS_KEYS = {"band", "active_deal_count", "active_project_count", "executive_worthy"}
LINK_KEYS = {
    "source", "target", "basis", "edge_basis", "confidence", "matched_token", "evidence",
    "source_system", "layer1_fingerprint", "linker_version",
}
RECORD_CITATION_KEYS = {"kind", "entity", "id", "field"}
DOCUMENT_CITATION_KEYS = {"kind", "document_id", "start", "end"}
TICKET_KEYS = {"id", "priority", "category", "is_open", "breaches_sla", "created_date",
               "evidence"}
DEAL_KEYS = {"id", "stage", "probability", "amount", "evidence"}
SPAN_KEYS = {"ticket_ids", "ticket_count", "first_ticket_date", "last_ticket_date",
             "ticket_span_days", "rule"}
PATH_KEYS = {"customer", "account_owner", "account_owner_manager", "open_tickets",
             "assignees", "assignee_managers", "edges"}

#: §0.6.13.1 item 6's table, byte for byte.
RULE_TEXTS = {
    "open_ticket_count": "count of tickets where is_open",
    "open_high_priority_count": "count of tickets where is_open and priority == 'high'",
    "high_priority_total": "count of tickets where priority == 'high'",
    "open_sla_breach_high_count":
        "count of tickets where is_open and priority == 'high' and breaches_sla",
    "dominant_ticket_category":
        "most frequent category among tickets where category is neither null nor empty and "
        "lookback.start <= created_date <= lookback.end; ties go to the smallest category "
        "name in code-point order",
}
TICKET_SPAN_RULE = (
    "tickets where escalation_window.start <= created_date <= escalation_window.end; "
    "ticket_span_days = (last_ticket_date - first_ticket_date).days"
)

UUID_SHAPE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@pytest.fixture(scope="module")
def payload() -> dict:
    return meridian().payload()


def walk(node, path="$"):
    """Every (path, value) in a payload, containers included."""
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")


def derivation(payload, fact):
    (record,) = [one for one in payload["support_evidence"]["derivations"]
                 if one["fact"] == fact]
    return record


# ---------------------------------------------------------------------------
# Item 1: the value domain
# ---------------------------------------------------------------------------


def test_the_payload_holds_only_json_values_and_no_float(payload):
    for path, value in walk(payload):
        assert value is None or isinstance(value, dict | list | str | int | bool), path
        assert not isinstance(value, float), path
        if isinstance(value, dict):
            assert all(isinstance(key, str) for key in value), path


def test_the_payload_serialises_under_m1s_discipline(payload):
    assert json.loads(canonical_json(payload)) == payload


def test_no_database_id_is_in_the_payload(payload):
    """§0.6.13.1 item 10: every identifier is a source id or a configuration id."""
    text = canonical_json(payload)

    assert not UUID_SHAPE.search(text)
    for path, _ in walk(payload):
        assert not path.endswith((".uuid", "_uuid", ".assessment_id", ".brief_id")), path


# ---------------------------------------------------------------------------
# Item 2: the top level
# ---------------------------------------------------------------------------


def test_exactly_twelve_top_level_keys(payload):
    assert set(payload) == TOP_LEVEL_KEYS
    assert len(payload) == 12


def test_the_scope_versions_customer_band_and_rules(payload):
    assert payload["payload_version"] == 1
    assert payload["scope"] == {
        "source_system": "csv_demo", "as_of": "2026-09-18", "layer1_fingerprint": FINGERPRINT,
    }
    assert payload["versions"] == {"rules": 1, "linker": "1", "policy": 1}
    assert payload["customer"] == {"entity": "customers", "id": "CUST-007"}
    assert payload["band"] == "CRITICAL"
    assert payload["satisfied_rules"] == [
        "R-CRIT-001", "R-ELEV-001", "R-ELEV-002", "R-WATCH-001", "R-WATCH-002", "R-WATCH-003"]


def test_the_scope_carries_neither_as_of_source_nor_entity_counts(payload):
    assert "as_of_source" not in payload["scope"]
    assert "entity_counts" not in payload["scope"]


def test_the_versions_are_the_configurations_and_the_policys():
    inputs = meridian()
    config = inputs.config.__class__(**{**vars(inputs.config), "rules_version": 7,
                                        "linker_version": "9"})

    versions = inputs.replace(config=config).payload()["versions"]

    assert versions == {"rules": 7, "linker": "9", "policy": 1}


# ---------------------------------------------------------------------------
# Item 3: frozen projections, embedded as they emit
# ---------------------------------------------------------------------------


def test_signals_and_reconciliation_are_the_frozen_projections(payload):
    inputs = meridian()

    assert payload["signals"] == inputs.contexts.commercial.signals.to_payload()
    assert payload["reconciliation"] == inputs.reconciliation.to_payload()


def test_the_frozen_projection_key_sets_are_pinned(payload):
    reconciliation = payload["reconciliation"]

    assert set(payload["signals"]) == SIGNAL_KEYS
    assert set(reconciliation) == RECONCILIATION_KEYS
    for one in reconciliation["ordered_positions"]:
        assert set(one) == POSITION_KEYS
    (conflict,) = reconciliation["conflicts"]
    assert set(conflict) == CONFLICT_KEYS
    (resolution,) = reconciliation["resolutions"]
    assert set(resolution) == RESOLUTION_KEYS
    assert set(reconciliation["worthiness"]) == WORTHINESS_KEYS
    assert [type(part) for part in reconciliation["ranking_key"]] == [int, int, int, str]


def test_evidence_carries_a_rule_id_only_when_it_has_one(payload):
    for path, value in walk(payload):
        if isinstance(value, dict) and "citation" in value and "kind" in value:
            assert set(value) <= {"kind", "citation", "rule_id"}, path
            assert value.get("rule_id", "present") is not None, path


def test_citations_have_exactly_their_wire_shapes(payload):
    for citation in payload_citations(payload):
        wire = citation.to_payload()
        expected = (RECORD_CITATION_KEYS if isinstance(citation, RecordCitation)
                    else DOCUMENT_CITATION_KEYS)
        assert set(wire) == expected


def test_the_signals_carry_s14_and_the_deal(payload):
    signals = payload["signals"]

    assert signals["contract_document_ids"] == ["DOC-006"]
    assert signals["active_deals"] == [{
        "id": "DEAL-001", "stage": "negotiation", "probability": "90",
        "amount": {"amount": "5361.44", "currency": "USD"},
    }]
    assert signals["active_project_count"] == 0


# ---------------------------------------------------------------------------
# Item 4: document_evidence
# ---------------------------------------------------------------------------


def test_document_evidence_is_every_own_stamp_link_by_document_then_basis(payload):
    entries = payload["document_evidence"]

    assert [(one["source"]["id"], one["basis"]) for one in entries] == [
        ("DOC-005", "EXACT_NAME"), ("DOC-005", "ID_TOKEN"),
        ("DOC-006", "EXACT_NAME"), ("DOC-006", "ID_TOKEN"),
        ("DOC-009", "EXACT_NAME"), ("DOC-009", "ID_TOKEN"),
    ]
    for entry in entries:
        assert set(entry) == LINK_KEYS
        assert "document_type" not in entry


def test_document_evidence_order_does_not_depend_on_arrival_order():
    inputs = meridian()
    shuffled = tuple(reversed(inputs.links))

    assert (inputs.replace(links=shuffled).payload()["document_evidence"]
            == inputs.payload()["document_evidence"])


def test_each_entry_is_the_links_own_projection(payload):
    links = sorted(meridian_links(), key=lambda one: (one.source.source_id, str(one.basis)))

    assert payload["document_evidence"] == [one.to_payload() for one in links]


def test_no_link_is_an_empty_list():
    assert quiet().payload()["document_evidence"] == []


# ---------------------------------------------------------------------------
# Item 5 and §0.6.13.3: cited_spans and the targets
# ---------------------------------------------------------------------------


def test_cited_spans_are_one_entry_per_applicable_target_by_name(payload):
    assert payload["cited_spans"] == [
        {"target": "DOC_003_ESCALATION_RULE",
         "citation": {"kind": "document", "document_id": "DOC-003", "start": 238, "end": 330}},
        {"target": "DOC_006_TERM_AND_NOTICE",
         "citation": {"kind": "document", "document_id": "DOC-006", "start": 153, "end": 238}},
        {"target": "DOC_009_DEAL_LINKAGE",
         "citation": {"kind": "document", "document_id": "DOC-009", "start": 238, "end": 333}},
    ]


def test_no_cited_span_holds_its_text(payload):
    for entry in payload["cited_spans"]:
        assert set(entry) == {"target", "citation"}


def test_the_three_targets_are_the_resolved_names_documents_and_phrases():
    assert [(one.name, one.document_id, one.phrase) for one in SPAN_TARGETS] == [
        ("DOC_003_ESCALATION_RULE", "DOC-003",
         "Customers raising three or more tickets within 14 days are escalated to their "
         "account owner."),
        ("DOC_006_TERM_AND_NOTICE", "DOC-006",
         "Term: 36 months, renewing annually unless either party gives 90 days' written "
         "notice."),
        ("DOC_009_DEAL_LINKAGE", "DOC-009",
         "The customer tied the Meridian Textiles - Seat Expansion decision (DEAL-001) to "
         "resolving them."),
    ]
    assert [len(one.phrase) for one in SPAN_TARGETS] == [92, 85, 95]
    assert all(one.phrase.isascii() for one in SPAN_TARGETS)
    assert [one.name for one in SPAN_TARGETS] == sorted(one.name for one in SPAN_TARGETS)


def test_all_three_targets_apply_to_cust_007():
    inputs = meridian()

    assert [one.name for one in applicable_targets(inputs.reconciliation, inputs.links)] == [
        "DOC_003_ESCALATION_RULE", "DOC_006_TERM_AND_NOTICE", "DOC_009_DEAL_LINKAGE"]


def test_the_resolution_alone_makes_doc_003_and_doc_009_apply():
    inputs = meridian()

    assert [one.name for one in applicable_targets(inputs.reconciliation, ())] == [
        "DOC_003_ESCALATION_RULE", "DOC_009_DEAL_LINKAGE"]


def test_a_link_alone_makes_its_document_apply():
    reconciliation = quiet().reconciliation
    only_doc_006 = (link("DOC-006", LinkBasis.ID_TOKEN, "CUST-007", 113, 121),)

    assert [one.name for one in applicable_targets(reconciliation, only_doc_006)] == [
        "DOC_006_TERM_AND_NOTICE"]


def test_no_target_applies_without_a_citation_of_its_document():
    inputs = quiet()

    assert applicable_targets(inputs.reconciliation, inputs.links) == ()
    assert inputs.payload()["cited_spans"] == []


def test_the_spans_must_be_exactly_the_applicable_targets():
    inputs = meridian()
    missing = {name: span for name, span in inputs.spans.items()
               if name != "DOC_006_TERM_AND_NOTICE"}
    extra = {**quiet().spans, "DOC_003_ESCALATION_RULE": DocumentCitation("DOC-003", 1, 2)}

    with pytest.raises(ContractViolationError, match="applicable targets"):
        inputs.replace(spans=missing).payload()
    with pytest.raises(ContractViolationError, match="applicable targets"):
        quiet().replace(spans=extra).payload()


@pytest.mark.parametrize(("text", "phrase", "expected"), [
    ("no match here", "phrase", ()),
    ("a phrase once", "phrase", (2,)),
    ("phrase and phrase", "phrase", (0, 11)),
    ("aaa", "aa", (0, 1)),
    ("Phrase", "phrase", ()),
    ("phrase  spaced", "phrase spaced", ()),
])
def test_first_occurrences_is_the_two_find_algorithm(text, phrase, expected):
    """Zero, one, several -- an overlapping second occurrence included; exact and case-sensitive."""
    assert first_occurrences(text, phrase) == expected


# ---------------------------------------------------------------------------
# Item 6 and §0.6.13.2: support_evidence
# ---------------------------------------------------------------------------


def test_support_evidence_has_exactly_six_keys(payload):
    assert set(payload["support_evidence"]) == {
        "tickets", "escalation_window", "ticket_span", "backlog_ticket_ids",
        "escalation_path", "derivations",
    }


def test_every_visible_ticket_with_its_date_facts_and_four_citations(payload):
    tickets = payload["support_evidence"]["tickets"]

    assert [(one["id"], one["created_date"], one["priority"], one["category"], one["is_open"])
            for one in tickets] == [
        ("TKT-073", "2026-08-18", "high", "performance", False),
        ("TKT-075", "2026-08-20", "high", "performance", True),
        ("TKT-076", "2026-08-23", "high", "integration", True),
        ("TKT-079", "2026-08-25", "medium", "billing", True),
        ("TKT-080", "2026-08-27", "high", "performance", True),
    ]
    for one in tickets:
        assert set(one) == TICKET_KEYS
        assert one["evidence"] == [
            {"kind": "CANONICAL_FACT", "citation": {
                "kind": "record", "entity": "support_tickets", "id": one["id"], "field": field}}
            for field in ("created_at", "priority", "category", "resolved_at")
        ]


def test_tickets_are_ascending_by_id_whatever_the_context_order():
    inputs = meridian(tickets=tuple(reversed(MERIDIAN_TICKETS)))

    ids = [one["id"] for one in inputs.payload()["support_evidence"]["tickets"]]
    assert ids == sorted(ids)


def test_a_null_priority_or_category_is_null_and_never_a_placeholder():
    tickets = (*MERIDIAN_TICKETS, ticket("TKT-081", priority=None, category=None,
                                         is_open=False, breaches_sla=False))
    dates = {**MERIDIAN_DATES, "TKT-081": date(2026, 5, 1)}
    inputs = meridian(tickets=tickets).replace(created_dates=dates)

    (extra,) = [one for one in inputs.payload()["support_evidence"]["tickets"]
                if one["id"] == "TKT-081"]
    assert (extra["priority"], extra["category"]) == (None, None)


def test_the_window_and_the_path_are_embedded_verbatim(payload):
    evidence = payload["support_evidence"]
    inputs = meridian()

    assert evidence["escalation_window"] == {"start": "2026-08-18", "end": "2026-08-31",
                                             "count": 5}
    assert evidence["escalation_path"] == dict(inputs.escalation_path)
    assert set(evidence["escalation_path"]) == PATH_KEYS
    assert evidence["backlog_ticket_ids"] == []


def test_the_backlog_is_m3s_tuple_as_a_list():
    inputs = meridian().replace(backlog_ticket_ids=("TKT-039",))

    assert inputs.payload()["support_evidence"]["backlog_ticket_ids"] == ["TKT-039"]


def test_cust_007s_ticket_span_is_five_tickets_in_nine_days(payload):
    """OPEN-M7-3: 08-18 to 08-27 is 9 elapsed days, never 10, and never the 14-day window."""
    span = payload["support_evidence"]["ticket_span"]

    assert span == {
        "ticket_ids": ["TKT-073", "TKT-075", "TKT-076", "TKT-079", "TKT-080"],
        "ticket_count": 5,
        "first_ticket_date": "2026-08-18",
        "last_ticket_date": "2026-08-27",
        "ticket_span_days": 9,
        "rule": TICKET_SPAN_RULE,
    }
    assert set(span) == SPAN_KEYS
    window = payload["support_evidence"]["escalation_window"]
    assert (window["start"], window["end"]) != (span["first_ticket_date"],
                                                span["last_ticket_date"])


def test_one_ticket_in_the_window_is_a_zero_day_span():
    span = quiet().payload()["support_evidence"]["ticket_span"]

    assert span["ticket_ids"] == ["TKT-078"]
    assert span["ticket_count"] == 1
    assert span["first_ticket_date"] == span["last_ticket_date"] == "2026-08-24"
    assert span["ticket_span_days"] == 0


def test_a_ticket_outside_the_window_is_listed_but_not_spanned():
    tickets = (*MERIDIAN_TICKETS, ticket("TKT-060", priority="low", category="billing",
                                         is_open=False, breaches_sla=False))
    dates = {**MERIDIAN_DATES, "TKT-060": date(2026, 9, 5)}
    inputs = meridian(tickets=tickets, open_ticket_count=4, tickets_in_lookback=6,
                      dominant_ticket_category="performance").replace(created_dates=dates)

    evidence = inputs.payload()["support_evidence"]
    assert "TKT-060" in [one["id"] for one in evidence["tickets"]]
    assert "TKT-060" not in evidence["ticket_span"]["ticket_ids"]
    assert evidence["ticket_span"]["last_ticket_date"] == "2026-08-27"


def test_several_tickets_on_one_date_each_count_once():
    dates = {**MERIDIAN_DATES, "TKT-075": date(2026, 8, 18), "TKT-076": date(2026, 8, 18)}

    span = meridian().replace(created_dates=dates).payload()["support_evidence"]["ticket_span"]

    assert span["ticket_count"] == 5
    assert span["ticket_ids"] == ["TKT-073", "TKT-075", "TKT-076", "TKT-079", "TKT-080"]
    assert span["ticket_span_days"] == 9


@pytest.mark.parametrize(("as_of", "first", "last", "days"), [
    (date(2026, 9, 18), date(2026, 8, 20), date(2026, 8, 20), 0),
    (date(2026, 9, 18), date(2026, 8, 20), date(2026, 8, 21), 1),
    (date(2026, 9, 18), date(2026, 8, 31), date(2026, 9, 1), 1),
    (date(2027, 1, 10), date(2026, 12, 31), date(2027, 1, 1), 1),
    (date(2028, 3, 5), date(2028, 2, 28), date(2028, 3, 1), 2),
    (date(2026, 9, 18), date(2026, 8, 18), date(2026, 8, 27), 9),
])
def test_the_span_is_the_elapsed_days_between_its_two_dates(as_of, first, last, days):
    """
    DR15 over the CalendarDate protocol: the same day is 0, adjacent dates are
    1, and month, year and leap-day boundaries count as a calendar does.
    """
    dates = {**dict.fromkeys(MERIDIAN_DATES, first), "TKT-080": last}
    window = {"start": first.isoformat(), "end": last.isoformat(), "count": 5}
    inputs = meridian().replace(scope=scope(as_of=as_of), created_dates=dates,
                                escalation_window=window)

    span = inputs.payload()["support_evidence"]["ticket_span"]

    assert (span["first_ticket_date"], span["last_ticket_date"], span["ticket_span_days"]) == (
        first.isoformat(), last.isoformat(), days)
    assert span["ticket_span_days"] == (last - first).days


def test_the_span_ends_are_the_earliest_and_latest_dates_whatever_the_id_order():
    """The highest id has the earliest date here, and the mapping arrives in either order."""
    dates = {"TKT-073": date(2026, 8, 27), "TKT-075": date(2026, 8, 20),
             "TKT-076": date(2026, 8, 23), "TKT-079": date(2026, 8, 25),
             "TKT-080": date(2026, 8, 18)}

    for created in (dates, dict(reversed(list(dates.items())))):
        evidence = meridian().replace(created_dates=created).payload()["support_evidence"]
        span = evidence["ticket_span"]
        assert (span["first_ticket_date"], span["last_ticket_date"],
                span["ticket_span_days"]) == ("2026-08-18", "2026-08-27", 9)
        assert span["ticket_ids"] == ["TKT-073", "TKT-075", "TKT-076", "TKT-079", "TKT-080"]
        assert {one["id"]: one["created_date"] for one in evidence["tickets"]} == {
            ticket_id: day.isoformat() for ticket_id, day in dates.items()}


def test_no_window_means_no_span():
    """§0.6.13.2: visible tickets but none in the lookback -- nothing is stated or invented."""
    evidence = meridian().replace(escalation_window=None).payload()["support_evidence"]

    assert evidence["escalation_window"] is None
    assert evidence["ticket_span"] is None


def test_a_span_that_disagrees_with_the_window_count_raises():
    """DR16: the span must describe the burst the window counts."""
    window = {"start": "2026-08-18", "end": "2026-08-31", "count": 4}

    with pytest.raises(ContractViolationError, match="DR16"):
        meridian().replace(escalation_window=window).payload()


def test_the_five_derivations_in_order_with_their_rules_values_and_tickets(payload):
    derivations = payload["support_evidence"]["derivations"]

    assert [one["fact"] for one in derivations] == list(RULE_TEXTS)
    assert [one["rule"] for one in derivations] == list(RULE_TEXTS.values())
    assert [(one["fact"], one["value"], one["ticket_ids"]) for one in derivations[:4]] == [
        ("open_ticket_count", 4, ["TKT-075", "TKT-076", "TKT-079", "TKT-080"]),
        ("open_high_priority_count", 3, ["TKT-075", "TKT-076", "TKT-080"]),
        ("high_priority_total", 4, ["TKT-073", "TKT-075", "TKT-076", "TKT-080"]),
        ("open_sla_breach_high_count", 3, ["TKT-075", "TKT-076", "TKT-080"]),
    ]
    for one in derivations[:4]:
        assert set(one) == {"fact", "value", "rule", "ticket_ids"}


def test_the_dominant_category_counts_every_ticket_it_counts(payload):
    """MP1 revision (c): all five tickets, not only the winning category's three."""
    record = derivation(payload, "dominant_ticket_category")

    assert record == {
        "fact": "dominant_ticket_category",
        "value": "performance",
        "rule": RULE_TEXTS["dominant_ticket_category"],
        "lookback": {"start": "2026-06-21", "end": "2026-09-18"},
        "category_counts": {"billing": 1, "integration": 1, "performance": 3},
        "ticket_ids": ["TKT-073", "TKT-075", "TKT-076", "TKT-079", "TKT-080"],
    }


def test_the_rule_texts_are_ascii_and_are_the_modules_constants():
    texts = [payloads.OPEN_TICKET_COUNT_RULE, payloads.OPEN_HIGH_PRIORITY_COUNT_RULE,
             payloads.HIGH_PRIORITY_TOTAL_RULE, payloads.OPEN_SLA_BREACH_HIGH_COUNT_RULE,
             payloads.DOMINANT_TICKET_CATEGORY_RULE]

    assert texts == list(RULE_TEXTS.values())
    assert payloads.TICKET_SPAN_RULE == TICKET_SPAN_RULE
    assert all(text.isascii() for text in [*texts, TICKET_SPAN_RULE])


def test_high_priority_is_m3s_literal():
    """DR22: payload.py may not import M3, so it states the literal and this pins it."""
    from app.intelligence.signals import HIGH_PRIORITY

    assert payloads.HIGH_PRIORITY == HIGH_PRIORITY == "high"


def test_s10_excludes_uncategorised_tickets_and_those_outside_the_lookback():
    tickets = (*MERIDIAN_TICKETS,
               ticket("TKT-061", priority="low", category="", is_open=False, breaches_sla=False),
               ticket("TKT-062", priority="low", category=None, is_open=False,
                      breaches_sla=False),
               ticket("TKT-063", priority="low", category="billing", is_open=False,
                      breaches_sla=False))
    dates = {**MERIDIAN_DATES, "TKT-061": date(2026, 9, 1), "TKT-062": date(2026, 9, 2),
             "TKT-063": date(2026, 6, 20)}
    inputs = meridian(tickets=tickets).replace(created_dates=dates)

    record = derivation(inputs.payload(), "dominant_ticket_category")
    assert record["category_counts"] == {"billing": 1, "integration": 1, "performance": 3}
    assert record["ticket_ids"] == ["TKT-073", "TKT-075", "TKT-076", "TKT-079", "TKT-080"]


def test_s10_counts_a_ticket_on_the_first_day_of_the_lookback():
    tickets = (*MERIDIAN_TICKETS, ticket("TKT-063", priority="low", category="billing",
                                         is_open=False, breaches_sla=False))
    dates = {**MERIDIAN_DATES, "TKT-063": date(2026, 6, 21)}
    inputs = meridian(tickets=tickets).replace(created_dates=dates)

    record = derivation(inputs.payload(), "dominant_ticket_category")
    assert record["category_counts"]["billing"] == 2


def test_an_s10_tie_goes_to_the_smaller_name():
    """CUST-025's shape: billing 1, onboarding 1, and billing wins."""
    assert dominant_category({"onboarding": 1, "billing": 1}) == "billing"
    assert dominant_category({"b": 2, "a": 1}) == "b"
    assert dominant_category({"Z": 1, "a": 1}) == "Z"
    assert dominant_category({}) is None


def test_no_counted_ticket_is_an_empty_count_and_a_null_value():
    record = CategoryDerivation(value=None, lookback=("2026-06-21", "2026-09-18"),
                                category_counts={}, ticket_ids=())

    assert record.to_payload()["category_counts"] == {}
    assert record.to_payload()["value"] is None
    assert record.to_payload()["ticket_ids"] == []


def test_a_count_disagreeing_with_its_tickets_raises():
    """DR14: a payload may not state a fact its provenance does not produce."""
    with pytest.raises(ContractViolationError, match="open_ticket_count is 5"):
        meridian(open_ticket_count=5).payload()


def test_a_count_derivation_refuses_a_value_its_tickets_do_not_give():
    with pytest.raises(ContractViolationError):
        CountDerivation(fact="high_priority_total", value=2, rule="r", ticket_ids=("T",))


def test_a_dominant_category_disagreeing_with_its_counts_raises():
    with pytest.raises(ContractViolationError, match="produce 'performance'"):
        meridian(dominant_ticket_category="billing").payload()


def test_the_category_counts_must_sum_to_the_tickets_counted():
    with pytest.raises(ContractViolationError, match="sum to 2"):
        CategoryDerivation(value="a", lookback=("x", "y"), category_counts={"a": 2},
                           ticket_ids=("T1",))


def test_a_null_value_with_counts_raises():
    with pytest.raises(ContractViolationError, match="produce 'a'"):
        CategoryDerivation(value=None, lookback=("x", "y"), category_counts={"a": 1},
                           ticket_ids=("T1",))


def test_every_count_is_zero_when_no_ticket_is_visible():
    """§0.6.13.2's first edge case; unreachable in a brief, stated all the same."""
    inputs = quiet(tickets=(), open_ticket_count=0, tickets_in_lookback=0,
                   max_tickets_in_14d_window=0, days_since_last_ticket=None,
                   sla_breach_count=0, dominant_ticket_category=None)
    evidence = inputs.replace(created_dates={}, escalation_window=None).payload()[
        "support_evidence"]

    assert evidence["tickets"] == []
    assert evidence["ticket_span"] is None
    for record in evidence["derivations"][:4]:
        assert (record["value"], record["ticket_ids"]) == (0, [])
    assert (evidence["derivations"][4]["value"], evidence["derivations"][4]["category_counts"]
            ) == (None, {})


# ---------------------------------------------------------------------------
# Item 7: commercial_evidence
# ---------------------------------------------------------------------------


def test_commercial_evidence_is_each_active_deal_with_five_citations(payload):
    assert payload["commercial_evidence"] == {"deals": [{
        "id": "DEAL-001",
        "stage": "negotiation",
        "probability": "90",
        "amount": {"amount": "5361.44", "currency": "USD"},
        "evidence": [
            {"kind": "CANONICAL_FACT", "citation": {
                "kind": "record", "entity": "deals", "id": "DEAL-001", "field": field}}
            for field in ("is_active", "stage", "probability", "amount", "currency")
        ],
    }]}
    assert set(payload["commercial_evidence"]["deals"][0]) == DEAL_KEYS


def test_deals_are_ascending_by_id_in_every_currency():
    deals = (deal("DEAL-090", stage="proposal", probability=40, amount="10.5", currency="INR"),
             deal("DEAL-002", stage="negotiation", probability=85, amount="1200", currency="USD"),
             deal("DEAL-050", stage="qualification", probability=10, amount="7", currency="INR"))

    listed = meridian(deals=deals).payload()["commercial_evidence"]["deals"]

    assert [one["id"] for one in listed] == ["DEAL-002", "DEAL-050", "DEAL-090"]
    assert [one["amount"] for one in listed] == [
        {"amount": "1200", "currency": "USD"}, {"amount": "7", "currency": "INR"},
        {"amount": "10.5", "currency": "INR"}]


def test_no_active_deal_is_an_empty_list():
    assert quiet().payload()["commercial_evidence"] == {"deals": []}


# ---------------------------------------------------------------------------
# Items 8-11: absence, citations and the hash
# ---------------------------------------------------------------------------


def test_null_appears_only_where_the_contract_allows_it():
    """Item 8: an absence is null only where items 2, 6 or 7 allow it, or a frozen projection emits one."""
    allowed = re.compile(
        r"\$\.support_evidence\.(escalation_window|ticket_span"
        r"|tickets\[\d+\]\.(priority|category)|derivations\[4\]\.value"
        r"|escalation_path\.(account_owner|account_owner_manager))$"
        r"|\$\.signals\.(days_since_last_ticket|dominant_ticket_category)$")
    for inputs in (meridian(), quiet(), meridian().replace(escalation_window=None)):
        for path, value in walk(inputs.payload()):
            if value is None:
                assert allowed.match(path), path


def test_empty_collections_are_empty_and_never_null():
    payload = quiet().payload()

    assert payload["document_evidence"] == []
    assert payload["cited_spans"] == []
    assert payload["commercial_evidence"]["deals"] == []
    assert payload["reconciliation"]["ordered_positions"] == []
    assert payload["signals"]["exposure_by_currency"] == {}


def test_payload_citations_are_distinct_and_ascending_by_wire_form(payload):
    citations = payload_citations(payload)
    wires = [canonical_json(one.to_payload()) for one in citations]

    assert wires == sorted(set(wires))
    every = [canonical_json(value) for path, value in walk(payload)
             if path.endswith(".citation")]
    assert set(every) == set(wires)
    assert len(every) > len(wires), "some citations repeat, and each counts once"


def test_payload_citations_rebuild_both_kinds(payload):
    kinds = {type(one) for one in payload_citations(payload)}

    assert kinds == {RecordCitation, DocumentCitation}


def test_the_hash_is_the_sha256_of_the_canonical_form(payload):
    digest = payload_hash(payload)

    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert digest == hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def test_the_hash_ignores_key_order_and_survives_a_json_round_trip(payload):
    reordered = json.loads(json.dumps(payload, sort_keys=False))
    reordered = dict(reversed(list(reordered.items())))

    assert payload_hash(reordered) == payload_hash(payload)
    assert payload_hash(json.loads(canonical_json(payload))) == payload_hash(payload)


@pytest.mark.parametrize("change", [
    lambda inputs: inputs.replace(scope=scope(as_of=date(2026, 9, 19))),
    lambda inputs: inputs.replace(scope=scope(fingerprint="f" * 64)),
    lambda inputs: inputs.replace(scope=scope(source_system="other_demo")),
    lambda inputs: inputs.replace(backlog_ticket_ids=("TKT-039",)),
    lambda inputs: inputs.replace(escalation_path={**inputs.escalation_path, "assignees": []}),
    lambda inputs: inputs.replace(created_dates={**MERIDIAN_DATES,
                                                 "TKT-080": date(2026, 8, 28)}),
])
def test_every_hashed_input_moves_the_hash(change):
    """§0.6.7's inclusions: scope, and all approval-relevant evidence."""
    inputs = meridian()

    assert payload_hash(change(inputs).payload()) != payload_hash(inputs.payload())


def test_the_hash_is_identical_across_processes():
    """§0.6.15 criterion 8: two interpreters, two hash seeds, one digest."""
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "from tests.unit.m7_support import meridian;"
        "from app.decisions.payload import payload_hash;"
        "print(payload_hash(meridian().payload()))"
    )
    digests = {
        subprocess.run(
            [sys.executable, "-c", code, str(REPO)], cwd=REPO, capture_output=True, text=True,
            check=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                             "PYTHONHASHSEED": seed},
        ).stdout.strip()
        for seed in ("0", "4242")
    }

    assert digests == {payload_hash(meridian().payload())}
