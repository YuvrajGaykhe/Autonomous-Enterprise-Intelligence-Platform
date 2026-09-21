"""
Citation construction and resolution for derived links (VS-01 M4, §0.3.10.1).

A link that cannot be checked by hand is not evidence. This module builds
the citation every derived link carries, and resolves one back to the text
it names, so plan A25 test 8 — *every citation in every assessment and every
generated brief resolves* — is answerable rather than aspirational.

**The evidence kind is DERIVED_RELATIONSHIP**, and that is fixed by M1 rather
than chosen here: EvidenceKind's own docstring glosses it as *a link this
system inferred*, and M1's committed contract test pins a DerivedLink's
serialised evidence to `{"kind": "DERIVED_RELATIONSHIP", "citation":
{"kind": "document", ...}}`. Any other kind would fail a frozen test.

**Spans, never prose.** The hashed decision payload's evidence contract is
`{kind, document_id, start, end}` — a span, and never the document's text.
Rendering that span as quoted, escaped, length-capped narrative is a view
over the evidence and belongs to the milestone that renders (§0.3.10.5); the
only text resolution returns here is the matched token itself, whose length
is bounded by the match. No second evidence representation is introduced.

**Citable text is defined here**, not in the linker, because it exists for
the citation rather than for the match. M1's DocumentCitation is
`(document_id, start, end)` with no field discriminator, so a span can
address only one text per document; citable text is that text, and the
linker indexes it because a citation must. Defining it here also keeps the
dependency one-way: the linker reads this module, and this module reads no
part of the linker.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence import Scope
from app.intelligence.contract import DocumentCitation, Evidence, EvidenceKind
from app.persistence.models import Document

#: Layer 1 entity type a document citation addresses.
DOCUMENTS = "documents"

#: The separator between a document's title and its body in citable text.
CITABLE_SEPARATOR = "\n"


def citable_text(title: str | None, body_text: str | None) -> str:
    """
    The one string every M4 offset indexes.

    A NULL title contributes the empty string rather than raising: a
    document with a body and no title is still citable, and its body offsets
    simply start after the separator. Addressing body_text alone would make
    a title-only match unrepresentable, since a citation span must be
    non-empty.
    """
    return (title or "") + CITABLE_SEPARATOR + (body_text or "")


class CitationResolutionError(Exception):
    """
    A citation names a document or a span that cannot be read back.

    Raised rather than returning an empty string: a citation that silently
    resolves to nothing is exactly the failure the grounding guarantee
    exists to prevent.
    """


def document_citation(document_source_id: str, start: int, end: int) -> DocumentCitation:
    """One half-open span of one document's citable text."""
    return DocumentCitation(document_id=document_source_id, start=start, end=end)


def derived_relationship_evidence(
    document_source_id: str, start: int, end: int
) -> tuple[Evidence, ...]:
    """The evidence tuple every derived link carries: one document span."""
    return (
        Evidence(
            kind=EvidenceKind.DERIVED_RELATIONSHIP,
            citation=document_citation(document_source_id, start, end),
        ),
    )


def resolve_document_citation(
    session: Session, scope: Scope, citation: DocumentCitation
) -> str:
    """
    The exact text a citation names, read back from Layer 1.

    Resolution is against the same citable text the linker indexed, so a
    link's resolved text equals its matched_token whenever the snapshot has
    not moved. A citation naming a document outside the scope, or a span
    past the end of the text, is refused rather than truncated.
    """
    row = session.execute(
        select(Document.title, Document.body_text).where(
            Document.source_system == scope.source_system,
            Document.source_entity == DOCUMENTS,
            Document.source_id == citation.document_id,
        )
    ).one_or_none()
    if row is None:
        raise CitationResolutionError(
            f"citation names document {citation.document_id!r}, which is not in "
            f"source_system {scope.source_system!r}"
        )
    title, body_text = row
    text = citable_text(title, body_text)
    if citation.end > len(text):
        raise CitationResolutionError(
            f"citation [{citation.start}, {citation.end}) runs past the end of "
            f"{citation.document_id}'s citable text, which is {len(text)} characters"
        )
    return text[citation.start:citation.end]
