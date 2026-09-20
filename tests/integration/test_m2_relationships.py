"""
M2 relationship model against a real database.

The demo dataset is ingested by the clean full-dataset path, so every test
runs against a freshly rebuilt Layer 1 and the numbers asserted here are the
measured ones, not remembered ones.

Two kinds of test live here. Behaviour: the three queries return the
neighbourhoods plan A9 measured. Invariants: B1, B2, B5, B7, B8, B9(b) and
B10, each of which fails the build if a future change moves document linking
into M2 or reaches a customer-document association by another route. The
static half of the boundary (B3, B4, B6, B9a) is in
tests/unit/test_m2_boundary.py.

Every source key in the demo dataset resolves, so the null and unmatched
cases cannot be shown from it. They are shown with synthetic rows written
straight into the isolated test database, which is also how source-system
isolation gets a second source system to be isolated from.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.connectors import CsvConnector, CsvConnectorConfig, SourceConnector
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence import EdgeBasis, EntityRef, Scope, resolve_scope
from app.intelligence.scope import layer1_fingerprint
from app.persistence.models import Customer, Deal, Document, Employee, SupportTicket
from app.relationships import (
    EDGE_SPECS,
    Edge,
    EdgeType,
    UnknownCustomerError,
    all_edge_types,
    edges_of_type,
    escalation_path,
    neighbourhood,
    policy_documents,
)

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
PINNED = "1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00"
SOURCE_SYSTEM = "csv_demo"
OTHER_SOURCE_SYSTEM = "other_demo"

#: The flagship account, measured on the committed dataset (plan A9, M2).
MERIDIAN = "CUST-007"
MERIDIAN_TICKETS = ("TKT-073", "TKT-075", "TKT-076", "TKT-079", "TKT-080")
MERIDIAN_OPEN_TICKETS = ("TKT-075", "TKT-076", "TKT-079", "TKT-080")
MERIDIAN_DEALS = ("DEAL-001",)
MERIDIAN_OWNER = "EMP-007"
MERIDIAN_OWNER_MANAGER = "EMP-002"
OPEN_TICKET_ASSIGNEES = ("EMP-017", "EMP-018", "EMP-020", "EMP-021")
SUPPORT_MANAGER = "EMP-004"
POLICY_DOCUMENTS = ("DOC-001", "DOC-002", "DOC-003")
#: EMP-007 owns this contract and is also Meridian's account owner. The pair
#: is what makes B9(b)'s negative control a real hazard rather than a theory.
DELTAFORGE_CONTRACT = "DOC-007"

#: Tables whose rows nothing references by foreign key, so a test may delete
#: and reinsert them to change their physical order (B7).
REORDERABLE = ("employees", "support_tickets", "deals", "projects", "documents")


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
        return resolve_scope(session, source_system=SOURCE_SYSTEM)


def _ids(refs: Iterable[EntityRef]) -> tuple[str, ...]:
    return tuple(ref.source_id for ref in refs)


def _provenance(session: Session, entity_type: str) -> dict[str, object]:
    """Provenance columns a synthetic row needs. No FK constrains them."""
    return {
        "source_system": OTHER_SOURCE_SYSTEM,
        "source_entity": entity_type,
        "ingestion_run_id": uuid.uuid4(),
        "record_hash": "0" * 64,
        "ingested_at": datetime(2026, 1, 1, tzinfo=UTC),
    }


# --- Behaviour: the three queries -------------------------------------------

def test_neighbourhood_returns_the_measured_meridian_neighbourhood(demo, scope):
    """Plan A9/M2: 5 tickets, 1 deal, 0 projects, account owner EMP-007."""
    with demo() as session:
        result = neighbourhood(session, scope, MERIDIAN)

    assert result.customer == EntityRef("customers", MERIDIAN)
    assert _ids(result.tickets) == MERIDIAN_TICKETS
    assert _ids(result.deals) == MERIDIAN_DEALS
    assert result.projects == ()
    assert result.account_owner == EntityRef("employees", MERIDIAN_OWNER)


def test_escalation_path_returns_every_open_tickets_assignee_and_their_manager(demo, scope):
    """
    Plan A9 says each open ticket's assignee, so EMP-017 is on the path.

    TKT-079 is open and only medium priority. Filtering the path to high
    priority would drop the person actually handling it, which is why this
    asserts all four assignees rather than the three high-priority ones.
    """
    with demo() as session:
        path = escalation_path(session, scope, MERIDIAN)

    assert path.account_owner == EntityRef("employees", MERIDIAN_OWNER)
    assert path.account_owner_manager == EntityRef("employees", MERIDIAN_OWNER_MANAGER)
    assert _ids(path.open_tickets) == MERIDIAN_OPEN_TICKETS
    assert sorted(_ids(path.assignees)) == list(OPEN_TICKET_ASSIGNEES)
    assert _ids(path.assignee_managers) == (SUPPORT_MANAGER,)


def test_escalation_path_excludes_a_resolved_tickets_assignee(demo, scope):
    """TKT-073 is resolved; it must not put anyone on the escalation path."""
    with demo() as session:
        path = escalation_path(session, scope, MERIDIAN)

    assert "TKT-073" not in _ids(path.open_tickets)
    assigned = [edge for edge in path.edges if edge.edge_type is EdgeType.TICKET_ASSIGNED_TO]

    assert {edge.source.source_id for edge in assigned} == set(MERIDIAN_OPEN_TICKETS)


def test_policy_documents_returns_the_three_policies_in_order(demo, scope):
    with demo() as session:
        documents = policy_documents(session, scope)

    assert _ids(documents) == POLICY_DOCUMENTS
    assert {ref.entity_type for ref in documents} == {"documents"}


def test_a_customer_with_no_children_yields_empty_collections(demo, scope):
    """Plan A23: a ticketless customer is an empty neighbourhood, never an error."""
    with demo() as session:
        ticketless = session.scalars(
            select(Customer.source_id)
            .where(Customer.source_system == SOURCE_SYSTEM)
            .where(~Customer.source_id.in_(
                select(SupportTicket.customer_source_id)
                .where(SupportTicket.source_system == SOURCE_SYSTEM)))
            .order_by(Customer.source_id)
        ).first()

        assert ticketless is not None
        result = neighbourhood(session, scope, ticketless)

    assert result.tickets == ()
    assert result.customer.source_id == ticketless


def test_an_absent_customer_is_refused_rather_than_silently_empty(demo, scope):
    with demo() as session, pytest.raises(UnknownCustomerError):
        neighbourhood(session, scope, "CUST-DOES-NOT-EXIST")


def test_every_customer_can_be_asked_for_its_neighbourhood(demo, scope):
    """Not just the flagship: 50 customers, no error, no missing node."""
    with demo() as session:
        customers = session.scalars(
            select(Customer.source_id)
            .where(Customer.source_system == SOURCE_SYSTEM)
            .order_by(Customer.source_id)
        ).all()
        results = [neighbourhood(session, scope, source_id) for source_id in customers]

    assert len(results) == 50
    assert all(result.account_owner is not None for result in results)


# --- Behaviour: the edges themselves ----------------------------------------

def test_every_modelled_edge_type_resolves_on_the_demo_dataset(demo, scope):
    """An edge type that never resolves is a specification nobody exercised."""
    with demo() as session:
        counts = {
            edge_type: len(edges_of_type(edge_type, session, scope))
            for edge_type in all_edge_types()
        }

    assert set(counts) == set(EDGE_SPECS)
    assert all(count > 0 for count in counts.values()), counts


def test_canonical_fk_edge_counts_match_the_resolved_rows(demo, scope):
    with demo() as session:
        tickets = edges_of_type(EdgeType.CUSTOMER_HAS_TICKET, session, scope)
        deals = edges_of_type(EdgeType.CUSTOMER_HAS_DEAL, session, scope)
        projects = edges_of_type(EdgeType.CUSTOMER_HAS_PROJECT, session, scope)

    assert (len(tickets), len(deals), len(projects)) == (80, 44, 22)


def test_a_null_foreign_key_yields_no_edge_rather_than_an_error(demo, scope):
    """Plan A23: an unresolved FK is excluded from edges, never an error."""
    with demo() as session:
        session.execute(
            text("UPDATE support_tickets SET customer_id = NULL WHERE source_id = :ticket"),
            {"ticket": "TKT-073"},
        )
        session.flush()
        edges = edges_of_type(EdgeType.CUSTOMER_HAS_TICKET, session, scope)
        result = neighbourhood(session, scope, MERIDIAN)
        session.rollback()

    assert len(edges) == 79
    assert "TKT-073" not in _ids(result.tickets)


def test_an_employee_without_a_manager_yields_no_reporting_edge(demo, scope):
    """EMP-001 is the root of the hierarchy: a null carrier is not an edge."""
    with demo() as session:
        edges = edges_of_type(
            EdgeType.EMPLOYEE_REPORTS_TO, session, scope, source_ids=["EMP-001"]
        )

    assert edges == ()


def test_no_result_contains_a_duplicate_edge(demo, scope):
    with demo() as session:
        for edge_type in all_edge_types():
            edges = edges_of_type(edge_type, session, scope)
            identities = [edge.identity for edge in edges]

            assert len(identities) == len(set(identities)), edge_type


def test_every_edge_is_returned_in_its_total_order(demo, scope):
    with demo() as session:
        for edge_type in all_edge_types():
            edges = edges_of_type(edge_type, session, scope)
            keys = [edge.sort_key for edge in edges]

            assert keys == sorted(keys), edge_type


# --- B1: zero document to customer edges ------------------------------------

def test_b1_no_query_emits_a_document_to_customer_edge_for_any_customer(demo, scope):
    """
    B1, over every customer rather than CUST-007 alone.

    The assertion is over the edge set, so it holds for customers added later.
    """
    with demo() as session:
        customers = session.scalars(
            select(Customer.source_id)
            .where(Customer.source_system == SOURCE_SYSTEM)
            .order_by(Customer.source_id)
        ).all()
        edges: list[Edge] = []
        for source_id in customers:
            edges.extend(neighbourhood(session, scope, source_id).edges)
            edges.extend(escalation_path(session, scope, source_id).edges)

    assert edges
    endpoints = {edge.source.entity_type for edge in edges} | {
        edge.target.entity_type for edge in edges}

    assert "documents" not in endpoints


def test_b1_holds_over_every_modelled_edge_not_only_the_queried_ones(demo, scope):
    """Including deal_owned_by, which no query returns."""
    with demo() as session:
        for edge_type in all_edge_types():
            for edge in edges_of_type(edge_type, session, scope):
                assert edge.source.entity_type != "documents", edge_type
                assert edge.target.entity_type != "documents", edge_type


def test_b1_policy_documents_returns_nodes_and_never_an_edge(demo, scope):
    """The only document-touching query returns bare nodes, so it emits no edge."""
    with demo() as session:
        documents = policy_documents(session, scope)

    assert all(isinstance(ref, EntityRef) for ref in documents)
    assert not any(isinstance(ref, Edge) for ref in documents)


# --- B2: only the two canonical bases ---------------------------------------

def test_b2_every_edge_carries_a_canonical_or_source_key_basis(demo, scope):
    with demo() as session:
        bases = set()
        for edge_type in all_edge_types():
            bases.update(edge.basis for edge in edges_of_type(edge_type, session, scope))

    assert bases == {EdgeBasis.CANONICAL_FK, EdgeBasis.SOURCE_KEY_JOIN}
    assert EdgeBasis.DERIVED_TEXT_MATCH not in bases
    assert EdgeBasis.DERIVED_TOPIC_MATCH not in bases


def test_b2_a_querys_edges_carry_only_the_two_bases(demo, scope):
    with demo() as session:
        edges = neighbourhood(session, scope, MERIDIAN).edges + escalation_path(
            session, scope, MERIDIAN).edges

    assert {edge.basis for edge in edges} <= {
        EdgeBasis.CANONICAL_FK, EdgeBasis.SOURCE_KEY_JOIN}


# --- B5: policy_documents carries no customer scope -------------------------

def test_b5_policy_documents_takes_no_customer_argument(demo, scope):
    import inspect

    parameters = list(inspect.signature(policy_documents).parameters)

    assert parameters == ["session", "scope"]
    assert not any("customer" in name for name in parameters)


def test_b5_policy_documents_is_customer_independent(demo, scope):
    """Called for two different customers' work, it returns the identical set."""
    with demo() as session:
        neighbourhood(session, scope, MERIDIAN)
        first = policy_documents(session, scope)
        neighbourhood(session, scope, "CUST-002")
        second = policy_documents(session, scope)

    assert first == second == tuple(EntityRef("documents", d) for d in POLICY_DOCUMENTS)


