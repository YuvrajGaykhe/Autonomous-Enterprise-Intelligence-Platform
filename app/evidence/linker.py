"""
Deterministic Document to Customer linking (VS-01 M4, plan A11, §0.3.10.4).

Two mechanisms, and no others:

    ID_TOKEN     the canonical customer source_id appears as a whole token
                 in the document's citable text, case-sensitively. §A11 says
                 the *canonical* source_id appears, and a differently cased
                 string is not that identifier.
    EXACT_NAME   the customer's full name appears at token boundaries,
                 case-insensitively.

There is no TOPIC rule, no embedding, no similarity, no keyword expansion
and no fuzzy matching. §0.3.1 removed TOPIC from VS-01 on evidence, not on
taste: `documents` carries no topic field, `document_type` and ticket
`category` are disjoint vocabularies, and a topical overlap asserts no token
and no span, so it cannot satisfy the project's grounding guarantee.
`LinkBasis.TOPIC` stays in M1's frozen contract as reserved vocabulary and
is never constructed here.

**Substring matching is forbidden**, and the dataset is why. It holds
"Meridian Textiles" beside "Meridian Foods", "Westbrook Textiles",
"Northstar Textiles" and "Evergrid Textiles", and "Deltaforge Analytics"
beside "Deltaforge Health" — 26 shared-token groups in total (§0.3.8).
Requiring a non-word character on both sides of a match answers all of them,
measured, with zero false links. A customer never matches merely because one
token of its name appears inside another customer's name.

**Citable text** is title, a newline, then body, and every offset this
module produces indexes that string and no other. It is defined in
citations.py, because it exists for the citation rather than for the match:
one definition serves both the persisted columns and the citation, so the
two can never diverge.

**First occurrence wins.** A repeated name yields one row per
(document, customer, basis), carrying the lowest-offset span. DOC-009 says
"Meridian Textiles" three times and CUST-007 once, and persists exactly two
rows for CUST-007.

**No link crosses a source system.** Documents and customers are both read
within one Scope's source_system, so a cross-source pair is never even
considered — isolation by construction, not by a filter someone can forget.

Nothing here is normalized: no Unicode normalization, no case folding beyond
EXACT_NAME's own comparison, no whitespace collapsing, no punctuation
stripping and no accent folding. Citable text is searched exactly as Layer 1
stores it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evidence.citations import citable_text, derived_relationship_evidence
from app.intelligence import Scope
from app.intelligence.config import RiskRulesConfig, default_risk_rules
from app.intelligence.contract import (
    DerivedLink,
    DocumentCitation,
    EntityRef,
    LinkBasis,
)
from app.persistence.models import Customer, Document
from app.persistence.repositories.document_links import LinkRow, insert_links

#: Layer 1 entity types the link's two endpoints address.
DOCUMENTS = "documents"
CUSTOMERS = "customers"

#: What counts as *inside* a token for each basis, so a match must be
#: bounded by something else or by the edge of the text. The hyphen is a
#: token character for ID_TOKEN, which is what stops `CUST-007` matching
#: inside `CUST-0071`; it is not one for EXACT_NAME, so a hyphen may
#: legitimately abut a company name.
ID_TOKEN_CHARACTER = re.compile(r"[A-Za-z0-9_-]")
NAME_CHARACTER = re.compile(r"[A-Za-z0-9]")


class UnciteableLinkError(Exception):
    """A link that cannot be persisted, because its evidence names no span."""


@dataclass(frozen=True)
class TextMatch:
    """One occurrence, as a half-open span plus the text the document wrote."""

    start: int
    end: int
    matched_token: str


def find_id_token(text: str, source_id: str) -> TextMatch | None:
    """First whole-token, case-sensitive occurrence of a canonical source id."""
    return _first_occurrence(text, source_id, ID_TOKEN_CHARACTER, fold_case=False)


def find_exact_name(text: str, name: str) -> TextMatch | None:
    """First token-bounded, case-insensitive occurrence of a full customer name."""
    return _first_occurrence(text, name, NAME_CHARACTER, fold_case=True)


def derive_links(
    session: Session,
    scope: Scope,
    *,
    config: RiskRulesConfig | None = None,
) -> tuple[DerivedLink, ...]:
    """
    Every link the two mechanisms find in one Layer 1 snapshot.

    A document whose body_text is NULL is skipped entirely (plan A23); a
    document whose title is NULL is not, because a body still carries
    citable text. Both bases are tried independently against every customer,
    and a pair matching on both yields two links — they do not compete, and
    no precedence between them exists or may be introduced.
    """
    rules = config if config is not None else default_risk_rules()
    documents = session.execute(
        select(Document.source_id, Document.title, Document.body_text)
        .where(
            Document.source_system == scope.source_system,
            Document.source_entity == DOCUMENTS,
        )
        .order_by(Document.source_id)
    ).all()
    customers = session.execute(
        select(Customer.source_id, Customer.name)
        .where(
            Customer.source_system == scope.source_system,
            Customer.source_entity == CUSTOMERS,
        )
        .order_by(Customer.source_id)
    ).all()

    links: list[DerivedLink] = []
    for document_source_id, title, body_text in documents:
        if body_text is None:
            continue
        text = citable_text(title, body_text)
        for customer_source_id, name in customers:
            for basis, match in (
                (LinkBasis.ID_TOKEN, find_id_token(text, customer_source_id)),
                (LinkBasis.EXACT_NAME, find_exact_name(text, name)),
            ):
                if match is None:
                    continue
                links.append(
                    _link(
                        scope=scope,
                        linker_version=rules.linker_version,
                        document_source_id=document_source_id,
                        customer_source_id=customer_source_id,
                        basis=basis,
                        match=match,
                    )
                )
    return tuple(links)


def persist_links(
    session: Session, scope: Scope, links: Sequence[DerivedLink]
) -> int:
    """
    Persist derived links, returning how many rows were actually inserted.

    The linker derives and the repository persists. Re-deriving over an
    unchanged snapshot with an unchanged linker inserts nothing, because
    every row conflicts on the identity constraint; a changed fingerprint or
    linker version appends a new set and leaves the old rows attributable to
    the snapshot and linker that produced them.
    """
    return insert_links(session, scope.source_system, [_row(link) for link in links])


def derive_and_persist(
    session: Session, scope: Scope, *, config: RiskRulesConfig | None = None
) -> int:
    """Derive every link in scope and write it. Returns rows actually inserted."""
    return persist_links(session, scope, derive_links(session, scope, config=config))


def _link(
    *,
    scope: Scope,
    linker_version: str,
    document_source_id: str,
    customer_source_id: str,
    basis: LinkBasis,
    match: TextMatch,
) -> DerivedLink:
    """One derived link, stamped with the snapshot and linker that produced it."""
    return DerivedLink(
        source=EntityRef(DOCUMENTS, document_source_id),
        target=EntityRef(CUSTOMERS, customer_source_id),
        basis=basis,
        # Confidence follows from the basis and is never chosen per link;
        # M1 refuses a link that claims otherwise.
        confidence=basis.confidence,
        matched_token=match.matched_token,
        evidence=derived_relationship_evidence(
            document_source_id, match.start, match.end
        ),
        source_system=scope.source_system,
        layer1_fingerprint=scope.layer1_fingerprint,
        linker_version=linker_version,
    )


def _row(link: DerivedLink) -> LinkRow:
    """
    A derived link as the columns that persist it.

    The span comes from the link's own citation, so a persisted row and the
    citation a reviewer resolves can never disagree. DERIVED_RELATIONSHIP
    evidence may cite either shape, so a link carrying a record citation is
    refused here rather than persisted with an invented span: the link table
    addresses document text, and a record field has no offsets.
    """
    citation = link.evidence[0].citation
    if not isinstance(citation, DocumentCitation):
        raise UnciteableLinkError(
            f"a persisted link must cite a document span, but the link from "
            f"{link.source.source_id} to {link.target.source_id} cites "
            f"{type(citation).__name__}"
        )
    return LinkRow(
        document_source_id=link.source.source_id,
        customer_source_id=link.target.source_id,
        basis=str(link.basis),
        matched_token=link.matched_token,
        match_start=citation.start,
        match_end=citation.end,
        linker_version=link.linker_version,
        layer1_fingerprint=link.layer1_fingerprint,
    )


def _first_occurrence(
    text: str, needle: str, inside_token: re.Pattern[str], *, fold_case: bool
) -> TextMatch | None:
    """
    The lowest-offset token-bounded occurrence of needle, or None.

    Candidates are scanned in order and the first correctly bounded one
    wins, so a rejected substring hit never hides a genuine match later in
    the text.
    """
    if not needle:
        return None
    haystack = text.lower() if fold_case else text
    target = needle.lower() if fold_case else needle
    for candidate in re.finditer(re.escape(target), haystack):
        start, end = candidate.start(), candidate.end()
        if _bounded(text, start, end, inside_token):
            # Sliced from the original text, so the token is what the
            # document wrote, not the canonical form that was searched for.
            return TextMatch(start=start, end=end, matched_token=text[start:end])
    return None


def _bounded(text: str, start: int, end: int, inside_token: re.Pattern[str]) -> bool:
    """Whether a span is a whole token: edge of text, or a non-token character."""
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return _outside_token(before, inside_token) and _outside_token(after, inside_token)


def _outside_token(character: str, inside_token: re.Pattern[str]) -> bool:
    """The edge of the text bounds a token, and so does any non-token character."""
    return character == "" or inside_token.fullmatch(character) is None
