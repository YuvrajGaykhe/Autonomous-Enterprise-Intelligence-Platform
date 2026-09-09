"""
CSV source connector for Layer 1.

Implements the SourceConnector protocol for CSV file-based sources.
Reads CSV files from a configured directory, exposes source records
through the standard connector interface, and preserves all source
values exactly as they appear in the CSV.

This connector:
- Reads CSV files using Python's standard csv module
- Supports all 7 entity types via declarative YAML configuration
- Provides stable source IDs from configured ID columns
- Supports cursor-based pagination (offset-based for static files)
- Preserves source-native values (no normalization)
- Is strictly read-only
- Has no database or HTTP dependencies

Architecture:
    CSV file → csv.DictReader → raw dict → Page[dict]
    B3 source schemas validate the raw dicts downstream (or in tests)
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.connectors.types import (
    ConnectorCapabilities,
    ConnectorConfigurationError,
    ConnectorEntityError,
    ConnectorHealth,
    ConnectorRequestError,
    Page,
    SourceEntity,
)


@dataclass
class CsvEntityConfig:
    """Configuration for a single CSV entity mapping."""

    entity_type: str
    file: str
    id_column: str


@dataclass
class CsvConnectorConfig:
    """Configuration for the CSV connector."""

    source_name: str
    source_type: str
    data_directory: str
    entities: dict[str, CsvEntityConfig] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> CsvConnectorConfig:
        """Load configuration from a YAML file.

        Args:
            path: path to the YAML configuration file.

        Returns:
            Parsed CsvConnectorConfig.

        Raises:
            ConnectorConfigurationError: if the file is missing or invalid.
        """
        config_path = Path(path)
        if not config_path.exists():
            raise ConnectorConfigurationError(
                f"Configuration file not found: {config_path}",
                source_name="csv",
            )

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except Exception as exc:
            raise ConnectorConfigurationError(
                f"Failed to parse configuration: {exc}",
                source_name="csv",
            ) from exc

        if not isinstance(raw, dict):
            raise ConnectorConfigurationError(
                "Configuration must be a YAML mapping",
                source_name="csv",
            )

        source_name = raw.get("source_name", "csv_demo")
        source_type = raw.get("source_type", "csv")
        data_directory = raw.get("data_directory", "data/demo")

        entities: dict[str, CsvEntityConfig] = {}
        raw_entities = raw.get("entities", {})
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
            file_name = entity_cfg.get("file")
            id_column = entity_cfg.get("id_column")
            if not file_name or not id_column:
                raise ConnectorConfigurationError(
                    f"Entity '{entity_type}' requires 'file' and 'id_column'",
                    source_name=source_name,
                )
            entities[entity_type] = CsvEntityConfig(
                entity_type=entity_type,
                file=file_name,
                id_column=id_column,
            )

        return cls(
            source_name=source_name,
            source_type=source_type,
            data_directory=data_directory,
            entities=entities,
        )

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> CsvConnectorConfig:
        """Create configuration from a plain dictionary.

        Useful for tests and programmatic construction.
        """
        source_name = config.get("source_name", "csv_demo")
        source_type = config.get("source_type", "csv")
        data_directory = config.get("data_directory", "data/demo")

        entities: dict[str, CsvEntityConfig] = {}
        for entity_type, entity_cfg in config.get("entities", {}).items():
            entities[entity_type] = CsvEntityConfig(
                entity_type=entity_type,
                file=entity_cfg["file"],
                id_column=entity_cfg["id_column"],
            )

        return cls(
            source_name=source_name,
            source_type=source_type,
            data_directory=data_directory,
            entities=entities,
        )


class CsvConnector:
    """CSV source connector implementing the SourceConnector protocol.

    Reads CSV files from a configured directory and exposes source
    records through the standard connector interface.

    All values remain source-native strings. No normalization,
    type conversion, or whitespace stripping is performed.
    """

    def __init__(
        self,
        config: CsvConnectorConfig,
        *,
        base_path: str | Path | None = None,
    ) -> None:
        """Initialize the CSV connector.

        Args:
            config: parsed CSV connector configuration.
            base_path: optional base directory for resolving relative
                data_directory paths. Defaults to current working directory.
        """
        self._config = config
        if base_path is not None:
            self._base_path = Path(base_path)
        else:
            self._base_path = Path.cwd()

    @property
    def source_name(self) -> str:
        """Logical source identifier (e.g. 'csv_demo')."""
        return self._config.source_name

    @property
    def source_type(self) -> str:
        """Connector technology type: 'csv'."""
        return self._config.source_type

    def _data_dir(self) -> Path:
        """Resolve the data directory path."""
        data_dir = Path(self._config.data_directory)
        if not data_dir.is_absolute():
            data_dir = self._base_path / data_dir
        return data_dir

    def _entity_path(self, entity_type: str) -> Path:
        """Resolve the file path for an entity type.

        Raises:
            ConnectorEntityError: if the entity type is not configured.
        """
        entity_cfg = self._config.entities.get(entity_type)
        if entity_cfg is None:
            raise ConnectorEntityError(
                f"Entity type '{entity_type}' is not configured",
                source_name=self.source_name,
                entity_type=entity_type,
            )
        return self._data_dir() / entity_cfg.file

    def _read_csv(self, entity_type: str) -> list[dict[str, str]]:
        """Read all rows from a CSV file for the given entity type.

        Returns rows as list of dicts with string values.
        Values are preserved exactly as they appear in the CSV.
        Empty CSV fields become empty strings (csv.DictReader default).

        Raises:
            ConnectorEntityError: if the entity type is not configured.
            ConnectorRequestError: if the file cannot be read.
        """
        file_path = self._entity_path(entity_type)

        if not file_path.exists():
            raise ConnectorRequestError(
                f"Source file not found: {file_path}",
                source_name=self.source_name,
            )

        try:
            with open(file_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception as exc:
            raise ConnectorRequestError(
                f"Failed to read CSV file '{file_path}': {exc}",
                source_name=self.source_name,
            ) from exc

        return rows

    def health_check(self) -> ConnectorHealth:
        """Check whether the configured CSV source is accessible.

        Verifies:
        - data directory exists
        - configured entity files exist

        Returns ConnectorHealth with diagnostic information.
        """
        data_dir = self._data_dir()

        if not data_dir.exists():
            return ConnectorHealth(
                healthy=False,
                source_name=self.source_name,
                message=f"Data directory not found: {data_dir}",
            )

        if not data_dir.is_dir():
            return ConnectorHealth(
                healthy=False,
                source_name=self.source_name,
                message=f"Data path is not a directory: {data_dir}",
            )

        missing_files = []
        for entity_type, entity_cfg in self._config.entities.items():
            file_path = data_dir / entity_cfg.file
            if not file_path.exists():
                missing_files.append(f"{entity_type}: {entity_cfg.file}")

        if missing_files:
            return ConnectorHealth(
                healthy=False,
                source_name=self.source_name,
                message=f"Missing source files: {', '.join(missing_files)}",
            )

        return ConnectorHealth(
            healthy=True,
            source_name=self.source_name,
            message=f"All {len(self._config.entities)} entity files found",
        )

    def list_entities(self) -> list[SourceEntity]:
        """Discover available entity types based on configuration.

        Only returns entities whose configured files actually exist.
        """
        data_dir = self._data_dir()
        entities = []

        for entity_type, entity_cfg in sorted(self._config.entities.items()):
            file_path = data_dir / entity_cfg.file
            if file_path.exists():
                entities.append(SourceEntity(entity_type=entity_type))

        return entities

    def fetch_entities(
        self,
        entity_type: str,
        cursor: str | None = None,
        page_size: int = 100,
    ) -> Page[dict]:
        """Fetch a page of source records for the given entity type.

        Uses offset-based pagination. The cursor is an opaque string
        representing the row offset.

        Args:
            entity_type: which entity to fetch (e.g. 'customers').
            cursor: opaque pagination cursor (None for first page).
            page_size: maximum records per page. Must be > 0.

        Returns:
            Page[dict] with source-native records.

        Raises:
            ConnectorEntityError: if entity type is not configured.
            ConnectorRequestError: if page_size is invalid or cursor
                is malformed.
        """
        if page_size <= 0:
            raise ConnectorRequestError(
                f"page_size must be positive, got {page_size}",
                source_name=self.source_name,
            )

        # Parse cursor (offset)
        offset = 0
        if cursor is not None:
            try:
                offset = int(cursor)
            except ValueError:
                raise ConnectorRequestError(
                    f"Invalid cursor: '{cursor}'",
                    source_name=self.source_name,
                )
            if offset < 0:
                raise ConnectorRequestError(
                    f"Cursor offset must be non-negative, got {offset}",
                    source_name=self.source_name,
                )

        rows = self._read_csv(entity_type)
        total = len(rows)

        page_rows = rows[offset : offset + page_size]
        next_offset = offset + len(page_rows)
        has_more = next_offset < total

        return Page(
            items=page_rows,
            next_cursor=str(next_offset) if has_more else None,
            has_more=has_more,
            total_count=total,
        )

    def get_entity(
        self,
        entity_type: str,
        source_id: str,
    ) -> dict:
        """Fetch a single source record by its source-native ID.

        Args:
            entity_type: which entity to search.
            source_id: the source-native ID value.

        Returns:
            Raw source record as a dict.

        Raises:
            ConnectorEntityError: if the entity type is not configured
                or the record is not found.
        """
        entity_cfg = self._config.entities.get(entity_type)
        if entity_cfg is None:
            raise ConnectorEntityError(
                f"Entity type '{entity_type}' is not configured",
                source_name=self.source_name,
                entity_type=entity_type,
            )

        rows = self._read_csv(entity_type)
        id_column = entity_cfg.id_column

        for row in rows:
            if row.get(id_column) == source_id:
                return row

        raise ConnectorEntityError(
            f"Record not found: {entity_type}/{source_id}",
            source_name=self.source_name,
            entity_type=entity_type,
            source_id=source_id,
        )

    def capabilities(self) -> ConnectorCapabilities:
        """Declare CSV connector capabilities.

        CSV files are static snapshots, so incremental sync is not
        supported. The connector is strictly read-only.
        """
        return ConnectorCapabilities(
            supported_entity_types=sorted(self._config.entities.keys()),
            supports_incremental=False,
            supports_health_check=True,
            read_only=True,
        )
