"""
Shared harness for the H2 connector contract suite.

Spec Section 15 requires that "every connector obeys the same interface and
never uses write methods". The C-task suites each test one connector against
its own doubles; this harness instead builds all three *real* connectors over
*real* sources and hands them to one parameterized suite, so a connector that
drifts from the shared contract fails here even if its own suite still passes.

Sources:
    csv_demo   the committed data/demo CSV files, read through CsvConnector.
    odoo_mock  the C3 mock-source served in-process, /odoo namespace.
    rest_mock  the same server, /rest namespace.

The mock-source is started once per session on an ephemeral port and loaded
from the same committed CSVs, so all three connectors expose the same demo
records in three source-native shapes. Every request the connectors make is
recorded, which is how the read-only assertions are proved at runtime rather
than by inspection alone.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Iterator
from http.server import HTTPServer

import pytest

from app.connectors.base import SourceConnector
from app.connectors.registry import PROJECT_ROOT, build_connector

sys.path.insert(0, str(PROJECT_ROOT / "docker"))

import mock_source  # noqa: E402

DEMO_DIR = PROJECT_ROOT / "data" / "demo"

#: Every canonical entity type each connector must offer (spec Section 6).
CONTRACT_ENTITIES = (
    "organizations", "employees", "customers", "deals",
    "projects", "support_tickets", "documents",
)

#: The three configured sources, by logical source name.
CONTRACT_SOURCES = ("csv_demo", "odoo_mock", "rest_mock")

#: The id column each entity's CSV carries. The HTTP sources always use "id".
#: The interface is shared; the identity field name is not, which is exactly
#: why the contract is expressed through get_entity, not payload shape.
CSV_ID_COLUMNS = {
    "organizations": "organization_id",
    "employees": "employee_id",
    "customers": "customer_id",
    "deals": "deal_id",
    "projects": "project_id",
    "support_tickets": "ticket_id",
    "documents": "document_id",
}


def source_id_of(connector: SourceConnector, entity_type: str, record: dict) -> str:
    """The source-native identifier of a record, as that source spells it."""
    field = CSV_ID_COLUMNS[entity_type] if connector.source_name == "csv_demo" else "id"
    return str(record[field])


class RecordingHandler(mock_source.MockSourceHandler):
    """Mock-source handler that records the method and path of every request."""

    requests: list[tuple[str, str]] = []

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming
        RecordingHandler.requests.append(("GET", self.path))
        super().do_GET()

    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output clean."""


@pytest.fixture(scope="session")
def mock_source_url() -> Iterator[str]:
    """The C3 mock-source, loaded from the committed demo CSVs."""
    odoo, rest = mock_source.load_source_data(DEMO_DIR)
    mock_source.ODOO_DATA.update(odoo)
    mock_source.REST_DATA.update(rest)

    server = HTTPServer(("127.0.0.1", 0), RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def requests_seen() -> Iterator[list[tuple[str, str]]]:
    """The requests the mock-source received during one test."""
    RecordingHandler.requests.clear()
    yield RecordingHandler.requests
    RecordingHandler.requests.clear()


def make_connector(source: str, mock_source_url: str) -> SourceConnector:
    """Build one configured connector over the real demo sources."""
    if source == "csv_demo":
        return build_connector(source, data_directory=DEMO_DIR)
    return build_connector(source, base_url=mock_source_url)


@pytest.fixture(params=CONTRACT_SOURCES)
def connector(request: pytest.FixtureRequest, mock_source_url: str) -> SourceConnector:
    """Each configured connector in turn, over the same demo dataset."""
    return make_connector(request.param, mock_source_url)


@pytest.fixture
def csv_connector() -> SourceConnector:
    return build_connector("csv_demo", data_directory=DEMO_DIR)
