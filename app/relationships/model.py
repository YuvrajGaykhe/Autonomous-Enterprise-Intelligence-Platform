"""
The M2 relationship vocabulary: what an edge is, and how it is known.

Layer 1 holds relationships in two forms, and this package refuses to blur
them. A CANONICAL_FK edge follows a resolved foreign key: E1 already proved
the parent exists in the same source system, so the edge is a fact. A
SOURCE_KEY_JOIN edge follows a *_source_id string that Layer 1 never
resolved, joined at read time under exactly E1's own predicate
(source_system, source_entity, source_id). It is no stronger than the string
it came from, which is why every edge names the carrier field it was derived
from rather than presenting itself as an anonymous arrow.

Three properties are structural here rather than asserted by a test:

    Document isolation   No edge may touch a document. EDGE_SPECS declares
                         none, and Edge refuses to be constructed with a
                         documents endpoint whatever a caller passes, so
                         there is no first hop from which a Document could be
                         composed into a Customer. Deriving that association
                         is M4's sole responsibility (plan A9, A9.2).
    Basis honesty        An edge's basis and carrier field are read off its
                         specification, never chosen per edge, so no caller
                         can mint a SOURCE_KEY_JOIN that claims to be a
                         CANONICAL_FK.
    Total order          Edges sort by (edge type, source id, target id),
                         which is total because a source identity is unique
                         within one source system and entity. PostgreSQL
                         guarantees no row order without an ORDER BY, and an
                         unordered result is not reproducible.

The EdgeBasis vocabulary is M1's and is not redeclared (plan A9).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from app.intelligence import EdgeBasis, EntityRef
from app.relationships.errors import RelationshipContractError

#: Canonical entity types this package addresses, by their Layer 1 table name.
CUSTOMERS = "customers"
DEALS = "deals"
PROJECTS = "projects"
SUPPORT_TICKETS = "support_tickets"
EMPLOYEES = "employees"
DOCUMENTS = "documents"

#: Entity types no edge may ever touch. A document reaches a customer only
#: through M4's derived link, which cites the text asserting the relationship.
#: Employee ownership of a document is not evidence about a customer.
ISOLATED_ENTITIES = frozenset({DOCUMENTS})


class EdgeType(StrEnum):
    """The seven relationships M2 models. There is no eighth (plan A9)."""

    CUSTOMER_HAS_TICKET = "customer_has_ticket"
    CUSTOMER_HAS_DEAL = "customer_has_deal"
    CUSTOMER_HAS_PROJECT = "customer_has_project"
    CUSTOMER_OWNED_BY = "customer_owned_by"
    TICKET_ASSIGNED_TO = "ticket_assigned_to"
    EMPLOYEE_REPORTS_TO = "employee_reports_to"
    DEAL_OWNED_BY = "deal_owned_by"


@dataclass(frozen=True)
class EdgeSpec:
    """
    How one edge type is derived from Layer 1.

    carrier_field is the fully qualified Layer 1 column the edge is read
    from: a resolved FK column for CANONICAL_FK, an unresolved *_source_id
    string for SOURCE_KEY_JOIN. It travels on every edge so a reader can
    tell how the relationship is known without consulting the plan.
    """

    edge_type: EdgeType
    source_entity: str
    target_entity: str
    basis: EdgeBasis
    carrier_field: str
    carrier_entity: str

    def __post_init__(self) -> None:
        touched = {self.source_entity, self.target_entity} & ISOLATED_ENTITIES
        if touched:
            raise RelationshipContractError(
                f"{self.edge_type} would touch {sorted(touched)}, which M2 models as an "
                f"isolated node: a document reaches a customer only through M4's derived link"
            )
        if self.basis not in (EdgeBasis.CANONICAL_FK, EdgeBasis.SOURCE_KEY_JOIN):
            raise RelationshipContractError(
                f"{self.edge_type} carries {self.basis}: M2 emits canonical relationships "
                f"only, and a derived basis belongs to M4"
            )
        if self.carrier_entity not in (self.source_entity, self.target_entity):
            raise RelationshipContractError(
                f"{self.edge_type} carrier lives on {self.carrier_entity}, which is neither "
                f"endpoint: an edge is derived from a column of one of the rows it joins"
            )
        if not self.carrier_field.startswith(f"{self.carrier_entity}."):
            raise RelationshipContractError(
                f"{self.edge_type} carrier {self.carrier_field!r} does not name a column of "
                f"{self.carrier_entity}"
            )

    @property
    def is_source_key_join(self) -> bool:
        return self.basis is EdgeBasis.SOURCE_KEY_JOIN


_SPECS: tuple[EdgeSpec, ...] = (
    # Canonical FKs: E1 resolved these against a same-source parent, so the
    # relationship is recorded in Layer 1 rather than joined at read time.
    EdgeSpec(EdgeType.CUSTOMER_HAS_TICKET, CUSTOMERS, SUPPORT_TICKETS,
             EdgeBasis.CANONICAL_FK, "support_tickets.customer_id", SUPPORT_TICKETS),
    EdgeSpec(EdgeType.CUSTOMER_HAS_DEAL, CUSTOMERS, DEALS,
             EdgeBasis.CANONICAL_FK, "deals.customer_id", DEALS),
    EdgeSpec(EdgeType.CUSTOMER_HAS_PROJECT, CUSTOMERS, PROJECTS,
             EdgeBasis.CANONICAL_FK, "projects.customer_id", PROJECTS),
    # Source-key joins: unresolved *_source_id strings, joined under E1's own
    # predicate at read time. Four of Layer 1's six (plan A9.1 row 6).
    EdgeSpec(EdgeType.CUSTOMER_OWNED_BY, CUSTOMERS, EMPLOYEES,
             EdgeBasis.SOURCE_KEY_JOIN, "customers.owner_source_id", CUSTOMERS),
    EdgeSpec(EdgeType.TICKET_ASSIGNED_TO, SUPPORT_TICKETS, EMPLOYEES,
             EdgeBasis.SOURCE_KEY_JOIN, "support_tickets.assignee_source_id", SUPPORT_TICKETS),
    EdgeSpec(EdgeType.EMPLOYEE_REPORTS_TO, EMPLOYEES, EMPLOYEES,
             EdgeBasis.SOURCE_KEY_JOIN, "employees.manager_source_id", EMPLOYEES),
    # Modelled substrate. VS-02's per-owner aggregation and VS-03's people map
    # need it; no VS-01 query returns it, and none may be added to (plan A9.1).
    EdgeSpec(EdgeType.DEAL_OWNED_BY, DEALS, EMPLOYEES,
             EdgeBasis.SOURCE_KEY_JOIN, "deals.owner_source_id", DEALS),
)

#: Every edge M2 models, by type. Nothing outside this mapping can be built.
EDGE_SPECS: Mapping[EdgeType, EdgeSpec] = MappingProxyType(
    {spec.edge_type: spec for spec in _SPECS}
)


def spec_for(edge_type: EdgeType) -> EdgeSpec:
    """The specification of one edge type."""
    spec = EDGE_SPECS.get(edge_type)
    if spec is None:
        raise RelationshipContractError(f"{edge_type!r} is not an edge M2 models")
    return spec


@dataclass(frozen=True)
class Edge:
    """
    One relationship between two canonical entities, with its provenance.

    The basis and carrier field are not arguments a caller chooses: they are
    checked against the edge type's specification, so an edge cannot claim to
    be better evidence than the Layer 1 column it came from.
    """

    edge_type: EdgeType
    source: EntityRef
    target: EntityRef
    basis: EdgeBasis
    carrier_field: str
    source_system: str

    def __post_init__(self) -> None:
        spec = spec_for(self.edge_type)
        if self.source.entity_type != spec.source_entity:
            raise RelationshipContractError(
                f"{self.edge_type} runs from {spec.source_entity}, "
                f"not {self.source.entity_type}"
            )
        if self.target.entity_type != spec.target_entity:
            raise RelationshipContractError(
                f"{self.edge_type} runs to {spec.target_entity}, "
                f"not {self.target.entity_type}"
            )
        if self.basis is not spec.basis:
            raise RelationshipContractError(
                f"{self.edge_type} is known by {spec.basis}, not {self.basis}: the basis "
                f"follows from the edge type and is never chosen per edge"
            )
        if self.carrier_field != spec.carrier_field:
            raise RelationshipContractError(
                f"{self.edge_type} is derived from {spec.carrier_field}, "
                f"not {self.carrier_field!r}"
            )
        touched = {self.source.entity_type, self.target.entity_type} & ISOLATED_ENTITIES
        if touched:
            raise RelationshipContractError(
                f"an edge may not touch {sorted(touched)}: M2 models documents as isolated "
                f"nodes, and M4 owns every Document to Customer association"
            )
        if not self.source_system.strip():
            raise RelationshipContractError("Edge.source_system must be a non-empty string")

    @property
    def sort_key(self) -> tuple[str, str, str]:
        """Total order within a result: edge type, then source identity, then target."""
        return (str(self.edge_type), self.source.source_id, self.target.source_id)

    @property
    def identity(self) -> tuple[str, str, str, str]:
        """What makes two edges the same edge. Used to prove results hold no duplicate."""
        return (str(self.edge_type), self.source.source_id,
                self.target.source_id, self.source_system)

    def to_payload(self) -> dict[str, object]:
        """Deterministic projection. Carries the basis and the carrier, never a timestamp."""
        return {
            "edge": str(self.edge_type),
            "source": self.source.to_payload(),
            "target": self.target.to_payload(),
            "basis": str(self.basis),
            "carrier_field": self.carrier_field,
            "source_system": self.source_system,
        }


def order_edges(edges: tuple[Edge, ...]) -> tuple[Edge, ...]:
    """Edges in their total order, with duplicates removed."""
    unique: dict[tuple[str, str, str, str], Edge] = {}
    for edge in edges:
        unique.setdefault(edge.identity, edge)
    return tuple(sorted(unique.values(), key=lambda edge: edge.sort_key))
