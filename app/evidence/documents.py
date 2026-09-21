"""
Reading derived links back, and the S14 composition (VS-01 M4, §0.3.10.2, §0.3.6).

**This module is the sole place a DerivedLink or a LinkedDocument is built
from persisted data** (§0.3.11 D-M4-B1). The repository performs the query
and the `documents` join and returns rows; reconstruction is domain work and
lives here, because doing it in the repository would make app/persistence
depend on app.intelligence, which §0.3.9 T2 forbids. There are still exactly
two modules and one query, so the single-place property §0.3.10.2 protects
holds — it names this module rather than the repository.

LinkedDocument **wraps** a frozen M1 DerivedLink by composition. It does not
extend, subclass, widen or modify it, and `document_type` is never added to
DerivedLink: M1 is frozen, and composition rather than extension is the
whole reason a second type exists. `document_type` is read from Layer 1 at
join time and never stored on the link row, so a Layer 1 correction is
reflected without re-deriving anything.

`documents_for()` reads persisted rows. **It does not re-run the linker** —
the linker derives, the repository persists, and this reads back.

**S14 — with_contract_documents.** M4 owns the composition function; **M5
owns invoking it** when it builds the executive context, and nothing in M4's
own pipeline calls it. The projection is deliberately narrow: a link
contributes only its document id, and only after `document_type` has decided
whether it takes part at all. Basis, confidence, matched token, evidence,
source system, fingerprint and linker version are **not consulted**, which is
what makes the absence of evidence priority structural rather than merely
promised. One customer-document pair legitimately has more than one evidence
link — DOC-006 reaches CUST-007 on both bases, and both rows are correct and
both are kept — so the function projects evidence grain onto document grain
by deduplicating on document id alone.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from app.evidence.citations import derived_relationship_evidence
from app.intelligence import Scope
from app.intelligence.contract import DerivedLink, EntityRef, LinkBasis, SignalSet
from app.persistence.repositories.document_links import PersistedLink, read_links

#: Layer 1 entity types a link's two endpoints address.
DOCUMENTS = "documents"
CUSTOMERS = "customers"

#: The document type S14 selects. Exact, case-sensitive equality and nothing
#: else, matching M2's frozen POLICY_DOCUMENT_TYPE predicate: "Contract",
#: "CONTRACT", " contract" and "contract_amendment" are not contract
#: documents, and neither is NULL.
CONTRACT_DOCUMENT_TYPE = "contract"


@dataclass(frozen=True)
class LinkedDocument:
    """
    One derived link, together with the Layer 1 type of the document it cites.

    Composition, not extension: the frozen M1 DerivedLink is held whole, and
    document_type sits beside it. It is nullable because Layer 1's column is.
    """

    link: DerivedLink
    document_type: str | None

    @property
    def document_source_id(self) -> str:
        """The document this link cites. link.source is the document end."""
        return self.link.source.source_id

    @property
    def customer_source_id(self) -> str:
        """The customer this link names. link.target is the customer end."""
        return self.link.target.source_id

    @property
    def is_contract(self) -> bool:
        """Whether S14 counts this document. NULL is unknown, and never a contract."""
        return self.document_type == CONTRACT_DOCUMENT_TYPE


def documents_for(
    session: Session, scope: Scope, customer_source_id: str
) -> tuple[LinkedDocument, ...]:
    """
    Every persisted derived link for one customer, as LinkedDocument values.

    Reads persisted rows; it never derives. A customer whose links were
    written under a superseded snapshot or linker still has those rows, so
    the result is everything persisted for that customer rather than only
    the current snapshot's links — the stamps on each link say which is
    which.
    """
    return tuple(
        linked_document(row) for row in read_links(session, scope.source_system, customer_source_id)
    )


def linked_document(row: PersistedLink) -> LinkedDocument:
    """
    Rebuild one LinkedDocument, and the frozen M1 link inside it, from a row.

    Confidence is taken from the basis rather than persisted, so a row
    cannot assert a standing its basis does not carry; M1 refuses a link
    that tries.
    """
    basis = LinkBasis(row.basis)
    return LinkedDocument(
        link=DerivedLink(
            source=EntityRef(DOCUMENTS, row.document_source_id),
            target=EntityRef(CUSTOMERS, row.customer_source_id),
            basis=basis,
            confidence=basis.confidence,
            matched_token=row.matched_token,
            evidence=derived_relationship_evidence(
                row.document_source_id, row.match_start, row.match_end
            ),
            source_system=row.source_system,
            layer1_fingerprint=row.layer1_fingerprint,
            linker_version=row.linker_version,
        ),
        document_type=row.document_type,
    )


def with_contract_documents(
    signals: SignalSet, links: Sequence[LinkedDocument]
) -> SignalSet:
    """
    A copy of a SignalSet carrying S14, the customer's contract document ids.

    Pure and total: it takes no session, reads no clock, and returns a new
    frozen SignalSet with every other field carried through unchanged. Zero
    contract links yield an empty tuple rather than an error.

    Ids are deduplicated by document id and by nothing else, then ordered
    lexicographically ascending — a sort key over ids, never a priority over
    evidence. The order is frozen because M5 consumes this field, and
    determinism alone would let two correct implementations disagree.

    M4 defines and proves this function. **M4 never calls it in production**;
    M5 does, when it constructs the executive context.
    """
    document_ids = {link.document_source_id for link in links if link.is_contract}
    return replace(signals, contract_document_ids=tuple(sorted(document_ids)))
