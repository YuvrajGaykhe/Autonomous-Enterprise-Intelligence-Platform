"""
Connector result types and exception hierarchy for Layer 1.

These types form the return-value contract for SourceConnector.
They are purely structural and have no database, HTTP, or
canonical-schema dependencies.

Design decisions:
- dataclass(frozen=True): immutable results prevent accidental mutation
- Page is Generic[T]: connectors return Page[dict] but the type is
  reusable if a future connector returns typed source schemas
- ConnectorCapabilities.supported_entity_types: list[str] so E1 can
  discover what a connector offers without hardcoding
- All exceptions inherit from ConnectorError so E1 can catch connector
  failures uniformly while still distinguishing failure categories
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConnectorHealth:
    """Result of a connector health check.

    Attributes:
        healthy: whether the source is reachable and operational.
        source_name: logical source identifier (e.g. 'csv_demo').
        message: human-readable diagnostic (optional).
        latency_ms: round-trip time in milliseconds (optional).
    """

    healthy: bool
    source_name: str
    message: str | None = None
    latency_ms: float | None = None


@dataclass(frozen=True)
class SourceEntity:
    """Describes an entity type available from a source connector.

    Attributes:
        entity_type: canonical entity name (e.g. 'customers').
        description: optional human-readable description.
    """

    entity_type: str
    description: str | None = None


@dataclass(frozen=True)
class Page(Generic[T]):
    """A single page of results from a paginated connector fetch.

    Pagination contract:
        1. First request: cursor=None
        2. Connector returns Page with items, next_cursor, has_more
        3. If has_more is True, caller passes next_cursor to the next request
        4. If has_more is False, pagination is complete

    Attributes:
        items: records in this page.
        next_cursor: opaque cursor for the next page (None if last page).
        has_more: whether additional pages exist.
        total_count: total records across all pages if known (optional).
    """

    items: list[T] = field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
    total_count: int | None = None


@dataclass(frozen=True)
class ConnectorCapabilities:
    """Declares what a connector supports.

    Layer 1 connectors are strictly read-only.

    Attributes:
        supported_entity_types: entity types this connector can fetch.
        supports_incremental: whether cursor-based incremental sync works.
        supports_health_check: whether the connector can verify source reachability.
        read_only: always True for Layer 1 connectors.
    """

    supported_entity_types: list[str] = field(default_factory=list)
    supports_incremental: bool = False
    supports_health_check: bool = True
    read_only: bool = True


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class ConnectorError(Exception):
    """Base exception for all connector failures.

    E1 can catch this to handle any connector failure uniformly.
    """

    def __init__(self, message: str, source_name: str | None = None) -> None:
        self.source_name = source_name
        super().__init__(message)


class ConnectorConfigurationError(ConnectorError):
    """Raised when connector configuration is invalid or missing."""


class ConnectorAuthenticationError(ConnectorError):
    """Raised when source authentication fails."""


class ConnectorUnavailableError(ConnectorError):
    """Raised when the source system is unreachable."""


class ConnectorRequestError(ConnectorError):
    """Raised when a source request fails (timeout, bad response, etc.)."""


class ConnectorEntityError(ConnectorError):
    """Raised when a specific entity fetch fails."""

    def __init__(
        self,
        message: str,
        source_name: str | None = None,
        entity_type: str | None = None,
        source_id: str | None = None,
    ) -> None:
        self.entity_type = entity_type
        self.source_id = source_id
        super().__init__(message, source_name)
