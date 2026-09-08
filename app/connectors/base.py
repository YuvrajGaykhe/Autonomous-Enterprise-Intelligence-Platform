"""
Source connector protocol for Layer 1.

Defines the structural contract that every Layer 1 connector must
satisfy. Uses typing.Protocol for structural subtyping: any class
with matching attributes and methods is a valid SourceConnector
without explicit inheritance.

The spec (Section 5) defines exactly this interface:

    class SourceConnector(Protocol):
        source_name: str
        source_type: str
        def health_check(self) -> ConnectorHealth: ...
        def list_entities(self) -> list[SourceEntity]: ...
        def fetch_entities(...) -> Page[dict]: ...
        def get_entity(...) -> dict: ...
        def capabilities(self) -> ConnectorCapabilities: ...

Layer 1 connectors are strictly read-only. No create/update/delete
methods exist in this contract.

This module has NO dependencies on:
- app.persistence (SQLAlchemy / database)
- app.schemas.canonical (canonical Pydantic schemas)
- app.schemas.source (source Pydantic schemas)
- HTTP libraries (requests, httpx, etc.)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.connectors.types import (
    ConnectorCapabilities,
    ConnectorHealth,
    Page,
    SourceEntity,
)


@runtime_checkable
class SourceConnector(Protocol):
    """Protocol defining the Layer 1 source connector contract.

    Every connector (CSV, Odoo, Generic REST, future GraphQL, etc.)
    must satisfy this structural interface.

    Attributes:
        source_name: logical source identifier (e.g. 'csv_demo',
            'odoo_demo'). Maps to source_system in canonical records.
        source_type: connector technology (e.g. 'csv', 'odoo', 'rest').

    All methods are read-only. No write operations are permitted.
    """

    @property
    def source_name(self) -> str:
        """Logical source identifier (e.g. 'csv_demo')."""
        ...

    @property
    def source_type(self) -> str:
        """Connector technology type (e.g. 'csv', 'odoo', 'rest')."""
        ...

    def health_check(self) -> ConnectorHealth:
        """Check whether the source system is reachable and healthy.

        Returns:
            ConnectorHealth with status and diagnostics.
        """
        ...

    def list_entities(self) -> list[SourceEntity]:
        """Discover which entity types this connector can provide.

        Returns:
            List of SourceEntity descriptors.
        """
        ...

    def fetch_entities(
        self,
        entity_type: str,
        cursor: str | None = None,
        page_size: int = 100,
    ) -> Page[dict]:
        """Fetch a page of source records for the given entity type.

        Records are returned as raw dicts (source-native payloads).
        No normalization is performed.

        Args:
            entity_type: which entity to fetch (e.g. 'customers').
            cursor: opaque pagination cursor (None for first page).
            page_size: maximum records per page.

        Returns:
            Page[dict] containing source records and cursor state.

        Raises:
            ConnectorEntityError: if the entity type is unsupported.
            ConnectorRequestError: if the source request fails.
        """
        ...

    def get_entity(
        self,
        entity_type: str,
        source_id: str,
    ) -> dict:
        """Fetch a single source record by its source-native ID.

        Args:
            entity_type: which entity to fetch from.
            source_id: the source-native identifier (NOT a canonical UUID).

        Returns:
            Raw source record as a dict.

        Raises:
            ConnectorEntityError: if the entity is not found.
        """
        ...

    def capabilities(self) -> ConnectorCapabilities:
        """Declare what this connector supports.

        Returns:
            ConnectorCapabilities describing supported entities,
            incremental sync, and read-only status.
        """
        ...
