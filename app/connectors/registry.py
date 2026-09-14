"""
Configured source connectors.

The single place that turns a logical source name into a connector built
from its committed configuration in config/connectors/. The ingestion CLI
(scripts/ingest_demo.py) and the API both build connectors through here.

Overrides exist for operators and tests only: base_url for the HTTP sources
(e.g. http://localhost:8080 outside Docker) and data_directory for csv_demo.
The API never accepts either from a request.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.connectors.base import SourceConnector
from app.connectors.csv import CsvConnector, CsvConnectorConfig
from app.connectors.odoo import OdooConnectorConfig, OdooMockConnector
from app.connectors.rest import RestConnector, RestConnectorConfig
from app.connectors.types import ConnectorConfigurationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONNECTOR_CONFIG_DIR = PROJECT_ROOT / "config" / "connectors"
SOURCE_CONFIG_FILES = {
    "csv_demo": "csv_demo.yaml",
    "odoo_mock": "odoo.yaml",
    "rest_mock": "rest.yaml",
}


def _http_config(source: str, base_url: str | None) -> dict[str, Any]:
    path = CONNECTOR_CONFIG_DIR / SOURCE_CONFIG_FILES[source]
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ConnectorConfigurationError(f"{path.name} must be a YAML mapping", source_name=source)
    return raw if base_url is None else {**raw, "base_url": base_url}


def build_connector(
    source: str,
    *,
    base_url: str | None = None,
    data_directory: Path | None = None,
) -> SourceConnector:
    """Build a configured connector from config/connectors/ with optional overrides."""
    if source not in SOURCE_CONFIG_FILES:
        raise ConnectorConfigurationError(f"unknown source {source!r}", source_name=source)
    if source == "csv_demo":
        if base_url is not None:
            raise ConnectorConfigurationError("--base-url applies to HTTP sources only",
                                              source_name=source)
        config = CsvConnectorConfig.from_yaml(CONNECTOR_CONFIG_DIR / SOURCE_CONFIG_FILES[source])
        if data_directory is not None:
            config.data_directory = str(data_directory)
        return CsvConnector(config, base_path=PROJECT_ROOT)
    if data_directory is not None:
        raise ConnectorConfigurationError("--data-directory applies to csv_demo only",
                                          source_name=source)
    if source == "odoo_mock":
        return OdooMockConnector(OdooConnectorConfig.from_dict(_http_config(source, base_url)))
    return RestConnector(RestConnectorConfig.from_dict(_http_config(source, base_url)))
