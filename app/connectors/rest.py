"""
Generic REST source connector for Layer 1.

Implements the SourceConnector protocol for configurable REST API
sources. Unlike the Odoo connector which targets a specific API shape,
this connector is fully configuration-driven: endpoints, authentication,
and entity mappings are supplied through YAML/dict configuration.

Architecture:
    RestConnector
         |  HTTP GET (httpx)
         v
    REST API (e.g. C3 mock-source /rest/{entity})
         |
         v
    data/demo/*.csv (shared source of truth)

This connector:
- Uses httpx for HTTP communication
- Returns REST source-native dicts (string IDs, camelCase fields)
- Validates responses against B3 REST source schemas
- Maps HTTP/network failures to C1 exception hierarchy
- Is strictly read-only (GET only)
- Supports configurable authentication (none, api_key, bearer)
- Has no database or canonical-schema dependencies

Does NOT:
- Normalize field names to canonical
- Generate UUIDs
- Access PostgreSQL / SQLAlchemy
- Perform write operations
- Strip whitespace or convert types beyond source-schema parsing
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.connectors.types import (
    ConnectorAuthenticationError,
    ConnectorCapabilities,
    ConnectorConfigurationError,
    ConnectorEntityError,
    ConnectorHealth,
    ConnectorRequestError,
    ConnectorUnavailableError,
    Page,
    SourceEntity,
)
from app.schemas.source.rest import (
    RestCustomerSource,
    RestDealSource,
    RestDocumentSource,
    RestEmployeeSource,
    RestOrganizationSource,
    RestProjectSource,
    RestSupportTicketSource,
)


# ---------------------------------------------------------------------------
# B3 REST schema mapping
# ---------------------------------------------------------------------------

_ENTITY_SCHEMAS: dict[str, type] = {
    "organizations": RestOrganizationSource,
    "employees": RestEmployeeSource,
    "customers": RestCustomerSource,
    "deals": RestDealSource,
    "projects": RestProjectSource,
    "support_tickets": RestSupportTicketSource,
    "documents": RestDocumentSource,
}

# Maximum retries for transient network/server errors
_MAX_RETRIES = 2
_RETRY_BASE_DELAY_S = 0.5  # exponential backoff: base * 2^attempt
_RETRY_MAX_DELAY_S = 4.0


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class RestEntityConfig:
    """Configuration for a single REST entity endpoint."""

    entity_type: str
    path: str
    description: str | None = None


@dataclass
class RestAuthConfig:
    """Authentication configuration for the REST connector.

    Supported mechanisms:
    - none: no authentication
    - api_key: API key via header (key from env var)
    - bearer: Bearer token via Authorization header (token from env var)
    """

    mechanism: str = "none"
    header_name: str = "Authorization"
    env_var: str = ""

    def get_headers(self) -> dict[str, str]:
        """Build authentication headers from configuration.

        Credentials are resolved from environment variables at call
        time, never stored in configuration files.

        Raises:
            ConnectorConfigurationError: if required env var is missing.
        """
        if self.mechanism == "none":
            return {}

        if not self.env_var:
            raise ConnectorConfigurationError(
                f"Auth mechanism '{self.mechanism}' requires 'env_var' "
                f"to be configured",
                source_name="rest",
            )

        credential = os.environ.get(self.env_var)
        if not credential:
            raise ConnectorConfigurationError(
                f"Environment variable '{self.env_var}' not set "
                f"(required for {self.mechanism} authentication)",
                source_name="rest",
            )

        if self.mechanism == "api_key":
            return {self.header_name: credential}
        elif self.mechanism == "bearer":
            return {"Authorization": f"Bearer {credential}"}
        else:
            raise ConnectorConfigurationError(
                f"Unsupported auth mechanism: '{self.mechanism}'. "
                f"Supported: none, api_key, bearer",
                source_name="rest",
            )


@dataclass
class RestConnectorConfig:
    """Configuration for the Generic REST connector."""

    source_name: str
    source_type: str
    base_url: str
    timeout: float
    health_endpoint: str
    auth: RestAuthConfig
    entities: dict[str, RestEntityConfig] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> RestConnectorConfig:
        """Load configuration from a YAML file.

        Raises:
            ConnectorConfigurationError: if the file is missing or invalid.
        """
        config_path = Path(path)
        if not config_path.exists():
            raise ConnectorConfigurationError(
                f"Configuration file not found: {config_path}",
                source_name="rest",
            )

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except Exception as exc:
            raise ConnectorConfigurationError(
                f"Failed to parse configuration: {exc}",
                source_name="rest",
            ) from exc

        if not isinstance(raw, dict):
            raise ConnectorConfigurationError(
                "Configuration must be a YAML mapping",
                source_name="rest",
            )

        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> RestConnectorConfig:
        """Create configuration from a plain dictionary."""
        source_name = config.get("source_name", "rest_demo")
        source_type = config.get("source_type", "rest")
        base_url = config.get("base_url")
        timeout = config.get("timeout", 10)
        health_endpoint = config.get("health_endpoint", "/health")

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

        # Parse auth
        raw_auth = config.get("auth", {})
        if not isinstance(raw_auth, dict):
            raw_auth = {}
        auth = RestAuthConfig(
            mechanism=raw_auth.get("mechanism", "none"),
            header_name=raw_auth.get("header_name", "Authorization"),
            env_var=raw_auth.get("env_var", ""),
        )

        # Parse entities
        entities: dict[str, RestEntityConfig] = {}
        raw_entities = config.get("entities", {})
        if not isinstance(raw_entities, dict):
            raise ConnectorConfigurationError(
                "Configuration 'entities' must be a mapping",
                source_name=source_name,
            )

        for entity_type, entity_cfg in raw_entities.items():
            if not isinstance(entity_cfg, dict):
                raise ConnectorConfigurationError(
                    f"Entity '{entity_type}' configuration must be a mapping",
                    source_name=source_name,
                )
            entity_path = entity_cfg.get("path")
            if not entity_path:
                raise ConnectorConfigurationError(
                    f"Entity '{entity_type}' requires a 'path'",
                    source_name=source_name,
                )
            entities[entity_type] = RestEntityConfig(
                entity_type=entity_type,
                path=entity_path,
                description=entity_cfg.get("description"),
            )

        if not entities:
            raise ConnectorConfigurationError(
                "Configuration must include at least one entity",
                source_name=source_name,
            )

        return cls(
            source_name=source_name,
            source_type=source_type,
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            health_endpoint=health_endpoint,
            auth=auth,
            entities=entities,
        )


# ---------------------------------------------------------------------------
# Connector implementation
# ---------------------------------------------------------------------------


class RestConnector:
    """Generic REST connector implementing the SourceConnector protocol.

    Configuration-driven HTTP adapter for REST API sources.
    Returns source-native REST payloads. No normalization, no persistence.
    """

    def __init__(self, config: RestConnectorConfig) -> None:
        """Initialize the REST connector.

        Args:
            config: parsed REST connector configuration.
        """
        self._config = config

        # Build auth headers (may raise ConnectorConfigurationError)
        try:
            auth_headers = config.auth.get_headers()
        except ConnectorConfigurationError:
            # Defer auth errors to actual requests, not construction
            auth_headers = {}
            self._auth_deferred = True
        else:
            self._auth_deferred = False

        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            headers=auth_headers,
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
        """Check whether the REST source is reachable.

        Uses the configured health_endpoint. Returns ConnectorHealth
        with healthy=False on any failure rather than raising.
        """
        start = time.monotonic()
        try:
            resp = self._client.get(self._config.health_endpoint)
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

            status = body.get("status", "")
            if status != "healthy":
                return ConnectorHealth(
                    healthy=False,
                    source_name=self.source_name,
                    message=f"Source reports unhealthy: {body}",
                    latency_ms=latency_ms,
                )

            return ConnectorHealth(
                healthy=True,
                source_name=self.source_name,
                message=f"REST source healthy ({self._config.base_url})",
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
        """Return configured REST entity types.

        Deterministic, derived from configuration. No network call.
        """
        return [
            SourceEntity(
                entity_type=entity_cfg.entity_type,
                description=entity_cfg.description or f"REST {entity_cfg.entity_type}",
            )
            for entity_cfg in sorted(
                self._config.entities.values(),
                key=lambda e: e.entity_type,
            )
        ]

    def fetch_entities(
        self,
        entity_type: str,
        cursor: str | None = None,
        page_size: int = 100,
    ) -> Page[dict]:
        """Fetch a page of REST source records.

        Translates cursor/page_size into the REST API's limit/offset
        query parameters.

        Args:
            entity_type: which entity to fetch.
            cursor: offset as string, or None for first page.
            page_size: max records per page. Must be > 0.

        Returns:
            Page[dict] with REST source-native records.

        Raises:
            ConnectorEntityError: if entity_type is unsupported.
            ConnectorRequestError: if page_size or cursor is invalid,
                or the upstream response is malformed.
            ConnectorUnavailableError: if the source is unreachable.
        """
        entity_cfg = self._get_entity_config(entity_type)

        if page_size <= 0:
            raise ConnectorRequestError(
                f"page_size must be positive, got {page_size}",
                source_name=self.source_name,
            )

        offset = self._parse_cursor(cursor)

        params = {"limit": page_size, "offset": offset}
        body = self._get_json(entity_cfg.path, params=params)

        # Validate response structure
        if "data" not in body or "pagination" not in body:
            raise ConnectorRequestError(
                f"Malformed collection response from {entity_cfg.path}: "
                f"missing 'data' or 'pagination'",
                source_name=self.source_name,
            )

        pagination = body["pagination"]
        required_fields = {"offset", "limit", "total", "has_more"}
        missing = required_fields - set(pagination.keys())
        if missing:
            raise ConnectorRequestError(
                f"Malformed pagination from {entity_cfg.path}: "
                f"missing fields: {missing}",
                source_name=self.source_name,
            )

        records = body["data"]
        if not isinstance(records, list):
            raise ConnectorRequestError(
                f"Expected 'data' to be a list, got {type(records).__name__}",
                source_name=self.source_name,
            )

        # Validate each record against B3 REST source schema
        schema_cls = _ENTITY_SCHEMAS.get(entity_type)
        validated_records = []
        for record in records:
            if schema_cls:
                try:
                    schema_cls.model_validate(record)
                except Exception as exc:
                    raise ConnectorRequestError(
                        f"Malformed {entity_type} payload from REST source: {exc}",
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
        """Fetch a single REST source record by ID.

        Args:
            entity_type: which entity to fetch.
            source_id: the REST source-native ID (string).

        Returns:
            REST source-native dict.

        Raises:
            ConnectorEntityError: if entity_type is unsupported
                or the record is not found.
            ConnectorRequestError: if the response is malformed.
            ConnectorUnavailableError: if the source is unreachable.
        """
        entity_cfg = self._get_entity_config(entity_type)

        endpoint = f"{entity_cfg.path}/{source_id}"

        try:
            body = self._get_json(endpoint)
        except ConnectorRequestError as exc:
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
        schema_cls = _ENTITY_SCHEMAS.get(entity_type)
        if schema_cls:
            try:
                schema_cls.model_validate(record)
            except Exception as exc:
                raise ConnectorRequestError(
                    f"Malformed {entity_type} payload: {exc}",
                    source_name=self.source_name,
                )

        return record

    def capabilities(self) -> ConnectorCapabilities:
        """Declare REST connector capabilities.

        Pagination is supported but true incremental sync is not.
        The connector is strictly read-only.
        """
        return ConnectorCapabilities(
            supported_entity_types=sorted(self._config.entities.keys()),
            supports_incremental=False,
            supports_health_check=True,
            read_only=True,
        )

    # -------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------

    def _get_entity_config(self, entity_type: str) -> RestEntityConfig:
        """Get entity configuration or raise ConnectorEntityError."""
        entity_cfg = self._config.entities.get(entity_type)
        if entity_cfg is None:
            raise ConnectorEntityError(
                f"Unsupported entity type: '{entity_type}'. "
                f"Configured: {sorted(self._config.entities.keys())}",
                source_name=self.source_name,
                entity_type=entity_type,
            )
        return entity_cfg

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
        """Execute GET request with retry and exponential backoff.

        Retries on:
        - Connection errors (ConnectError)
        - Timeouts (TimeoutException)
        - Rate limiting (HTTP 429, respects Retry-After)
        - Transient server errors (HTTP 502, 503, 504)

        Does NOT retry on:
        - HTTP 400, 401, 403, 404, 409, 422
        - Schema validation errors
        - Configuration errors

        Returns parsed JSON body.

        Raises:
            ConnectorAuthenticationError: HTTP 401/403.
            ConnectorUnavailableError: connection or timeout failure.
            ConnectorRequestError: HTTP error or malformed response.
        """
        # Check deferred auth errors
        if self._auth_deferred:
            try:
                headers = self._config.auth.get_headers()
                self._client.headers.update(headers)
                self._auth_deferred = False
            except ConnectorConfigurationError:
                raise

        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = self._client.get(endpoint, params=params)

                if resp.status_code == 404:
                    raise ConnectorRequestError(
                        f"HTTP 404 from {endpoint}",
                        source_name=self.source_name,
                    )

                if resp.status_code == 401:
                    raise ConnectorAuthenticationError(
                        f"HTTP 401 Unauthorized from {endpoint}",
                        source_name=self.source_name,
                    )

                if resp.status_code == 403:
                    raise ConnectorAuthenticationError(
                        f"HTTP 403 Forbidden from {endpoint}",
                        source_name=self.source_name,
                    )

                # Rate limiting: retry with Retry-After if available
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if attempt < _MAX_RETRIES:
                        delay = _RETRY_MAX_DELAY_S
                        if retry_after:
                            try:
                                delay = min(float(retry_after), _RETRY_MAX_DELAY_S)
                            except (ValueError, TypeError):
                                pass
                        time.sleep(delay)
                        continue
                    raise ConnectorRequestError(
                        f"Rate limited (HTTP 429) from {endpoint} "
                        f"after {_MAX_RETRIES + 1} attempts",
                        source_name=self.source_name,
                    )

                # Transient server errors: retry with backoff
                if resp.status_code in (502, 503, 504):
                    if attempt < _MAX_RETRIES:
                        delay = min(
                            _RETRY_BASE_DELAY_S * (2 ** attempt),
                            _RETRY_MAX_DELAY_S,
                        )
                        time.sleep(delay)
                        continue
                    raise ConnectorRequestError(
                        f"HTTP {resp.status_code} from {endpoint} "
                        f"after {_MAX_RETRIES + 1} attempts: "
                        f"{resp.text[:200]}",
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

            except (
                ConnectorRequestError,
                ConnectorEntityError,
                ConnectorAuthenticationError,
                ConnectorConfigurationError,
            ):
                raise

            except httpx.ConnectError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    delay = min(
                        _RETRY_BASE_DELAY_S * (2 ** attempt),
                        _RETRY_MAX_DELAY_S,
                    )
                    time.sleep(delay)
                    continue

            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    delay = min(
                        _RETRY_BASE_DELAY_S * (2 ** attempt),
                        _RETRY_MAX_DELAY_S,
                    )
                    time.sleep(delay)
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
