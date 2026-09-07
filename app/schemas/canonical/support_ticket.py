"""
SupportTicket canonical schema.

Spec fields: customer_source_id, priority, status, category,
             subject, description, created_at, resolved_at,
             assignee_source_id
is_active: No (not meaningful for SupportTicket per spec)

customer_id is a canonical FK added by B1 per the spec's
relationship-key pattern (retain both source key and canonical key).
"""

import uuid
from datetime import datetime

from app.schemas.canonical.common import CanonicalBase


class SupportTicketCanonical(CanonicalBase):
    """
    Source-neutral canonical representation of a Support Ticket.

    Supports risk/support signal analysis. No is_active field.
    """

    subject: str | None = None
    description: str | None = None
    priority: str | None = None
    status: str | None = None
    category: str | None = None
    created_at: datetime | None = None
    resolved_at: datetime | None = None

    # Source keys
    customer_source_id: str | None = None
    assignee_source_id: str | None = None

    # Canonical FK: customer (nullable)
    customer_id: uuid.UUID | None = None
