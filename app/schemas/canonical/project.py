"""
Project canonical schema.

Spec fields: name, customer_source_id, owner_source_id, status,
             start_date, end_date, budget
is_active: Yes

The spec (Section 6, line 362) explicitly lists customer_source_id
and owner_source_id as minimum Project fields. The spec (line 373-377)
says "retain both the source foreign key and a canonical resolved key."
Therefore customer_id canonical FK is included, nullable.

Budget uses Decimal for fixed-precision representation.
"""

import uuid
from datetime import date
from decimal import Decimal

from app.schemas.canonical.common import CanonicalBase


class ProjectCanonical(CanonicalBase):
    """
    Source-neutral canonical representation of a Project.

    Supports delivery/resource context. customer_id is nullable
    because the customer reference may not resolve.
    """

    name: str
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget: Decimal | None = None
    is_active: bool

    # Source keys
    customer_source_id: str | None = None
    owner_source_id: str | None = None

    # Canonical FK: customer (nullable)
    customer_id: uuid.UUID | None = None
