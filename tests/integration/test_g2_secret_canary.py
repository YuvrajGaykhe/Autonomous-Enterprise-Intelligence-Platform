"""
G2 end-to-end secret canary (spec Section 15: "Secrets not returned/logged").

Synthetic canary values enter Layer 1 through every channel a secret or a
private source value can use: a REST API key from the environment, upstream
error and health bodies, schema-invalid upstream records, CSV payload values,
a database password in an unreachable DATABASE_URL, request bodies and query
strings, and exception messages from connector construction.

Each canary is first shown to really be inside the system (sent upstream,
carried by a connector exception, stored in ingestion_errors) and then shown
never to appear in any API response (POST, every GET route in the OpenAPI
document, error envelopes), the OpenAPI document or /docs, JSON or text log
lines, or ingest_demo output.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from e1_support import CSV_ROWS, csv_row
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.api.connectors import ConnectorProvider
from app.connectors import registry
from app.connectors import rest as rest_module
from app.connectors.odoo import OdooConnectorConfig, OdooMockConnector
from app.connectors.rest import RestConnector, RestConnectorConfig
from app.connectors.types import ConnectorConfigurationError, ConnectorRequestError
from app.core.logging import configured_logging
from app.main import create_app
from app.persistence.models import IngestionError

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
RUNS = "/api/v1/ingestion/runs"
PREFIX = "g2-synthetic-canary-"
API_KEY_CANARY = PREFIX + "api-key-7Qx"
SERVER_CANARY = PREFIX + "upstream-body-4Lm"
PAYLOAD_CANARY = PREFIX + "payload-9Rt"
DB_CANARY = PREFIX + "db-password-2Vw"
REQUEST_CANARY = PREFIX + "request-5Kp"
EXCEPTION_CANARY = PREFIX + "exception-8Zn"
CANARIES = {"api key": API_KEY_CANARY, "upstream body": SERVER_CANARY, "payload": PAYLOAD_CANARY,
            "database password": DB_CANARY, "request": REQUEST_CANARY, "exception": EXCEPTION_CANARY}
AUTH_VARIABLE = "G2_CANARY_REST_AUTH"
UNREACHABLE_DB = f"postgresql://g2_probe:{DB_CANARY}@127.0.0.1:9/g2_unreachable"
REST_ENTITIES = ("organizations", "employees", "customers", "deals")
SOURCES = ("csv_demo", "rest_mock", "odoo_mock", "broken_config", "crashing")
ROUTE_PARAMETERS = {"source", "run_id", "entity_id"}
MISSING_ID = str(uuid.UUID(int=0))
EXPECTED_EVENTS = ("run_finished", "entity_failed", "record_rejected", "connector_health_check_failed",
                   "source_misconfigured", "request_failed", "retry_scheduled")


class UpstreamHandler(BaseHTTPRequestHandler):
    """A source that receives the API key and answers with canary-bearing bodies."""

    received_keys: list[str] = []

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        UpstreamHandler.received_keys.append(self.headers.get("X-Api-Key", ""))
        page = {"offset": 0, "limit": 100, "total": 1, "has_more": False}
        routes: dict[str, tuple[int, object]] = {
            "/health": (200, {"status": "healthy"}),
            "/odoo/health": (200, {"status": "down", "detail": SERVER_CANARY}),
            "/rest/organizations": (200, {"data": [{"id": ["ORG-801", PAYLOAD_CANARY], "name": "Org"}],
                                          "pagination": page}),
            "/rest/employees": (400, f"upstream rejected the request: {SERVER_CANARY}"),
            "/rest/customers": (503, f"upstream unavailable: {SERVER_CANARY}"),
            "/rest/deals": (401, f"upstream refused the key: {SERVER_CANARY}"),
        }
        status, body = routes.get(self.path.split("?", 1)[0], (404, SERVER_CANARY))
        data = (json.dumps(body) if isinstance(body, dict) else str(body)).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json" if isinstance(body, dict) else "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def upstream_url():
    server = HTTPServer(("127.0.0.1", 0), UpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _write_csv_sources(directory: Path) -> Path:
    rows = {
        "organizations": [csv_row("organizations")],
        "employees": [csv_row("employees"),
                      csv_row("employees", employee_id="EMP-002", employee_name="Bob Owner",
                              email_address="bob@acme.example")],
        "customers": [csv_row("customers", customer_id="CUST-801", status=PAYLOAD_CANARY),
                      csv_row("customers", customer_id="CUST-802")],
        "deals": [csv_row("deals", deal_id="DEAL-801", customer_id="CUST-802",
                          amount=f"password={PAYLOAD_CANARY}"),
                  csv_row("deals", deal_id="DEAL-802", customer_id="CUST-802",
                          stage=f"Bearer {PAYLOAD_CANARY}")],
    }
    for entity, header in CSV_ROWS.items():
        with open(directory / f"{entity}.csv", "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(header))
            writer.writeheader()
            writer.writerows(rows.get(entity, []))
    return directory


def _builder(upstream: str, csv_directory: Path):
    def build(source: str):
        if source == "csv_demo":
            return registry.build_connector("csv_demo", data_directory=csv_directory)
        if source == "rest_mock":
            return RestConnector(RestConnectorConfig.from_dict({
                "source_name": "rest_mock", "source_type": "rest", "base_url": upstream, "timeout": 5,
                "health_endpoint": "/health",
                "auth": {"mechanism": "api_key", "header_name": "X-Api-Key", "env_var": AUTH_VARIABLE},
                "entities": {name: {"path": f"/rest/{name}"} for name in REST_ENTITIES},
            }))
        if source == "odoo_mock":
            return OdooMockConnector(OdooConnectorConfig.from_dict({
                "source_name": "odoo_mock", "source_type": "mock", "base_url": f"{upstream}/odoo",
                "timeout": 5,
            }))
        if source == "broken_config":
            raise ConnectorConfigurationError(
                f"invalid base_url http://operator:{EXCEPTION_CANARY}@internal", source_name=source)
        raise RuntimeError(f"connector construction crashed: {EXCEPTION_CANARY}")

    return build


def _get_paths(client: TestClient, run_ids: list[str]) -> tuple[list[str], int]:
    """Every GET route with its parameters filled; unknown parameters fail the test."""
    paths: list[str] = []
    templates = [template for template, operations in sorted(client.app.openapi()["paths"].items())
                 if "get" in operations]
    for template in templates:
        names = re.findall(r"\{([^}]+)\}", template)
        assert set(names) <= ROUTE_PARAMETERS and len(names) <= 1, template
        if not names:
            paths.append(template)
        elif names == ["source"]:
            paths += [template.replace("{source}", source) for source in SOURCES]
        elif names == ["run_id"]:
            paths += [template.replace("{run_id}", run_id) for run_id in [*run_ids, MISSING_ID]]
        else:
            listing = client.get(template.rsplit("/", 1)[0]).json()["items"]
            ids = [item["id"] for item in listing] + [MISSING_ID]
            paths += [template.replace("{entity_id}", entity_id) for entity_id in ids]
    return paths, len(templates)


def _leaks(outputs: dict[str, str]) -> list[tuple[str, str]]:
    return [(channel, name) for channel, text in outputs.items()
            for name, canary in CANARIES.items() if canary in text]


@pytest.mark.parametrize("log_format", ["json", "text"])
def test_canaries_never_reach_api_responses_openapi_or_logs(
    e1_sessions, tmp_path, monkeypatch, upstream_url, log_format,
):
    monkeypatch.setenv(AUTH_VARIABLE, API_KEY_CANARY)
    monkeypatch.setattr(rest_module.time, "sleep", lambda seconds: None)
    UpstreamHandler.received_keys.clear()
    build = _builder(upstream_url, _write_csv_sources(tmp_path))
    outputs: dict[str, str] = {}
    stream = io.StringIO()

    with configured_logging("DEBUG", log_format, stream):
        client = TestClient(create_app(sessions=e1_sessions,
                                       connectors=ConnectorProvider(build, SOURCES)),
                            raise_server_exceptions=False)
        statuses = {}
        for source in ("csv_demo", "rest_mock", "odoo_mock"):
            response = client.post(RUNS, json={"source": source})
            assert response.status_code == 201, (source, response.status_code)
            statuses[source] = response.json()["status"]
            outputs[f"POST {source}"] = response.text + json.dumps(dict(response.headers))

        rejected = {
            "unknown source": ({"source": REQUEST_CANARY}, 422),
            "extra field": ({"source": "csv_demo", "note": REQUEST_CANARY}, 422),
            "invalid entity": ({"source": "csv_demo", "entities": [REQUEST_CANARY]}, 422),
            "invalid page size": ({"source": "csv_demo", "page_size": REQUEST_CANARY}, 422),
            "misconfigured source": ({"source": "broken_config"}, 500),
            "crashing source": ({"source": "crashing"}, 500),
        }
        for label, (body, status) in rejected.items():
            response = client.post(RUNS, json=body)
            assert response.status_code == status, (label, response.status_code)
            outputs[f"POST {label}"] = response.text
        response = client.get(RUNS, params={"limit": REQUEST_CANARY})
        assert response.status_code == 422
        outputs["GET invalid query"] = response.text

        run_ids = [item["run_id"] for item in client.get(RUNS).json()["items"]]
        paths, templates = _get_paths(client, run_ids)
        for path in paths:
            outputs[f"GET {path}"] = client.get(path).text
        for path in ("/docs", "/redoc", "/openapi.json"):
            outputs[f"GET {path}"] = client.get(path).text

    outputs[f"{log_format} logs"] = stream.getvalue()

    # The scenario really ran every channel.
    assert statuses == {"csv_demo": "PARTIAL_SUCCESS", "rest_mock": "FAILED", "odoo_mock": "FAILED"}
    assert len(run_ids) == 3 and templates >= 20 and len(paths) > templates
    for event in EXPECTED_EVENTS:
        assert event in outputs[f"{log_format} logs"], event
    assert API_KEY_CANARY in UpstreamHandler.received_keys
    with e1_sessions() as session:
        stored = session.scalars(select(IngestionError.message)).all()
    assert any(PAYLOAD_CANARY in message for message in stored)
    connector = build("rest_mock")
    with pytest.raises(ConnectorRequestError) as upstream_error:
        connector.fetch_entities("employees")
    assert SERVER_CANARY in str(upstream_error.value)
    with pytest.raises(ConnectorRequestError) as payload_error:
        connector.fetch_entities("organizations")
    assert PAYLOAD_CANARY in str(payload_error.value)
    health = build("odoo_mock").health_check()
    assert health.healthy is False and SERVER_CANARY in (health.message or "")

    # ...and no canary reached any output.
    assert _leaks(outputs) == []


@pytest.mark.parametrize("log_format", ["json", "text"])
def test_database_credentials_never_reach_readiness_or_run_failures(log_format):
    sessions = sessionmaker(bind=create_engine(UNREACHABLE_DB, hide_parameters=True,
                                               connect_args={"connect_timeout": 2}))
    assert sessions.kw["bind"].url.password == DB_CANARY  # the password really is configured
    stream = io.StringIO()
    with configured_logging("DEBUG", log_format, stream):
        client = TestClient(create_app(sessions=sessions), raise_server_exceptions=False)
        health = client.get("/api/v1/health")
        run = client.post(RUNS, json={"source": "csv_demo"})
    assert (health.status_code, run.status_code) == (503, 500)
    assert run.json()["error"]["code"] == "INTERNAL_ERROR"
    logs = stream.getvalue()
    assert "readiness_check_failed" in logs and "request_failed" in logs
    assert _leaks({"health": health.text, "run": run.text, "logs": logs}) == []


def test_database_credentials_never_reach_ingest_demo_output(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DB)
    monkeypatch.setenv("LOG_FORMAT", "text")
    spec = importlib.util.spec_from_file_location("ingest_demo_g2_canary",
                                                  REPO / "scripts" / "ingest_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert DB_CANARY in module.get_settings().effective_database_url  # the command really uses it
    with pytest.raises(DBAPIError) as failure:
        module.main(["--data-directory", str(_write_csv_sources(tmp_path))])
    output = capsys.readouterr()
    assert _leaks({"stdout": output.out, "stderr": output.err, "exception": str(failure.value),
                   "exception repr": repr(failure.value)}) == []
