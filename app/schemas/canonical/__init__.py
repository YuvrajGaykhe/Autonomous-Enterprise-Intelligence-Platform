"""
Canonical schema package for Layer 1.

Provides source-neutral Pydantic data contracts for the seven
canonical enterprise entities.
"""

from app.schemas.canonical.common import CanonicalBase
from app.schemas.canonical.organization import OrganizationCanonical
from app.schemas.canonical.employee import EmployeeCanonical
from app.schemas.canonical.customer import CustomerCanonical
from app.schemas.canonical.deal import DealCanonical
from app.schemas.canonical.project import ProjectCanonical
from app.schemas.canonical.support_ticket import SupportTicketCanonical
from app.schemas.canonical.document import DocumentCanonical

__all__ = [
    "CanonicalBase",
    "OrganizationCanonical",
    "EmployeeCanonical",
    "CustomerCanonical",
    "DealCanonical",
    "ProjectCanonical",
    "SupportTicketCanonical",
    "DocumentCanonical",
]
