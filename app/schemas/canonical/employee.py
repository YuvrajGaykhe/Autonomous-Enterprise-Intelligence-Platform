"""
Employee canonical schema.

Spec fields: name, email, department, title, manager_source_id,
             status, hire_date
is_active: Yes

manager_source_id is explicitly listed in the spec as a minimum
Employee field. It remains a source-system string reference, not
a canonical UUID, because the manager may not resolve to a
canonical employee.

organization_id is a canonical FK added by B1 for the
Organization -> Employee relationship.
"""

import uuid
from datetime import date

from app.schemas.canonical.common import CanonicalBase


class EmployeeCanonical(CanonicalBase):
    """
    Source-neutral canonical representation of an Employee.

    Supports HR and ownership relationships. manager_source_id
    is a source-system reference (not a canonical UUID) because
    the manager may come from any source system.
    """

    name: str
    email: str | None = None
    department: str | None = None
    title: str | None = None
    manager_source_id: str | None = None
    status: str | None = None
    hire_date: date | None = None
    is_active: bool

    # Canonical FK: organization (nullable, may not be resolved)
    organization_id: uuid.UUID | None = None
