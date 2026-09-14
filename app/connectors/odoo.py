"""
Odoo mock connector for Layer 1.

Implements the SourceConnector protocol for the C3 mock-source
Odoo namespace. Communicates via HTTP GET to /odoo/... endpoints
and returns source-native Odoo payloads without normalization.

Architecture:
    OdooMockConnector
         │  HTTP GET
         ▼
    C3 mock-source /odoo/{entity}
         │
         ▼
    data/demo/*.csv (shared source of truth)

This connector:
- Uses httpx for HTTP communication
- Returns Odoo source-native dicts (int IDs, Odoo field names)
- Validates responses against B3 Odoo source schemas
- Maps HTTP/network failures to C1 exception hierarchy
- Is strictly read-only (GET only)
- Has no database or canonical-schema dependencies

Does NOT:
- Normalize field names to canonical
- Generate UUIDs
- Access PostgreSQL / SQLAlchemy
- Perform write operations
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.connectors.types import (
    ConnectorCapabilities,
    ConnectorConfigurationError,
    ConnectorEntityError,
    ConnectorHealth,
    ConnectorRequestError,
    ConnectorUnavailableError,
    Page,
    SourceEntity,
)
from app.schemas.source.odoo import (
    OdooCustomerSource,
    OdooDealSource,
    OdooDocumentSource,
    OdooEmployeeSource,
    OdooOrganizationSource,
    OdooProjectSource,
    OdooSupportTicketSource,
)


# ---------------------------------------------------------------------------
# Supported entities and their B3 schema validators
# ---------------------------------------------------------------------------

_ENTITY_SCHEMAS = {
    "organizations": OdooOrganizationSource,
    "employees": OdooEmployeeSource,
    "customers": OdooCustomerSource,
    "deals": OdooDealSource,
    "projects": OdooProjectSource,
    "support_tickets": OdooSupportTicketSource,
    "documents": OdooDocumentSource,
}

_ENTITY_DESCRIPTIONS = {
    "organizations": "Odoo res.company records",
    "employees": "Odoo hr.employee records",
    "customers": "Odoo res.partner (customer) records",
    "deals": "Odoo crm.lead (opportunity) records",
    "projects": "Odoo project.project records",
    "support_tickets": "Odoo helpdesk.ticket records",
    "documents": "Odoo documents.document records",
}

SUPPORTED_ENTITIES = sorted(_ENTITY_SCHEMAS.keys())

# Maximum retries for transient network errors (connection refused, timeout)
_MAX_RETRIES = 2
_RETRY_DELAY_S = 0.5


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class OdooConnectorConfig:
    """Configuration for the Odoo mock connector."""

    source_name: str
    source_type: str
    base_url: str
    timeout: float

    @classmethod
    def from_yaml(cls, path: str | Path) -> OdooConnectorConfig:
        """Load configuration from a YAML file.

        Raises:
            ConnectorConfigurationError: if the file is missing or invalid.
        """
        config_path = Path(path)
        if not config_path.exists():
            raise ConnectorConfigurationError(
                f"Configuration file not found: {config_path}",
                source_name="odoo",
            )

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except Exception as exc:
            raise ConnectorConfigurationError(
                f"Failed to parse configuration: {exc}",
                source_name="odoo",
            ) from exc

        if not isinstance(raw, dict):
            raise ConnectorConfigurationError(
                "Configuration must be a YAML mapping",
                source_name="odoo",
            )

        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> OdooConnectorConfig:
        """Create configuration from a plain dictionary."""
        source_name = config.get("source_name", "odoo_mock")
        source_type = config.get("source_type", "mock")
        base_url = config.get("base_url")
        timeout = config.get("timeout", 10)

        if not base_url:
            raise ConnectorConfigurationError(
                "Configuration requires 'base_url'",
                source_name=source_name,
            )

        if not isinstance(base_url, str) or not base_url.startswith("http"):
            raise ConnectorConfigurationError(
                f"Invalid base_url: '{base_url}'. Must be an HTTP(S) URL.",
                source_name=source_name,
            )

        try:
            timeout = float(timeout)
            if timeout <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ConnectorConfigurationError(
                f"Invalid timeout: '{timeout}'. Must be a positive number.",
                source_name=source_name,
            )

        return cls(
            source_name=source_name,
            source_type=source_type,
            base_url=base_url.rstrip("/"),
            timeout=timeout,
        )


# ---------------------------------------------------------------------------
# Connector implementation
# ---------------------------------------------------------------------------


class OdooMockConnector:
    """Odoo mock connector implementing the SourceConnector protocol.

    Communicates with the C3 mock-source /odoo/ namespace via HTTP GET.
    Returns source-native Odoo payloads. No normalization, no persistence.
    """

    def __init__(self, config: OdooConnectorConfig) -> None:
        """Initialize the Odoo mock connector.

        Args:
            config: parsed Odoo connector configuration.
        """
        self._config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
        )

    @property
    def source_name(self) -> str:
        """Logical source identifier."""
        return self._config.source_name

    @property
    def source_type(self) -> str:
        """Connector technology type."""
        return self._config.source_type

    def health_check(self) -> ConnectorHealth:
        """Check whether the Odoo mock source is reachable.

        Calls GET /health and measures latency. Returns ConnectorHealth
        with healthy=False on any failure rather than raising.
        """
        start = time.monotonic()
        try:
            resp = self._client.get("/health")
            latency_ms = (time.monotonic() - start) * 1000

            if resp.status_code != 200:
                return ConnectorHealth(
                    healthy=False,
                    source_name=self.source_name,
                    message=f"Health check returned HTTP {resp.status_code}",
                    latency_ms=latency_ms,
                )

            try:
                body = resp.json()
            except Exception:
                return ConnectorHealth(
                    healthy=False,
                    source_name=self.source_name,
                    message="Health check returned malformed JSON",
                    latency_ms=latency_ms,
                )

            if body.get("status") != "healthy":
                return ConnectorHealth(
                    healthy=False,
                    source_name=self.source_name,
                    message=f"Source reports unhealthy: {body}",
                    latency_ms=latency_ms,
                )

            return ConnectorHealth(
                healthy=True,
                source_name=self.source_name,
                message=f"Odoo mock source healthy, {len(body.get('entities', []))} entities",
                latency_ms=latency_ms,
            )

        except httpx.ConnectError as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return ConnectorHealth(
                healthy=False,
                source_name=self.source_name,
                message=f"Connection refused: {exc}",
                latency_ms=latency_ms,
            )

        except httpx.TimeoutException as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return ConnectorHealth(
                healthy=False,
                source_name=self.source_name,
                message=f"Connection timed out: {exc}",
                latency_ms=latency_ms,
            )

        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return ConnectorHealth(
                healthy=False,
                source_name=self.source_name,
                message=f"Unexpected error: {exc}",
                latency_ms=latency_ms,
            )

    def list_entities(self) -> list[SourceEntity]:
        """Return the seven supported Odoo entity types.

        Deterministic, no network call required.
        """
        return [
            SourceEntity(
                entity_type=entity_type,
                description=_ENTITY_DESCRIPTIONS[entity_type],
            )
            for entity_type in SUPPORTED_ENTITIES
        ]

    def fetch_entities(
        self,
        entity_type: str,
        cursor: str | None = None,
        page_size: int = 100,
    ) -> Page[dict]:
        """Fetch a page of Odoo source records.

        Translates the connector pagination contract (cursor/page_size)
        into C3's limit/offset query parameters.

        Args:
            entity_type: which entity to fetch.
            cursor: offset as string, or None for first page.
            page_size: max records per page. Must be > 0.

        Returns:
            Page[dict] with Odoo source-native records.

        Raises:
            ConnectorEntityError: if entity_type is unsupported.
            ConnectorRequestError: if page_size or cursor is invalid,
                or the upstream response is malformed.
            ConnectorUnavailableError: if the source is unreachable.
        """
        self._validate_entity_type(entity_type)

        if page_size <= 0:
            raise ConnectorRequestError(
                f"page_size must be positive, got {page_size}",
                source_name=self.source_name,
            )

        offset = self._parse_cursor(cursor)

        endpoint = f"/odoo/{entity_type}"
        params = {"limit": page_size, "offset": offset}

        body = self._get_json(endpoint, params=params)

        # Validate response structure
        if "data" not in body or "pagination" not in body:
            raise ConnectorRequestError(
                f"Malformed collection response from {endpoint}: "
                f"missing 'data' or 'pagination'",
                source_name=self.source_name,
            )

        pagination = body["pagination"]
        required_fields = {"offset", "limit", "total", "has_more"}
        missing = required_fields - set(pagination.keys())
        if missing:
            raise ConnectorRequestError(
                f"Malformed pagination from {endpoint}: "
                f"missing fields: {missing}",
                source_name=self.source_name,
            )

        records = body["data"]
        if not isinstance(records, list):
            raise ConnectorRequestError(
                f"Expected 'data' to be a list, got {type(records).__name__}",
                source_name=self.source_name,
            )

        # Validate each record against B3 Odoo source schema
        schema_cls = _ENTITY_SCHEMAS[entity_type]
        validated_records = []
        for record in records:
            try:
                schema_cls.model_validate(record)
            except Exception as exc:
                raise ConnectorRequestError(
                    f"Malformed {entity_type} payload from Odoo source: {exc}",
                    source_name=self.source_name,
                )
            validated_records.append(record)

        has_more = pagination["has_more"]
        next_cursor = None
        if has_more:
            next_offset = pagination.get("next_offset")
            if next_offset is not None:
                next_cursor = str(next_offset)
            else:
                # Fallback: compute from offset + len(records)
                next_cursor = str(offset + len(records))

        return Page(
            items=validated_records,
            next_cursor=next_cursor,
            has_more=has_more,
            total_count=pagination.get("total"),
        )

    def get_entity(
        self,
        entity_type: str,
        source_id: str,
    ) -> dict:
        """Fetch a single Odoo source record by ID.

        Args:
            entity_type: which entity to fetch.
            source_id: the Odoo source-native ID (as string).

        Returns:
            Odoo source-native dict.

        Raises:
            ConnectorEntityError: if entity_type is unsupported
                or the record is not found.
            ConnectorRequestError: if the response is malformed.
            ConnectorUnavailableError: if the source is unreachable.
        """
        self._validate_entity_type(entity_type)

        endpoint = f"/odoo/{entity_type}/{source_id}"

        try:
            body = self._get_json(endpoint)
        except ConnectorRequestError as exc:
            # 404 from C3 means record not found
            if "HTTP 404" in str(exc):
                raise ConnectorEntityError(
                    f"Record not found: {entity_type}/{source_id}",
                    source_name=self.source_name,
                    entity_type=entity_type,
                    source_id=source_id,
                ) from exc
            raise

        if "data" not in body:
            raise ConnectorRequestError(
                f"Malformed detail response from {endpoint}: missing 'data'",
                source_name=self.source_name,
            )

        record = body["data"]

        # Validate against B3 schema
        schema_cls = _ENTITY_SCHEMAS[entity_type]
        try:
            schema_cls.model_validate(record)
        except Exception as exc:
            raise ConnectorRequestError(
                f"Malformed {entity_type} payload: {exc}",
                source_name=self.source_name,
            )

        return record

    def capabilities(self) -> ConnectorCapabilities:
        """Declare Odoo mock connector capabilities.

        The mock Odoo source supports pagination but not true
        incremental sync. The connector is strictly read-only.
        """
        return ConnectorCapabilities(
            supported_entity_types=list(SUPPORTED_ENTITIES),
            supports_incremental=False,
            supports_health_check=True,
            read_only=True,
        )

    # -------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------

    def _validate_entity_type(self, entity_type: str) -> None:
        """Raise ConnectorEntityError if entity_type is unsupported."""
        if entity_type not in _ENTITY_SCHEMAS:
            raise ConnectorEntityError(
                f"Unsupported entity type: '{entity_type}'. "
                f"Supported: {SUPPORTED_ENTITIES}",
                source_name=self.source_name,
                entity_type=entity_type,
            )

    def _parse_cursor(self, cursor: str | None) -> int:
        """Parse cursor string into integer offset.

        Raises ConnectorRequestError for invalid cursors.
        """
        if cursor is None:
            return 0

        try:
            offset = int(cursor)
        except ValueError:
            raise ConnectorRequestError(
                f"Invalid cursor: '{cursor}'. Must be a non-negative integer.",
                source_name=self.source_name,
            )

        if offset < 0:
            raise ConnectorRequestError(
                f"Cursor offset must be non-negative, got {offset}",
                source_name=self.source_name,
            )

        return offset

    def _get_json(
        self,
        endpoint: str,
        params: dict | None = None,
    ) -> dict:
        """Execute GET request with retry for transient failures.

        Retries on connection errors and timeouts only.
        Does NOT retry on 4xx, schema validation, or other errors.

        Returns parsed JSON body.

        Raises:
            ConnectorUnavailableError: connection or timeout failure.
            ConnectorRequestError: HTTP error or malformed response.
        """
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = self._client.get(endpoint, params=params)

                if resp.status_code == 404:
                    raise ConnectorRequestError(
                        f"HTTP 404 from {endpoint}",
                        source_name=self.source_name,
                    )

                if resp.status_code >= 400:
                    raise ConnectorRequestError(
                        f"HTTP {resp.status_code} from {endpoint}: "
                        f"{resp.text[:200]}",
                        source_name=self.source_name,
                    )

                try:
                    return resp.json()
                except Exception as exc:
                    raise ConnectorRequestError(
                        f"Malformed JSON from {endpoint}: {exc}",
                        source_name=self.source_name,
                    ) from exc

            except (ConnectorRequestError, ConnectorEntityError):
                # Don't retry client errors or entity errors
                raise

            except httpx.ConnectError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY_S)
                    continue

            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY_S)
                    continue

            except Exception as exc:
                raise ConnectorUnavailableError(
                    f"Unexpected error requesting {endpoint}: {exc}",
                    source_name=self.source_name,
                ) from exc

        raise ConnectorUnavailableError(
            f"Source unreachable after {_MAX_RETRIES + 1} attempts: {last_exc}",
            source_name=self.source_name,
        )
