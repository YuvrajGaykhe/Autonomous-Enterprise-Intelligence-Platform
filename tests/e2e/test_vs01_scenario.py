"""
The VS-01 acceptance scenario (scripts/vs01_acceptance.py) driven end to end (plan §0.8.10).

Part B M9 requires "the full §A28 flow over HTTP"; §0.8.5 maps §A28's steps
onto the checks A27.1b ... A27.9. These tests run the command's scenario
against the real application over the real migrated test database, both
through TestClient and through the script's own loopback server over a real
socket, so a check that silently stops proving its criterion fails here.

A27.7's and A27.10's runners are stubbed, so the suite never runs itself:
the stubs record the fixed argument lists they are given, and the corpus
itself runs at A27.7 of every real `make verify-vs01` and in this suite.

The database is the suite's own `_test` database, freshly truncated by
e1_sessions; the command's own `_vs01` database is not used here.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.registry import build_connector
from app.core.database import Base
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence import default_risk_rules
from app.persistence.models import BriefDecision, RiskAssessment, RiskBrief

pytestmark = pytest.mark.e2e

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
BAD_FIXTURE_DIR = REPO / "data" / "fixtures" / "csv_demo_bad"
#: The entity types make verify-layer1 ingests (spec Section 20 step E).
LAYER1_SCENARIO_ENTITIES = ["customers", "employees", "deals", "projects", "support_tickets"]


def _load_script() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "vs01_acceptance", REPO / "scripts" / "vs01_acceptance.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # The script defines dataclasses, which resolve their own module by name.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vs01 = _load_script()
Outcome = vs01.Outcome
PIN = default_risk_rules().pinned_fingerprint("csv_demo")

#: §0.8.5's order, as (label, name, outcome on a clean database).
EXPECTED = (
    ("A27.1", "clean_dataset", Outcome.PASS),
    ("A27.1b", "pinned_fingerprint", Outcome.PASS),
    ("A27.2", "single_escalation", Outcome.PASS),
    ("A27.3", "brief_facts", Outcome.PASS),
    ("A27.4", "no_active_project", Outcome.PASS),
    ("A27.5", "conflict_and_dissent", Outcome.PASS),
    ("A27.6", "citations_resolve", Outcome.PASS),
    ("A27.9", "approval_boundary", Outcome.PASS),
    ("A27.8", "determinism", Outcome.PASS),
    ("A27.7", "named_tests", Outcome.PASS),
    ("A27.10", "regression", Outcome.SKIPPED),
    ("A28.citations", "hand_citations", Outcome.OPERATOR),
)


class Runners:
    """Stubs for A27.7 and A27.10: they record their argument lists and never run pytest."""

    def __init__(self) -> None:
        self.ran: list[tuple[str, ...]] = []

    def proofs(self, argv: tuple[str, ...]) -> Any:
        self.ran.append(argv)
        return vs01.CommandResult(0, f"{vs01.A25_PROOF_COUNT} passed in 1.00s\n")

    def regression(self, argv: tuple[str, ...]) -> Any:
        raise AssertionError("A27.10 runs only under --with-tests")


class RecordingClient(TestClient):
    """TestClient that remembers every request the scenario sends."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.sent: list[tuple[str, str]] = []

    def request(self, method: str, url: Any, **kwargs: Any) -> httpx.Response:  # type: ignore[override]
        self.sent.append((method.upper(), str(url)))
        return super().request(method, url, **kwargs)


@pytest.fixture
def api(e1_sessions) -> Iterator[RecordingClient]:
    """The real application the command serves, over the migrated test database."""
    with RecordingClient(vs01.build_app(e1_sessions), raise_server_exceptions=False) as client:
        yield client


def scenario(client: Any, sessions: sessionmaker[Session], runners: Runners | None = None):
    runners = Runners() if runners is None else runners
    return vs01.run_scenario(client, sessions, proof_runner=runners.proofs,
                             regression_runner=runners.regression)


def lines(report: Any) -> list[str]:
    return [str(check) for check in report.checks] + [report.summary()]


