"""
Application-scoped connector provider for the API.

Each configured source's connector is built on first use and then reused:
HTTP connectors own a connection pool, so building one per request would
leak pools. Construction is lazy so the API still starts (and /health still
answers) when a connector configuration is broken; a failed build is not
cached and is retried on the next request.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable

from app.connectors.base import SourceConnector
from app.connectors.registry import SOURCE_CONFIG_FILES, build_connector


class UnknownSourceError(LookupError):
    """The requested source is not configured."""


class ConnectorProvider:
    """Builds each configured connector once and hands out the shared instance."""

    def __init__(
        self,
        build: Callable[[str], SourceConnector] = build_connector,
        sources: Iterable[str] = SOURCE_CONFIG_FILES,
    ) -> None:
        self._build = build
        self._sources = tuple(sorted(sources))
        self._connectors: dict[str, SourceConnector] = {}
        self._lock = threading.Lock()

    @property
    def source_names(self) -> tuple[str, ...]:
        """Configured source names in stable (sorted) order."""
        return self._sources

    def get(self, source: str) -> SourceConnector:
        """Return the connector for a configured source.

        Raises:
            UnknownSourceError: the source is not configured.
            ConnectorConfigurationError: its configuration is invalid.
        """
        if source not in self._sources:
            raise UnknownSourceError(source)
        with self._lock:
            connector = self._connectors.get(source)
            if connector is None:
                connector = self._build(source)
                self._connectors[source] = connector
        return connector
