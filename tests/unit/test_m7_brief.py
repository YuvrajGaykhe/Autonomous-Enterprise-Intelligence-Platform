"""
The narrative: quoting, money, absence and the four rendering failures (§0.6.10, §0.6.13.4-5).

§0.6.13.4 is proved on fixtures, because the three committed targets are 92,
85 and 95 characters long and so never reach the cap: exactly 500 renders
whole, 501 renders 500 and the marker after the closing quote, a multibyte
character at the cut counts once and is never split, and escaping is exactly
`json.dumps(..., ensure_ascii=False)`.

§0.6.13.5's four conditions each raise BriefRenderError. Where an underlying
exception exists -- a read error, a substitution error, an unparsable
Decimal -- it is the cause. A failed check has none, and none is
manufactured: its cause is None.
"""

from __future__ import annotations

import copy
import json
from decimal import InvalidOperation

import pytest

from app.decisions import brief as briefs
from app.decisions.brief import (
    MAX_QUOTED_SPAN_CHARS,
    TEMPLATE_VERSION,
    TRUNCATION_MARKER,
    BriefRenderError,
    quote_span,
    render_brief,
)
from app.decisions.payload import SPAN_TARGETS
from app.intelligence.contract import canonical_json
from app.intelligence.errors import IntelligenceError
from tests.unit.m5_support import deal, ticket
from tests.unit.m7_support import MERIDIAN_DATES, MERIDIAN_TICKETS, meridian, quiet

pytestmark = pytest.mark.unit

PHRASES = {target.name: target.phrase for target in SPAN_TARGETS}

SECTIONS = (
    "1. IDENTITY", "2. RISK STATE AND WHY", "3. EVIDENCE", "4. COMMERCIAL CONTEXT (PER CURRENCY)",
    "5. CONFLICT AND HOW IT WAS RESOLVED", "6. RECORDED DISSENT",
    "7. POLICY AND CONTRACT CONTEXT", "8. CHRONIC BACKLOG", "9. RECOMMENDED ACTIONS",
    "10. ESCALATION PATH", "11. LIMITATIONS",
)


@pytest.fixture(scope="module")
def payload() -> dict:
    return meridian().payload()


@pytest.fixture(scope="module")
def narrative(payload) -> str:
    return render_brief(payload, PHRASES)


def edited(payload: dict, edit) -> dict:
    changed = copy.deepcopy(payload)
    edit(changed)
    return changed


def raised(payload, spans=PHRASES) -> BriefRenderError:
    with pytest.raises(BriefRenderError) as caught:
        render_brief(payload, spans)
    return caught.value


# ---------------------------------------------------------------------------
# §0.6.13.4: quote_span
# ---------------------------------------------------------------------------


def test_the_cap_and_the_marker_are_the_resolved_ones():
    assert MAX_QUOTED_SPAN_CHARS == 500
    assert TRUNCATION_MARKER == " [truncated]"
    assert TEMPLATE_VERSION == "1"


def test_exactly_five_hundred_characters_render_whole_with_no_marker():
    text = "a" * 500

    assert quote_span(text) == '"' + text + '"'


def test_five_hundred_and_one_render_five_hundred_then_the_marker_after_the_quote():
    text = "a" * 499 + "bc"

    assert quote_span(text) == '"' + "a" * 499 + 'b"' + " [truncated]"


def test_a_multibyte_character_at_the_cut_counts_once_and_is_never_split():
    text = "é" * 499 + "€" + "x"

    quoted = quote_span(text)

    assert quoted == '"' + "é" * 499 + '€" [truncated]'
    quoted.encode("utf-8").decode("utf-8")


def test_the_cap_counts_code_points_before_escaping():
    """500 quotes are 500 characters, even though each escapes to two."""
    text = '"' * 500

    assert quote_span(text) == json.dumps(text, ensure_ascii=False)
    assert TRUNCATION_MARKER not in quote_span(text)
    assert quote_span(text + '"').endswith('"' + TRUNCATION_MARKER)


@pytest.mark.parametrize(("text", "expected"), [
    ('say "hi"', r'"say \"hi\""'),
    ("back\\slash", r'"back\\slash"'),
    ("two\nlines", r'"two\nlines"'),
    ("tab\there", r'"tab\there"'),
    ("bell\x07", r'"bell\u0007"'),
    ("naïve €", '"naïve €"'),
    ("", '""'),
])
def test_escaping_is_exactly_json_dumps_without_ascii_escapes(text, expected):
    assert quote_span(text) == expected == json.dumps(text, ensure_ascii=False)