# --- B7: determinism and row-order independence -----------------------------

def _query_all(session: Session, scope: Scope) -> tuple[object, ...]:
    return (
        neighbourhood(session, scope, MERIDIAN).to_payload(),
        escalation_path(session, scope, MERIDIAN).to_payload(),
        tuple(ref.to_payload()["id"] for ref in policy_documents(session, scope)),
        tuple(edge.to_payload() for edge_type in all_edge_types()
              for edge in edges_of_type(edge_type, session, scope)),
    )


def test_b7_two_runs_in_one_session_are_identical(demo, scope):
    with demo() as session:
        first = _query_all(session, scope)
        second = _query_all(session, scope)

    assert first == second


def test_b7_results_do_not_change_when_physical_row_order_changes(demo, scope):
    """
    The strong half of B7: rewrite the heap in reverse and re-ask.

    A query that relied on PostgreSQL's incidental row order passes the
    repeat-in-one-session test above and fails this one.
    """
    with demo() as session:
        before = _query_all(session, scope)

    with demo() as session:
        for table in REORDERABLE:
            session.execute(text(
                f"CREATE TEMP TABLE reorder_{table} AS "
                f"SELECT * FROM {table} ORDER BY source_id DESC"))
            session.execute(text(f"DELETE FROM {table}"))
            session.execute(text(f"INSERT INTO {table} SELECT * FROM reorder_{table}"))
        session.execute(text("ANALYZE"))
        after = _query_all(session, scope)
        fingerprint, _ = layer1_fingerprint(session, SOURCE_SYSTEM)
        session.rollback()

    assert after == before
    assert fingerprint == PINNED


