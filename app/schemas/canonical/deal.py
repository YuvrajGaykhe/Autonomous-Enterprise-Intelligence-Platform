"""
Deal canonical schema.

Spec fields: name, customer_source_id, owner_source_id, stage,
             amount, currency, probability, expected_close_date
is_active: Yes

CRITICAL: customer_id MUST be nullable. The spec explicitly requires
that if a Deal references a source customer that cannot be resolved,
the deal is NOT rejected. Instead, customer_id=None, the original
customer_source_id is preserved, and a WARNING is emitted.

Money uses Decimal for fixed-precision representation per spec.
"""

import uuid
from datetime import date
from decimal import Decimal

from app.schemas.canonical.common import CanonicalBase


class DealCanonical(CanonicalBase):
    """
    Source-neutral canonical representation of a Deal.

    customer_id is nullable because unresolved customer references
    must be preserved, not rejected. The original customer_source_id
    is always preserved for tracking.
    """

    name: str
    stage: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    probability: Decimal | None = None
    expected_close_date: date | None = None
    is_active: bool

    # Source keys (preserved even when canonical FK is NULL)
    customer_source_id: str | None = None
    owner_source_id: str | None = None

    # Canonical FK: customer (nullable per unresolved-FK requirement)
    customer_id: uuid.UUID | None = None
