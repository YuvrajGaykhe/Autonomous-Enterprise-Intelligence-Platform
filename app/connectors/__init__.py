"""
Connector package for Layer 1.

Exposes the public connector contract: the SourceConnector protocol,
result types, and exception hierarchy. Concrete connector implementations
(CSV, Odoo, REST) will be added in C2, C4, and C5.
"""

from app.connectors.base import SourceConnector
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
