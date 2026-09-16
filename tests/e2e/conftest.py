"""
Shared harness for the H5 end-to-end suite.

Spec Section 15 requires an end-to-end layer covering "demo source ->
ingestion -> PostgreSQL -> API query". The E1 and E2 suites drive the
orchestrator directly and stop at the database; the F suites query the API
over rows written by a direct ingestion. Neither exercises the whole path.

This harness builds the real FastAPI application over the real migrated test
database and drives every step through HTTP, so the run is started, observed
and queried exactly as a reviewer or a Layer 2 consumer would.

Connectors are injected rather than taken from the committed configuration,
because the API deliberately refuses to accept a data directory or base URL
from a request. That lets the failure suite point the same application at the
bad fixture or at a connector that cannot answer, without weakening the API.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.api.connectors import ConnectorProvider
from app.connectors.base import SourceConnector
from app.connectors.registry import build_connector
from app.main import create_app

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
BAD_FIXTURE_DIR = REPO / "data" / "fixtures" / "csv_demo_bad"

#: The run clock, so every assertion about timing is deterministic.
T0 = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)

API = "/api/v1"
ENTITY_TYPES = ("organizations", "employees", "customers", "deals",
                "projects", "support_tickets", "documents")

CSV_ENTITIES = yaml.safe_load(
    (REPO / "config" / "connectors" / "csv_demo.yaml").read_text(encoding="utf-8")
)["entities"]


def csv_rows(directory: Path, entity: str) -> list[dict[str, str]]:
    """The source rows a CSV fixture holds, read independently of the connector."""
    with (directory / CSV_ENTITIES[entity]["file"]).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def csv_ids(directory: Path, entity: str) -> set[str]:
    column = CSV_ENTITIES[entity]["id_column"]
    return {row[column] for row in csv_rows(directory, entity)}


def make_app(sessions, build: Callable[[str], SourceConnector] | None = None):
    """The real application, optionally over injected connectors."""
    connectors = None if build is None else ConnectorProvider(build=build)
    return create_app(sessions=sessions, connectors=connectors)


@pytest.fixture
def api(e1_sessions) -> Iterator[TestClient]:
    """The application over the committed demo data."""
    def build(source: str) -> SourceConnector:
        if source == "csv_demo":
            return build_connector("csv_demo", data_directory=DEMO_DIR)
        return build_connector(source)

    with TestClient(make_app(e1_sessions, build), raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def bad_fixture_api(e1_sessions) -> Iterator[TestClient]:
    """The same application pointed at the deliberately malformed fixture."""
    def build(source: str) -> SourceConnector:
        if source == "csv_demo":
            return build_connector("csv_demo", data_directory=BAD_FIXTURE_DIR)
        return build_connector(source)

    with TestClient(make_app(e1_sessions, build), raise_server_exceptions=False) as client:
        yield client


def start_run(client: TestClient, **body: object) -> dict:
    """POST an ingestion run and return the created run document."""
    response = client.post(f"{API}/ingestion/runs", json={"source": "csv_demo", **body})
    assert response.status_code == 201, response.text
    return response.json()


def page(client: TestClient, entity: str, **params: object) -> dict:
    response = client.get(f"{API}/entities/{entity}", params={"limit": 500, **params})
    assert response.status_code == 200, response.text
    return response.json()
