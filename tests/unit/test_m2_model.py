"""
The M2 edge contract: what an edge refuses to be.

Every guard here is a structural claim made elsewhere in the milestone. A
guard that has never fired is a guard nobody has proved fires, so each one
is exercised on the thing it forbids rather than trusted because it is
written down.

The last test is the one worth reading: it bypasses EdgeSpec's own refusal
to declare a document endpoint and proves Edge refuses the edge anyway.
That is what "defence in depth" means in plan B9 — two independent guards,
so weakening either one alone does not open the boundary.
"""

from __future__ import annotations

import pytest

from app.intelligence import EdgeBasis, EntityRef
from app.relationships import (
    EDGE_SPECS,
    Edge,
    EdgeSpec,
    EdgeType,
    RelationshipContractError,
    order_edges,
    spec_for,
)
from app.relationships import model as model_module
from app.relationships.edges import canonical_fk_edges, source_key_edges

CUSTOMER = EntityRef("customers", "CUST-007")
EMPLOYEE = EntityRef("employees", "EMP-007")
TICKET = EntityRef("support_tickets", "TKT-075")
DOCUMENT = EntityRef("documents", "DOC-007")

OWNED_BY = spec_for(EdgeType.CUSTOMER_OWNED_BY)


def _owned_by_edge(**overrides: object) -> Edge:
    fields: dict[str, object] = {
        "edge_type": EdgeType.CUSTOMER_OWNED_BY,
        "source": CUSTOMER,
        "target": EMPLOYEE,
        "basis": EdgeBasis.SOURCE_KEY_JOIN,
        "carrier_field": "customers.owner_source_id",
        "source_system": "csv_demo",
    }
    fields.update(overrides)
    return Edge(**fields)  # type: ignore[arg-type]


# --- EdgeSpec refuses to declare an edge M2 does not model ------------------

def test_a_spec_may_not_declare_a_document_endpoint():
    """The first guard: document_owned_by cannot be written down."""
    with pytest.raises(RelationshipContractError, match="isolated node"):
        EdgeSpec(EdgeType.DEAL_OWNED_BY, "documents", "employees",
                 EdgeBasis.SOURCE_KEY_JOIN, "documents.owner_source_id", "documents")


def test_a_spec_may_not_declare_a_document_target():
    with pytest.raises(RelationshipContractError, match="isolated node"):
        EdgeSpec(EdgeType.CUSTOMER_HAS_DEAL, "customers", "documents",
                 EdgeBasis.CANONICAL_FK, "documents.owner_source_id", "documents")


@pytest.mark.parametrize("basis", [EdgeBasis.DERIVED_TEXT_MATCH, EdgeBasis.DERIVED_TOPIC_MATCH])
def test_a_spec_may_not_carry_a_derived_basis(basis):
    """A derived basis belongs to M4's link, not to a relationship edge."""
    with pytest.raises(RelationshipContractError, match="canonical relationships"):
        EdgeSpec(EdgeType.DEAL_OWNED_BY, "deals", "employees",
                 basis, "deals.owner_source_id", "deals")


def test_a_spec_carrier_must_live_on_one_of_the_endpoints():
    """An edge is derived from a column of a row it joins, not a third table."""
    with pytest.raises(RelationshipContractError, match="neither endpoint"):
        EdgeSpec(EdgeType.DEAL_OWNED_BY, "deals", "employees",
                 EdgeBasis.SOURCE_KEY_JOIN, "projects.owner_source_id", "projects")


def test_a_spec_carrier_field_must_name_a_column_of_its_carrier_table():
    with pytest.raises(RelationshipContractError, match="does not name a column"):
        EdgeSpec(EdgeType.DEAL_OWNED_BY, "deals", "employees",
                 EdgeBasis.SOURCE_KEY_JOIN, "employees.manager_source_id", "deals")


def test_an_unmodelled_edge_type_has_no_spec():
    with pytest.raises(RelationshipContractError, match="not an edge M2 models"):
        spec_for("document_owned_by")  # type: ignore[arg-type]


# --- Edge refuses to misstate how it is known -------------------------------

def test_an_edge_may_not_start_at_the_wrong_entity():
    with pytest.raises(RelationshipContractError, match="runs from customers"):
        _owned_by_edge(source=TICKET)