# --- B8: Layer 1 is untouched -----------------------------------------------

def test_b8_the_fingerprint_is_unchanged_after_the_queries_run(demo, scope):
    with demo() as session:
        before, _ = layer1_fingerprint(session, SOURCE_SYSTEM)
        _query_all(session, scope)
        after, _ = layer1_fingerprint(session, SOURCE_SYSTEM)

    assert before == after == PINNED


def test_b8_the_queries_leave_the_row_counts_untouched(demo, scope):
    with demo() as session:
        counts = {model.__tablename__: session.scalar(
            select(__import__("sqlalchemy").func.count()).select_from(model))
            for model in (Customer, Deal, Document, Employee, SupportTicket)}
        _query_all(session, scope)
        after = {model.__tablename__: session.scalar(
            select(__import__("sqlalchemy").func.count()).select_from(model))
            for model in (Customer, Deal, Document, Employee, SupportTicket)}

    assert counts == after


# --- B9(b): the ownership composition, as a negative control ----------------

def test_b9b_the_ownership_composition_exists_in_layer_1(demo, scope):
    """
    The negative control. Joining documents.owner_source_id to
    customers.owner_source_id reaches DOC-007, Deltaforge's signed contract,
    from CUST-007, Meridian Textiles, with no text matching whatsoever.

    Asserting the join still returns rows is what stops the test below
    passing vacuously if the data or the columns ever change.
    """
    with demo() as session:
        pairs = session.execute(text("""
            SELECT d.source_id, c.source_id
            FROM documents d
            JOIN customers c ON c.owner_source_id = d.owner_source_id
                            AND c.source_system = d.source_system
            WHERE d.source_system = :ss AND d.source_id = :doc AND c.source_id = :cust
        """), {"ss": SOURCE_SYSTEM, "doc": DELTAFORGE_CONTRACT, "cust": MERIDIAN}).all()

    assert pairs == [(DELTAFORGE_CONTRACT, MERIDIAN)], (
        "the ownership-composition hazard no longer exists in the data, so the "
        "control below would pass for the wrong reason")


