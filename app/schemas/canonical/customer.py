"""
Customer canonical schema.

Spec fields: name, email, segment, industry, status,
             owner_source_id, created_at
is_active: Yes

owner_source_id is a source-system reference to the account
owner (employee). It remains a string because the owner may
not resolve to a canonical employee.
"""

from datetime import datetime

from app.schemas.canonical.common import CanonicalBase


class CustomerCanonical(CanonicalBase):
    """
    Source-neutral canonical representation of a Customer.

    Supports customer/account intelligence. owner_source_id is
    a source-system reference to the account owner employee.
    """

    name: str
    email: str | None = None
    segment: str | None = None
    industry: str | None = None
    status: str | None = None
    owner_source_id: str | None = None
    created_at: datetime | None = None
    is_active: bool