def test_a_document_cannot_forge_the_marker():
    """A ` [truncated]` inside a document is rendered inside its quotes."""
    assert quote_span("ends [truncated]") == '"ends [truncated]"'


# ---------------------------------------------------------------------------
# The rendered narrative
# ---------------------------------------------------------------------------


def test_every_section_is_present_in_order(narrative):
    positions = [narrative.index(heading) for heading in SECTIONS]

    assert positions == sorted(positions)


def test_no_section_is_omitted_even_when_everything_is_absent():
    text = render_brief(quiet().payload(), {})

    for heading in SECTIONS:
        assert heading in text


def test_the_cited_spans_are_quoted_with_their_full_span(narrative):
    assert ('- DOC_003_ESCALATION_RULE, DOC-003 [238, 330): "Customers raising three or more '
            'tickets within 14 days are escalated to their account owner."') in narrative
    assert ("- DOC_006_TERM_AND_NOTICE, DOC-006 [153, 238): \"Term: 36 months, renewing "
            "annually unless either party gives 90 days' written notice.\"") in narrative
    assert ('- DOC_009_DEAL_LINKAGE, DOC-009 [238, 333): "The customer tied the Meridian '
            'Textiles - Seat Expansion decision (DEAL-001) to resolving them."') in narrative
    assert TRUNCATION_MARKER not in narrative


def test_a_long_span_is_capped_but_its_printed_span_is_the_whole_citation(payload):
    long_text = "x" * 600

    text = render_brief(payload, {**PHRASES, "DOC_003_ESCALATION_RULE": long_text})

    assert f'DOC-003 [238, 330): "{"x" * 500}" [truncated]' in text


def test_a_span_is_escaped_in_the_narrative(payload):
    text = render_brief(payload, {**PHRASES, "DOC_006_TERM_AND_NOTICE": 'a "b"\nc'})

    assert r'DOC-006 [153, 238): "a \"b\"\nc"' in text


def test_a_matched_token_is_quoted_by_the_same_rule(payload):
    changed = edited(payload, lambda one: one["document_evidence"][0].update(
        matched_token='Meridian "Textiles"'))

    assert r'matching "Meridian \"Textiles\""' in render_brief(changed, PHRASES)


def test_money_is_currency_space_and_comma_grouped_fixed_point(narrative):
    """DEAL-001 renders as USD 5,361.44: no rounding, no padding, no locale."""
    assert "amount USD 5,361.44" in narrative
    assert "- USD 5,361.44" in narrative
    assert "probability 90%" in narrative


def test_a_brief_in_two_currencies_states_each_and_totals_neither():
    deals = (deal("DEAL-001", stage="negotiation", probability=90, amount="5361.44"),
             deal("DEAL-040", stage="proposal", probability=50, amount="1234567.891",
                  currency="INR"),
             deal("DEAL-041", stage="qualification", probability=10, amount="0.5",
                  currency="INR"))

    text = render_brief(meridian(deals=deals).payload(), PHRASES)

    assert "amount INR 1,234,567.891" in text
    assert "amount INR 0.5" in text
    assert "- INR 1,234,568.391" in text
    assert "- USD 5,361.44" in text
    assert text.index("- INR 1,234,568.391") < text.index("- USD 5,361.44")


def test_the_absence_of_an_active_project_is_stated(narrative):
    """§A27.4: CUST-007 has no active project, and the brief says so."""
    assert "Active projects (S13): none. CUST-007 has no active project." in narrative


def test_an_active_project_count_is_stated_when_there_is_one():
    text = render_brief(meridian(active_project_count=2).payload(), PHRASES)

    assert "Active projects (S13): 2" in text
    assert "has no active project" not in text


@pytest.mark.parametrize("line", [
    "- none visible at this date",
    "- none under this snapshot and linker version",
    "- none, because no targeted document is cited in this payload",
    "Active deals:\n- none",
    "- none, because there is no active deal",
    "No conflict was detected between the functions' positions.",
    "No position was overruled, so no dissent is recorded.",
    "- none, because no targeted document is cited in this payload\nContract documents (S14)",
    "Contract documents (S14): none",
    "Chronic backlog tickets: none",
    "No action is recommended, because no function stated a position.",
    "Account owner: none stated",
    "Account owner's manager: none stated",
    "Open tickets (by status): none",
    "Assignees of open tickets: none",
    "Assignees' managers: none",
    "Edges:\n- none",
    "Satisfied band rules: none",
    "Escalation window: none, because no ticket was created in the lookback",
    "Ticket span: none, because there is no escalation window",
    "- S6 days_since_last_ticket: none",
    "- S10 dominant_ticket_category: none",
    "- dominant_ticket_category = none, counting no ticket; category counts none",
])
def test_every_absence_is_a_fixed_line(line):
    """DR24: a null or empty value becomes a fixed absence line."""
    inputs = quiet(tickets=(), open_ticket_count=0, tickets_in_lookback=0,
                   max_tickets_in_14d_window=0, days_since_last_ticket=None,
                   sla_breach_count=0, dominant_ticket_category=None, satisfied_rules=())
    payload = inputs.replace(created_dates={}, escalation_window=None).payload()

    assert line in render_brief(payload, {})