def test_b9b_no_m2_query_produces_that_pairing(demo, scope):
    """
    B9(b). Shared ownership is not evidence of a relationship.

    M2 emits no document edge at all, so the composition has no first hop.
    This asserts the consequence directly: nothing M2 returns pairs DOC-007
    with CUST-007, by any edge, in any query, at any number of hops.
    """
    with demo() as session:
        edges: list[Edge] = []
        for edge_type in all_edge_types():
            edges.extend(edges_of_type(edge_type, session, scope))
        reachable = _reachable_from(edges, ("customers", MERIDIAN))
        documents = policy_documents(session, scope)

    assert ("documents", DELTAFORGE_CONTRACT) not in reachable
    assert not any(node[0] == "documents" for node in reachable), (
        "a document is reachable from a customer through M2 edges")
    assert DELTAFORGE_CONTRACT not in _ids(documents)


def _reachable_from(
    edges: list[Edge], start: tuple[str, str]
) -> set[tuple[str, str]]:
    """Every node reachable from one node over M2's edges, in either direction."""
    adjacency: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for edge in edges:
        source = (edge.source.entity_type, edge.source.source_id)
        target = (edge.target.entity_type, edge.target.source_id)
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)
    seen: set[tuple[str, str]] = set()
    queue = [start]
    while queue:
        node = queue.pop()
        if node in seen:
            continue
        seen.add(node)
        queue.extend(adjacency.get(node, ()))
    return seen


