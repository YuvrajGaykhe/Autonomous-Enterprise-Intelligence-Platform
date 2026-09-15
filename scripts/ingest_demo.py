"""
Run a Layer 1 ingestion from the command line (make ingest-demo).

    python scripts/ingest_demo.py
    python scripts/ingest_demo.py --entities customers deals --page-size 50
    python scripts/ingest_demo.py --source odoo_mock --base-url http://localhost:8080

Prints the run summary as JSON (identifiers and counts only). Exit status:
    0  the run finished SUCCESS, PARTIAL_SUCCESS or NOOP
    1  the run finished FAILED
    2  invalid request, connector configuration or logging settings; no run
       was created
System failures (database unavailable, programming errors) propagate with a
traceback after the run is marked FAILED.

The database comes from DATABASE_URL / POSTGRES_* (app.core.config). Log
events go to stderr as configured by APP_LOG_LEVEL and LOG_FORMAT
(app.core.logging), so stdout carries only the summary.
Credentials are never accepted on the command line and never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.connectors import ConnectorConfigurationError  # noqa: E402
from app.connectors.registry import SOURCE_CONFIG_FILES, build_connector  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.logging import configured_logging, resolve_format, resolve_level  # noqa: E402
from app.ingestion.errors import IngestionRequestError  # noqa: E402
from app.ingestion.orchestrator import IngestionRequest, run_ingestion  # noqa: E402
from app.persistence.repositories.runs import RunStatus  # noqa: E402

__all__ = ["SOURCE_CONFIG_FILES", "build_connector", "main", "parse_args"]


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
    settings = get_settings()
    try:
        resolve_level(settings.app_log_level)
        resolve_format(settings.log_format)
    except ValueError as exc:
        print(f"ingest_demo: invalid logging settings: {exc}", file=sys.stderr)
        return 2
    with configured_logging(settings.app_log_level, settings.log_format):
        return _ingest(args, settings.effective_database_url)


def _ingest(args: argparse.Namespace, database_url: str) -> int:
    engine = create_engine(database_url, echo=False, pool_pre_ping=True)
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
