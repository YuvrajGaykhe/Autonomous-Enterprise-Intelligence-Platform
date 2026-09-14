"""
E1 batch reconciliation planner.

Given the D2-valid records of one batch (in input order), the persisted state
of their source identities, and the resolved parents of their source keys,
plan_batch decides deterministically:

    1. Canonical FK resolution. A canonical FK is resolved only from a source
       key the canonical contract carries (e.g. Deal.customer_source_id) and
       only to a parent persisted by the SAME source system. Cross-source
       records are never merged (spec Section 7). A source key without a
       persisted parent leaves the FK null and yields an UnresolvedReference;
       a null source key has nothing to resolve.

    2. Classification per record, against the state as of that record: the
       persisted state, updated by earlier records of the same batch.
           INSERTED   the source identity has no state
           UNCHANGED  record_hash, source_updated_at and resolved FKs all equal
           UPDATED    anything else
       Resolved FKs are compared because record_hash excludes them: a child
       whose parent arrives in a later run must be updated, not skipped.

    3. Writes. The latest record observed for an identity is its final state
       (duplicates in a batch: the last occurrence wins); only identities
       with at least one non-UNCHANGED record are written, ordered by
       source_id.

The planner performs no database access and never mutates its inputs.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from app.persistence.repositories.canonical import PersistedState
from app.schemas.canonical import CanonicalBase


@dataclass(frozen=True)
class ReferenceRule:
    """How one canonical FK is resolved.

    source_key_field is the canonical field holding the parent's source_id,
    or None when the canonical contract carries no source key for the
    relationship; the FK then stays null and nothing is reported.
    """

    field: str
    parent_entity: str
    source_key_field: str | None


REFERENCE_RULES: Mapping[str, tuple[ReferenceRule, ...]] = MappingProxyType({
    "organizations": (),
    # EmployeeCanonical carries no organization source key (B1/B2 contract
    # gap): organization_id cannot be resolved without fabricating a parent.
    "employees": (ReferenceRule("organization_id", "organizations", None),),
    "customers": (),
    "deals": (ReferenceRule("customer_id", "customers", "customer_source_id"),),
    "projects": (ReferenceRule("customer_id", "customers", "customer_source_id"),),
    "support_tickets": (ReferenceRule("customer_id", "customers", "customer_source_id"),),
    "documents": (),
})


class Outcome(StrEnum):
    INSERTED = "inserted"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class RecordDecision:
    record_index: int
    source_id: str
    outcome: Outcome


@dataclass(frozen=True)
class UnresolvedReference:
    record_index: int
    source_id: str
    rule: ReferenceRule
    source_key: str


@dataclass(frozen=True)
class BatchPlan:
    entity_type: str
    writes: tuple[tuple[CanonicalBase, Mapping[str, uuid.UUID | None]], ...]
    decisions: tuple[RecordDecision, ...]
    unresolved: tuple[UnresolvedReference, ...]

    def count(self, outcome: Outcome) -> int:
        return sum(1 for decision in self.decisions if decision.outcome is outcome)


@dataclass(frozen=True)
class _State:
    record_hash: str
    source_updated_at: datetime | None
    references: Mapping[str, uuid.UUID | None]

    def same_content(self, other: _State) -> bool:
        return (self.record_hash == other.record_hash
                and self.source_updated_at == other.source_updated_at
                and dict(self.references) == dict(other.references))


def _rules(entity_type: str) -> tuple[ReferenceRule, ...]:
    rules = REFERENCE_RULES.get(entity_type)
    if rules is None:
        raise ValueError(f"unknown canonical entity type {entity_type!r}")
    return rules


def parent_keys(
    entity_type: str,
    records: Sequence[CanonicalBase],
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Return {fk field: (parent entity, sorted distinct source keys)} to look up."""
    lookups = {}
    for rule in _rules(entity_type):
        if rule.source_key_field is None:
            continue
        keys = {getattr(record, rule.source_key_field) for record in records}
        keys.discard(None)
        lookups[rule.field] = (rule.parent_entity, tuple(sorted(keys)))
    return lookups


def plan_batch(
    entity_type: str,
    records: Sequence[tuple[int, CanonicalBase]],
    existing: Mapping[str, PersistedState],
    parents: Mapping[str, Mapping[str, uuid.UUID]],
) -> BatchPlan:
    """Plan the writes, decisions and unresolved references of one batch.

    Args:
        entity_type: canonical entity of every record.
        records: (record_index, D2-valid record) pairs in strictly increasing index order.
        existing: persisted state by source_id for this entity and source system.
        parents: {fk field: {source key: parent id}} for every rule with a source key.
    """
    rules = _rules(entity_type)
    resolvable = {rule.field for rule in rules if rule.source_key_field is not None}
    if set(parents) != resolvable:
        raise ValueError(f"{entity_type} requires parents for {sorted(resolvable)}")

    current = {
        source_id: _State(state.record_hash, state.source_updated_at, dict(state.references))
        for source_id, state in existing.items()
    }
    finals: dict[str, tuple[CanonicalBase, Mapping[str, uuid.UUID | None]]] = {}
    decisions: list[RecordDecision] = []
    unresolved: list[UnresolvedReference] = []
    previous_index = -1
    for index, record in records:
        if index <= previous_index:
            raise ValueError("records must be in strictly increasing record_index order")
        previous_index = index
        if record.source_entity != entity_type:
            raise ValueError(f"record source_entity does not match {entity_type!r}")

        references: dict[str, uuid.UUID | None] = {}
        for rule in rules:
            key = None if rule.source_key_field is None else getattr(record, rule.source_key_field)
            if key is None:
                references[rule.field] = None
                continue
            parent = parents[rule.field].get(key)
            references[rule.field] = parent
            if parent is None:
                unresolved.append(UnresolvedReference(index, record.source_id, rule, key))

        prior = current.get(record.source_id)
        state = _State(record.record_hash, record.source_updated_at, MappingProxyType(references))
        if prior is None:
            outcome = Outcome.INSERTED
        elif prior.same_content(state):
            outcome = Outcome.UNCHANGED
        else:
            outcome = Outcome.UPDATED
        decisions.append(RecordDecision(index, record.source_id, outcome))
        if outcome is not Outcome.UNCHANGED:
            finals[record.source_id] = (record, state.references)
        current[record.source_id] = state

    return BatchPlan(
        entity_type=entity_type,
        writes=tuple(finals[source_id] for source_id in sorted(finals)),
        decisions=tuple(decisions),
        unresolved=tuple(unresolved),
    )