def test_b9b_no_document_is_reachable_from_any_customer_at_any_depth(demo, scope):
    """The general form: document isolation over the whole graph, not one pair."""
    with demo() as session:
        edges: list[Edge] = []
        for edge_type in all_edge_types():
            edges.extend(edges_of_type(edge_type, session, scope))
        customers = session.scalars(
            select(Customer.source_id)
            .where(Customer.source_system == SOURCE_SYSTEM)
            .order_by(Customer.source_id)
        ).all()

    for source_id in customers:
        reachable = _reachable_from(edges, ("customers", source_id))

        assert not any(node[0] == "documents" for node in reachable), source_id


# --- B10: deal_owned_by, proved without a query consumer --------------------

def test_b10_a_every_emitted_edge_is_a_real_layer_1_pair(demo, scope):
    """B10(A). No fabricated edge."""
    with demo() as session:
        edges = edges_of_type(EdgeType.DEAL_OWNED_BY, session, scope)
        layer1 = set(session.execute(text("""
            SELECT d.source_id, e.source_id
            FROM deals d JOIN employees e ON e.source_id = d.owner_source_id
                                         AND e.source_system = d.source_system
            WHERE d.source_system = :ss
        """), {"ss": SOURCE_SYSTEM}).all())

    assert edges
    assert {(edge.source.source_id, edge.target.source_id) for edge in edges} <= layer1