def failures(report: Any) -> str:
    return "; ".join(f"{check.label}: {check.detail}" for check in report.failures)


def truncate(engine: Engine) -> None:
    """Empty every table again, exactly as e1_sessions does before each test."""
    tables = ", ".join(engine.dialect.identifier_preparer.quote(table.name)
                       for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


def count(sessions: sessionmaker[Session], model: Any) -> int:
    with sessions() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


# ---------------------------------------------------------------------------
# The scenario on a clean database
# ---------------------------------------------------------------------------


def test_every_check_passes_on_a_clean_database_in_the_specified_order(api, e1_sessions):
    runners = Runners()

    report = scenario(api, e1_sessions, runners)

    assert report.failures == (), failures(report)
    assert tuple((check.label, check.name, check.outcome) for check in report.checks) == EXPECTED
    assert report.summary() == "verify-vs01: 10 passed, 0 failed, 1 skipped, 1 operator"
    assert report.exit_code == 0
    assert runners.ran == [vs01.PROOF_COMMAND]


def test_the_report_is_byte_identical_through_testclient_the_loopback_server_and_a_rerun(
        api, e1_sessions, e1_engine):
    first = lines(scenario(api, e1_sessions))

    truncate(e1_engine)
    with vs01.serving(vs01.build_app(e1_sessions), 60) as base_url, \
            httpx.Client(base_url=base_url, timeout=60) as client:
        assert httpx.URL(base_url).host == "127.0.0.1"
        served = lines(scenario(client, e1_sessions))

    truncate(e1_engine)
    again = lines(scenario(api, e1_sessions))

    assert served == first
    assert again == first
    assert first[-1] == "verify-vs01: 10 passed, 0 failed, 1 skipped, 1 operator"


# ---------------------------------------------------------------------------
# §A28's flow, step by step, as §0.8.5 maps it
# ---------------------------------------------------------------------------


def test_each_step_of_the_a28_demo_is_carried_by_its_check(api, e1_sessions):
    runners = Runners()
    report = scenario(api, e1_sessions, runners)
    checks = {check.label: check for check in report.checks}
    assert report.failures == (), failures(report)

    # Assess: A27.1b's pinned run over the clean full-dataset path.
    assert checks["A27.1"].detail.endswith("233 fetched, 0 rejected: SUCCESS then NOOP")
    assert checks["A27.1b"].detail == (f"pinned {PIN[:8]} matched; deliberate mismatch refused, "
                                       "0 rows written; 50 assessments, 3 briefs")
    # List the one executive-worthy assessment: A27.2.
    assert checks["A27.2"].detail == ("50 assessments; CUST-007 alone is CRITICAL and "
                                      "executive-worthy")
    # Read the brief, its conflict and its dissent: A27.3 to A27.5.
    assert "payload_hash e93c29cf" in checks["A27.3"].detail
    assert checks["A27.5"].detail.startswith("CONF-001 over DEAL-001")
    # Verify the two citations: A27.6 automatically, A28.citations by hand.
    assert checks["A27.6"].detail == ("80 distinct citations across 50 assessments and 3 briefs "
                                      "resolve; 3 cited spans read back exactly")
    assert checks["A28.citations"].outcome is Outcome.OPERATOR
    assert "DOC-003 [238, 330)" in checks["A28.citations"].detail
    assert "DOC-009 [238, 333)" in checks["A28.citations"].detail
    # Reject, then read the history: A27.9, which also approves in chain order.
    with e1_sessions() as session:
        history = session.execute(
            select(BriefDecision.decision, BriefDecision.supersedes_id, BriefDecision.id,
                   BriefDecision.actor)
            .order_by(BriefDecision.supersedes_id.is_not(None))).all()
        (meridian,) = session.scalars(select(RiskBrief).where(
            RiskBrief.payload_hash == vs01.MERIDIAN_HASH)).all()
    assert [(row.decision, row.actor) for row in history] == [("REJECTED", "verify-vs01"),
                                                             ("APPROVED", "verify-vs01")]
    assert history[1].supersedes_id == history[0].id
    assert meridian.status == "DRAFT"
    # Re-run: identical hashes and no new rows, then a new snapshot mints new rows: A27.8.
    assert checks["A27.8"].detail.startswith("re-run 200: identical hashes, 0 rows")
    assert count(e1_sessions, RiskAssessment) == 100
    assert count(e1_sessions, RiskBrief) == 6
    # pytest -k doc005_leave_out: the one corpus node the selection names, inside A27.7.
    (argv,) = runners.ran
    assert [node for node in argv if "doc005_leave_out" in node] == [
        "tests/integration/test_m7_assessment.py::"
        "test_doc005_leave_out_changes_no_band_signal_escalation_or_resolution"]


def test_the_scenario_uses_only_published_routes(api, e1_sessions):
    """M8's route behaviour is unchanged: the command drives only what the API publishes."""
    scenario(api, e1_sessions)

    published = {(method.upper(), path) for path, methods in api.get(
        "/openapi.json").json()["paths"].items() for method in methods}

    def template(path: str) -> str:
        parts = []
        for segment in httpx.URL(path).path.split("/"):
            try:
                uuid.UUID(segment)
            except ValueError:
                parts.append(segment)
            else:
                parts.append("{id}")
        return "/".join(parts)

    templates = {(method, path.replace("{assessment_id}", "{id}").replace("{brief_id}", "{id}")
                  .replace("{entity_id}", "{id}")) for method, path in published}
    sent = {(method, template(url)) for method, url in api.sent if url != "/openapi.json"}
    assert sent <= templates, sorted(sent - templates)
    # R-M9-2 end to end: the clean path twice, the three decisions of A27.9, then A27.8's
    # two unpinned runs, the last write of all. No other check sends a write.
    assert [template(url) for method, url in api.sent if method != "GET"] == [
        "/api/v1/ingestion/runs", "/api/v1/ingestion/runs",
        "/api/v1/risk/briefs/{id}/decision", "/api/v1/risk/briefs/{id}/decision",
        "/api/v1/risk/briefs/{id}/decision",
        "/api/v1/risk/assessments", "/api/v1/risk/assessments"]
    assert {method for method, _ in api.sent} == {"GET", "POST"}


# ---------------------------------------------------------------------------
# A database left by make verify-layer1 (§A27.1b)
# ---------------------------------------------------------------------------


def _layer1_residue(sessions: sessionmaker[Session]) -> None:
    """What make verify-layer1 leaves: five entity types, then the malformed fixture."""
    run_ingestion(build_connector("csv_demo", data_directory=DEMO_DIR), sessions,
                  IngestionRequest(entities=LAYER1_SCENARIO_ENTITIES))
    run_ingestion(build_connector("csv_demo", data_directory=BAD_FIXTURE_DIR), sessions,
                  IngestionRequest())


def test_a_verify_layer1_residue_fails_a27_1_and_a27_1b_and_assesses_nothing(api, e1_sessions):
    _layer1_residue(e1_sessions)

    report = scenario(api, e1_sessions)
    checks = {check.label: check for check in report.checks}

    assert checks["A27.1"].outcome is Outcome.FAIL
    assert checks["A27.1"].detail.startswith("the database is not empty before the scenario")
    assert checks["A27.1b"].outcome is Outcome.FAIL
    assert f"expected {PIN}, computed " in checks["A27.1b"].detail
    assert "rebuild the database from the clean full-dataset path" in checks["A27.1b"].detail
    for label in ("A27.2", "A27.3", "A27.4", "A27.5", "A27.6", "A27.9", "A27.8"):
        assert checks[label].outcome is Outcome.FAIL
        assert checks[label].detail.startswith("A27.1b did not pass"), label
    assert count(e1_sessions, RiskAssessment) == 0
    assert count(e1_sessions, BriefDecision) == 0
    assert ("POST", "/api/v1/risk/assessments") not in api.sent
    assert not [url for method, url in api.sent if method == "POST" and url.endswith("/decision")]
    assert report.exit_code == 1
