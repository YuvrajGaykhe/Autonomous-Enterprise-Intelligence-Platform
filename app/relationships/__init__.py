"""
Layer 2 relationship model (VS-01 M2).

One uniform way to ask what a customer is connected to, where every edge
states how it is known. Read-only over frozen Layer 1 rows: this package
adds no table, no migration and no persistence, so its rollback is deleting
the package.

Public API:
    EdgeType / EdgeBasis   the seven relationships M2 models and the two
                           bases they carry. EdgeBasis is M1's vocabulary,
                           re-exported here so a caller needs one import.
    EdgeSpec / EDGE_SPECS  how each edge type is derived from Layer 1, and
                           the carrier column it is derived from.
    Edge                   one relationship, with its basis, its carrier and
                           its source system.
    neighbourhood          a customer's tickets, deals, projects and owner.
    escalation_path        the account owner's manager, and each open
                           ticket's assignee's manager.
    policy_documents       policy documents as bare nodes, with no customer
                           scope of any kind.

Documents are isolated. No edge has a document endpoint, so a document has
degree zero in this model and no path of any length reaches a customer.
Employee ownership of a document is not evidence that the document belongs
to, concerns or supports a customer: deriving a Document to Customer
association is M4's sole responsibility, through a link that cites the text
asserting it (plan A9, A9.2).

The import graph is a DAG: app.intelligence (M1) is read by this package,
which is read by app.evidence (M4). This package never names M4.
"""

from app.intelligence import EdgeBasis
from app.relationships.edges import (
    all_edge_types,
    canonical_fk_edges,
    edges_of_type,
    source_key_edges,
)
from app.relationships.errors import (
    RelationshipContractError,
    RelationshipError,
    UnknownCustomerError,
)
from app.relationships.model import (
    EDGE_SPECS,
    ISOLATED_ENTITIES,
    Edge,
    EdgeSpec,
    EdgeType,
    order_edges,
    spec_for,
)
from app.relationships.queries import (
    OPEN_TICKET_STATUS,
    POLICY_DOCUMENT_TYPE,
    EscalationPath,
    Neighbourhood,
    escalation_path,
    neighbourhood,
    policy_documents,
)

__all__ = [
    "EDGE_SPECS",
    "ISOLATED_ENTITIES",
    "OPEN_TICKET_STATUS",
    "POLICY_DOCUMENT_TYPE",
    "Edge",
    "EdgeBasis",
    "EdgeSpec",
    "EdgeType",
    "EscalationPath",
    "Neighbourhood",
    "RelationshipContractError",
    "RelationshipError",
    "UnknownCustomerError",
    "all_edge_types",
    "canonical_fk_edges",
    "edges_of_type",
    "escalation_path",
    "neighbourhood",
    "order_edges",
    "policy_documents",
    "source_key_edges",
    "spec_for",
]