def test_b10_b_every_valid_layer_1_pair_produces_exactly_one_edge(demo, scope):
    """B10(B). No dropped edge, and no duplicate."""
    with demo() as session:
        edges = edges_of_type(EdgeType.DEAL_OWNED_BY, session, scope)
        layer1 = session.execute(text("""
            SELECT d.source_id, e.source_id
            FROM deals d JOIN employees e ON e.source_id = d.owner_source_id
                                         AND e.source_system = d.source_system
            WHERE d.source_system = :ss AND d.owner_source_id IS NOT NULL
        """), {"ss": SOURCE_SYSTEM}).all()
        emitted = [(edge.source.source_id, edge.target.source_id) for edge in edges]

    assert sorted(emitted) == sorted(layer1)
    assert len(emitted) == len(set(emitted)) == 44


def test_b10_c_a_null_or_unmatched_owner_produces_no_edge(demo, scope):
    """B10(C). Both are ordinary Layer 1 state, and neither is an edge."""
    with demo() as session:
        session.execute(text(
            "UPDATE deals SET owner_source_id = NULL WHERE source_id = 'DEAL-001'"))
        session.execute(text(
            "UPDATE deals SET owner_source_id = 'EMP-NOT-A-REAL-EMPLOYEE' "
            "WHERE source_id = 'DEAL-002'"))
        session.flush()
        edges = edges_of_type(EdgeType.DEAL_OWNED_BY, session, scope)
        emitted = {edge.source.source_id for edge in edges}
        session.rollback()

    assert "DEAL-001" not in emitted
    assert "DEAL-002" not in emitted
    assert len(edges) == 42


def test_b10_d_the_join_never_crosses_a_source_system(demo, scope):
    """
    B10(D). A second source system reusing the same employee ids must not join.

    This is the failure that would silently merge two organisations' people.
    """
    with demo() as session:
        # A deal in the second source system owned by EMP-007, an id that
        # exists only in the first. If the join ignored source_system this
        # would resolve across the boundary; it must resolve to nothing.
        session.add(Deal(
            **_provenance(session, "deals"), source_id="DEAL-CROSS",
            name="Owner Exists Only Elsewhere", owner_source_id=MERIDIAN_OWNER,
            is_active=True))
        # A deal in the second source system owned inside it, to prove the
        # test is not simply failing to see any edge at all.
        session.add(Employee(
            **_provenance(session, "employees"), source_id="EMP-LOCAL",
            name="Second System Employee", is_active=True))
        session.add(Deal(
            **_provenance(session, "deals"), source_id="DEAL-LOCAL",
            name="Owner Exists Here", owner_source_id="EMP-LOCAL", is_active=True))
        session.flush()

        other_scope = Scope(
            source_system=OTHER_SOURCE_SYSTEM, as_of=scope.as_of,
            layer1_fingerprint=scope.layer1_fingerprint,
            as_of_source=scope.as_of_source,
            entity_counts=scope.entity_counts)
        ours = edges_of_type(EdgeType.DEAL_OWNED_BY, session, scope)
        theirs = edges_of_type(EdgeType.DEAL_OWNED_BY, session, other_scope)
        session.rollback()

    assert not {"DEAL-CROSS", "DEAL-LOCAL"} & {edge.source.source_id for edge in ours}
    assert len(ours) == 44
    assert [(edge.source.source_id, edge.target.source_id) for edge in theirs] == [
        ("DEAL-LOCAL", "EMP-LOCAL")], "DEAL-CROSS resolved across a source system"
    assert {edge.source_system for edge in theirs} == {OTHER_SOURCE_SYSTEM}


def test_b10_e_every_edge_names_its_basis_and_its_carrier_field(demo, scope):
    """B10(E). Provenance readable without consulting the plan."""
    with demo() as session:
        edges = edges_of_type(EdgeType.DEAL_OWNED_BY, session, scope)

    assert {edge.basis for edge in edges} == {EdgeBasis.SOURCE_KEY_JOIN}
    assert {edge.carrier_field for edge in edges} == {"deals.owner_source_id"}
    assert {edge.source_system for edge in edges} == {SOURCE_SYSTEM}
    payload = edges[0].to_payload()

    assert payload["basis"] == "SOURCE_KEY_JOIN"
    assert payload["carrier_field"] == "deals.owner_source_id"


