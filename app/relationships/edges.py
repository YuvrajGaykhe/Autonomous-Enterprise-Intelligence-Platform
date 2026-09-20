"""
Building M2's edges from frozen Layer 1 rows.

Two builders, one per basis, both parameterised by an EdgeSpec. Every edge
of a given basis is therefore produced by exactly one code path: the
source-system scoping, the null handling, the ordering and the duplicate
rule cannot drift apart between edge types, and a test of one path is a test
of all four source-key edges rather than of the one it names.

    canonical_fk_edges   follows a resolved FK column. E1 resolved it against
                         a parent in the same source system, so the edge is a
                         fact Layer 1 already holds.
    source_key_edges     joins an unresolved *_source_id string to its parent
                         under E1's own predicate: the same source_system,
                         the same source_entity, the same source_id that
                         app/ingestion resolves FKs with. The edge is
                         therefore exactly as strong as E1's own resolution
                         would have been, and no stronger.

A null carrier and an unmatched carrier both yield no edge. Neither is an
error: an unresolved source key is ordinary Layer 1 state (plan A23), and
inventing an edge for one would be fabricating a relationship.

Every statement is scoped to one source_system and ordered explicitly. The
caller owns the session; nothing here writes, commits or logs.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.intelligence import EntityRef, Scope
from app.persistence.repositories.canonical import ENTITY_MODELS
from app.relationships.errors import RelationshipContractError
from app.relationships.model import (
    EDGE_SPECS,
    Edge,
    EdgeSpec,
    EdgeType,
    order_edges,
    spec_for,
)


def _model(entity_type: str) -> Any:
    model = ENTITY_MODELS.get(entity_type)
    if model is None:
        raise RelationshipContractError(f"unknown canonical entity type {entity_type!r}")
    return model


def _in_scope(model: Any, entity_type: str, scope: Scope) -> tuple[Any, ...]:
    """E1's own identity predicate: one source system, one source entity."""
    return (
        model.source_system == scope.source_system,
        model.source_entity == entity_type,
    )


def _restrict(statement: Select[Any], column: Any, values: Collection[str] | None) -> Select[Any]:
    """Narrow a statement to named source ids, deterministically and without duplicates."""
    if values is None:
        return statement
    return statement.where(column.in_(sorted(set(values))))


def canonical_fk_edges(
    spec: EdgeSpec,
    session: Session,
    scope: Scope,
    *,
    customer_source_ids: Collection[str] | None = None,
) -> tuple[Edge, ...]:
    """
    Edges over a resolved canonical FK, from a customer to its child rows.

    The join is on the FK itself, so a child whose FK E1 could not resolve
    carries a NULL and contributes nothing. Both endpoints are constrained to
    the scope's source system: a resolved FK cannot cross source systems, and
    asserting it here means no future re-parenting can make it do so silently.
    """
    if spec.is_source_key_join:
        raise RelationshipContractError(f"{spec.edge_type} is not a canonical FK edge")
    parent = _model(spec.source_entity)
    child = _model(spec.carrier_entity)
    fk_column = getattr(child, spec.carrier_field.split(".", 1)[1])
    statement = (
        select(parent.source_id, child.source_id)
        .join(child, fk_column == parent.id)
        .where(
            *_in_scope(parent, spec.source_entity, scope),
            *_in_scope(child, spec.carrier_entity, scope),
        )
        .order_by(parent.source_id, child.source_id)
    )
    statement = _restrict(statement, parent.source_id, customer_source_ids)
    return _edges(spec, scope, session.execute(statement).all())


def source_key_edges(
    spec: EdgeSpec,
    session: Session,
    scope: Scope,
    *,
    carrier_source_ids: Collection[str] | None = None,
) -> tuple[Edge, ...]:
    """
    Edges over an unresolved source key, joined at read time.

    The join predicate is E1's: same source_system, same source_entity, same
    source_id. A NULL carrier matches nothing and an unmatched carrier
    matches nothing, so both yield no edge rather than a false one.
    """
    if not spec.is_source_key_join:
        raise RelationshipContractError(f"{spec.edge_type} is not a source-key join edge")
    carrier = _model(spec.carrier_entity)
    target = _model(spec.target_entity)
    carrier_column = getattr(carrier, spec.carrier_field.split(".", 1)[1])
    # Aliased so employee_reports_to, whose endpoints are both employees, joins
    # the table to itself rather than collapsing onto one row.
    parent = target.__table__.alias("relationship_target")
    statement = (
        select(carrier.source_id, parent.c.source_id)
        .join(
            parent,
            (parent.c.source_id == carrier_column)
            & (parent.c.source_system == carrier.source_system)
            & (parent.c.source_entity == spec.target_entity),
        )
        .where(
            *_in_scope(carrier, spec.carrier_entity, scope),
            carrier_column.is_not(None),
        )
        .order_by(carrier.source_id, parent.c.source_id)
    )
    statement = _restrict(statement, carrier.source_id, carrier_source_ids)
    return _edges(spec, scope, session.execute(statement).all())


def _edges(spec: EdgeSpec, scope: Scope, rows: Sequence[Any]) -> tuple[Edge, ...]:
    """Turn (source id, target id) rows into ordered, duplicate-free edges."""
    built = tuple(
        Edge(
            edge_type=spec.edge_type,
            source=EntityRef(spec.source_entity, source_id),
            target=EntityRef(spec.target_entity, target_id),
            basis=spec.basis,
            carrier_field=spec.carrier_field,
            source_system=scope.source_system,
        )
        for source_id, target_id in rows
    )
    return order_edges(built)


def edges_of_type(
    edge_type: EdgeType,
    session: Session,
    scope: Scope,
    *,
    source_ids: Collection[str] | None = None,
) -> tuple[Edge, ...]:
    """
    Every edge of one type in scope, optionally narrowed to named rows.

    source_ids names the edge's own source rows for a canonical FK (the
    customers), and the carrier rows for a source-key join. They are the same
    thing wherever the carrier lives on the source, which is every source-key
    edge M2 models.
    """
    spec = spec_for(edge_type)
    if spec.is_source_key_join:
        return source_key_edges(spec, session, scope, carrier_source_ids=source_ids)
    return canonical_fk_edges(spec, session, scope, customer_source_ids=source_ids)


def all_edge_types() -> tuple[EdgeType, ...]:
    """Every edge type M2 models, in declaration order."""
    return tuple(EDGE_SPECS)
