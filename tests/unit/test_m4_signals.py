"""
S14 composition and the LinkedDocument representation (plan §0.3.6).

with_contract_documents is the one piece of M4 that M5 will call, so its
contract is tested as a pure function here rather than only observed through
a database. Four properties carry the weight:

    purity          the input SignalSet is not mutated, and every field but
                    contract_document_ids is carried through unchanged
    selection       exactly document_type == "contract", case-sensitively,
                    with NULL meaning unknown and never contract
    projection      evidence grain collapses to document grain: DOC-006
                    reaching a customer on two bases yields ONE id
    determinism     the result never depends on the order links arrive in

The last two are the reason the function exists at all. Under the link grain
of §0.3.3 a contract document legitimately produces two evidence rows, and a
tuple of ids that repeated one would be wrong in a way no single-basis
fixture would reveal.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from types import MappingProxyType

import pytest

from app.evidence.documents import (
    CONTRACT_DOCUMENT_TYPE,
    LinkedDocument,
    with_contract_documents,
)
from app.intelligence.contract import (
    DerivedLink,
    EntityRef,
    EvidenceKind,
    LinkBasis,
    SignalSet,
)
from app.intelligence.money import MoneyValue

FINGERPRINT = "a" * 64
LINKER_VERSION = "1"
MERIDIAN = "CUST-007"


def link(
    document: str,
    *,
    customer: str = MERIDIAN,
    basis: LinkBasis = LinkBasis.EXACT_NAME,
    document_type: str | None = CONTRACT_DOCUMENT_TYPE,
    matched: str = "Meridian Textiles",
    start: int = 0,
    end: int = 17,
) -> LinkedDocument:
    """One LinkedDocument, built the way the evidence layer builds them."""
    from app.evidence.citations import derived_relationship_evidence

    return LinkedDocument(
        link=DerivedLink(
            source=EntityRef("documents", document),
            target=EntityRef("customers", customer),
            basis=basis,
            confidence=basis.confidence,
            matched_token=matched,
            evidence=derived_relationship_evidence(document, start, end),
            source_system="csv_demo",
            layer1_fingerprint=FINGERPRINT,
            linker_version=LINKER_VERSION,
        ),
        document_type=document_type,
    )


def signals(**overrides: object) -> SignalSet:
    """A SignalSet with every field populated, so pass-through is observable."""
    base: dict[str, object] = {
        "open_ticket_count": 3,
        "open_high_priority_count": 2,
        "high_priority_total": 4,
        "tickets_in_lookback": 5,
        "max_tickets_in_14d_window": 3,
        "policy_escalation_state": True,
        "days_since_last_ticket": 7,
        "sla_breach_count": 3,
        "open_sla_breach_high_count": 2,
        "stale_open_ticket_count": 1,
        "dominant_ticket_category": "performance",
        "active_deals": (),
        "exposure_by_currency": MappingProxyType(
            {"INR": MoneyValue(Decimal("1000.00"), "INR")}
        ),
        "active_project_count": 2,
        "contract_document_ids": (),
        "deal_under_pressure": False,
    }
    base.update(overrides)
    return SignalSet(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# LinkedDocument
# ---------------------------------------------------------------------------


def test_a_linked_document_wraps_a_derived_link_by_composition():
    """
    It holds a DerivedLink; it does not extend one. M1 is frozen, and
    document_type is never added to DerivedLink.
    """
    linked = link("DOC-006")

    assert isinstance(linked.link, DerivedLink)
    assert not isinstance(linked, DerivedLink)
    assert not hasattr(linked.link, "document_type")


def test_a_linked_document_preserves_the_whole_link():
    """Basis, token, span, provenance: a reviewer needs all of it."""
    linked = link("DOC-006", basis=LinkBasis.ID_TOKEN, matched="CUST-007", start=76, end=84)

    assert linked.link.basis is LinkBasis.ID_TOKEN
    assert linked.link.matched_token == "CUST-007"
    assert linked.link.layer1_fingerprint == FINGERPRINT
    assert linked.link.linker_version == LINKER_VERSION
    citation = linked.link.evidence[0].citation
    assert (citation.start, citation.end) == (76, 84)
    assert linked.link.evidence[0].kind is EvidenceKind.DERIVED_RELATIONSHIP


def test_the_document_end_is_the_source_and_the_customer_end_is_the_target():
    """Frozen by M1's own contract test. Reversing them would invert every link."""
    linked = link("DOC-006")

    assert linked.link.source.entity_type == "documents"
    assert linked.link.target.entity_type == "customers"
    assert linked.document_source_id == "DOC-006"
    assert linked.customer_source_id == MERIDIAN


