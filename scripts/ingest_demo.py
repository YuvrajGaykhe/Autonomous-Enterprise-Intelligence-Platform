"""
Run a Layer 1 ingestion from the command line (make ingest-demo).

    python scripts/ingest_demo.py
    python scripts/ingest_demo.py --entities customers deals --page-size 50
    python scripts/ingest_demo.py --source odoo_mock --base-url http://localhost:8080

Prints the run summary as JSON (identifiers and counts only). Exit status:
    0  the run finished SUCCESS, PARTIAL_SUCCESS or NOOP
    1  the run finished FAILED
    2  invalid request or connector configuration; no run was created
System failures (database unavailable, programming errors) propagate with a
traceback after the run is marked FAILED.

The database comes from DATABASE_URL / POSTGRES_* (app.core.config).
Credentials are never accepted on the command line and never printed.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.connectors import (  # noqa: E402
    ConnectorConfigurationError,
    CsvConnector,
    CsvConnectorConfig,
    OdooConnectorConfig,
    OdooMockConnector,
    RestConnector,
    RestConnectorConfig,
    SourceConnector,
)
from app.core.config import get_settings  # noqa: E402
from app.ingestion.errors import IngestionRequestError  # noqa: E402
from app.ingestion.orchestrator import IngestionRequest, run_ingestion  # noqa: E402
from app.persistence.repositories.runs import RunStatus  # noqa: E402

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


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one Layer 1 ingestion.")
    parser.add_argument("--source", choices=sorted(SOURCE_CONFIG_FILES), default="csv_demo")
    parser.add_argument("--entities", nargs="+", metavar="ENTITY",
                        help="entity types to ingest (default: every available entity)")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--base-url", help="override base_url for odoo_mock / rest_mock")
    parser.add_argument("--data-directory", type=Path, help="override the csv_demo directory")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    engine = create_engine(get_settings().effective_database_url, echo=False, pool_pre_ping=True)
    try:
        connector = build_connector(args.source, base_url=args.base_url,
                                    data_directory=args.data_directory)
        summary = run_ingestion(
            connector, sessionmaker(bind=engine, expire_on_commit=False),
            IngestionRequest(entities=args.entities, page_size=args.page_size),
        )
    except (IngestionRequestError, ConnectorConfigurationError) as exc:
        print(f"ingest_demo: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()
    print(json.dumps(summary.to_dict(), indent=2))
    return 1 if summary.status is RunStatus.FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
