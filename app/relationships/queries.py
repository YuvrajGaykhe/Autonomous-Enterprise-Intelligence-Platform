"""
The three public relationship queries of VS-01 (plan A9).

    neighbourhood(customer)     tickets, deals, projects, account owner
    escalation_path(customer)   account owner to manager, and each open
                                ticket's assignee to their manager
    policy_documents()          documents of type 'policy', as bare nodes

There is no fourth, and there is no generic traversal. A caller-directed
traverse() would be a speculative graph API: VS-01 asks three questions, so
M2 answers three questions, and a new question is a new named query with its
own ordering and its own test.

What these queries deliberately do not do:

    No document reaches a customer.  policy_documents() takes no customer
    argument and returns bare document nodes. No edge in this package has a
    document endpoint, so there is no path of any length from a document to a
    customer, by composition or otherwise. Deriving that association is M4's
    sole responsibility, through a link that cites the text asserting it.

    No ownership is composed.  An employee owns many customers, many deals
    and many documents, and those sets are unrelated. Shared ownership is not
    evidence of a relationship between the owned things, so no query here
    joins one ownership edge to another to reach a customer.

    deal_owned_by is not returned.  It is modelled substrate for VS-02's
    per-owner aggregation and VS-03's people map (plan A9.1). VS-01 has no
    consumer for it, and inventing one here to make the model look fully
    consumed is the specific failure the v2.2 decision forbids.

Every query takes the M1 Scope rather than a session plus loose arguments,
so no query can quietly widen the source system it reads. The caller owns
the session; nothing here writes, commits or logs.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence import EntityRef, Scope
from app.persistence.models import Customer, Document, SupportTicket
from app.relationships.edges import edges_of_type
from app.relationships.errors import UnknownCustomerError
from app.relationships.model import (
    CUSTOMERS,
    DOCUMENTS,
    SUPPORT_TICKETS,
    Edge,
    EdgeType,
    order_edges,
)

#: The canonical status of a ticket that is not yet resolved. The enum is
#: Layer 1's (config/mappings/normalization.yaml: [open, resolved]).
OPEN_TICKET_STATUS = "open"

#: The document type policy_documents() returns. A literal, not a caller's
#: argument: the query is customer-independent and returns the same set for
#: every caller, which is what keeps documents free of customer scope.
POLICY_DOCUMENT_TYPE = "policy"


@dataclass(frozen=True)
class Neighbourhood:
    """What one customer is connected to, and how each connection is known."""

    customer: EntityRef
    tickets: tuple[EntityRef, ...]
    deals: tuple[EntityRef, ...]
    projects: tuple[EntityRef, ...]
    account_owner: EntityRef | None
    edges: tuple[Edge, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "customer": self.customer.to_payload(),
            "tickets": [ref.to_payload() for ref in self.tickets],
            "deals": [ref.to_payload() for ref in self.deals],
            "projects": [ref.to_payload() for ref in self.projects],
            "account_owner": (
                None if self.account_owner is None else self.account_owner.to_payload()
            ),
            "edges": [edge.to_payload() for edge in self.edges],
        }


@dataclass(frozen=True)
class EscalationPath:
    """
    Who to escalate a customer's situation to, and why each person is on the path.

    Two routes, kept separate because they answer different questions: the
    account owner's line of report, and the support line for each ticket that
    is still open. A resolved ticket's assignee is not on the path.
    """

    customer: EntityRef
    account_owner: EntityRef | None
    account_owner_manager: EntityRef | None
    open_tickets: tuple[EntityRef, ...]
    assignees: tuple[EntityRef, ...]
    assignee_managers: tuple[EntityRef, ...]
    edges: tuple[Edge, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "customer": self.customer.to_payload(),
            "account_owner": (
                None if self.account_owner is None else self.account_owner.to_payload()
            ),
            "account_owner_manager": (
                None if self.account_owner_manager is None
                else self.account_owner_manager.to_payload()
            ),
            "open_tickets": [ref.to_payload() for ref in self.open_tickets],
            "assignees": [ref.to_payload() for ref in self.assignees],
            "assignee_managers": [ref.to_payload() for ref in self.assignee_managers],
            "edges": [edge.to_payload() for edge in self.edges],
        }


def _require_customer(session: Session, scope: Scope, customer_source_id: str) -> EntityRef:
    """Refuse a customer that is not in scope, rather than returning an empty result."""
    present = session.scalar(
        select(Customer.source_id).where(
            Customer.source_system == scope.source_system,
            Customer.source_entity == CUSTOMERS,
            Customer.source_id == customer_source_id,
        )
    )
    if present is None:
        raise UnknownCustomerError(customer_source_id, scope.source_system)
    return EntityRef(CUSTOMERS, present)


def _targets(edges: tuple[Edge, ...]) -> tuple[EntityRef, ...]:
    """Edge targets in edge order, without duplicates."""
    seen: dict[tuple[str, str], EntityRef] = {}
    for edge in edges:
        seen.setdefault((edge.target.entity_type, edge.target.source_id), edge.target)
    return tuple(seen.values())


def neighbourhood(
    session: Session, scope: Scope, customer_source_id: str
) -> Neighbourhood:
    """
    One customer's tickets, deals, projects and account owner.

    The three child collections are canonical FK edges; the account owner is
    a source-key join. A customer with no child rows of a kind gets an empty
    tuple, and a customer whose owner_source_id is null or unmatched gets no
    owner rather than a fabricated one.
    """
    customer = _require_customer(session, scope, customer_source_id)
    ids = (customer.source_id,)
    tickets = edges_of_type(EdgeType.CUSTOMER_HAS_TICKET, session, scope, source_ids=ids)
    deals = edges_of_type(EdgeType.CUSTOMER_HAS_DEAL, session, scope, source_ids=ids)
    projects = edges_of_type(EdgeType.CUSTOMER_HAS_PROJECT, session, scope, source_ids=ids)
    owned_by = edges_of_type(EdgeType.CUSTOMER_OWNED_BY, session, scope, source_ids=ids)
    owners = _targets(owned_by)
    return Neighbourhood(
        customer=customer,
        tickets=_targets(tickets),
        deals=_targets(deals),
        projects=_targets(projects),
        account_owner=owners[0] if owners else None,
        edges=order_edges(tickets + deals + projects + owned_by),
    )


def escalation_path(
    session: Session, scope: Scope, customer_source_id: str
) -> EscalationPath:
    """
    The account owner's manager, and the manager of every open ticket's assignee.

    Every open ticket counts, whatever its priority: plan A9 says each open
    ticket's assignee, and filtering to high priority would silently drop the
    person handling a medium-priority ticket that is still unresolved.
    """
    customer = _require_customer(session, scope, customer_source_id)
    ids = (customer.source_id,)
    owned_by = edges_of_type(EdgeType.CUSTOMER_OWNED_BY, session, scope, source_ids=ids)
    owners = _targets(owned_by)
    owner_reports_to = edges_of_type(
        EdgeType.EMPLOYEE_REPORTS_TO, session, scope,
        source_ids=[ref.source_id for ref in owners],
    )
    owner_managers = _targets(owner_reports_to)

    open_ticket_ids = _open_ticket_ids(session, scope, customer.source_id)
    assigned_to = edges_of_type(
        EdgeType.TICKET_ASSIGNED_TO, session, scope, source_ids=open_ticket_ids
    )
    assignees = _targets(assigned_to)
    assignee_reports_to = edges_of_type(
        EdgeType.EMPLOYEE_REPORTS_TO, session, scope,
        source_ids=[ref.source_id for ref in assignees],
    )
    return EscalationPath(
        customer=customer,
        account_owner=owners[0] if owners else None,
        account_owner_manager=owner_managers[0] if owner_managers else None,
        open_tickets=tuple(EntityRef(SUPPORT_TICKETS, ticket) for ticket in open_ticket_ids),
        assignees=assignees,
        assignee_managers=_targets(assignee_reports_to),
        edges=order_edges(owned_by + owner_reports_to + assigned_to + assignee_reports_to),
    )


def _open_ticket_ids(session: Session, scope: Scope, customer_source_id: str) -> tuple[str, ...]:
    """Source ids of the customer's unresolved tickets, in source-identity order."""
    rows = session.scalars(
        select(SupportTicket.source_id)
        .join(Customer, SupportTicket.customer_id == Customer.id)
        .where(
            SupportTicket.source_system == scope.source_system,
            SupportTicket.source_entity == SUPPORT_TICKETS,
            SupportTicket.status == OPEN_TICKET_STATUS,
            Customer.source_system == scope.source_system,
            Customer.source_entity == CUSTOMERS,
            Customer.source_id == customer_source_id,
        )
        .order_by(SupportTicket.source_id)
    ).all()
    return tuple(rows)


def policy_documents(session: Session, scope: Scope) -> tuple[EntityRef, ...]:
    """
    Every policy document in scope, as bare nodes.

    Takes no customer argument and returns the same set for every caller.
    M3's band rules cite DOC-003, which is why M2 reads the documents table
    at all; touching that table is not a licence to relate a document to a
    customer, and no edge here does.
    """
    rows = session.scalars(
        select(Document.source_id)
        .where(
            Document.source_system == scope.source_system,
            Document.source_entity == DOCUMENTS,
            Document.document_type == POLICY_DOCUMENT_TYPE,
        )
        .order_by(Document.source_id)
    ).all()
    return tuple(EntityRef(DOCUMENTS, source_id) for source_id in rows)
