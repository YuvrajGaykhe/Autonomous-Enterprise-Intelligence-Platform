"""
Assessment scope and Layer 1 snapshot identity (plan A5, A5.1, A24).

A scope is the complete statement of what an assessment was computed over:
one source system, one evaluation date, and one Layer 1 snapshot. Every
later milestone takes a Scope rather than a session plus loose arguments,
so no component can quietly widen what it reads or when it reads it as of.

The Layer 1 fingerprint is a Layer 2 composition over two frozen Layer 1
columns, source_id and record_hash. It requires no change to record_hash,
no change to any Layer 1 module, no migration and no D1 vocabulary change.

    Composition   SHA-256 over the canonical JSON of
                  {entity_type: {"count": n, "records": [[source_id, record_hash], ...]}}
                  for all seven canonical entity types in scope.
    Ordering      every records list is read with an explicit ORDER BY
                  source_id, with source_entity as a tiebreaker. PostgreSQL
                  guarantees no row order without one, and a fingerprint over
                  unordered rows is not reproducible. source_id alone is not
                  provably total, because a canonical table's uniqueness is
                  over (source_system, source_entity, source_id); the
                  tiebreaker makes the order total whatever the data holds,
                  and leaves the digest unchanged wherever no tie exists.
    Exclusions    ingested_at, ingestion_run_id and source_updated_at are
                  deliberately not read. They change on every ingestion, so
                  including them would make an unchanged re-ingestion mint a
                  new fingerprint and destroy the idempotency the fingerprint
                  exists to protect.

Why source_id is included: record_hash covers business fields only and
excludes all provenance, source_id among it. A composition over record_hash
values and counts alone is blind to every source_id rename - yet source_id
is the join key for every SOURCE_KEY_JOIN edge, the input to canonical_id,
what E1 resolves the customer FKs against, and the token quoted in document
links and brief citations. A rename re-keys rows and invalidates citations
while leaving every record_hash untouched.

This module reads. It never writes, commits or logs, and the caller owns the
session, matching the repository convention.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.intelligence.config import RiskRulesConfig, default_risk_rules
from app.intelligence.contract import canonical_json
from app.intelligence.errors import (
    ContractViolationError,
    FingerprintMismatchError,
    ScopeResolutionError,
)
from app.intelligence.timeutil import utc_date
from app.persistence.models import SupportTicket
from app.persistence.repositories.canonical import ENTITY_MODELS

#: The only source system VS-01 assesses. Cross-source aggregation is out of scope.
DEFAULT_SOURCE_SYSTEM = "csv_demo"


class AsOfSource(StrEnum):
    """Which path produced the evaluation date. Recorded, never inferred later."""

    #: The caller named the date. This is what acceptance always uses.
    EXPLICIT = "EXPLICIT"
    #: Derived from max(support_tickets.created_at) in scope: an ad-hoc convenience.
    MAX_TICKET_CREATED_AT = "MAX_TICKET_CREATED_AT"


@dataclass(frozen=True)
class Scope:
    """One source system, one evaluation date, one Layer 1 snapshot."""

    source_system: str
    as_of: date
    layer1_fingerprint: str
    as_of_source: AsOfSource
    entity_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        if not self.source_system.strip():
            raise ContractViolationError("Scope.source_system must be a non-empty string")
        if isinstance(self.as_of, datetime) or not isinstance(self.as_of, date):
            raise ContractViolationError(
                "Scope.as_of must be a calendar date, not a timestamp: a time of day would "
                "make two runs of the same day disagree"
            )
        if set(self.entity_counts) != set(ENTITY_MODELS):
            raise ContractViolationError(
                "Scope.entity_counts must cover every canonical entity type"
            )

    @property
    def record_count(self) -> int:
        """Canonical rows the fingerprint was computed over."""
        return sum(self.entity_counts.values())

    def to_payload(self) -> dict[str, object]:
        """Deterministic projection. Carries no timestamp and no run id."""
        return {
            "source_system": self.source_system,
            "as_of": self.as_of.isoformat(),
            "layer1_fingerprint": self.layer1_fingerprint,
            "as_of_source": str(self.as_of_source),
            "entity_counts": dict(sorted(self.entity_counts.items())),
        }


def layer1_fingerprint(
    session: Session, source_system: str
) -> tuple[str, Mapping[str, int]]:
    """The Layer 1 snapshot identity for one source system, and its per-entity counts."""
    models: Mapping[str, Any] = ENTITY_MODELS
    payload: dict[str, object] = {}
    counts: dict[str, int] = {}
    for entity_type, model in models.items():
        rows = session.execute(
            select(model.source_id, model.record_hash)
            .where(model.source_system == source_system)
            .order_by(model.source_id, model.source_entity)
        ).all()
        payload[entity_type] = {
            "count": len(rows),
            "records": [[row.source_id, row.record_hash] for row in rows],
        }
        counts[entity_type] = len(rows)
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return digest, MappingProxyType(counts)


def resolve_scope(
    session: Session,
    *,
    source_system: str = DEFAULT_SOURCE_SYSTEM,
    as_of: date | None = None,
    expected_fingerprint: str | None = None,
) -> Scope:
    """
    Resolve the scope an assessment will be computed over.

    as_of resolution order: the caller's date, otherwise the UTC date of the
    latest support ticket in scope. There is no third path. now() is
    forbidden, so a scope with neither a given date nor a ticket to derive
    one from has no defensible evaluation date and is refused.

    When expected_fingerprint is given, a Layer 1 snapshot that is not the
    expected one fails closed. Assessing a database that is not the one the
    configuration was pinned to is how stale or contaminated intelligence
    reaches a brief.
    """
    resolved_as_of, as_of_source = _resolve_as_of(session, source_system, as_of)
    digest, counts = layer1_fingerprint(session, source_system)
    if expected_fingerprint is not None and digest != expected_fingerprint:
        raise FingerprintMismatchError(source_system, expected_fingerprint, digest)
    return Scope(
        source_system=source_system,
        as_of=resolved_as_of,
        layer1_fingerprint=digest,
        as_of_source=as_of_source,
        entity_counts=counts,
    )


def resolve_pinned_scope(
    session: Session,
    *,
    source_system: str = DEFAULT_SOURCE_SYSTEM,
    as_of: date | None = None,
    config: RiskRulesConfig | None = None,
) -> Scope:
    """Resolve a scope against the fingerprint pinned in configuration (plan A27.1b)."""
    rules = config if config is not None else default_risk_rules()
    return resolve_scope(
        session,
        source_system=source_system,
        as_of=as_of,
        expected_fingerprint=rules.pinned_fingerprint(source_system),
    )


def _resolve_as_of(
    session: Session, source_system: str, as_of: date | None
) -> tuple[date, AsOfSource]:
    if as_of is not None:
        if isinstance(as_of, datetime) or not isinstance(as_of, date):
            raise ContractViolationError(
                "as_of must be a calendar date, not a timestamp"
            )
        return as_of, AsOfSource.EXPLICIT
    latest = session.scalar(
        select(func.max(SupportTicket.created_at))
        .where(SupportTicket.source_system == source_system)
    )
    if latest is None:
        raise ScopeResolutionError(
            f"no as_of was given and source_system {source_system!r} holds no support ticket "
            f"to derive one from; now() is forbidden, so there is no defensible evaluation date"
        )
    return utc_date(latest), AsOfSource.MAX_TICKET_CREATED_AT