def test_b10_f_the_edge_is_deterministic_under_row_order_changes(demo, scope):
    """B10(F). Built twice over a rewritten heap, exactly equal."""
    with demo() as session:
        before = [edge.to_payload() for edge in
                  edges_of_type(EdgeType.DEAL_OWNED_BY, session, scope)]

    with demo() as session:
        for table in ("deals", "employees"):
            session.execute(text(
                f"CREATE TEMP TABLE shuffle_{table} AS "
                f"SELECT * FROM {table} ORDER BY source_id DESC"))
            session.execute(text(f"DELETE FROM {table}"))
            session.execute(text(f"INSERT INTO {table} SELECT * FROM shuffle_{table}"))
        after = [edge.to_payload() for edge in
                 edges_of_type(EdgeType.DEAL_OWNED_BY, session, scope)]
        session.rollback()

    assert after == before


# --- Source-system isolation across every edge type -------------------------

def test_no_source_key_edge_of_any_type_crosses_a_source_system(demo, scope):
    """The generic form of B10(D): one join path, so one test covers all four."""
    with demo() as session:
        session.add(Employee(
            **_provenance(session, "employees"), source_id="EMP-004",
            name="Other System Manager", is_active=True))
        session.add(Employee(
            **_provenance(session, "employees"), source_id="EMP-900",
            name="Other System Report", manager_source_id="EMP-004", is_active=True))
        session.add(Customer(
            **_provenance(session, "customers"), source_id="CUST-900",
            name="Other System Customer", owner_source_id="EMP-004", is_active=True))
        session.add(SupportTicket(
            **_provenance(session, "support_tickets"), source_id="TKT-900",
            status="open", assignee_source_id="EMP-004"))
        session.flush()

        for edge_type in all_edge_types():
            edges = edges_of_type(edge_type, session, scope)

            assert {edge.source_system for edge in edges} == {SOURCE_SYSTEM}, edge_type
            foreign = {"CUST-900", "EMP-900", "TKT-900", "DEAL-OTHER"}
            assert not foreign & {edge.source.source_id for edge in edges}, edge_type
        session.rollback()


def test_a_source_key_that_matches_only_in_another_source_system_yields_no_edge(demo, scope):
    """The carrier resolves, but only against a row E1 would never have resolved it to."""
    with demo() as session:
        session.add(Employee(
            **_provenance(session, "employees"), source_id="EMP-ONLY-ELSEWHERE",
            name="Elsewhere", is_active=True))
        session.execute(text(
            "UPDATE deals SET owner_source_id = 'EMP-ONLY-ELSEWHERE' "
            "WHERE source_id = 'DEAL-001'"))
        session.flush()
        edges = edges_of_type(EdgeType.DEAL_OWNED_BY, session, scope)
        session.rollback()

    assert "DEAL-001" not in {edge.source.source_id for edge in edges}
    assert len(edges) == 43


# --- The exact query contract -----------------------------------------------

def test_the_package_exposes_exactly_three_public_queries(demo, scope):
    import app.relationships as package

    queries = {name for name in package.__all__ if name in
               {"neighbourhood", "escalation_path", "policy_documents", "documents_for"}}

    assert queries == {"neighbourhood", "escalation_path", "policy_documents"}


def test_the_queries_take_a_scope_rather_than_loose_arguments(demo, scope):
    import inspect

    for query in (neighbourhood, escalation_path, policy_documents):
        parameters = list(inspect.signature(query).parameters)

        assert parameters[:2] == ["session", "scope"], query.__name__


def test_a_neighbourhood_payload_states_how_every_edge_is_known(demo, scope):
    with demo() as session:
        payload = neighbourhood(session, scope, MERIDIAN).to_payload()

    edges = payload["edges"]
    assert isinstance(edges, list)
    assert edges
    for edge in edges:
        assert set(edge) == {
            "edge", "source", "target", "basis", "carrier_field", "source_system"}
        assert edge["basis"] in {"CANONICAL_FK", "SOURCE_KEY_JOIN"}