def test_a_linked_document_is_frozen():
    linked = link("DOC-006")

    with pytest.raises(FrozenInstanceError):
        linked.document_type = "report"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_the_contract_document_type_is_exactly_contract():
    assert CONTRACT_DOCUMENT_TYPE == "contract"


def test_a_contract_document_is_selected():
    result = with_contract_documents(signals(), (link("DOC-006"),))

    assert result.contract_document_ids == ("DOC-006",)


@pytest.mark.parametrize("document_type", [
    "report", "policy", "meeting_notes", "proposal", "runbook",
])
def test_a_document_of_another_type_contributes_nothing(document_type):
    result = with_contract_documents(
        signals(), (link("DOC-005", document_type=document_type),)
    )

    assert result.contract_document_ids == ()


@pytest.mark.parametrize("document_type", [
    "Contract", "CONTRACT", " contract", "contract ", "contract_amendment",
    "contracts", "subcontract",
])
def test_the_comparison_is_exact_and_case_sensitive(document_type):
    """
    §0.3.6: no normalization, no case folding, no stripping, no prefix or
    substring test, no synonym list. This matches M2's frozen
    document_type == POLICY_DOCUMENT_TYPE predicate.
    """
    result = with_contract_documents(
        signals(), (link("DOC-006", document_type=document_type),)
    )

    assert result.contract_document_ids == ()


def test_a_null_document_type_is_unknown_and_never_a_contract():
    """
    Stated as a property rather than left to Python's comparison semantics:
    None == "contract" is false, but the behaviour must be specified.
    """
    result = with_contract_documents(signals(), (link("DOC-006", document_type=None),))

    assert result.contract_document_ids == ()


def test_zero_contract_links_yield_an_empty_tuple_rather_than_raising():
    assert with_contract_documents(signals(), ()).contract_document_ids == ()


# ---------------------------------------------------------------------------
# Projection: evidence grain onto document grain
# ---------------------------------------------------------------------------


def test_two_evidence_links_for_one_document_yield_one_id():
    """
    The measured norm, not an edge case: DOC-006 reaches CUST-007 on both
    ID_TOKEN and EXACT_NAME, and both rows are correct evidence. S14 is a
    tuple of document ids, so it must collapse them.
    """
    links = (
        link("DOC-006", basis=LinkBasis.EXACT_NAME, matched="Meridian Textiles"),
        link("DOC-006", basis=LinkBasis.ID_TOKEN, matched="CUST-007", start=113, end=121),
    )

    result = with_contract_documents(signals(), links)

    assert result.contract_document_ids == ("DOC-006",)


def test_deduplication_is_by_document_id_and_by_nothing_else():
    """
    Two links differing in every other field still collapse, because only
    the document id is consulted.
    """
    links = (
        link("DOC-006", basis=LinkBasis.EXACT_NAME, matched="Meridian Textiles",
             start=0, end=17),
        link("DOC-006", basis=LinkBasis.ID_TOKEN, customer="CUST-021",
             matched="CUST-021", start=99, end=107),
    )

    assert with_contract_documents(signals(), links).contract_document_ids == ("DOC-006",)


def test_distinct_contract_documents_are_all_kept():
    links = (link("DOC-006"), link("DOC-002"), link("DOC-014"))

    result = with_contract_documents(signals(), links)

    assert result.contract_document_ids == ("DOC-002", "DOC-006", "DOC-014")


