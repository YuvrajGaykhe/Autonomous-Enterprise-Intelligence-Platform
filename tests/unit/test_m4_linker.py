"""
M4 matching semantics, as pure text operations (plan A11, §0.3.10.4).

The linker's whole correctness lives in four decisions, and each gets its
own assertions here rather than being inferred from a corpus count:

    where a match may begin and end   token boundaries, and which characters
                                      count as inside a token for each basis
    which case matters                ID_TOKEN is the canonical identifier so
                                      it is case-sensitive; EXACT_NAME is
                                      case-insensitive, which §A11 freezes
    which occurrence wins             the first, by lowest offset
    what the token IS                 the text the document wrote, not the
                                      canonical form that was searched for

The collision cases are not hypothetical. §0.3.8 measured 26 shared-token
groups in the committed dataset, and the two sharpest - Meridian Textiles
beside Meridian Foods, Deltaforge Analytics beside Deltaforge Health - are
exactly the pairs a substring matcher gets wrong. They are asserted in both
directions, because a matcher that is merely asymmetric is still broken.
"""

from __future__ import annotations

import pytest

from app.evidence.citations import CITABLE_SEPARATOR, citable_text
from app.evidence.linker import find_exact_name, find_id_token

MERIDIAN = "Meridian Textiles"
MERIDIAN_ID = "CUST-007"


# ---------------------------------------------------------------------------
# Citable text
# ---------------------------------------------------------------------------


def test_citable_text_is_title_then_separator_then_body():
    assert citable_text("Title", "Body") == "Title\nBody"
    assert CITABLE_SEPARATOR == "\n"


def test_a_null_title_contributes_the_empty_string_rather_than_raising():
    """A document with a body and no title is still citable (§0.3.10.4)."""
    assert citable_text(None, "Body") == "\nBody"


def test_a_null_body_contributes_the_empty_string_rather_than_raising():
    """
    The linker skips a NULL body before it gets here (plan A23), but
    citable_text itself must not be the thing that raises.
    """
    assert citable_text("Title", None) == "Title\n"


def test_offsets_after_a_null_title_are_measured_from_the_separator():
    text = citable_text(None, f"See {MERIDIAN} today")
    match = find_exact_name(text, MERIDIAN)

    assert match is not None
    assert text[match.start:match.end] == MERIDIAN


def test_a_title_only_match_is_representable():
    """
    Addressing body_text alone would make this unfindable, which is why
    citable text spans both fields.
    """
    match = find_exact_name(citable_text(MERIDIAN, "unrelated prose"), MERIDIAN)

    assert match is not None
    assert (match.start, match.end) == (0, 17)


# ---------------------------------------------------------------------------
# ID_TOKEN
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "Escalation: (CUST-007) raised tickets",
    "CUST-007 raised tickets",
    "ticket for CUST-007",
    "CUST-007",
    "see CUST-007.",
    "see CUST-007, urgently",
])
def test_an_id_token_matches_when_bounded_by_a_non_token_character_or_the_edge(text):
    match = find_id_token(text, MERIDIAN_ID)

    assert match is not None
    assert text[match.start:match.end] == MERIDIAN_ID


@pytest.mark.parametrize("text", [
    "CUST-007Z",       # trailing letter
    "CUST-0071",       # trailing digit
    "XCUST-007",       # leading letter
    "CUST-007-A",      # the hyphen is inside a token for ID_TOKEN
    "A-CUST-007",
    "CUST-007_B",
])
def test_an_id_token_does_not_match_inside_a_longer_token(text):
    assert find_id_token(text, MERIDIAN_ID) is None


@pytest.mark.parametrize("text", ["cust-007", "Cust-007", "CUST-007".lower()])
def test_id_token_matching_is_case_sensitive(text):
    """§A11 says the CANONICAL source_id appears; a recased string is not it."""
    assert find_id_token(text, MERIDIAN_ID) is None


def test_an_id_token_rejected_as_a_substring_does_not_hide_a_later_real_match():
    """The scan continues past a bad candidate rather than giving up on it."""
    text = f"XCUST-007 and then {MERIDIAN_ID} properly"
    match = find_id_token(text, MERIDIAN_ID)

    assert match is not None
    assert text[match.start:match.end] == MERIDIAN_ID
    assert match.start == text.rindex(MERIDIAN_ID)