def test_a_null_priority_or_category_is_stated_as_absent():
    tickets = (*MERIDIAN_TICKETS, ticket("TKT-081", priority=None, category=None,
                                         is_open=False, breaches_sla=False))
    inputs = meridian(tickets=tickets).replace(
        created_dates={**MERIDIAN_DATES, "TKT-081": MERIDIAN_DATES["TKT-073"]},
        escalation_window={"start": "2026-08-18", "end": "2026-08-31", "count": 6})

    text = render_brief(inputs.payload(), PHRASES)

    assert "- TKT-081: created 2026-08-18, priority none stated, category none stated" in text


def test_an_item_with_no_evidence_states_that_none_is_stated(payload):
    changed = edited(payload, lambda one: one["document_evidence"][0].update(evidence=[]))

    assert "  evidence:\n  - none stated" in render_brief(changed, PHRASES)


def test_a_rule_id_is_rendered_where_the_evidence_carries_one(payload):
    changed = edited(payload, lambda one: one["document_evidence"][0]["evidence"][0].update(
        kind="DETERMINISTIC_RULE", rule_id="RULE-9"))

    assert "- DETERMINISTIC_RULE document DOC-005 [171, 188) (rule RULE-9)" in render_brief(
        changed, PHRASES)


def test_the_narrative_is_a_function_of_the_payloads_content_not_its_key_order(payload):
    """The stored JSONB comes back with its keys reordered; the narrative does not move."""
    stored = json.loads(canonical_json(payload))
    reordered = json.loads(json.dumps(payload))
    reordered = dict(reversed(list(reordered.items())))

    assert render_brief(stored, PHRASES) == render_brief(reordered, PHRASES) == render_brief(
        payload, PHRASES)


def test_the_span_texts_mapping_order_does_not_matter(payload):
    reversed_spans = dict(reversed(list(PHRASES.items())))

    assert render_brief(payload, reversed_spans) == render_brief(payload, PHRASES)


# ---------------------------------------------------------------------------
# §0.6.13.5: the four conditions
# ---------------------------------------------------------------------------


def test_brief_render_error_is_a_message_only_layer_2_failure():
    error = BriefRenderError("brief.txt: something")

    assert isinstance(error, IntelligenceError)
    assert error.args == ("brief.txt: something",)


def test_condition_1_an_unreadable_template_chains_the_read_error(payload, tmp_path,
                                                                    monkeypatch):
    monkeypatch.setattr(briefs, "TEMPLATE_PATH", tmp_path / "missing.txt")

    error = raised(payload)

    assert isinstance(error.__cause__, FileNotFoundError)
    assert str(error) == "missing.txt: the template cannot be read as UTF-8 text"


def test_condition_1_a_template_that_is_not_utf8_chains_the_decode_error(payload, tmp_path,
                                                                        monkeypatch):
    path = tmp_path / "latin1.txt"
    path.write_bytes("caf\xe9 ${customer}".encode("latin-1"))
    monkeypatch.setattr(briefs, "TEMPLATE_PATH", path)

    error = raised(payload)

    assert isinstance(error.__cause__, UnicodeDecodeError)


def test_condition_2_a_placeholder_with_no_value_chains_the_key_error(payload, tmp_path,
                                                                     monkeypatch):
    path = tmp_path / "brief.txt"
    path.write_text("${customer} ${no_such_section}\n", encoding="utf-8")
    monkeypatch.setattr(briefs, "TEMPLATE_PATH", path)

    error = raised(payload)

    assert isinstance(error.__cause__, KeyError)
    assert str(error) == "brief.txt: placeholder $no_such_section has no value"


def test_condition_2_an_invalid_placeholder_chains_the_value_error(payload, tmp_path,
                                                                  monkeypatch):
    path = tmp_path / "brief.txt"
    path.write_text("${customer} costs $ 5\n", encoding="utf-8")
    monkeypatch.setattr(briefs, "TEMPLATE_PATH", path)

    error = raised(payload)

    assert isinstance(error.__cause__, ValueError)
    assert str(error).startswith("brief.txt: the template holds an invalid placeholder")