def test_no_basis_outranks_another():
    """
    There is no evidence priority. A document reached only by ID_TOKEN and
    one reached only by EXACT_NAME are equally present.
    """
    by_token = with_contract_documents(
        signals(), (link("DOC-006", basis=LinkBasis.ID_TOKEN, matched="CUST-007"),)
    )
    by_name = with_contract_documents(
        signals(), (link("DOC-006", basis=LinkBasis.EXACT_NAME),)
    )

    assert by_token.contract_document_ids == by_name.contract_document_ids == ("DOC-006",)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_the_result_is_ordered_lexicographically_by_document_id():
    """
    Frozen order, because M5 consumes this field (§0.3.6).

    Deliberately twelve ids rather than three. The implementation collects
    into a set before sorting, and a set of three strings can iterate in
    sorted order by chance under some PYTHONHASHSEED values - which would
    let an implementation that dropped the sort pass intermittently. With
    twelve the chance is 1/12!, so the assertion fails every run instead of
    most runs.
    """
    identifiers = [f"DOC-{number:03d}" for number in (14, 2, 6, 31, 9, 27, 1, 40, 18, 5, 22, 11)]
    links = tuple(link(identifier) for identifier in identifiers)

    result = with_contract_documents(signals(), links)

    assert result.contract_document_ids == tuple(sorted(identifiers))
    assert list(result.contract_document_ids) == sorted(result.contract_document_ids)


def test_the_result_does_not_depend_on_input_link_order():
    """
    Determinism and ordering are independent properties. Without the sort,
    two correct implementations could disagree on the same input.
    """
    links = [link("DOC-014"), link("DOC-002"), link("DOC-006")]
    forward = with_contract_documents(signals(), tuple(links))
    reversed_ = with_contract_documents(signals(), tuple(reversed(links)))

    assert forward.contract_document_ids == reversed_.contract_document_ids


def test_the_same_input_always_gives_the_same_output():
    links = (link("DOC-006"), link("DOC-002"))
    base = signals()

    assert (with_contract_documents(base, links).contract_document_ids
            == with_contract_documents(base, links).contract_document_ids)


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------


def test_the_input_signal_set_is_not_mutated():
    """SignalSet is frozen, so the result is a replacement copy."""
    before = signals()

    result = with_contract_documents(before, (link("DOC-006"),))

    assert before.contract_document_ids == ()
    assert result is not before
    assert result.contract_document_ids == ("DOC-006",)


def test_every_other_field_is_carried_through_unchanged():
    """
    S1-S13 and S15 are untouched. Compared field by field rather than by
    equality, so a future field added to SignalSet is covered automatically.
    """
    before = signals()

    result = with_contract_documents(before, (link("DOC-006"),))

    for field in before.__dataclass_fields__:
        if field == "contract_document_ids":
            continue
        assert getattr(result, field) == getattr(before, field), field


def test_the_function_is_equivalent_to_replacing_only_that_one_field():
    before = signals()

    result = with_contract_documents(before, (link("DOC-006"),))

    assert result == replace(before, contract_document_ids=("DOC-006",))


def test_an_already_populated_signal_set_is_replaced_not_merged():
    """
    The function states S14, it does not accumulate it. Merging would make
    the result depend on how many times it had been called.
    """
    before = signals(contract_document_ids=("DOC-999",))

    result = with_contract_documents(before, (link("DOC-006"),))

    assert result.contract_document_ids == ("DOC-006",)


def test_applying_it_twice_changes_nothing_further():
    base = signals()
    links = (link("DOC-006"),)

    once = with_contract_documents(base, links)
    twice = with_contract_documents(once, links)

    assert once == twice


def test_the_composition_touches_no_database_and_no_clock():
    """
    Pure and total: it is handed a SignalSet and links, and nothing else.
    That is the property which makes M5's deferred invocation design safe.
    """
    import ast
    import inspect
    import textwrap

    from app.evidence import documents as module

    signature = inspect.signature(with_contract_documents)
    assert list(signature.parameters) == ["signals", "links"]

    # The body only. Its docstring says it takes no session, and a raw text
    # scan would trip on the promise instead of checking it.
    function = ast.parse(
        textwrap.dedent(inspect.getsource(module.with_contract_documents))
    ).body[0]
    assert isinstance(function, ast.FunctionDef)
    body = ast.unparse(ast.Module(body=function.body[1:], type_ignores=[]))

    for forbidden in ("session", "select(", "datetime", "now(", "random"):
        assert forbidden not in body, forbidden