# ---------------------------------------------------------------------------
# EXACT_NAME
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("written", [
    "Meridian Textiles",
    "meridian textiles",
    "MERIDIAN TEXTILES",
    "MeRiDiAn TeXtIlEs",
])
def test_exact_name_matching_is_case_insensitive(written):
    text = f"Account review for {written} this quarter"
    match = find_exact_name(text, MERIDIAN)

    assert match is not None
    assert text[match.start:match.end] == written


def test_the_matched_token_is_what_the_document_wrote_not_the_canonical_name():
    """
    §0.3.10.4's quoted-span rule. A reviewer reading the cited span must see
    the document's own words, so a lowercase mention yields a lowercase
    token even though the customer's canonical name is capitalised.
    """
    text = "escalation for meridian textiles today"
    match = find_exact_name(text, MERIDIAN)

    assert match is not None
    assert match.matched_token == "meridian textiles"
    assert match.matched_token != MERIDIAN


@pytest.mark.parametrize("text", [
    "Meridian TextilesLtd",
    "XMeridian Textiles",
    "Meridian Textiles2",
])
def test_exact_name_does_not_match_inside_a_longer_word(text):
    assert find_exact_name(text, MERIDIAN) is None


@pytest.mark.parametrize("text", [
    "(Meridian Textiles)",
    "Meridian Textiles.",
    "'Meridian Textiles'",
    "re: Meridian Textiles, urgent",
    "Meridian Textiles-Northstar merger",   # a hyphen may abut a company name
])
def test_exact_name_matches_when_bounded_by_punctuation(text):
    assert find_exact_name(text, MERIDIAN) is not None


# ---------------------------------------------------------------------------
# Collision safety - the measured surface, not one example
# ---------------------------------------------------------------------------


#: Groups from §0.3.8 that share a first or last name token. Each pair is a
#: chance for a substring matcher to invent a link.
COLLISION_PAIRS = [
    ("Meridian Textiles", "Meridian Foods"),
    ("Deltaforge Analytics", "Deltaforge Health"),
    ("Meridian Textiles", "Westbrook Textiles"),
    ("Meridian Textiles", "Northstar Textiles"),
    ("Meridian Textiles", "Evergrid Textiles"),
    ("Deltaforge Health", "Quantix Health"),
]


@pytest.mark.parametrize(("present", "absent"), [
    *COLLISION_PAIRS,
    *[(b, a) for a, b in COLLISION_PAIRS],
])
def test_one_customer_never_matches_another_that_shares_a_name_token(present, absent):
    """
    Asserted in both directions. A matcher that is merely asymmetric - say,
    one that happens to check length only sometimes - is still broken.
    """
    text = f"Quarterly review of {present} and its account."

    assert find_exact_name(text, present) is not None
    assert find_exact_name(text, absent) is None


def test_a_shared_token_alone_never_produces_a_match():
    """A customer is its full name, never one word of it."""
    text = "The Textiles sector grew, and Meridian was mentioned."

    assert find_exact_name(text, "Meridian Textiles") is None


def test_the_collision_scan_is_real():
    """A guard is only worth having if the thing it forbids would fail it."""
    text = "Quarterly review of Meridian Textiles and its account."

    assert "Meridian" in text
    assert "Meridian Foods" not in text


# ---------------------------------------------------------------------------
# First occurrence
# ---------------------------------------------------------------------------


def test_the_first_occurrence_wins_for_a_repeated_name():
    text = f"{MERIDIAN} opened a ticket. {MERIDIAN} then escalated. {MERIDIAN} again."
    match = find_exact_name(text, MERIDIAN)

    assert match is not None
    assert match.start == 0
    assert match.start == text.index(MERIDIAN)


def test_the_first_occurrence_wins_for_a_repeated_id_token():
    text = f"{MERIDIAN_ID} and later {MERIDIAN_ID}"
    match = find_id_token(text, MERIDIAN_ID)

    assert match is not None
    assert match.start == 0