def test_substitute_never_leaves_a_placeholder_in_the_text(payload, tmp_path, monkeypatch):
    """DR9: `substitute`, not `safe_substitute`: a missing value fails, it is not left as $name."""
    path = tmp_path / "brief.txt"
    path.write_text("$customer $customer_name\n", encoding="utf-8")
    monkeypatch.setattr(briefs, "TEMPLATE_PATH", path)

    raised(payload)


@pytest.mark.parametrize(("edit", "path"), [
    (lambda one: one["signals"].pop("open_ticket_count"), "signals.open_ticket_count"),
    (lambda one: one.pop("support_evidence"), "support_evidence"),
    (lambda one: one["commercial_evidence"]["deals"][0]["amount"].pop("amount"),
     "commercial_evidence.deals[0].amount.amount"),
    (lambda one: one["reconciliation"]["resolutions"][0].pop("policy_id"),
     "reconciliation.resolutions[0].policy_id"),
])
def test_condition_3_a_missing_value_names_its_path_and_has_no_cause(payload, edit, path):
    error = raised(edited(payload, edit))

    assert str(error) == f"brief.txt: payload value {path} is missing"
    assert error.__cause__ is None


@pytest.mark.parametrize(("edit", "path", "problem"), [
    (lambda one: one.update(band=3), "band", "is not a string"),
    (lambda one: one["signals"].update(open_ticket_count=[4]), "signals.open_ticket_count",
     "is not a string"),
    (lambda one: one["versions"].update(rules=True), "versions.rules", "is not an integer"),
    (lambda one: one["support_evidence"]["tickets"][0].update(is_open="no"),
     "support_evidence.tickets[0].is_open", "is not a boolean"),
    (lambda one: one.update(satisfied_rules="R-CRIT-001"), "satisfied_rules",
     "is not an array"),
    (lambda one: one["signals"].update(exposure_by_currency=[]),
     "signals.exposure_by_currency", "is not an object"),
    (lambda one: one["commercial_evidence"]["deals"][0]["amount"].update(amount="NaN"),
     "commercial_evidence.deals[0].amount.amount", "is not a finite amount"),
    (lambda one: one["document_evidence"][0]["evidence"][0]["citation"].update(kind="web"),
     "document_evidence[0].evidence[0].citation.kind", "is not a citation kind"),
])
def test_condition_3_a_value_of_the_wrong_type_names_its_path_and_has_no_cause(
    payload, edit, path, problem
):
    error = raised(edited(payload, edit))

    assert str(error) == f"brief.txt: payload value {path} {problem}"
    assert error.__cause__ is None


def test_condition_3_an_unparsable_amount_chains_the_decimal_error(payload):
    changed = edited(payload, lambda one: one["commercial_evidence"]["deals"][0]["amount"].update(
        amount="5,361.44"))

    error = raised(changed)

    assert isinstance(error.__cause__, InvalidOperation)
    assert str(error) == ("brief.txt: payload value commercial_evidence.deals[0].amount.amount "
                          "is not a decimal amount")
    assert "5,361.44" not in str(error)


def test_condition_3_an_infinite_amount_is_refused_by_the_check(payload):
    changed = edited(payload, lambda one: one["signals"]["exposure_by_currency"]["USD"].update(
        amount="Infinity"))

    error = raised(changed)

    assert error.__cause__ is None
    assert "signals.exposure_by_currency.USD.amount is not a finite amount" in str(error)


@pytest.mark.parametrize("spans", [
    {},
    {name: text for name, text in PHRASES.items() if name != "DOC_006_TERM_AND_NOTICE"},
    {**PHRASES, "DOC_999_UNKNOWN": "text"},
])
def test_condition_4_span_texts_that_are_not_the_payloads_targets(payload, spans):
    error = raised(payload, spans)

    assert "the span texts name" in str(error)
    assert error.__cause__ is None
    for phrase in PHRASES.values():
        assert phrase not in str(error)


def test_condition_4_a_span_text_that_is_not_a_string(payload):
    error = raised(payload, {**PHRASES, "DOC_009_DEAL_LINKAGE": 95})

    assert str(error) == "brief.txt: the span text for DOC_009_DEAL_LINKAGE is not a string"
    assert error.__cause__ is None


def test_no_message_carries_a_payload_value(payload):
    """§0.6.13.5: the message names the path, never the value."""
    for edit in (lambda one: one.update(band=["CRITICAL-SECRET-VALUE"]),
                 lambda one: one["scope"].update(as_of=20260918)):
        message = str(raised(edited(payload, edit)))
        assert "CRITICAL-SECRET-VALUE" not in message
        assert "20260918" not in message
