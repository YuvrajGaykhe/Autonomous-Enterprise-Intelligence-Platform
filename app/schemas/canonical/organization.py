"""
Organization canonical schema.

Spec fields: name, industry, country, status
is_active: No (not meaningful for Organization per spec)
"""

from app.schemas.canonical.common import CanonicalBase


class OrganizationCanonical(CanonicalBase):
    """
    Source-neutral canonical representation of an Organization.

    Represents the enterprise boundary / tenant. The demo system
    has one organization (e.g. "Acme Corp").
    """

    name: str
    industry: str | None = None
    country: str | None = None
    status: str | None = None