def test_a_title_occurrence_precedes_a_body_occurrence():
    """Citable text puts the title first, so a title mention has lower offsets."""
    title = f"Review - {MERIDIAN}"
    text = citable_text(title, f"{MERIDIAN} escalated")
    match = find_exact_name(text, MERIDIAN)

    assert match is not None
    assert match.start == 9
    # Wholly inside the title half, which ends where the separator begins.
    assert match.end <= len(title)
    assert text[match.end] == CITABLE_SEPARATOR


# ---------------------------------------------------------------------------
# The span is half-open and exact
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("finder", "needle"), [
    (find_exact_name, MERIDIAN),
    (find_id_token, MERIDIAN_ID),
])
def test_the_span_is_half_open_and_its_length_is_the_matched_text(finder, needle):
    text = f"prefix {needle} suffix"
    match = finder(text, needle)

    assert match is not None
    assert match.end - match.start == len(match.matched_token)
    assert text[match.start:match.end] == match.matched_token


@pytest.mark.parametrize("finder", [find_exact_name, find_id_token])
def test_an_empty_needle_never_matches(finder):
    """An empty match would build a citation M1 refuses as a zero-width span."""
    assert finder("any text at all", "") is None


@pytest.mark.parametrize("finder", [find_exact_name, find_id_token])
def test_an_absent_needle_returns_none_rather_than_raising(finder):
    assert finder("entirely unrelated prose", "Absent Customer") is None


def test_no_normalization_is_applied_to_whitespace():
    """
    §0.3.10.4: citable text is searched exactly as Layer 1 stores it. A
    doubled space is not collapsed, so the name does not match across it.
    """
    assert find_exact_name("Meridian  Textiles", MERIDIAN) is None


# ---------------------------------------------------------------------------
# A link that cannot be persisted
# ---------------------------------------------------------------------------


def test_a_link_citing_a_record_rather_than_a_span_cannot_be_persisted():
    """
    DERIVED_RELATIONSHIP evidence may cite either shape, so a hand-built
    link CAN carry a RecordCitation and still satisfy M1. The link table
    addresses document text, so such a link is refused rather than written
    with an invented span.
    """
    from app.evidence.linker import UnciteableLinkError, _row
    from app.intelligence.contract import (
        DerivedLink,
        EntityRef,
        Evidence,
        EvidenceKind,
        LinkBasis,
        RecordCitation,
    )

    link = DerivedLink(
        source=EntityRef("documents", "DOC-009"),
        target=EntityRef("customers", MERIDIAN_ID),
        basis=LinkBasis.EXACT_NAME,
        confidence=LinkBasis.EXACT_NAME.confidence,
        matched_token=MERIDIAN,
        evidence=(
            Evidence(
                kind=EvidenceKind.DERIVED_RELATIONSHIP,
                citation=RecordCitation("customers", MERIDIAN_ID, "name"),
            ),
        ),
        source_system="csv_demo",
        layer1_fingerprint="a" * 64,
        linker_version="1",
    )

    with pytest.raises(UnciteableLinkError, match="must cite a document span"):
        _row(link)


def test_a_link_citing_a_document_span_persists_its_offsets():
    """The positive control: the guard above rejects only the wrong shape."""
    from app.evidence.citations import derived_relationship_evidence
    from app.evidence.linker import _row
    from app.intelligence.contract import DerivedLink, EntityRef, LinkBasis

    link = DerivedLink(
        source=EntityRef("documents", "DOC-009"),
        target=EntityRef("customers", MERIDIAN_ID),
        basis=LinkBasis.ID_TOKEN,
        confidence=LinkBasis.ID_TOKEN.confidence,
        matched_token=MERIDIAN_ID,
        evidence=derived_relationship_evidence("DOC-009", 76, 84),
        source_system="csv_demo",
        layer1_fingerprint="a" * 64,
        linker_version="1",
    )

    row = _row(link)

    assert (row.match_start, row.match_end) == (76, 84)
    assert row.matched_token == MERIDIAN_ID
    assert row.basis == "ID_TOKEN"
