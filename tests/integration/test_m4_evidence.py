"""
M4 derivation, persistence and read-back against a real database.

The demo dataset is ingested by the clean full-dataset path, so every number
asserted here is measured rather than remembered. Four kinds of test:

Corpus: the whole 11-row expectation of §0.3.8, asserted as a set rather
than customer by customer, so a link the linker invents for one of the other
47 customers fails the build. DOC-009's spans are pinned literally, because
§0.3.10.4 says they are uniquely determined and a matcher that got the
offsets right by luck would still be wrong.

Persistence identity: re-deriving inserts nothing; a changed fingerprint
appends; a changed linker version appends; nothing is ever updated or
deleted. These are the properties the unique key exists for, and they are
asserted through the key rather than through an application-level check.

Read-back: documents_for reads persisted rows and does not re-run the
linker, document_type comes from Layer 1 rather than the link row, and every
persisted span still resolves to its matched token.

Isolation: a second source system is written straight into the test
database, because the demo dataset holds only one. No link crosses it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors import CsvConnector, CsvConnectorConfig, SourceConnector
from app.evidence.citations import (
    CitationResolutionError,
    citable_text,
    resolve_document_citation,
)
from app.evidence.documents import (
    CONTRACT_DOCUMENT_TYPE,
    documents_for,
    with_contract_documents,
)
from app.evidence.linker import derive_and_persist, derive_links
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence import Scope, resolve_scope
from app.intelligence.config import default_risk_rules
from app.intelligence.contract import DocumentCitation, LinkBasis
from app.persistence.models import Customer, Document
from app.persistence.models.document_customer_link import DocumentCustomerLink
from app.persistence.repositories.document_links import LinkRow, insert_links, read_links

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
SOURCE_SYSTEM = "csv_demo"
OTHER_SOURCE_SYSTEM = "other_demo"
ACCEPTANCE_AS_OF = date(2026, 9, 18)

MERIDIAN = "CUST-007"
UNITY = "CUST-015"
DELTAFORGE = "CUST-021"

#: §0.3.8, measured against the committed 233-row dataset. Eleven rows.
EXPECTED_LINKS = {
    ("DOC-005", MERIDIAN, "EXACT_NAME"),
    ("DOC-005", MERIDIAN, "ID_TOKEN"),
    ("DOC-006", MERIDIAN, "EXACT_NAME"),
    ("DOC-006", MERIDIAN, "ID_TOKEN"),
    ("DOC-009", MERIDIAN, "EXACT_NAME"),
    ("DOC-009", MERIDIAN, "ID_TOKEN"),
    ("DOC-004", UNITY, "EXACT_NAME"),
    ("DOC-008", UNITY, "EXACT_NAME"),
    ("DOC-007", DELTAFORGE, "EXACT_NAME"),
    ("DOC-007", DELTAFORGE, "ID_TOKEN"),
    ("DOC-011", DELTAFORGE, "EXACT_NAME"),
}
EXPECTED_ROW_COUNT = 11

#: The three customers any link at all belongs to. The other 47 have none.
LINKED_CUSTOMERS = {MERIDIAN, UNITY, DELTAFORGE}

#: §0.3.10.4. DOC-009 says "Meridian Textiles" three times and CUST-007 once;
#: under the first-occurrence rule exactly these two rows survive.
DOC_009_ROWS = {
    ("EXACT_NAME", "Meridian Textiles", 23, 40),
    ("ID_TOKEN", "CUST-007", 76, 84),
}

ALTERNATE_FINGERPRINT = "b" * 64


def _csv_connector() -> SourceConnector:
    config = CsvConnectorConfig.from_yaml(REPO / "config" / "connectors" / "csv_demo.yaml")
    config.data_directory = str(DEMO_DIR)
    return CsvConnector(config)


@pytest.fixture
def demo(e1_sessions: sessionmaker[Session]) -> sessionmaker[Session]:
    """The clean full-dataset path of plan A28: 233 rows, 7 entity types, 0 rejected."""
    counts = run_ingestion(_csv_connector(), e1_sessions, IngestionRequest()).counts
    assert counts.rejected == 0
    return e1_sessions


@pytest.fixture
def scope(demo: sessionmaker[Session]) -> Scope:
    with demo() as session:
        return resolve_scope(session, source_system=SOURCE_SYSTEM, as_of=ACCEPTANCE_AS_OF)


@pytest.fixture
def linked(demo: sessionmaker[Session], scope: Scope) -> sessionmaker[Session]:
    """The demo dataset with every derived link persisted."""
    with demo.begin() as session:
        derive_and_persist(session, scope)
    return demo


def _triples(links) -> set[tuple[str, str, str]]:
    return {
        (link.source.source_id, link.target.source_id, str(link.basis)) for link in links
    }


def _persisted_triples(sessions) -> set[tuple[str, str, str]]:
    with sessions() as session:
        rows = session.execute(
            select(
                Document.source_id, Customer.source_id, DocumentCustomerLink.basis
            )
            .join(Document, DocumentCustomerLink.document_id == Document.id)
            .join(Customer, DocumentCustomerLink.customer_id == Customer.id)
        ).all()
    return {tuple(row) for row in rows}


def _row_count(sessions) -> int:
    with sessions() as session:
        return session.scalar(select(func.count()).select_from(DocumentCustomerLink)) or 0


# ---------------------------------------------------------------------------
# The measured corpus
# ---------------------------------------------------------------------------


def test_the_linker_derives_exactly_the_measured_eleven_links(demo, scope):
    """
    §0.3.8 in full. Asserted as set equality, not as a count and three spot
    checks: a spurious link for any of the other 47 customers fails here.
    """
    links = derive_links_in(demo, scope)

    assert _triples(links) == EXPECTED_LINKS
    assert len(links) == EXPECTED_ROW_COUNT


def derive_links_in(sessions, scope: Scope):
    with sessions() as session:
        return derive_links(session, scope)


def test_meridian_matches_all_three_documents_on_both_bases(demo, scope):
    """
    The §0.3.2 correction: EXACT_NAME includes DOC-005, whose body names
    "Meridian Textiles" as well as CUST-007. The two bases agree here, and
    both rows are kept because neither outranks the other.
    """
    links = derive_links_in(demo, scope)
    by_basis = {
        basis: {
            link.source.source_id for link in links
            if link.basis is basis and link.target.source_id == MERIDIAN
        }
        for basis in (LinkBasis.ID_TOKEN, LinkBasis.EXACT_NAME)
    }

    assert by_basis[LinkBasis.ID_TOKEN] == {"DOC-005", "DOC-006", "DOC-009"}
    assert by_basis[LinkBasis.EXACT_NAME] == {"DOC-005", "DOC-006", "DOC-009"}


def test_unity_pharma_is_reached_only_by_name(demo, scope):
    """CUST-015 is named but never id-referenced in the corpus."""
    links = derive_links_in(demo, scope)
    unity = {(link.source.source_id, str(link.basis))
             for link in links if link.target.source_id == UNITY}

    assert unity == {("DOC-004", "EXACT_NAME"), ("DOC-008", "EXACT_NAME")}


def test_deltaforge_is_reached_by_both_in_one_document_and_by_name_in_another(demo, scope):
    links = derive_links_in(demo, scope)
    deltaforge = {(link.source.source_id, str(link.basis))
                  for link in links if link.target.source_id == DELTAFORGE}

    assert deltaforge == {
        ("DOC-007", "EXACT_NAME"), ("DOC-007", "ID_TOKEN"), ("DOC-011", "EXACT_NAME"),
    }


def test_the_other_forty_seven_customers_acquire_no_link(demo, scope):
    """Including every customer sharing a name token with a linked one."""
    links = derive_links_in(demo, scope)

    assert {link.target.source_id for link in links} == LINKED_CUSTOMERS


@pytest.mark.parametrize("customer", ["CUST-038", "CUST-027", "CUST-039"])
def test_a_collision_customer_acquires_no_link(demo, scope, customer):
    """
    Plan A25 test 7, widened. CUST-038 is Meridian Foods, CUST-027 is
    Deltaforge Health and CUST-039 is Evergrid Textiles: each shares a name
    token with a genuinely linked customer, and substring matching would
    give all three a link they must not have.
    """
    links = derive_links_in(demo, scope)

    assert all(link.target.source_id != customer for link in links)


@pytest.mark.parametrize("document", ["DOC-001", "DOC-002", "DOC-003", "DOC-010", "DOC-012"])
def test_a_document_that_names_no_customer_is_linked_to_none(demo, scope, document):
    """
    DOC-010 in particular: the nightly-sync postmortem is the document
    §0.3.1 removed TOPIC over. It stays what the data says it is - a report
    naming no customer.
    """
    links = derive_links_in(demo, scope)

    assert all(link.source.source_id != document for link in links)


# ---------------------------------------------------------------------------
# DOC-009, the adversarial fixture
# ---------------------------------------------------------------------------


def test_doc_009_persists_exactly_two_rows_at_the_pinned_offsets(linked, scope):
    """
    §0.3.10.4's literal expectation. Three name occurrences and one id
    occurrence collapse to one row per basis, at uniquely determined spans.
    """
    with linked() as session:
        rows = session.execute(
            select(
                DocumentCustomerLink.basis,
                DocumentCustomerLink.matched_token,
                DocumentCustomerLink.match_start,
                DocumentCustomerLink.match_end,
            )
            .join(Document, DocumentCustomerLink.document_id == Document.id)
            .where(Document.source_id == "DOC-009")
        ).all()

    assert {tuple(row) for row in rows} == DOC_009_ROWS


def test_doc_009_really_does_repeat_the_name_three_times(demo):
    """
    The fixture assumption behind the test above. If DOC-009 stopped
    repeating the name, the first-occurrence rule would still be satisfied
    trivially and the test would no longer prove anything.
    """
    with demo() as session:
        title, body = session.execute(
            select(Document.title, Document.body_text).where(
                Document.source_system == SOURCE_SYSTEM, Document.source_id == "DOC-009"
            )
        ).one()
    text = citable_text(title, body)

    assert text.lower().count("meridian textiles") == 3
    assert text.count("CUST-007") == 1


def test_the_id_token_span_is_the_only_one_and_the_name_span_is_the_earliest(demo):
    """The two rows are not merely valid: no other offsets satisfy the rules."""
    with demo() as session:
        title, body = session.execute(
            select(Document.title, Document.body_text).where(
                Document.source_system == SOURCE_SYSTEM, Document.source_id == "DOC-009"
            )
        ).one()
    text = citable_text(title, body)

    name_starts = [i for i in range(len(text)) if text.lower().startswith("meridian textiles", i)]
    assert name_starts == [23, 57, 260]
    assert min(name_starts) == 23
    assert text.index("CUST-007") == 76


# ---------------------------------------------------------------------------
# Every persisted span resolves to its matched token
# ---------------------------------------------------------------------------


def test_every_persisted_span_slices_back_to_its_matched_token(linked, scope):
    """
    §0.3.10.4's quoted-span invariant, over every row rather than a sample:
    citable_text[start:end] == matched_token.
    """
    with linked() as session:
        rows = session.execute(
            select(
                Document.title,
                Document.body_text,
                DocumentCustomerLink.matched_token,
                DocumentCustomerLink.match_start,
                DocumentCustomerLink.match_end,
            ).join(Document, DocumentCustomerLink.document_id == Document.id)
        ).all()

    assert len(rows) == EXPECTED_ROW_COUNT
    for title, body, token, start, end in rows:
        assert citable_text(title, body)[start:end] == token


def test_every_link_citation_resolves_to_its_matched_token(linked, scope):
    """Plan A25 test 8, for the links M4 owns."""
    with linked() as session:
        for customer in sorted(LINKED_CUSTOMERS):
            for linked_document in documents_for(session, scope, customer):
                citation = linked_document.link.evidence[0].citation
                resolved = resolve_document_citation(session, scope, citation)
                assert resolved == linked_document.link.matched_token


def test_a_citation_naming_an_absent_document_is_refused(demo, scope):
    with demo() as session:
        with pytest.raises(CitationResolutionError, match="DOC-999"):
            resolve_document_citation(session, scope, DocumentCitation("DOC-999", 0, 5))


def test_a_citation_running_past_the_end_of_the_text_is_refused(demo, scope):
    """Refused rather than silently truncated to whatever happens to be there."""
    with demo() as session:
        with pytest.raises(CitationResolutionError, match="runs past the end"):
            resolve_document_citation(session, scope, DocumentCitation("DOC-009", 0, 99999))


def test_a_citation_ending_one_character_past_the_text_is_refused(demo, scope):
    """
    The boundary, not a wildly out-of-range value: a span ending at
    len(text) + 1 is out of range and must be refused, while one ending
    exactly at len(text) is the last legal span.
    """
    with demo() as session:
        title, body = session.execute(
            select(Document.title, Document.body_text).where(
                Document.source_system == SOURCE_SYSTEM, Document.source_id == "DOC-009"
            )
        ).one()
        length = len(citable_text(title, body))

        assert resolve_document_citation(
            session, scope, DocumentCitation("DOC-009", length - 5, length)
        )
        with pytest.raises(CitationResolutionError, match="runs past the end"):
            resolve_document_citation(
                session, scope, DocumentCitation("DOC-009", length - 5, length + 1)
            )


# ---------------------------------------------------------------------------
# Persistence identity
# ---------------------------------------------------------------------------


def test_deriving_and_persisting_writes_exactly_eleven_rows(demo, scope):
    with demo.begin() as session:
        inserted = derive_and_persist(session, scope)

    assert inserted == EXPECTED_ROW_COUNT
    assert _row_count(demo) == EXPECTED_ROW_COUNT
    assert _persisted_triples(demo) == EXPECTED_LINKS


def test_re_deriving_with_identical_inputs_inserts_nothing(linked, scope):
    """
    Plan A27.8. Satisfied by the unique constraint, not by an
    application-level pre-existence check.
    """
    with linked.begin() as session:
        inserted = derive_and_persist(session, scope)

    assert inserted == 0
    assert _row_count(linked) == EXPECTED_ROW_COUNT


def test_re_deriving_three_times_still_inserts_nothing(linked, scope):
    for _ in range(3):
        with linked.begin() as session:
            assert derive_and_persist(session, scope) == 0

    assert _row_count(linked) == EXPECTED_ROW_COUNT


def test_a_changed_fingerprint_appends_and_retains_the_earlier_rows(linked, scope):
    """
    §0.3.4: a link derived under a superseded snapshot stays attributable to
    it. The old rows are retained, not rewritten.
    """
    moved = Scope(
        source_system=scope.source_system,
        as_of=scope.as_of,
        layer1_fingerprint=ALTERNATE_FINGERPRINT,
        as_of_source=scope.as_of_source,
        entity_counts=scope.entity_counts,
    )

    with linked.begin() as session:
        inserted = derive_and_persist(session, moved)

    assert inserted == EXPECTED_ROW_COUNT
    assert _row_count(linked) == EXPECTED_ROW_COUNT * 2
    with linked() as session:
        fingerprints = set(
            session.scalars(select(DocumentCustomerLink.layer1_fingerprint)).all()
        )
    assert fingerprints == {scope.layer1_fingerprint, ALTERNATE_FINGERPRINT}


def test_a_changed_linker_version_appends_and_retains_the_earlier_rows(linked, scope):
    with linked() as session:
        links = derive_links(session, scope)
    bumped = [
        LinkRow(
            document_source_id=link.source.source_id,
            customer_source_id=link.target.source_id,
            basis=str(link.basis),
            matched_token=link.matched_token,
            match_start=link.evidence[0].citation.start,
            match_end=link.evidence[0].citation.end,
            linker_version="2",
            layer1_fingerprint=link.layer1_fingerprint,
        )
        for link in links
    ]

    with linked.begin() as session:
        inserted = insert_links(session, SOURCE_SYSTEM, bumped)

    assert inserted == EXPECTED_ROW_COUNT
    assert _row_count(linked) == EXPECTED_ROW_COUNT * 2
    with linked() as session:
        versions = set(session.scalars(select(DocumentCustomerLink.linker_version)).all())
    assert versions == {"1", "2"}


def test_re_derivation_never_updates_a_row_in_place(linked, scope):
    """
    The primary keys are unchanged after a no-op re-run, so nothing was
    deleted and re-inserted either.
    """
    with linked() as session:
        before = set(session.scalars(select(DocumentCustomerLink.id)).all())

    with linked.begin() as session:
        derive_and_persist(session, scope)

    with linked() as session:
        after = set(session.scalars(select(DocumentCustomerLink.id)).all())

    assert after == before


def test_every_row_carries_the_linker_version_and_the_fingerprint(linked, scope):
    with linked() as session:
        rows = session.execute(
            select(
                DocumentCustomerLink.linker_version,
                DocumentCustomerLink.layer1_fingerprint,
            )
        ).all()

    assert len(rows) == EXPECTED_ROW_COUNT
    assert {tuple(row) for row in rows} == {
        (default_risk_rules().linker_version, scope.layer1_fingerprint)
    }


def test_the_configured_linker_version_is_a_non_empty_string():
    """
    DerivedLink requires a string where rules_version is an int, so the two
    are deliberately not interchangeable.
    """
    version = default_risk_rules().linker_version

    assert isinstance(version, str)
    assert version.strip()
    assert version == "1"


# ---------------------------------------------------------------------------
# documents_for
# ---------------------------------------------------------------------------


def test_documents_for_returns_every_persisted_link_for_one_customer(linked, scope):
    with linked() as session:
        results = documents_for(session, scope, MERIDIAN)

    assert {(item.document_source_id, str(item.link.basis)) for item in results} == {
        (document, basis)
        for document, customer, basis in EXPECTED_LINKS
        if customer == MERIDIAN
    }


def test_documents_for_reads_persisted_rows_and_does_not_re_run_the_linker(demo, scope):
    """
    §0.3.10.2. Before anything is persisted the read is empty, even though
    the linker would find six links for this customer if it were invoked.
    """
    with demo() as session:
        assert documents_for(session, scope, MERIDIAN) == ()
        assert len(derive_links(session, scope)) == EXPECTED_ROW_COUNT


def test_documents_for_returns_nothing_for_an_unlinked_customer(linked, scope):
    with linked() as session:
        assert documents_for(session, scope, "CUST-038") == ()


def test_the_document_type_comes_from_layer_1_rather_than_the_link_row(linked, scope):
    """
    §0.3.10.2: joined at read time, never stored. Editing Layer 1's
    document_type changes what the read reports, with no re-derivation.
    """
    with linked() as session:
        before = {
            item.document_source_id: item.document_type
            for item in documents_for(session, scope, MERIDIAN)
        }
    assert before["DOC-006"] == CONTRACT_DOCUMENT_TYPE

    with linked.begin() as session:
        document = session.scalars(
            select(Document).where(
                Document.source_system == SOURCE_SYSTEM, Document.source_id == "DOC-006"
            )
        ).one()
        document.document_type = "report"

    with linked() as session:
        after = {
            item.document_source_id: item.document_type
            for item in documents_for(session, scope, MERIDIAN)
        }
    assert after["DOC-006"] == "report"
    assert _row_count(linked) == EXPECTED_ROW_COUNT


def test_the_link_table_carries_no_document_type_column():
    """The other half of the same guarantee, asserted structurally."""
    columns = {column.name for column in DocumentCustomerLink.__table__.columns}

    assert "document_type" not in columns


def test_a_returned_link_carries_its_basis_token_and_offsets(linked, scope):
    """§A11: a basis, a matched token and a citation into the text, or it does not exist."""
    with linked() as session:
        results = documents_for(session, scope, MERIDIAN)

    by_key = {
        (item.document_source_id, str(item.link.basis)): item for item in results
    }
    id_token = by_key[("DOC-009", "ID_TOKEN")]

    assert id_token.link.matched_token == "CUST-007"
    assert (id_token.link.evidence[0].citation.start,
            id_token.link.evidence[0].citation.end) == (76, 84)
    assert id_token.link.source_system == SOURCE_SYSTEM
    assert id_token.link.layer1_fingerprint == scope.layer1_fingerprint


# ---------------------------------------------------------------------------
# S14, composed against a real signal set
# ---------------------------------------------------------------------------


def test_composing_s14_for_meridian_yields_the_single_contract_document(linked, scope):
    """
    §0.3.6's acceptance value. DOC-006 is the only contract document linked
    to CUST-007, and it reaches the customer on both bases, so the two
    evidence rows must collapse to one id.
    """
    from app.intelligence.signals import compute_signals

    with linked() as session:
        computed = compute_signals(session, scope, MERIDIAN)
        links = documents_for(session, scope, MERIDIAN)

    assert computed.signals.contract_document_ids == ()

    composed = with_contract_documents(computed.signals, links)

    assert composed.contract_document_ids == ("DOC-006",)
    assert len([item for item in links if item.is_contract]) == 2


def test_composing_s14_leaves_every_other_signal_untouched(linked, scope):
    """M4 populates evidence; it makes no signal document-derived."""
    from app.intelligence.signals import compute_signals

    with linked() as session:
        computed = compute_signals(session, scope, MERIDIAN)
        links = documents_for(session, scope, MERIDIAN)

    composed = with_contract_documents(computed.signals, links)

    for field in computed.signals.__dataclass_fields__:
        if field == "contract_document_ids":
            continue
        assert getattr(composed, field) == getattr(computed.signals, field), field


# ---------------------------------------------------------------------------
# Source-system isolation
# ---------------------------------------------------------------------------


def _provenance(entity_type: str, source_system: str = OTHER_SOURCE_SYSTEM) -> dict:
    return {
        "source_system": source_system,
        "source_entity": entity_type,
        "ingestion_run_id": uuid.uuid4(),
        "record_hash": "0" * 64,
        "ingested_at": datetime(2026, 1, 1, tzinfo=UTC),
    }


@pytest.fixture
def cross_source(demo: sessionmaker[Session]) -> sessionmaker[Session]:
    """
    A second source system naming the SAME customer and document ids.

    The demo dataset holds one source system, so the only way to test that a
    link never crosses one is to write the other by hand. Its document names
    csv_demo's customer explicitly, which is precisely the link that must
    not be derived.
    """
    with demo.begin() as session:
        session.add(Customer(
            name="Meridian Textiles", **_provenance("customers"), source_id=MERIDIAN,
        ))
        session.add(Document(
            title="Foreign review - Meridian Textiles",
            document_type=CONTRACT_DOCUMENT_TYPE,
            body_text=f"Meridian Textiles ({MERIDIAN}) is discussed here.",
            **_provenance("documents"), source_id="DOC-900",
        ))
    return demo


def test_a_link_is_never_derived_across_source_systems(cross_source, scope):
    """
    The csv_demo scope sees neither the foreign document nor the foreign
    customer, even though both name text that would match.
    """
    with cross_source() as session:
        links = derive_links(session, scope)

    assert _triples(links) == EXPECTED_LINKS
    assert all(link.source.source_id != "DOC-900" for link in links)
    assert all(link.source_system == SOURCE_SYSTEM for link in links)


def test_the_foreign_scope_links_its_own_rows_only(cross_source):
    """
    The isolation is symmetric: the other source system derives its own
    single link and never reaches csv_demo's twelve documents.
    """
    with cross_source() as session:
        foreign = resolve_scope(
            session, source_system=OTHER_SOURCE_SYSTEM, as_of=ACCEPTANCE_AS_OF
        )
        links = derive_links(session, foreign)

    assert {link.source.source_id for link in links} == {"DOC-900"}
    assert all(link.source_system == OTHER_SOURCE_SYSTEM for link in links)


def test_writing_no_rows_is_a_no_op_that_touches_nothing(demo):
    """
    An empty derivation short-circuits before it reads the identity maps,
    so a source system with no links costs no queries and writes nothing.
    """
    with demo.begin() as session:
        assert insert_links(session, SOURCE_SYSTEM, []) == 0

    assert _row_count(demo) == 0


def test_a_cross_source_row_offered_to_the_repository_is_not_written(cross_source, scope):
    """
    Isolation is enforced at the write too, not only by what the linker
    happens to look at: a row naming a foreign document has no surrogate key
    to point at within the source system and is dropped.
    """
    row = LinkRow(
        document_source_id="DOC-900",
        customer_source_id=MERIDIAN,
        basis="EXACT_NAME",
        matched_token="Meridian Textiles",
        match_start=0,
        match_end=17,
        linker_version="1",
        layer1_fingerprint=scope.layer1_fingerprint,
    )

    with cross_source.begin() as session:
        inserted = insert_links(session, SOURCE_SYSTEM, [row])

    assert inserted == 0
    assert _row_count(cross_source) == 0


def test_a_row_naming_an_unknown_customer_is_not_written(demo, scope):
    """
    The mirror of the test above, and it isolates the CUSTOMER half.

    The document resolves and the customer does not, so only the second
    endpoint check can reject this row. An implementation that checked the
    document alone would raise a KeyError looking the customer up.
    """
    row = LinkRow(
        document_source_id="DOC-009",
        customer_source_id="CUST-999",
        basis="EXACT_NAME",
        matched_token="Meridian Textiles",
        match_start=23,
        match_end=40,
        linker_version="1",
        layer1_fingerprint=scope.layer1_fingerprint,
    )

    with demo.begin() as session:
        assert insert_links(session, SOURCE_SYSTEM, [row]) == 0

    assert _row_count(demo) == 0


def test_the_read_refuses_a_cross_source_row_even_if_one_were_written(cross_source, scope):
    """
    Defence in depth. insert_links cannot create a link whose document and
    customer sit in different source systems, so this writes one directly
    against the model to prove the READ constrains both ends on its own
    rather than relying on the write having been careful.
    """
    with cross_source.begin() as session:
        foreign_document = session.scalars(
            select(Document).where(
                Document.source_system == OTHER_SOURCE_SYSTEM,
                Document.source_id == "DOC-900",
            )
        ).one()
        local_customer = session.scalars(
            select(Customer).where(
                Customer.source_system == SOURCE_SYSTEM, Customer.source_id == MERIDIAN
            )
        ).one()
        session.add(DocumentCustomerLink(
            document_id=foreign_document.id,
            customer_id=local_customer.id,
            basis="EXACT_NAME",
            matched_token="Meridian Textiles",
            match_start=0,
            match_end=17,
            linker_version="1",
            layer1_fingerprint=scope.layer1_fingerprint,
        ))

    assert _row_count(cross_source) == 1

    with cross_source() as session:
        assert read_links(session, SOURCE_SYSTEM, MERIDIAN) == ()
        assert documents_for(session, scope, MERIDIAN) == ()


def test_reading_a_customer_in_one_source_system_never_returns_the_others_links(
    cross_source, scope
):
    with cross_source.begin() as session:
        derive_and_persist(session, scope)
        foreign = resolve_scope(
            session, source_system=OTHER_SOURCE_SYSTEM, as_of=ACCEPTANCE_AS_OF
        )
        derive_and_persist(session, foreign)

    with cross_source() as session:
        local = read_links(session, SOURCE_SYSTEM, MERIDIAN)
        other = read_links(session, OTHER_SOURCE_SYSTEM, MERIDIAN)

    assert {row.document_source_id for row in local} == {"DOC-005", "DOC-006", "DOC-009"}
    assert {row.document_source_id for row in other} == {"DOC-900"}


# ---------------------------------------------------------------------------
# NULL handling
# ---------------------------------------------------------------------------


@pytest.fixture
def null_fields(demo: sessionmaker[Session], scope: Scope) -> sessionmaker[Session]:
    """Two documents in scope: one with no title, one with no body."""
    with demo.begin() as session:
        session.add(Document(
            title=None, document_type="report",
            body_text=f"Untitled note about Meridian Textiles ({MERIDIAN}).",
            **_provenance("documents", SOURCE_SYSTEM), source_id="DOC-901",
        ))
        session.add(Document(
            title="Meridian Textiles quarterly", document_type="report",
            body_text=None,
            **_provenance("documents", SOURCE_SYSTEM), source_id="DOC-902",
        ))
    return demo


def test_a_null_title_still_yields_a_link_with_offsets_into_citable_text(null_fields, scope):
    """The title contributes the empty string; the body is still citable."""
    with null_fields() as session:
        links = derive_links(session, scope)
        title, body = session.execute(
            select(Document.title, Document.body_text).where(
                Document.source_system == SOURCE_SYSTEM, Document.source_id == "DOC-901"
            )
        ).one()

    untitled = [link for link in links if link.source.source_id == "DOC-901"]
    text = citable_text(title, body)

    assert {str(link.basis) for link in untitled} == {"ID_TOKEN", "EXACT_NAME"}
    for link in untitled:
        citation = link.evidence[0].citation
        assert text[citation.start:citation.end] == link.matched_token


def test_a_null_body_is_skipped_rather_than_raising(null_fields, scope):
    """
    Plan A23: the linker skips a NULL body. DOC-902's title names the
    customer, so this is the case where skipping is observable.
    """
    with null_fields() as session:
        links = derive_links(session, scope)

    assert all(link.source.source_id != "DOC-902" for link in links)


def test_null_fields_do_not_disturb_the_rest_of_the_corpus(null_fields, scope):
    with null_fields() as session:
        links = derive_links(session, scope)

    assert EXPECTED_LINKS <= _triples(links)


# ---------------------------------------------------------------------------
# Layer 1 is untouched
# ---------------------------------------------------------------------------


def test_deriving_links_does_not_change_the_layer_1_fingerprint(linked, scope):
    """
    M4 writes a Layer 2 table and nothing else. If the fingerprint moved,
    every assessment identity would move with it.
    """
    from app.intelligence.scope import layer1_fingerprint

    with linked() as session:
        digest, counts = layer1_fingerprint(session, SOURCE_SYSTEM)

    assert digest == scope.layer1_fingerprint
    assert sum(counts.values()) == 233


def test_the_link_rows_are_the_only_thing_written(linked, scope):
    """Canonical row counts are unchanged by a derivation."""
    with linked() as session:
        documents = session.scalar(
            select(func.count()).select_from(Document).where(
                Document.source_system == SOURCE_SYSTEM
            )
        )
        customers = session.scalar(
            select(func.count()).select_from(Customer).where(
                Customer.source_system == SOURCE_SYSTEM
            )
        )

    assert (documents, customers) == (12, 50)