def test_an_edge_may_not_end_at_the_wrong_entity():
    with pytest.raises(RelationshipContractError, match="runs to employees"):
        _owned_by_edge(target=CUSTOMER)


def test_an_edge_may_not_claim_a_basis_its_type_does_not_have():
    """The basis follows from the edge type and is never chosen per edge."""
    with pytest.raises(RelationshipContractError, match="never chosen per edge"):
        _owned_by_edge(basis=EdgeBasis.CANONICAL_FK)


def test_an_edge_may_not_claim_a_carrier_its_type_does_not_have():
    with pytest.raises(RelationshipContractError, match="is derived from"):
        _owned_by_edge(carrier_field="customers.name")


def test_an_edge_must_name_its_source_system():
    with pytest.raises(RelationshipContractError, match="source_system"):
        _owned_by_edge(source_system="   ")


def test_an_edge_that_bypasses_its_spec_is_still_refused_a_document(monkeypatch):
    """
    B9 defence in depth, proved rather than asserted.

    EdgeSpec already refuses a document endpoint, so this constructs one
    behind its back and shows the Edge guard fires independently. If a later
    change weakens EdgeSpec, this is what still closes the boundary.
    """
    smuggled = object.__new__(EdgeSpec)
    for field, value in (
        ("edge_type", EdgeType.CUSTOMER_OWNED_BY), ("source_entity", "documents"),
        ("target_entity", "employees"), ("basis", EdgeBasis.SOURCE_KEY_JOIN),
        ("carrier_field", "documents.owner_source_id"), ("carrier_entity", "documents"),
    ):
        object.__setattr__(smuggled, field, value)
    monkeypatch.setattr(model_module, "spec_for", lambda _edge_type: smuggled)

    with pytest.raises(RelationshipContractError, match="may not touch"):
        Edge(edge_type=EdgeType.CUSTOMER_OWNED_BY, source=DOCUMENT, target=EMPLOYEE,
             basis=EdgeBasis.SOURCE_KEY_JOIN, carrier_field="documents.owner_source_id",
             source_system="csv_demo")


# --- Ordering and identity --------------------------------------------------

def test_order_edges_removes_duplicates_and_sorts():
    first = _owned_by_edge()
    duplicate = _owned_by_edge()
    other = _owned_by_edge(source=EntityRef("customers", "CUST-002"))

    assert order_edges((first, duplicate, other)) == (other, first)


def test_two_edges_of_the_same_relationship_share_an_identity():
    assert _owned_by_edge().identity == _owned_by_edge().identity


def test_an_edges_payload_states_its_basis_and_carrier():
    payload = _owned_by_edge().to_payload()

    assert payload == {
        "edge": "customer_owned_by",
        "source": {"entity": "customers", "id": "CUST-007"},
        "target": {"entity": "employees", "id": "EMP-007"},
        "basis": "SOURCE_KEY_JOIN",
        "carrier_field": "customers.owner_source_id",
        "source_system": "csv_demo",
    }


def test_every_spec_agrees_with_the_edge_type_that_keys_it():
    for edge_type, spec in EDGE_SPECS.items():
        assert spec.edge_type is edge_type


# --- The builders refuse the wrong basis ------------------------------------

def test_the_canonical_fk_builder_refuses_a_source_key_edge():
    with pytest.raises(RelationshipContractError, match="not a canonical FK edge"):
        canonical_fk_edges(OWNED_BY, None, None)  # type: ignore[arg-type]


def test_the_source_key_builder_refuses_a_canonical_fk_edge():
    with pytest.raises(RelationshipContractError, match="not a source-key join edge"):
        source_key_edges(spec_for(EdgeType.CUSTOMER_HAS_DEAL), None, None)  # type: ignore[arg-type]


def test_an_unknown_entity_type_has_no_model():
    smuggled = object.__new__(EdgeSpec)
    for field, value in (
        ("edge_type", EdgeType.CUSTOMER_OWNED_BY), ("source_entity", "customers"),
        ("target_entity", "not_a_table"), ("basis", EdgeBasis.SOURCE_KEY_JOIN),
        ("carrier_field", "customers.owner_source_id"), ("carrier_entity", "customers"),
    ):
        object.__setattr__(smuggled, field, value)

    with pytest.raises(RelationshipContractError, match="unknown canonical entity type"):
        source_key_edges(smuggled, None, None)  # type: ignore[arg-type]
