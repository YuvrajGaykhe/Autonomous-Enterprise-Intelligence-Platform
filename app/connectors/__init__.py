"""
Connector package for Layer 1.

Exposes the public connector contract: the SourceConnector protocol,
result types, exception hierarchy, and concrete connector implementations.
"""

from app.connectors.base import SourceConnector
from app.connectors.csv import CsvConnector, CsvConnectorConfig
from app.connectors.types import (
    ConnectorCapabilities,
    ConnectorHealth,
    Page,
    SourceEntity,
    ConnectorError,
    ConnectorConfigurationError,
    ConnectorAuthenticationError,
    ConnectorUnavailableError,
    ConnectorRequestError,
    ConnectorEntityError,
)

__all__ = [
    # Protocol
    "SourceConnector",
    # Concrete connectors
    "CsvConnector",
    "CsvConnectorConfig",
    # Result types
    "ConnectorCapabilities",
    "ConnectorHealth",
    "Page",
    "SourceEntity",
    # Exceptions
    "ConnectorError",
    "ConnectorConfigurationError",
    "ConnectorAuthenticationError",
    "ConnectorUnavailableError",
    "ConnectorRequestError",
    "ConnectorEntityError",
]

