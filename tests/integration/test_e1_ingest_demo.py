"""
scripts/ingest_demo.py command-line tests against the migrated test database.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest
from e1_support import CSV_ROWS, csv_row
from sqlalchemy import func, select

from app.connectors import ConnectorConfigurationError
from app.persistence.models import Customer, Deal, IngestionRun

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]


def _load_script():
    spec = importlib.util.spec_from_file_location("ingest_demo", REPO / "scripts" / "ingest_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ingest_demo = _load_script()


@pytest.fixture
def demo_database(e1_engine, e1_sessions, monkeypatch):
    """Point app settings at the isolated test database."""
    monkeypatch.setenv("DATABASE_URL", e1_engine.url.render_as_string(hide_password=False))
    return e1_sessions


def _write_csvs(directory: Path, rows_by_entity) -> None:
    for entity, header in CSV_ROWS.items():
        with open(directory / f"{entity}.csv", "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(header))
            writer.writeheader()
            writer.writerows(rows_by_entity.get(entity, []))


def _count(sessions, model) -> int:
    with sessions() as session:
        return session.scalar(select(func.count()).select_from(model))


def test_csv_ingestion_prints_a_summary_and_is_idempotent(demo_database, tmp_path, capsys):
    _write_csvs(tmp_path, {"customers": [csv_row("customers")], "deals": [csv_row("deals")]})

    assert ingest_demo.main(["--data-directory", str(tmp_path)]) == 0
    first = capsys.readouterr()
    summary = json.loads(first.out)
    assert (summary["status"], summary["records_inserted"], summary["records_fetched"]) == (
        "SUCCESS", 2, 2)
    assert "postgresql://" not in first.out + first.err

    assert ingest_demo.main(["--data-directory", str(tmp_path), "--page-size", "1"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert (second["status"], second["records_unchanged"], second["batches_committed"]) == (
        "NOOP", 2, 7)
    assert _count(demo_database, Customer) == 1 and _count(demo_database, Deal) == 1


def test_entities_option_limits_the_run(demo_database, tmp_path, capsys):
    _write_csvs(tmp_path, {"customers": [csv_row("customers")], "deals": [csv_row("deals")]})
    assert ingest_demo.main(["--data-directory", str(tmp_path), "--entities", "customers"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert [e["entity_type"] for e in summary["entities"]] == ["customers"]
    assert _count(demo_database, Deal) == 0


def test_failed_run_exits_with_status_1(demo_database, tmp_path, capsys):
    assert ingest_demo.main(["--data-directory", str(tmp_path / "missing")]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAILED"


@pytest.mark.parametrize("argv", [
    ["--entities", "invoices"],
    ["--page-size", "0"],
    ["--base-url", "http://localhost:8080"],
    ["--source", "odoo_mock", "--data-directory", "data/demo"],
    ["--source", "rest_mock", "--base-url", "ftp://localhost"],
])
def test_invalid_requests_exit_with_status_2_and_create_no_run(demo_database, capsys, argv):
    assert ingest_demo.main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.startswith("ingest_demo: ")
    assert _count(demo_database, IngestionRun) == 0


def test_unknown_source_is_rejected_by_the_parser():
    with pytest.raises(SystemExit) as caught:
        ingest_demo.parse_args(["--source", "salesforce"])
    assert caught.value.code == 2


def test_committed_connector_configurations_build_without_network_access():
    csv_connector = ingest_demo.build_connector("csv_demo")
    assert csv_connector.source_name == "csv_demo"
    assert len(csv_connector.capabilities().supported_entity_types) == 7
    odoo = ingest_demo.build_connector("odoo_mock", base_url="http://localhost:8080/")
    rest = ingest_demo.build_connector("rest_mock", base_url="http://localhost:8080")
    assert (odoo.source_name, rest.source_name) == ("odoo_mock", "rest_mock")
    assert odoo._config.base_url == rest._config.base_url == "http://localhost:8080"
    assert ingest_demo.build_connector("rest_mock")._config.base_url == "http://mock-source:8080"
    with pytest.raises(ConnectorConfigurationError):
        ingest_demo.build_connector("salesforce")
