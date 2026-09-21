"""
Derived document evidence (VS-01 M4).

The only mechanism in VS-01 by which a Document and a Customer are ever
related. There is no canonical FK, no source key, no composable ownership
path and no relationship query that reaches one from the other, so every
customer-document association in a brief carries a basis, a matched token
and a citation into the text, or it does not exist.

Public API:
    citable_text             title, a newline, then body: the one string
                             every offset in this package indexes.
    derive_links             ID_TOKEN and EXACT_NAME matching over one
                             Layer 1 snapshot. No TOPIC, no embeddings, no
                             similarity, no fuzzy matching.
    persist_links            write derived links; re-deriving an unchanged
                             snapshot inserts nothing.
    documents_for            read persisted links back for one customer.
    LinkedDocument           a frozen M1 DerivedLink composed with Layer 1's
                             document_type.
    with_contract_documents  S14: a new SignalSet carrying the customer's
                             contract document ids. M4 defines and proves
                             it; M5 invokes it.
    resolve_document_citation  read a cited span back out of Layer 1, so a
                             citation can be checked rather than trusted.

The import graph is a DAG: app.intelligence (M1) is read by app.relationships
(M2), and both may be read here. Nothing below this package names it —
app.relationships must not import app.evidence, M3 must not import
app.evidence, and app.persistence imports neither app.evidence nor
app.intelligence (plan §0.3.11). Those directions are asserted by tests on
both sides, so neither package can absorb the other's responsibility.
"""

from app.evidence.citations import (
    CITABLE_SEPARATOR,
    CitationResolutionError,
    citable_text,
    derived_relationship_evidence,
    document_citation,
    resolve_document_citation,
)
from app.evidence.documents import (
    CONTRACT_DOCUMENT_TYPE,
    LinkedDocument,
    documents_for,
    linked_document,
    with_contract_documents,
)
from app.evidence.linker import (
    CUSTOMERS,
    DOCUMENTS,
    TextMatch,
    UnciteableLinkError,
    derive_and_persist,
    derive_links,
    find_exact_name,
    find_id_token,
    persist_links,
)

__all__ = [
    "CITABLE_SEPARATOR",
    "CONTRACT_DOCUMENT_TYPE",
    "CUSTOMERS",
    "DOCUMENTS",
    "CitationResolutionError",
    "LinkedDocument",
    "TextMatch",
    "UnciteableLinkError",
    "citable_text",
    "derive_and_persist",
    "derive_links",
    "derived_relationship_evidence",
    "document_citation",
    "documents_for",
    "find_exact_name",
    "find_id_token",
    "linked_document",
    "persist_links",
    "resolve_document_citation",
    "with_contract_documents",
]
