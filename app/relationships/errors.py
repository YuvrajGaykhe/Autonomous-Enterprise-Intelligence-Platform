"""
Relationship model errors.

These are contract violations, not data problems: a null source key or an
unmatched one is ordinary Layer 1 state and yields no edge rather than an
error (plan A23). What raises here is an attempt to build a relationship M2
does not model, or to claim a basis an edge has not earned.
"""

from __future__ import annotations

from app.intelligence.errors import IntelligenceError


class RelationshipError(IntelligenceError):
    """Base class for every error this package raises."""


class RelationshipContractError(RelationshipError):
    """An edge was constructed that M2 does not model, or that misstates its basis."""


class UnknownCustomerError(RelationshipError):
    """A query was asked about a customer that is not in scope."""

    def __init__(self, source_id: str, source_system: str) -> None:
        super().__init__(
            f"customer {source_id!r} is not in source system {source_system!r}: a "
            f"neighbourhood of an absent customer would be silently empty"
        )
        self.source_id = source_id
        self.source_system = source_system
