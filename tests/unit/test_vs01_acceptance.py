"""
scripts/vs01_acceptance.py unit tests: the command surface without a database (plan §0.8.10).

The e2e suite (tests/e2e/test_vs01_scenario.py) proves the scenario passes
against the real application over a real database. These tests cover what a
passing run cannot show: the argument contract and every exit-2 path, the
isolation invariant (R-M9-1), the environment check (R-M9-3), the report
model, the message each check produces when its criterion is violated, and
the structural rules K1 and K2 put on the script: its closed Layer 2 import
set, its pinned calls, its only non-GET requests and its fixed subprocesses.

The API is a stub and the database a fake world here, so a check can be
driven into exactly one failure at a time.
"""

from __future__ import annotations

import ast
import asyncio
import copy
import importlib.util
import re
import subprocess
import sys
import types
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError

from app.intelligence import FingerprintMismatchError, default_risk_rules

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "vs01_acceptance.py"


def _load_script() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("vs01_acceptance", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # The script defines dataclasses, which resolve their own module by name.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vs01 = _load_script()
Check = vs01.Check
CheckFailed = vs01.CheckFailed
CommandResult = vs01.CommandResult
EnvironmentRefused = vs01.EnvironmentRefused
Outcome = vs01.Outcome
Report = vs01.Report
Scenario = vs01.Scenario

PIN = default_risk_rules().pinned_fingerprint("csv_demo")
CHANGED = "c" * 64
SOURCE_TREE = ast.parse(SCRIPT.read_text(encoding="utf-8"))
SOURCE = SCRIPT.read_text(encoding="utf-8")

#: §0.8.5's order, as (label, name).
EXPECTED_CHECKS = (
    ("A27.1", "clean_dataset"),
    ("A27.1b", "pinned_fingerprint"),
    ("A27.2", "single_escalation"),
    ("A27.3", "brief_facts"),
    ("A27.4", "no_active_project"),
    ("A27.5", "conflict_and_dissent"),
    ("A27.6", "citations_resolve"),
    ("A27.9", "approval_boundary"),
    ("A27.8", "determinism"),
    ("A27.7", "named_tests"),
    ("A27.10", "regression"),
    ("A28.citations", "hand_citations"),
)
UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}|\d+\.\d+s\b|\d+:\d{2}:\d{2}")


# ---------------------------------------------------------------------------
# A fake world: the database as row counts and a fake run, the API as a stub
# ---------------------------------------------------------------------------


class StubResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class FakeTransaction:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def commit(self) -> None:
        self.log.append("commit")

    def rollback(self) -> None:
        self.log.append("rollback")


class FakeSession:
    def __init__(self, world: World) -> None:
        self.world = world

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.world.transactions)

    def execute(self, statement: Any) -> None:
        self.world.executed.append(str(statement).split()[0])
        if self.world.on_execute is not None:
            self.world.on_execute()
        if self.world.execute_error is not None:
            raise self.world.execute_error


class FakeSessions:
    def __init__(self, world: World) -> None:
        self.world = world

    def __call__(self) -> FakeSession:
        return FakeSession(self.world)

    @contextmanager
    def begin(self):
        yield FakeSession(self.world)


class TriggerError(Exception):
    """A psycopg2-shaped error: pgcode and diag.message_primary."""

    def __init__(self, pgcode: str, message: str) -> None:
        super().__init__(message)
        self.pgcode = pgcode
        self.diag = SimpleNamespace(message_primary=message)


def _document(document_id: str, start: int, phrase: str) -> dict[str, Any]:
    title = "Policy"
    body = "x" * (start - len(title) - 1) + phrase + " Closing sentence."
    return {"title": title, "body_text": body}


def _record(entity: str, source_id: str, **fields: Any) -> dict[str, Any]:
    return {"source_system": "csv_demo", "source_entity": entity, "source_id": source_id,
            **fields}


def _citation(entity: str, source_id: str, field: str) -> dict[str, Any]:
    return {"kind": "record", "entity": entity, "id": source_id, "field": field}


class World:
    """A consistent, passing VS-01 world; each test breaks exactly one thing."""

    def __init__(self) -> None:
        self.counts = dict.fromkeys(("customers", "deals", "support_tickets", "documents",
                                     "risk_assessments", "risk_briefs", "brief_decisions"), 0)
        self.heads = ("070e4968a497",)
        self.current = ("070e4968a497",)
        self.computed = PIN
        self.transactions: list[str] = []
        self.executed: list[str] = []
        self.execute_error: Exception | None = IntegrityError(
            "UPDATE", {}, TriggerError("23001", vs01.APPEND_ONLY_MESSAGE))
        self.on_execute: Any = None
        self.assessment_calls: list[dict[str, Any]] = []
        self.ingestions: list[tuple[str, ...]] = []
        self.refused_writes = False
        self.fixture_counts = (1, 0)
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.overrides: dict[tuple[str, str], Any] = {}
        self.pinned = [SimpleNamespace(assessment_id=uuid.uuid4(), created=True, brief_id=None,
                                       payload_hash=None) for _ in range(50)]
        for index, digest in enumerate((vs01.MERIDIAN_HASH, "2" * 64, "3" * 64)):
            self.pinned[index].brief_id = uuid.uuid4()
            self.pinned[index].payload_hash = digest
        self.listed = [{"id": str(result.assessment_id), "customer_source_id": f"CUST-{i:03d}",
                        "layer1_fingerprint": PIN} for i, result in enumerate(self.pinned)]
        self.listed[0]["customer_source_id"] = "CUST-007"
        self.new_results: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.records = self._records()
        self.brief = self._brief()
        self.openapi = {"paths": {
            "/api/v1/health": {"get": {}},
            "/api/v1/ingestion/runs": {"get": {}, "post": {}},
            vs01.ASSESSMENTS: {"get": {}, "post": {}},
            vs01.ASSESSMENTS + "/{assessment_id}": {"get": {}},
            vs01.BRIEFS + "/{brief_id}": {"get": {}},
            vs01.DECISION: {"post": {}},
            vs01.DECISIONS: {"get": {}},
        }}
        self.ingestion_runs = [
            {"status": "SUCCESS", "records_fetched": 233, "records_rejected": 0,
             "records_inserted": 233, "records_updated": 0},
            {"status": "NOOP", "records_fetched": 233, "records_rejected": 0,
             "records_inserted": 0, "records_updated": 0},
        ]

    # -- The fake database ---------------------------------------------------

    def _records(self) -> dict[str, list[dict[str, Any]]]:
        documents = [
            _record("documents", document, **_document(document, start, phrase))
            for document, start, _, phrase in vs01.CITED_SPANS.values()
        ]
        tickets = [_record("support_tickets", ticket, created_at="2026-08-18T10:00:00Z",
                           priority="high", category="performance", resolved_at=None)
                   for ticket in vs01.ALL_FIVE]
        deals = [_record("deals", "DEAL-001", is_active=True, stage="negotiation",
                         probability="90", amount="5361.44", currency="USD")]
        customers = [_record("customers", "CUST-007", name="Meridian Textiles", email=None)]
        return {"organizations": [], "employees": [], "customers": customers, "deals": deals,
                "projects": [], "support_tickets": tickets, "documents": documents}

    def _brief(self) -> dict[str, Any]:
        dissent = {"function": "SALES", "stance": "ADVANCE",
                   "proposed_action": "ACCELERATE_DEAL_CLOSE", "object_ref": "DEAL-001",
                   "evidence": copy.deepcopy(vs01.DISSENT_CITATIONS)}
        pause = {"function": "SUPPORT", "stance": "RESTRAIN",
                 "proposed_action": "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED",
                 "object_ref": "DEAL-001", "evidence": []}
        payload = {
            "signals": {"active_project_count": 0},
            "reconciliation": {
                "policy_version": 1,
                "conflicts": [{"object_ref": "DEAL-001", "positions": [dissent, pause]}],
                "resolutions": [{"policy_id": "CONF-001", "conflict": {},
                                 "resolved_action": "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED",
                                 "prevailing": pause, "dissent": [copy.deepcopy(dissent)],
                                 "evidence": [{"kind": "CANONICAL_FACT", "citation": _citation(
                                     "documents", "DOC-003", "body_text")}]}],
                "dissent": [copy.deepcopy(dissent)],
                "worthiness": {"active_project_count": 0},
            },
            "support_evidence": {
                "tickets": copy.deepcopy(vs01.MERIDIAN_TICKETS),
                "escalation_window": dict(vs01.MERIDIAN_WINDOW),
                "ticket_span": copy.deepcopy(vs01.MERIDIAN_SPAN),
                "backlog_ticket_ids": [],
                "derivations": copy.deepcopy(vs01.MERIDIAN_DERIVATIONS),
                "escalation_path": {
                    "customer": {"entity": "customers", "id": "CUST-007"},
                    "account_owner": {"entity": "employees", "id": "EMP-007"},
                    "account_owner_manager": {"entity": "employees", "id": "EMP-002"},
                    "assignees": [{"entity": "employees", "id": one}
                                  for one in ("EMP-018", "EMP-021", "EMP-017", "EMP-020")],
                    "assignee_managers": [{"entity": "employees", "id": "EMP-004"}],
                    "open_tickets": [{"entity": "support_tickets", "id": one}
                                     for one in ("TKT-075", "TKT-076", "TKT-079", "TKT-080")],
                },
            },
            "commercial_evidence": copy.deepcopy(vs01.MERIDIAN_COMMERCIAL),
            "cited_spans": copy.deepcopy(vs01.MERIDIAN_CITED_SPANS),
        }
        citations = [_citation("customers", "CUST-007", field)
                     for field in ("name", "email")] * 18
        return {"payload_hash": vs01.MERIDIAN_HASH, "status": "DRAFT",
                "decision_status": "PENDING", "policy_version": 1,
                "narrative": vs01.GOLDEN.read_text(encoding="utf-8"),
                "citations": citations, "payload": payload}

    def row_counts(self, sessions: object) -> dict[str, int]:
        return dict(self.counts)

    def run_assessment(self, session: object, **kwargs: Any) -> list[SimpleNamespace]:
        self.assessment_calls.append(kwargs)
        if self.refused_writes:
            self.counts["risk_assessments"] += 1
        expected = kwargs["expected_fingerprint"]
        if expected != self.computed:
            raise FingerprintMismatchError("csv_demo", expected, self.computed)
        return self.pinned

    def run_ingestion(self, connector: object, sessions: object, request: Any) -> Any:
        self.ingestions.append(tuple(request.entities))
        self.computed = CHANGED
        inserted, rejected = self.fixture_counts
        return SimpleNamespace(counts=SimpleNamespace(inserted=inserted, rejected=rejected))

    # -- The stub API --------------------------------------------------------

    def request(self, method: str, path: str, **kwargs: Any) -> StubResponse:
        self.calls.append((method, path, kwargs))
        override = self.overrides.get((method, path))
        if override is not None:
            return override(kwargs) if callable(override) else override
        params = kwargs.get("params") or {}
        body = kwargs.get("json")
        if (method, path) == ("POST", vs01.INGESTION_RUNS):
            return StubResponse(self.ingestion_runs.pop(0), 201)
        if (method, path) == ("GET", "/api/v1/metrics/ingestion"):
            return StubResponse({"totals": {"canonical_records": dict(vs01.CANONICAL_COUNTS)}})
        if method == "GET" and path.startswith("/api/v1/entities/"):
            entity = path.rsplit("/", 1)[1]
            items = self.records[entity][params["offset"]:params["offset"] + params["limit"]]
            return StubResponse({"items": items, "total": len(self.records[entity])})
        if (method, path) == ("GET", vs01.ASSESSMENTS):
            if "executive_worthy" in params or "band" in params:
                return StubResponse({"items": [self.listed[0]], "total": 1})
            listed = self.listed + self.new_results
            return StubResponse({"items": listed, "total": len(listed)})
        if method == "GET" and path.startswith(vs01.ASSESSMENTS + "/"):
            positions = []
            if path.endswith(str(self.pinned[0].assessment_id)):
                positions = [{"citations": [{"kind": "CANONICAL_FACT",
                                             "citation": _citation("deals", "DEAL-001", "stage")}]}]
            return StubResponse({"positions": positions})
        if (method, path) == ("POST", vs01.ASSESSMENTS):
            return self._assess()
        if method == "GET" and path.endswith("/decisions"):
            return StubResponse({"items": self.decisions})
        if method == "POST" and path.endswith("/decision"):
            return self._decide(body)
        if method == "GET" and path.startswith(vs01.BRIEFS + "/"):
            brief = copy.deepcopy(self.brief)
            if path != f"{vs01.BRIEFS}/{self.pinned[0].brief_id}":
                brief["payload"]["cited_spans"] = []
            if self.decisions:
                brief["decision_status"] = self.decisions[-1]["decision"]
            return StubResponse(brief)
        if (method, path) == ("GET", "/openapi.json"):
            return StubResponse(self.openapi)
        raise AssertionError(f"the scenario made an unrouted request: {method} {path}")

    def _assess(self) -> StubResponse:
        if self.computed == PIN:
            return StubResponse({"items": [
                {"assessment_id": str(one.assessment_id), "created": False,
                 "brief_id": None if one.brief_id is None else str(one.brief_id),
                 "payload_hash": one.payload_hash} for one in self.pinned]}, 200)
        items = [{"assessment_id": str(uuid.uuid4()), "created": True, "brief_id": None,
                  "payload_hash": None} for _ in range(50)]
        self.counts["risk_assessments"] += 50
        self.new_results = [{"id": item["assessment_id"], "customer_source_id": "CUST-001",
                             "layer1_fingerprint": CHANGED} for item in items]
        return StubResponse({"items": items}, 201)

    def _decide(self, body: dict[str, Any]) -> StubResponse:
        head = self.decisions[-1]["id"] if self.decisions else None
        if body["supersedes_id"] != head:
            reason = "SUPERSEDES_REQUIRED" if head else "NO_PREDECESSOR"
            return StubResponse({"error": {"code": "DECISION_CONFLICT",
                                           "details": {"reason": reason}}}, 409)
        decision = {"id": str(uuid.uuid4()), "decision": body["decision"],
                    "supersedes_id": body["supersedes_id"]}
        self.decisions.append(decision)
        self.counts["brief_decisions"] += 1
        return StubResponse(decision, 201)

    # -- Runners -------------------------------------------------------------

    proof_output = CommandResult(0, "........\n44 passed, 2 warnings in 31.20s\n")
    suite_output = CommandResult(0, "Name  Stmts  Miss  Cover\nTOTAL    7456      0   100%\n"
                                    "6600 passed, 2 warnings in 612.34s (0:10:12)\n")
    ruff_output = CommandResult(1, "Found 69 errors.\n")
    mypy_output = CommandResult(1, "Found 9 errors in 4 files (checked 130 source files)\n")
    scan_output = CommandResult(0, "secret-scan: 400 files scanned, 3 binary files skipped, "
                                   "0 findings\n")

    def runner(self, argv: tuple[str, ...]) -> CommandResult:
        self.ran.append(argv)
        return {vs01.PROOF_COMMAND: self.proof_output, vs01.SUITE_COMMAND: self.suite_output,
                vs01.RUFF_COMMAND: self.ruff_output, vs01.MYPY_COMMAND: self.mypy_output,
                vs01.SECRET_SCAN_COMMAND: self.scan_output}[argv]

    ran: list[tuple[str, ...]]


class StubClient:
    def __init__(self, world: World) -> None:
        self.world = world

    def request(self, method: str, path: str, **kwargs: Any) -> StubResponse:
        return self.world.request(method, path, **kwargs)


@pytest.fixture
def world(monkeypatch) -> World:
    world = World()
    world.ran = []
    monkeypatch.setattr(vs01, "row_counts", world.row_counts)
    monkeypatch.setattr(vs01, "current_heads", lambda sessions: world.current)
    monkeypatch.setattr(vs01, "script_heads", lambda: world.heads)
    monkeypatch.setattr(vs01, "run_assessment", world.run_assessment)
    monkeypatch.setattr(vs01, "run_ingestion", world.run_ingestion)
    monkeypatch.setattr(vs01, "build_connector", lambda source, **kwargs: object())
    return world


def run(world: World, *, with_tests: bool = False) -> Report:
    return vs01.run_scenario(StubClient(world), FakeSessions(world), with_tests=with_tests,
                             proof_runner=world.runner, regression_runner=world.runner)


def check(report: Report, name: str) -> Check:
    return next(one for one in report.checks if one.name == name)


def failed(report: Report, name: str, message: str) -> None:
    found = check(report, name)
    assert found.outcome is Outcome.FAIL, found
    assert message in found.detail, found.detail


def _failures(report: Report) -> str:
    return "; ".join(f"{one.label}: {one.detail}" for one in report.failures)


# ---------------------------------------------------------------------------
# The passing world, the order and the report
# ---------------------------------------------------------------------------


def test_the_fake_world_passes_every_check(world):
    report = run(world, with_tests=True)

    assert report.failures == (), _failures(report)
    assert report.summary() == "verify-vs01: 11 passed, 0 failed, 0 skipped, 1 operator"
    assert report.exit_code == 0


def test_the_checks_run_and_print_in_the_specified_order(world):
    streamed: list[Check] = []

    report = vs01.run_scenario(StubClient(world), FakeSessions(world),
                               proof_runner=world.runner, report_line=streamed.append)

    assert tuple((one.label, one.name) for one in report.checks) == EXPECTED_CHECKS
    assert streamed == list(report.checks)


def test_a27_10_is_skipped_without_with_tests_and_names_the_option(world):
    report = run(world)

    regression = check(report, "regression")
    assert (regression.outcome, regression.detail) == (Outcome.SKIPPED,
                                                       "not run; pass --with-tests")
    assert world.ran == [vs01.PROOF_COMMAND]
    assert report.summary() == "verify-vs01: 10 passed, 0 failed, 1 skipped, 1 operator"


def test_a28_citations_is_always_an_operator_check_naming_both_spans(world):
    detail = check(run(world), "hand_citations")

    assert detail.outcome is Outcome.OPERATOR
    for target in vs01.HAND_CITATIONS:
        document, start, end, phrase = vs01.CITED_SPANS[target]
        assert f'{document} [{start}, {end}) reads "{phrase}"' in detail.detail
    assert "DOC-006" not in detail.detail


def test_a28_citations_says_so_when_a27_6_did_not_prove_the_spans(world):
    world.records["documents"] = []

    report = run(world)

    hand = check(report, "hand_citations")
    assert hand.outcome is Outcome.OPERATOR
    assert "A27.6 did not prove the cited spans" in hand.detail


def test_a_check_line_names_its_label_name_outcome_and_evidence():
    line = str(Check("A27.1b", "pinned_fingerprint", Outcome.PASS, "pinned 1d891b0b matched"))

    assert line == ("verify-vs01: A27.1b        pinned_fingerprint   PASS      "
                    "pinned 1d891b0b matched")


def test_the_widest_label_and_name_keep_the_columns_aligned():
    lines = [str(Check(label, name, Outcome.OPERATOR, "x")) for label, name in EXPECTED_CHECKS]

    assert len({line.index("OPERATOR") for line in lines}) == 1


def test_a_report_counts_each_outcome_and_fails_only_on_a_failure():
    report = Report((Check("A", "one", Outcome.PASS, ""), Check("B", "two", Outcome.SKIPPED, ""),
                     Check("C", "three", Outcome.OPERATOR, "")))
    failing = Report((*report.checks, Check("D", "four", Outcome.FAIL, "why")))

    assert report.exit_code == 0 and report.failures == ()
    assert failing.exit_code == 1 and [one.name for one in failing.failures] == ["four"]
    assert failing.summary() == "verify-vs01: 1 passed, 1 failed, 1 skipped, 1 operator"


def test_an_unexpected_exception_fails_its_check_by_class_name_only(world, monkeypatch):
    def boom(*args: object, **kwargs: object) -> None:
        raise KeyError("a source value that must not be printed")

    monkeypatch.setattr(vs01, "run_ingestion", boom)

    report = run(world)

    failed(report, "determinism", "the check raised KeyError")
    assert "source value" not in check(report, "determinism").detail
    assert check(report, "named_tests").outcome is Outcome.PASS


def test_every_evidence_line_is_deterministic_ascii(world):
    first = [str(one) for one in run(world, with_tests=True).checks]

    for line in first:
        assert line.isascii(), line
        assert not UUID_PATTERN.search(line), line
        assert not TIMESTAMP_PATTERN.search(line), line
        assert str(REPO) not in line and "127.0.0.1" not in line, line


def test_two_worlds_with_different_uuids_print_identical_reports(monkeypatch):
    def report_of() -> list[str]:
        world = World()
        world.ran = []
        monkeypatch.setattr(vs01, "row_counts", world.row_counts)
        monkeypatch.setattr(vs01, "current_heads", lambda sessions: world.current)
        monkeypatch.setattr(vs01, "script_heads", lambda: world.heads)
        monkeypatch.setattr(vs01, "run_assessment", world.run_assessment)
        monkeypatch.setattr(vs01, "run_ingestion", world.run_ingestion)
        monkeypatch.setattr(vs01, "build_connector", lambda source, **kwargs: object())
        return [str(one) for one in run(world, with_tests=True).checks]

    assert report_of() == report_of()


# ---------------------------------------------------------------------------
# A27.1: the clean full-dataset path
# ---------------------------------------------------------------------------


def test_a27_1_reports_the_version_head_counts_and_both_runs(world):
    detail = check(run(world), "clean_dataset").detail

    assert detail == (f"sqlalchemy {vs01.installed_version('sqlalchemy')}; head 070e4968a497; "
                      "organizations 1, employees 24, customers 50, deals 44, projects 22, "
                      "support_tickets 80, documents 12; 233 fetched, 0 rejected: "
                      "SUCCESS then NOOP")


def test_a27_1_posts_the_unfiltered_ingestion_twice(world):
    run(world)

    posts = [kwargs["json"] for method, path, kwargs in world.calls
             if (method, path) == ("POST", vs01.INGESTION_RUNS)]
    assert posts == [{"source": "csv_demo"}, {"source": "csv_demo"}]


@pytest.mark.parametrize("change, message", [
    (lambda w: setattr(w, "heads", ("aaa", "bbb")), "has heads aaa, bbb, not 070e4968a497"),
    (lambda w: setattr(w, "current", ("8bfd73b6af60",)), "the database is at 8bfd73b6af60"),
    (lambda w: setattr(w, "current", ()), "the database is at no revision"),
    (lambda w: w.counts.update(customers=52, deals=46),
     "the database is not empty before the scenario: customers 52, deals 46"),
    (lambda w: w.ingestion_runs[0].update(status="PARTIAL_SUCCESS"),
     "the ingestion finished PARTIAL_SUCCESS with 233 fetched and 0 rejected"),
    (lambda w: w.ingestion_runs[0].update(records_fetched=94), "with 94 fetched"),
    (lambda w: w.ingestion_runs[0].update(records_rejected=4), "and 4 rejected"),
    (lambda w: w.ingestion_runs[1].update(status="SUCCESS"), "the repeated ingestion finished "
                                                            "SUCCESS"),
    (lambda w: w.ingestion_runs[1].update(records_updated=3), "and 3 updated, not NOOP"),
])
def test_a27_1_fails_on_the_first_state_that_differs(world, change, message):
    change(world)

    failed(run(world), "clean_dataset", message)


def test_a27_1_fails_when_the_ingestion_route_refuses(world):
    world.overrides[("POST", vs01.INGESTION_RUNS)] = StubResponse({}, 422)

    failed(run(world), "clean_dataset", "POST /api/v1/ingestion/runs answered 422, not 201")


def test_a27_1_fails_when_the_canonical_counts_differ(world):
    counts = {**vs01.CANONICAL_COUNTS, "documents": 0, "organizations": 0}
    world.overrides[("GET", "/api/v1/metrics/ingestion")] = StubResponse(
        {"totals": {"canonical_records": counts}})

    failed(run(world), "clean_dataset", "organizations 0, employees 24")


def test_an_unreachable_api_fails_a_check_rather_than_crashing(world):
    def unreachable(kwargs: object) -> None:
        raise httpx.ConnectError("refused")

    world.overrides[("POST", vs01.INGESTION_RUNS)] = unreachable

    failed(run(world), "clean_dataset",
           "POST /api/v1/ingestion/runs could not be reached (ConnectError)")


# ---------------------------------------------------------------------------
# A27.1b: the pinned fingerprint (K1)
# ---------------------------------------------------------------------------


def test_a27_1b_refuses_the_mismatch_then_runs_pinned_and_commits(world):
    detail = check(run(world), "pinned_fingerprint").detail

    assert detail == (f"pinned {PIN[:8]} matched; deliberate mismatch refused, 0 rows written; "
                      "50 assessments, 3 briefs")
    assert [call["expected_fingerprint"] for call in world.assessment_calls[:2]] == [
        vs01.MISMATCH, PIN]
    assert world.transactions[:2] == ["rollback", "commit"]


def test_every_assessment_call_carries_the_pin_or_a_deliberate_refusal(world):
    run(world)

    assert world.assessment_calls
    for call in world.assessment_calls:
        assert call["expected_fingerprint"] in {PIN, vs01.MISMATCH}
        assert call["source_system"] == "csv_demo"
        assert call["as_of"] == default_risk_rules().acceptance_as_of


def test_the_deliberate_mismatch_is_not_the_pin():
    assert vs01.MISMATCH != PIN
    assert re.fullmatch(r"[0-9a-f]{64}", vs01.MISMATCH)


def test_a_contaminated_snapshot_fails_a27_1b_with_the_named_message_and_assesses_nothing(world):
    world.computed = "d" * 64

    report = run(world)

    failed(report, "pinned_fingerprint", f"expected {PIN}, computed {'d' * 64}")
    failed(report, "pinned_fingerprint", "rebuild the database from the clean full-dataset path")
    assert [call["expected_fingerprint"] for call in world.assessment_calls] == [vs01.MISMATCH]
    assert "commit" not in world.transactions
    for name in ("single_escalation", "brief_facts", "no_active_project", "conflict_and_dissent",
                 "citations_resolve", "approval_boundary", "determinism"):
        failed(report, name, "A27.1b did not pass")
    assert not [call for call in world.calls if call[0] == "POST" and call[1] != vs01.INGESTION_RUNS]


def test_a_mismatch_that_is_not_refused_fails_a27_1b_and_is_rolled_back(world, monkeypatch):
    monkeypatch.setattr(vs01, "run_assessment", lambda session, **kwargs: world.pinned)

    report = run(world)

    failed(report, "pinned_fingerprint", "the deliberately mismatched run was not refused")
    assert world.transactions == ["rollback"]


def test_a_refused_run_that_writes_anything_fails_a27_1b(world):
    world.refused_writes = True

    failed(run(world), "pinned_fingerprint",
           "the refused deliberately mismatched run changed row counts: risk_assessments 0->1")


def test_a_pinned_run_that_fails_after_the_check_is_rolled_back_and_reported(world, monkeypatch):
    calls: list[str] = []

    def mismatch_then_raise(session, **kwargs):
        calls.append(kwargs["expected_fingerprint"])
        if kwargs["expected_fingerprint"] == vs01.MISMATCH:
            raise FingerprintMismatchError("csv_demo", vs01.MISMATCH, PIN)
        raise FingerprintMismatchError("csv_demo", PIN, "e" * 64)

    monkeypatch.setattr(vs01, "run_assessment", mismatch_then_raise)

    report = run(world)

    failed(report, "pinned_fingerprint", f"expected {PIN}, computed {'e' * 64}")
    assert world.transactions == ["rollback", "rollback"]


@pytest.mark.parametrize("change, message", [
    (lambda w: w.pinned.pop(), "returned 49 results, 49 created, not 50 created"),
    (lambda w: setattr(w.pinned[5], "created", False), "returned 50 results, 49 created"),
    (lambda w: setattr(w.pinned[2], "brief_id", None), "wrote 2 briefs, not 3"),
])
def test_a27_1b_fails_when_the_pinned_run_is_not_fifty_created_with_three_briefs(
        world, change, message):
    change(world)

    failed(run(world), "pinned_fingerprint", message)


# ---------------------------------------------------------------------------
# A27.2 ... A27.5: the listing and the brief
# ---------------------------------------------------------------------------


def test_a27_2_fails_when_the_total_is_not_fifty(world):
    world.listed.pop()

    failed(run(world), "single_escalation", "reports 49 assessments, not 50")


def test_a27_2_fails_when_another_customer_is_executive_worthy(world):
    world.overrides[("GET", vs01.ASSESSMENTS)] = lambda kwargs: StubResponse(
        {"items": world.listed[:2], "total": 2} if len(kwargs["params"]) > 1
        else {"items": world.listed, "total": 50})

    failed(run(world), "single_escalation",
           "executive_worthy=true lists 2 assessments (CUST-007, CUST-001), not CUST-007 alone")


def test_a27_2_fails_when_the_server_reads_another_database(world):
    world.listed[0] = {**world.listed[0], "id": str(uuid.uuid4())}

    failed(run(world), "single_escalation", "the command and the server read different databases")


@pytest.mark.parametrize("change, message", [
    (lambda b: b.update(payload_hash="f" * 64), "payload_hash is ffffffff, not e93c29cf"),
    (lambda b: b.update(narrative=b["narrative"] + "\n"), "the narrative differs from tests/golden"),
    (lambda b: b.update(decision_status="REJECTED"), "is DRAFT/REJECTED, not DRAFT/PENDING"),
    (lambda b: b["citations"].pop(), "carries 35 citations, not 36"),
    (lambda b: b["payload"]["support_evidence"]["tickets"][0].update(priority="low"),
     "support_evidence.tickets differs"),
    (lambda b: b["payload"]["support_evidence"].update(escalation_window=None),
     "support_evidence.escalation_window differs"),
    (lambda b: b["payload"]["support_evidence"]["ticket_span"].update(ticket_span_days=13),
     "ticket_span (5 tickets in a 9-day span) differs"),
    (lambda b: b["payload"]["support_evidence"]["derivations"][1].update(value=4),
     "3 open high-priority SLA breaches; dominant performance) differs"),
    (lambda b: b["payload"]["support_evidence"].update(backlog_ticket_ids=["TKT-001"]),
     "support_evidence.backlog_ticket_ids differs"),
    (lambda b: b["payload"]["support_evidence"]["escalation_path"]["account_owner"].update(
        id="EMP-001"), "support_evidence.escalation_path differs"),
    (lambda b: b["payload"]["commercial_evidence"]["deals"][0]["amount"].update(currency="INR"),
     "commercial_evidence (DEAL-001 negotiation at 90% for USD 5361.44) differs"),
    (lambda b: b["payload"]["cited_spans"][1]["citation"].update(start=154),
     "cited_spans (DOC-003's rule; DOC-006's term and notice; DOC-009's linkage) differs"),
])
def test_a27_3_names_the_first_fact_that_differs(world, change, message):
    change(world.brief)

    failed(run(world), "brief_facts", message)


def test_a27_3_evidence_names_the_hash_the_golden_size_and_the_citations(world):
    detail = check(run(world), "brief_facts").detail

    assert detail == ("payload_hash e93c29cf; narrative equals the golden file (12474 bytes); "
                      "the 10 facts of A27.3; 36 citations")


def test_the_briefless_meridian_result_fails_the_brief_checks_by_name(world):
    world.pinned[0].brief_id = None
    world.pinned[3].brief_id = uuid.uuid4()

    report = run(world)

    for name in ("brief_facts", "no_active_project", "conflict_and_dissent"):
        failed(report, name, "CUST-007's pinned result has no brief")


@pytest.mark.parametrize("change, message", [
    (lambda b: b["payload"]["signals"].update(active_project_count=1),
     "records 1 active projects in signals and 0 in worthiness"),
    (lambda b: b["payload"]["reconciliation"]["worthiness"].update(active_project_count=2),
     "records 0 active projects in signals and 2 in worthiness"),
    (lambda b: b.update(narrative=b["narrative"].replace(vs01.PROJECT_ABSENCE_LINE, "")),
     "the narrative does not carry the project-absence line"),
])
def test_a27_4_fails_on_the_field_or_the_line(world, change, message):
    change(world.brief)

    failed(run(world), "no_active_project", message)


def _reconciliation(brief: dict[str, Any]) -> dict[str, Any]:
    reconciliation: dict[str, Any] = brief["payload"]["reconciliation"]
    return reconciliation


@pytest.mark.parametrize("change, message", [
    (lambda r: r["conflicts"].append({}), "holds 2 conflicts, not 1"),
    (lambda r: r["conflicts"][0].update(object_ref="DEAL-002"), "over DEAL-001"),
    (lambda r: r["resolutions"].clear(), "holds 0 resolutions, not 1"),
    (lambda r: r["resolutions"][0].update(policy_id="CONF-002"), "resolved by CONF-002"),
    (lambda r: r.update(policy_version=2), "at policy_version 2, not CONF-001 at 1"),
    (lambda r: r["resolutions"][0].update(resolved_action="ACCELERATE_DEAL_CLOSE"),
     "ACCELERATE_DEAL_CLOSE wins, not PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED"),
    (lambda r: r["dissent"].clear(), "the dissent in reconciliation is not SALES"),
    (lambda r: r["resolutions"][0]["dissent"][0].update(function="SUPPORT"),
     "the dissent in the resolution is not SALES"),
    (lambda r: r["dissent"][0]["evidence"].pop(), "does not carry its three citations"),
])
def test_a27_5_fails_on_the_element_that_differs(world, change, message):
    change(_reconciliation(world.brief))

    failed(run(world), "conflict_and_dissent", message)


@pytest.mark.parametrize("line", [*vs01.CONFLICT_LINES,
                                  "  - CANONICAL_FACT record deals DEAL-001 probability",
                                  vs01.DISSENT_HEADING])
def test_a27_5_fails_when_the_narrative_does_not_state_an_element(world, line):
    narrative = world.brief["narrative"]
    if line.startswith("  - CANONICAL"):
        head, dissent = narrative.split(vs01.DISSENT_HEADING, 1)
        world.brief["narrative"] = head + vs01.DISSENT_HEADING + dissent.replace(line, "", 1)
    else:
        world.brief["narrative"] = narrative.replace(line, "")

    assert check(run(world), "conflict_and_dissent").outcome is Outcome.FAIL


# ---------------------------------------------------------------------------
# A27.6: citations
# ---------------------------------------------------------------------------


def test_a27_6_counts_the_distinct_citations_it_resolved(world):
    detail = check(run(world), "citations_resolve").detail

    assert detail == ("31 distinct citations across 50 assessments and 3 briefs resolve; "
                      "3 cited spans read back exactly")


@pytest.mark.parametrize("change, message", [
    (lambda w: w.records["deals"].clear(), 'citation {"entity":"deals","field":"amount"'),
    (lambda w: w.records["deals"][0].update(amount=None),
     'citation {"entity":"deals","field":"amount","id":"DEAL-001","kind":"record"} does not'),
    (lambda w: w.records["support_tickets"][0].pop("priority"),
     '"field":"priority","id":"TKT-073"'),
    (lambda w: w.records["documents"][0].update(body_text="short"),
     '{"document_id":"DOC-003","end":330,"kind":"document","start":238} does not resolve'),
    (lambda w: w.records["customers"][0].update(source_system="other_demo"),
     '"entity":"customers","field":"email","id":"CUST-007"'),
])
def test_a27_6_names_the_first_citation_that_does_not_resolve(world, change, message):
    change(world)

    failed(run(world), "citations_resolve", message)


def test_a27_6_accepts_a_null_field_outside_dr21(world):
    world.records["support_tickets"][0]["resolved_at"] = None

    assert check(run(world), "citations_resolve").outcome is Outcome.PASS


def test_a27_6_fails_when_a_span_does_not_read_back_its_phrase(world):
    document = world.records["documents"][1]
    document["body_text"] = document["body_text"].replace("Term: 36", "Term: 48")

    failed(run(world), "citations_resolve",
           "DOC_006_TERM_AND_NOTICE does not read back its phrase from DOC-006")


def test_a27_6_fails_when_a_target_is_missing(world):
    world.brief["payload"]["cited_spans"].pop()

    failed(run(world), "citations_resolve", "the briefs cite spans for DOC_003_ESCALATION_RULE, "
                                            "DOC_006_TERM_AND_NOTICE, not the three targets")


def test_a27_6_fails_when_paging_loses_records(world):
    world.overrides[("GET", "/api/v1/entities/deals")] = StubResponse(
        {"items": [], "total": 1})

    failed(run(world), "citations_resolve", "paging deals returned 0 of 1 records")


def test_a27_6_reads_every_assessment_and_every_brief(world):
    run(world)

    paths = [path for method, path, _ in world.calls if method == "GET"]
    for result in world.pinned:
        assert f"{vs01.ASSESSMENTS}/{result.assessment_id}" in paths
        if result.brief_id is not None:
            assert f"{vs01.BRIEFS}/{result.brief_id}" in paths


# ---------------------------------------------------------------------------
# A27.9: the approval boundary (R-M9-6)
# ---------------------------------------------------------------------------


def test_a27_9_decides_rejected_then_is_refused_then_approves(world):
    report = run(world)

    assert check(report, "approval_boundary").outcome is Outcome.PASS
    bodies = [kwargs["json"] for method, path, kwargs in world.calls
              if method == "POST" and path.endswith("/decision")]
    first = world.decisions[0]["id"]
    assert [(one["decision"], one["supersedes_id"]) for one in bodies] == [
        ("REJECTED", None), ("APPROVED", None), ("APPROVED", first)]
    assert {one["actor"] for one in bodies} == {"verify-vs01"}
    assert {one["payload_hash"] for one in bodies} == {vs01.MERIDIAN_HASH}
    assert world.executed == ["UPDATE", "DELETE"]


def test_a27_9_runs_before_a27_8_changes_the_snapshot(world):
    run(world)

    decided = next(index for index, (method, path, _) in enumerate(world.calls)
                   if path.endswith("/decision"))
    reassessed = next(index for index, (method, path, _) in enumerate(world.calls)
                      if (method, path) == ("POST", vs01.ASSESSMENTS))
    assert decided < reassessed


def _decision_override(world: World, step: int, response: StubResponse):
    calls = {"n": 0}
    original = world._decide

    def answer(kwargs):
        calls["n"] += 1
        return response if calls["n"] == step else original(kwargs["json"])

    world.overrides[("POST", vs01.DECISION.format(brief_id=world.pinned[0].brief_id))] = answer


@pytest.mark.parametrize("step, response, message", [
    (1, StubResponse({}, 500), "(i) REJECTED answered 500, not 201"),
    (2, StubResponse({"id": "x"}, 201), "(ii) APPROVED without supersedes_id answered 201"),
    (2, StubResponse({"error": {"code": "DECISION_CONFLICT",
                                "details": {"reason": "NOT_HEAD"}}}, 409),
     "not 409 DECISION_CONFLICT SUPERSEDES_REQUIRED"),
    (3, StubResponse({}, 409), "(iii) APPROVED superseding (i) answered 409, not 201"),
])
def test_a27_9_fails_on_the_step_that_differs(world, step, response, message):
    _decision_override(world, step, response)

    failed(run(world), "approval_boundary", message)


def test_a27_9_fails_when_a_decision_writes_more_than_one_row(world):
    original = world._decide

    def two_rows(kwargs):
        response = original(kwargs["json"])
        world.counts["risk_briefs"] += 1
        return response

    world.overrides[("POST", vs01.DECISION.format(brief_id=world.pinned[0].brief_id))] = two_rows

    failed(run(world), "approval_boundary",
           "(i) REJECTED did not write exactly one brief_decisions row: risk_briefs 0->1")


def test_a27_9_fails_when_the_refused_decision_writes(world):
    def refused_but_written(kwargs):
        if kwargs["json"]["supersedes_id"] is None and world.decisions:
            world.counts["brief_decisions"] += 1
            return StubResponse({"error": {"code": "DECISION_CONFLICT",
                                           "details": {"reason": "SUPERSEDES_REQUIRED"}}}, 409)
        return world._decide(kwargs["json"])

    world.overrides[("POST", vs01.DECISION.format(
        brief_id=world.pinned[0].brief_id))] = refused_but_written

    failed(run(world), "approval_boundary", "(ii) the refused decision changed row counts")


def test_a27_9_fails_when_the_history_is_not_in_chain_order(world):
    world.overrides[("GET", vs01.DECISIONS.format(brief_id=world.pinned[0].brief_id))] = (
        lambda kwargs: StubResponse({"items": list(reversed(world.decisions))}))

    failed(run(world), "approval_boundary", "(iv) the history is not REJECTED then APPROVED")


def test_a27_9_fails_when_the_brief_status_moves(world):
    world.brief["status"] = "APPROVED"

    failed(run(world), "approval_boundary", "(iv) the brief is APPROVED/APPROVED, not DRAFT/APPROVED")


def test_a27_9_fails_when_an_update_or_delete_is_not_refused(world):
    world.execute_error = None

    failed(run(world), "approval_boundary", "an UPDATE on brief_decisions was not refused")


def test_a27_9_fails_when_another_error_refuses_the_statement(world):
    world.execute_error = IntegrityError("UPDATE", {}, TriggerError("23503", "fk"))

    failed(run(world), "approval_boundary",
           "the UPDATE failed with SQLSTATE 23503, not the append-only trigger's 23001")


def test_a27_9_refuses_the_right_sqlstate_with_another_message(world):
    """23001 is also a RESTRICT foreign key's SQLSTATE: the trigger's message must match too."""
    world.execute_error = IntegrityError("DELETE", {}, TriggerError(
        "23001", "update or delete on table violates RESTRICT setting"))

    failed(run(world), "approval_boundary",
           "the UPDATE failed with SQLSTATE 23001, not the append-only trigger's 23001")


def test_a27_9_accepts_only_the_trigger_error(world):
    world.execute_error = IntegrityError("UPDATE", {}, TriggerError("23001",
                                                                    vs01.APPEND_ONLY_MESSAGE))

    assert check(run(world), "approval_boundary").outcome is Outcome.PASS


def test_a27_9_fails_when_a_refused_statement_changes_counts(world):
    def delete_one_row() -> None:
        world.counts["brief_decisions"] -= 1

    world.on_execute = delete_one_row

    failed(run(world), "approval_boundary",
           "the refused UPDATE changed row counts: brief_decisions 2->1")


@pytest.mark.parametrize("path, methods, message", [
    ("/api/v1/risk/briefs/{brief_id}/execute", {"post": {}},
     "(vi) the API publishes 4 non-GET operations"),
    (vs01.DECISIONS, {"get": {}, "delete": {}}, "(vi) the API publishes 4 non-GET operations"),
    ("/api/v1/risk/summary", {"get": {}}, "(vi) the API publishes 7 risk operations"),
])
def test_a27_9_fails_when_anything_else_is_executable(world, path, methods, message):
    world.openapi["paths"][path] = methods

    failed(run(world), "approval_boundary", message)


# ---------------------------------------------------------------------------
# A27.8: determinism and the changed snapshot
# ---------------------------------------------------------------------------


def test_a27_8_re_runs_unpinned_ingests_the_fixture_and_re_runs(world):
    report = run(world)

    assert check(report, "determinism").detail == (
        "re-run 200: identical hashes, 0 rows; one extra ticket: pinned run refused, unpinned "
        "run 201 with 50 new assessments")
    posts = [kwargs["json"] for method, path, kwargs in world.calls
             if (method, path) == ("POST", vs01.ASSESSMENTS)]
    assert posts == [{"as_of": "2026-09-18", "source_system": "csv_demo",
                      "customer_source_id": None}] * 2
    assert world.ingestions == [("support_tickets",)]
    assert [call["expected_fingerprint"] for call in world.assessment_calls] == [
        vs01.MISMATCH, PIN, PIN]


def test_a27_8_is_the_last_check_that_writes(world):
    run(world)

    writes = [index for index, (method, _, _) in enumerate(world.calls) if method != "GET"]
    last_listing = max(index for index, (method, path, _) in enumerate(world.calls)
                       if (method, path) == ("GET", vs01.ASSESSMENTS))
    assert writes[-1] < last_listing
    assert world.ran == [vs01.PROOF_COMMAND]


@pytest.mark.parametrize("change, message", [
    (lambda w: w.overrides.__setitem__(("POST", vs01.ASSESSMENTS), StubResponse({}, 201)),
     "(i) the re-run answered 201, not 200"),
    (lambda w: w.overrides.__setitem__(("POST", vs01.ASSESSMENTS),
                                       StubResponse({"items": []}, 200)),
     "(i) the re-run's results are not the pinned run's"),
    (lambda w: setattr(w, "fixture_counts", (0, 1)),
     "(ii) the unresolved_ticket fixture inserted 0 and rejected 1 rows, not 1 and 0"),
])
def test_a27_8_fails_on_the_step_that_differs(world, change, message):
    change(world)

    failed(run(world), "determinism", message)


def test_a27_8_fails_when_the_re_run_writes(world):
    original = world._assess

    def writes(kwargs):
        world.counts["risk_briefs"] += 1
        return original()

    world.overrides[("POST", vs01.ASSESSMENTS)] = writes

    failed(run(world), "determinism", "(i) the re-run changed row counts: risk_briefs 0->1")


def test_a27_8_fails_when_the_pinned_gate_accepts_the_changed_snapshot(world, monkeypatch):
    original = world.run_ingestion

    def unchanged(*args):
        summary = original(*args)
        world.computed = PIN
        return summary

    monkeypatch.setattr(vs01, "run_ingestion", unchanged)

    failed(run(world), "determinism", "the pinned run on the changed snapshot was not refused")


def test_a27_8_fails_when_the_changed_snapshot_is_not_new_assessments(world):
    original = world._assess

    def answer(kwargs):
        response = original()
        if response.status_code == 201:
            response._payload["items"][0]["created"] = False
        return response

    world.overrides[("POST", vs01.ASSESSMENTS)] = answer

    failed(run(world), "determinism", "(iv) the changed snapshot answered 50 results, not 50 new")


def test_a27_8_fails_when_the_earlier_assessments_are_not_retained(world):
    original = world._assess

    def answer(kwargs):
        response = original()
        if response.status_code == 201:
            world.counts["risk_assessments"] -= 50
        return response

    world.overrides[("POST", vs01.ASSESSMENTS)] = answer

    failed(run(world), "determinism", "(iv) the earlier assessments were not all retained")


def test_a27_8_fails_when_the_listing_holds_one_fingerprint(world):
    original = world._assess

    def answer(kwargs):
        response = original()
        for item in world.new_results:
            item["layer1_fingerprint"] = PIN
        return response

    world.overrides[("POST", vs01.ASSESSMENTS)] = answer

    failed(run(world), "determinism", "(iv) the listing holds 100 assessments under 1 fingerprints")


def test_a27_8_fails_when_the_changed_snapshot_is_not_answered_201(world):
    world.overrides[("POST", vs01.ASSESSMENTS)] = lambda kwargs: (
        world._assess() if world.computed == PIN else StubResponse({}, 500))

    failed(run(world), "determinism", "(iv) the run on the changed snapshot answered 500, not 201")


# ---------------------------------------------------------------------------
# A27.7 and A27.10: the fixed subprocesses
# ---------------------------------------------------------------------------


def test_a27_7_reports_the_corpus_count(world):
    assert check(run(world), "named_tests").detail == "44 passed: A25 tests 1-14 and 13b"


@pytest.mark.parametrize("output, message", [
    (CommandResult(1, "1 failed, 43 passed in 30.00s\n"), "pytest exited 1: 1 failed, 43 passed"),
    (CommandResult(0, "43 passed, 1 skipped in 30.00s\n"), "pytest exited 0: 43 passed, 1 skipped"),
    (CommandResult(1, "43 passed, 1 error in 30.00s\n"), "pytest exited 1: 1 error, 43 passed"),
    (CommandResult(0, "43 passed in 30.00s\n"), "43 passed, but the corpus collects 44"),
    (CommandResult(4, "ERROR: not found\n"), "pytest exited 4 with no summary line"),
    (CommandResult(5, "44 passed in 1.00s\n"), "pytest exited 5: 44 passed"),
])
def test_a27_7_fails_unless_every_proof_passed(world, output, message):
    world.proof_output = output

    failed(run(world), "named_tests", message)


def test_a27_10_reports_every_baseline_and_the_tool_versions(world):
    detail = check(run(world, with_tests=True), "regression").detail

    assert detail == (f"6600 passed; coverage 100% over 7456 statements; "
                      f"ruff {vs01.installed_version('ruff')}: 69; "
                      f"mypy {vs01.installed_version('mypy')}: 9; secret scan 0; "
                      f"head 070e4968a497")
    assert world.ran == [vs01.PROOF_COMMAND, *vs01.REGRESSION_COMMANDS]


@pytest.mark.parametrize("attribute, output, message", [
    ("suite_output", CommandResult(1, "TOTAL 7456 0 100%\n2 failed, 6598 passed in 1.0s\n"),
     "pytest exited 1: 2 failed, 6598 passed"),
    ("suite_output", CommandResult(0, "TOTAL    7456      3    99%\n6600 passed in 1.0s\n"),
     "app/ coverage is 99%, not 100%"),
    ("suite_output", CommandResult(0, "6600 passed in 1.0s\n"),
     "the suite printed no coverage total"),
    ("ruff_output", CommandResult(1, "Found 70 errors.\n"),
     "ruff check app/ tests/ scripts/ reports 70, not 69"),
    ("ruff_output", CommandResult(0, "All checks passed!\n"),
     "ruff check app/ tests/ scripts/ reports 0, not 69"),
    ("ruff_output", CommandResult(2, "error: unreadable\n"),
     "ruff check app/ tests/ scripts/ reports None, not 69"),
    ("mypy_output", CommandResult(1, "Found 1 error in 1 file (checked 130 source files)\n"),
     "mypy app/ reports 1, not 9"),
    ("mypy_output", CommandResult(0, "Success: no issues found in 130 source files\n"),
     "mypy app/ reports 0, not 9"),
    ("scan_output", CommandResult(1, "x.py:1: secret\nsecret-scan: 4 files scanned, "
                                     "0 binary files skipped, 1 findings\n"),
     "the secret scan exited 1 with 1 findings, not 0"),
])
def test_a27_10_fails_on_the_first_measurement_that_differs(world, attribute, output, message):
    setattr(world, attribute, output)

    failed(run(world, with_tests=True), "regression", message)


def test_a27_10_fails_when_the_migration_history_has_another_head(world, monkeypatch):
    heads = iter([("070e4968a497",), ("070e4968a497", "abc")])
    monkeypatch.setattr(vs01, "script_heads", lambda: next(heads))

    failed(run(world, with_tests=True), "regression",
           "the migration history has heads 070e4968a497, abc, not 070e4968a497")


@pytest.mark.parametrize("stdout, expected", [
    ("..\n43 passed, 2 warnings in 3.10s\n", {"passed": 43}),
    ("1 failed, 2 passed, 3 skipped, 1 error in 2s\n",
     {"failed": 1, "passed": 2, "skipped": 3, "error": 1}),
    ("2 errors in 1s\n", {"error": 2}),
    ("no tests ran in 0.01s\n", {}),
    ("7 passed\nTOTAL 1 0 100%\n", {"passed": 7}),
])
def test_the_pytest_summary_is_parsed_from_its_last_outcome_line(stdout, expected):
    assert vs01.pytest_outcomes(stdout) == expected


# ---------------------------------------------------------------------------
# K2: the fixed subprocess argument lists and the only non-GET requests
# ---------------------------------------------------------------------------


def test_the_subprocess_argument_lists_are_exactly_the_specified_ones():
    pytest_prefix = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o",
                     "addopts="]

    assert list(vs01.PROOF_COMMAND) == [*pytest_prefix, *vs01.A25_PROOFS]
    assert [list(argv) for argv in vs01.REGRESSION_COMMANDS] == [
        [*pytest_prefix, "--cov=app", "--cov-report=term"],
        [sys.executable, "-m", "ruff", "check", "app/", "tests/", "scripts/"],
        [sys.executable, "-m", "mypy", "app/"],
        [sys.executable, "scripts/secret_scan.py"],
    ]


def test_run_command_runs_the_list_from_the_repository_root_without_a_shell(monkeypatch):
    seen: dict[str, Any] = {}

    def fake_run(argv, **kwargs):
        seen.update(argv=argv, **kwargs)
        return SimpleNamespace(returncode=3, stdout="out")

    monkeypatch.setattr(vs01.subprocess, "run", fake_run)

    result = vs01.run_command(vs01.MYPY_COMMAND)

    assert result == CommandResult(3, "out")
    assert seen == {"argv": list(vs01.MYPY_COMMAND), "cwd": vs01.PROJECT_ROOT,
                    "capture_output": True, "text": True, "check": False}


def _calls(tree: ast.AST, dotted: str) -> list[ast.Call]:
    def name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{name(node.value)}.{node.attr}"
        return ""

    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and name(node.func) == dotted]


def test_the_script_has_one_subprocess_call_and_it_uses_no_shell():
    (call,) = _calls(SOURCE_TREE, "subprocess.run")

    assert [ast.unparse(argument) for argument in call.args] == ["list(argv)"]
    assert {keyword.arg: ast.unparse(keyword.value) for keyword in call.keywords} == {
        "cwd": "PROJECT_ROOT", "capture_output": "True", "text": "True", "check": "False"}
    assert not [keyword for node in ast.walk(SOURCE_TREE) if isinstance(node, ast.Call)
                for keyword in node.keywords if keyword.arg == "shell"]
    called = {ast.unparse(node.func) for node in ast.walk(SOURCE_TREE)
              if isinstance(node, ast.Call)}
    assert not {"os.system", "os.popen", "subprocess.Popen", "subprocess.call",
                "subprocess.check_output"} & called


def test_every_request_method_is_get_or_post_and_every_post_is_one_of_the_three_writes():
    requests = _calls(SOURCE_TREE, "self._request")
    methods = {call.args[0].value for call in requests if isinstance(call.args[0], ast.Constant)}
    posts = {ast.unparse(call.args[0]) for call in _calls(SOURCE_TREE, "self._post")}

    assert methods == {"GET", "POST"}
    assert all(isinstance(call.args[0], ast.Constant) for call in requests)
    assert [ast.unparse(call.func) for call in _calls(SOURCE_TREE, "self.client.request")] == [
        "self.client.request"]
    assert posts == {"INGESTION_RUNS", "ASSESSMENTS", "DECISION.format(brief_id=brief_id)"}
    assert vs01.WRITES == {("POST", "/api/v1/ingestion/runs"), ("POST", "/api/v1/risk/assessments"),
                           ("POST", "/api/v1/risk/briefs/{brief_id}/decision")}


def test_a_passing_run_sends_exactly_the_three_writes_and_only_relative_paths(world):
    run(world)

    def template(path: str) -> str:
        return re.sub(UUID_PATTERN, "{brief_id}", path)

    non_get = {(method, template(path)) for method, path, _ in world.calls if method != "GET"}
    assert non_get == vs01.WRITES
    assert all(path.startswith("/") for _, path, _ in world.calls)


def test_the_client_is_built_as_httpx_client_on_the_served_base_url():
    (call,) = _calls(SOURCE_TREE, "httpx.Client")

    assert {keyword.arg: ast.unparse(keyword.value) for keyword in call.keywords} == {
        "base_url": "base_url", "timeout": "args.timeout"}


# ---------------------------------------------------------------------------
# K1: the closed Layer 2 import set and the pinned calls
# ---------------------------------------------------------------------------


LAYER2 = ("app.intelligence", "app.relationships", "app.evidence", "app.analysts",
          "app.decisions", "app.api.v1.risk")


def _imports(tree: ast.AST) -> set[tuple[str, str]]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update((alias.name, "") for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.update((node.module or "", alias.name) for alias in node.names)
    return found


def _layer2_imports(tree: ast.AST) -> set[tuple[str, str]]:
    return {(module, name) for module, name in _imports(tree)
            if module.startswith(LAYER2) or (module == "app" and name in {
                "intelligence", "relationships", "evidence", "analysts", "decisions"})}


def test_the_layer_2_imports_are_exactly_the_closed_set():
    assert _layer2_imports(SOURCE_TREE) == {
        ("app.decisions.assessment", "run_assessment"),
        ("app.intelligence", "FingerprintMismatchError"),
        ("app.intelligence", "default_risk_rules"),
    }


@pytest.mark.parametrize("source", [
    "from app.decisions.approval import record_decision\n",
    "import app.api.v1.risk\n",
    "from app.intelligence import resolve_scope\n",
    "from app import decisions\n",
    "from app.evidence import derive_and_persist\n",
])
def test_the_import_scan_would_catch_another_layer_2_import(source):
    assert _layer2_imports(ast.parse(source))


def _indirections(tree: ast.AST) -> list[str]:
    """TYPE_CHECKING blocks, dynamic imports and imports anywhere but the module's top level."""
    found = [ast.unparse(node.test) for node in ast.walk(tree)
             if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test)]
    found += [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
              and ast.unparse(node.func).endswith(("import_module", "__import__"))]
    top_level = {id(node) for node in getattr(tree, "body", [])}
    found += [ast.unparse(node) for node in ast.walk(tree)
              if isinstance(node, ast.Import | ast.ImportFrom) and id(node) not in top_level]
    return found


def test_no_indirection_disguises_an_import():
    assert _indirections(SOURCE_TREE) == []


@pytest.mark.parametrize("source", [
    "if TYPE_CHECKING:\n    from app.decisions import approval\n",
    "module = importlib.import_module('app.decisions.approval')\n",
    "module = __import__('app.decisions.approval')\n",
    "def f():\n    from app.decisions import approval\n",
])
def test_the_indirection_scan_would_catch_each_form(source):
    assert _indirections(ast.parse(source))


def _pinned_calls_ok(tree: ast.AST) -> bool:
    calls = _calls(tree, "run_assessment")
    for call in calls:
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        value = keywords.get("expected_fingerprint")
        if value is None or (isinstance(value, ast.Constant) and value.value is None):
            return False
    return bool(calls)


def test_every_run_assessment_call_passes_expected_fingerprint_as_a_keyword():
    assert _pinned_calls_ok(SOURCE_TREE)
    (call,) = _calls(SOURCE_TREE, "run_assessment")
    assert [ast.unparse(keyword.value) for keyword in call.keywords
            if keyword.arg == "expected_fingerprint"] == ["expected_fingerprint"]


@pytest.mark.parametrize("source", [
    "run_assessment(session, as_of=day)\n",
    "run_assessment(session, as_of=day, expected_fingerprint=None)\n",
    "run_assessment(session, day, 'csv_demo', None, None)\n",
])
def test_the_pinned_call_scan_would_catch_an_unpinned_call(source):
    assert not _pinned_calls_ok(ast.parse(source))


def test_every_pinned_run_is_given_the_pin_or_the_deliberate_mismatch():
    arguments = [ast.unparse(call.args[0]) for name in ("self._pinned_run", "self._refused")
                 for call in _calls(SOURCE_TREE, name)]

    assert sorted(arguments) == ["MISMATCH", "expected_fingerprint", "self.pin", "self.pin"]


def test_the_only_unpinned_run_is_a27_8s_post_after_the_pinned_gate_refused():
    """K1: no check substitutes an unpinned run for a pinned one."""
    unpinned = _calls(SOURCE_TREE, "self._assess_unpinned")
    method = next(node for node in ast.walk(SOURCE_TREE)
                  if isinstance(node, ast.FunctionDef) and node.name == "determinism")
    in_method = [call.lineno for call in _calls(method, "self._assess_unpinned")]
    (gate,) = [call.lineno for call in _calls(method, "self._refused")]

    assert len(unpinned) == len(in_method) == 2
    assert in_method[0] < gate < in_method[1]


#: The script's other imports (§0.8.4, PROPOSED): a closed list.
OTHER_IMPORTS = {
    ("argparse", ""), ("json", ""), ("os", ""), ("re", ""), ("socket", ""), ("subprocess", ""),
    ("sys", ""), ("threading", ""), ("time", ""), ("tomllib", ""),
    ("collections.abc", "Callable"), ("collections.abc", "Iterator"),
    ("collections.abc", "Mapping"), ("collections.abc", "Sequence"),
    ("contextlib", "contextmanager"), ("dataclasses", "dataclass"), ("enum", "StrEnum"),
    ("importlib", "metadata"), ("pathlib", "Path"), ("typing", "Any"),
    ("__future__", "annotations"),
    ("httpx", ""), ("uvicorn", ""), ("alembic", "command"), ("alembic.config", "Config"),
    ("alembic.runtime.migration", "MigrationContext"), ("alembic.script", "ScriptDirectory"),
    ("sqlalchemy", "create_engine"), ("sqlalchemy", "delete"), ("sqlalchemy", "func"),
    ("sqlalchemy", "select"), ("sqlalchemy", "text"), ("sqlalchemy", "update"),
    ("sqlalchemy.engine", "URL"), ("sqlalchemy.engine", "make_url"),
    ("sqlalchemy.exc", "SQLAlchemyError"), ("sqlalchemy.orm", "Session"),
    ("sqlalchemy.orm", "sessionmaker"),
    ("app.persistence.models", ""), ("app.api.connectors", "ConnectorProvider"),
    ("app.connectors.registry", "build_connector"), ("app.core.config", "get_settings"),
    ("app.core.database", "Base"), ("app.core.logging", "configured_logging"),
    ("app.core.logging", "resolve_format"), ("app.core.logging", "resolve_level"),
    ("app.ingestion.orchestrator", "IngestionRequest"),
    ("app.ingestion.orchestrator", "run_ingestion"), ("app.main", "create_app"),
}


def test_the_other_imports_are_exactly_the_closed_list():
    assert _imports(SOURCE_TREE) - _layer2_imports(SOURCE_TREE) == OTHER_IMPORTS


def test_the_other_import_list_would_report_an_addition():
    tree = ast.parse(SOURCE + "\nimport requests\n")

    assert _imports(tree) - _layer2_imports(tree) != OTHER_IMPORTS


def test_sqlalchemy_text_is_used_only_for_the_two_database_statements():
    uses = [ast.unparse(call.args[0]) for call in _calls(SOURCE_TREE, "text")]

    assert uses == ["f'DROP DATABASE IF EXISTS {quoted} WITH (FORCE)'",
                    "f'CREATE DATABASE {quoted}'"]


# ---------------------------------------------------------------------------
# The §A25 proof corpus (§0.8.6)
# ---------------------------------------------------------------------------


def test_every_proof_names_an_existing_test_function():
    for node_id in vs01.A25_PROOFS:
        path, name = node_id.split("::")
        tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
        functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        assert name in functions, node_id


def test_the_corpus_is_31_distinct_node_ids_covering_tests_1_to_14_and_13b():
    """§0.8.6's thirty, plus test 10's Phase 5 proof in tests/integration/test_vs01_a25_closure.py."""
    assert len(vs01.A25_PROOFS) == 31 == len(set(vs01.A25_PROOFS))
    assert vs01.A25_PROOFS[20] == ("tests/integration/test_vs01_a25_closure.py::"
                                   "test_the_four_inactive_customers_are_ticketless_and_yield_none_"
                                   "not_worthy")
    assert "doc005_leave_out" in vs01.A25_PROOFS[7]
    assert vs01.A25_PROOFS[17].endswith("test_no_brief_holds_another_customers_identifiers")


def test_the_corpus_collects_exactly_the_count_a27_7_expects():
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
         "--collect-only", *vs01.A25_PROOFS],
        cwd=REPO, capture_output=True, text=True, check=False)

    assert re.search(rf"^{vs01.A25_PROOF_COUNT} tests collected", completed.stdout,
                     re.MULTILINE), completed.stdout[-500:]


def test_the_fixture_a27_8_ingests_is_the_manifests_unresolved_ticket_delta():
    import yaml

    manifest = yaml.safe_load((REPO / "tests" / "fixtures" / "vs01" / "manifest.yaml").read_text(
        encoding="utf-8"))
    (entry,) = [one for one in manifest["fixtures"] if one["name"] == "unresolved_ticket"]

    assert vs01.UNRESOLVED_TICKET_DIR == REPO / "tests" / "fixtures" / "vs01" / "unresolved_ticket"
    assert tuple(entry["entities"]) == vs01.UNRESOLVED_TICKET_ENTITIES
    assert entry["form"] == "delta" and entry["fingerprint"] == "changed"


def test_the_constants_restate_the_plans_measured_values():
    rules = default_risk_rules()

    assert rules.acceptance_as_of.isoformat() == "2026-09-18"
    assert PIN.startswith("1d891b0b")
    assert vs01.GOLDEN.read_bytes().decode("utf-8").count(vs01.PROJECT_ABSENCE_LINE) == 1
    assert sum(vs01.CANONICAL_COUNTS.values()) == vs01.DEMO_ROWS == 233
    for target, (_, start, end, phrase) in vs01.CITED_SPANS.items():
        assert end - start == len(phrase) and phrase.isascii(), target


# ---------------------------------------------------------------------------
# The environment check (R-M9-3)
# ---------------------------------------------------------------------------


def test_the_specifiers_are_read_from_pyproject():
    declared = vs01.declared_specifiers()

    assert declared["sqlalchemy"] == ">=2.0.0,<2.1"
    assert declared["ruff"] == "==0.16.7"
    assert declared["mypy"] == "==2.3.1"
    assert declared["uvicorn"] == ">=0.29.0"
    assert declared["types-pytz"] == ""


def test_the_script_holds_no_second_copy_of_the_pins():
    for pin in ("<2.1", "0.16.7", "2.3.1"):
        assert pin not in SOURCE


def test_a_declared_specifier_is_read_from_the_given_file(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\ndependencies = ["SQLAlchemy[asyncio] >= 2.0 , < 3 ; '
                         'python_version >= \'3.11\'"]\n'
                         '[project.optional-dependencies]\ndev = ["Ruff_Lint==1.2"]\n',
                         encoding="utf-8")

    assert vs01.declared_specifiers(pyproject) == {"sqlalchemy": ">= 2.0 , < 3",
                                                    "ruff-lint": "==1.2"}


@pytest.mark.parametrize("version, specifier, expected", [
    ("2.0.54", ">=2.0.0,<2.1", True),
    ("2.1.0", ">=2.0.0,<2.1", False),
    ("2.1", ">=2.0.0,<2.1", False),
    ("1.4.52", ">=2.0.0,<2.1", False),
    ("0.16.7", "==0.16.7", True),
    ("0.16.8", "==0.16.7", False),
    ("2.3.1", "==2.3.1", True),
    ("2.3.1.0", "==2.3.1", True),
    ("2.3", "==2.3.1", False),
    ("3", ">2,!=3", False),
    ("4", ">2,!=3", True),
    ("2", "<=2.0.0", True),
])
def test_a_plain_release_is_compared_clause_by_clause(version, specifier, expected):
    assert vs01.satisfies(version, specifier) is expected


@pytest.mark.parametrize("version, specifier, message", [
    ("2.1.0b1", "<2.1", "is not a plain release"),
    ("2.0.54", "~=2.0", "is not one this check can compare"),
    ("2.0.54", "==2.*", "is not one this check can compare"),
    ("2.0.54", "", "is not one this check can compare"),
])
def test_anything_the_check_cannot_compare_is_refused(version, specifier, message):
    with pytest.raises(EnvironmentRefused, match=re.escape(message)):
        vs01.satisfies(version, specifier)


DECLARED = {"sqlalchemy": ">=2.0.0,<2.1", "ruff": "==0.16.7", "mypy": "==2.3.1"}


def _installed(versions: dict[str, str], seen: list[str]):
    def version(package: str) -> str:
        seen.append(package)
        return versions[package]
    return version


def test_sqlalchemy_is_always_checked_and_the_tools_only_with_tests(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(vs01, "installed_version", _installed(
        {"sqlalchemy": "2.0.54", "ruff": "9.9.9", "mypy": "9.9.9"}, seen))

    assert vs01.check_environment(False, DECLARED) == {"sqlalchemy": "2.0.54"}
    assert seen == ["sqlalchemy"]
    with pytest.raises(EnvironmentRefused, match="ruff 9.9.9 is installed"):
        vs01.check_environment(True, DECLARED)


@pytest.mark.parametrize("package, version, message", [
    ("sqlalchemy", "2.1.0", "sqlalchemy 2.1.0 is installed, but pyproject.toml declares "
                            "sqlalchemy>=2.0.0,<2.1"),
    ("ruff", "0.4.0", "ruff 0.4.0 is installed, but pyproject.toml declares ruff==0.16.7"),
    ("mypy", "1.10.0", "mypy 1.10.0 is installed, but pyproject.toml declares mypy==2.3.1"),
    ("sqlalchemy", "2.1.0rc1", "sqlalchemy: installed version '2.1.0rc1' is not a plain release"),
])
def test_a_version_outside_its_specifier_is_refused_by_name(monkeypatch, package, version,
                                                             message):
    versions = {"sqlalchemy": "2.0.54", "ruff": "0.16.7", "mypy": "2.3.1", package: version}
    monkeypatch.setattr(vs01, "installed_version", _installed(versions, []))

    with pytest.raises(EnvironmentRefused) as refused:
        vs01.check_environment(True, DECLARED)

    assert str(refused.value) == message


def test_an_undeclared_package_is_refused_rather_than_accepted(monkeypatch):
    monkeypatch.setattr(vs01, "installed_version", _installed({"sqlalchemy": "2.0.54"}, []))

    with pytest.raises(EnvironmentRefused,
                       match="pyproject.toml declares no version specifier for sqlalchemy"):
        vs01.check_environment(False, {"sqlalchemy": ""})


def test_a_missing_package_is_refused_by_name():
    with pytest.raises(EnvironmentRefused, match="no-such-package-vs01 is not installed"):
        vs01.installed_version("no-such-package-vs01")


def test_the_installed_environment_satisfies_the_declared_one():
    versions = vs01.check_environment(True)

    assert set(versions) == {"sqlalchemy", "ruff", "mypy"}


# ---------------------------------------------------------------------------
# The command line and every exit-2 path
# ---------------------------------------------------------------------------


def test_the_defaults_and_the_options():
    args = vs01.parse_args([])

    assert (args.with_tests, args.timeout) == (False, 180.0)
    assert {name for name, _ in args._get_kwargs()} == {"with_tests", "timeout"}
    overridden = vs01.parse_args(["--with-tests", "--timeout", "5"])
    assert (overridden.with_tests, overridden.timeout) == (True, 5.0)


@pytest.mark.parametrize("argv", [["--base-url", "http://localhost:8000"], ["--drop-database"],
                                  ["--timeout", "soon"]])
def test_an_unknown_or_malformed_option_exits_two(argv, capsys):
    with pytest.raises(SystemExit) as exited:
        vs01.parse_args(argv)

    assert exited.value.code == 2


class Refuse:
    """Stands in for every environment step; any call fails the test."""

    def __init__(self, monkeypatch, *names: str) -> None:
        for name in names:
            monkeypatch.setattr(vs01, name, self._refuse(name))

    @staticmethod
    def _refuse(name: str):
        def refuse(*args: object, **kwargs: object) -> None:
            raise AssertionError(f"{name} must not be reached")
        return refuse


ENVIRONMENT_STEPS = ("recreate_database", "migrate_to_head", "serving", "run_scenario",
                     "create_engine")


@pytest.mark.parametrize("argv", [["--timeout", "0"], ["--timeout", "-1"]])
def test_an_invalid_timeout_exits_two_before_anything_starts(argv, monkeypatch, capsys):
    Refuse(monkeypatch, "check_environment", *ENVIRONMENT_STEPS)

    assert vs01.main(argv) == 2
    assert "--timeout must be greater than zero" in capsys.readouterr().err


def test_invalid_logging_settings_exit_two_before_anything_starts(monkeypatch, capsys):
    Refuse(monkeypatch, "check_environment", *ENVIRONMENT_STEPS)
    monkeypatch.setattr(vs01, "get_settings", lambda: SimpleNamespace(
        app_log_level="LOUD", log_format="json", effective_database_url="postgresql:///x"))

    assert vs01.main([]) == 2
    assert "invalid logging settings" in capsys.readouterr().err


def test_an_environment_mismatch_exits_two_naming_the_package(monkeypatch, capsys):
    Refuse(monkeypatch, *ENVIRONMENT_STEPS)
    monkeypatch.setattr(vs01, "installed_version", _installed({"sqlalchemy": "2.1.0"}, []))

    assert vs01.main([]) == 2
    err = capsys.readouterr().err
    assert "sqlalchemy 2.1.0 is installed, but pyproject.toml declares sqlalchemy>=2.0.0,<2.1" in err


def test_with_tests_checks_the_tools_before_anything_starts(monkeypatch, capsys):
    Refuse(monkeypatch, *ENVIRONMENT_STEPS)
    monkeypatch.setattr(vs01, "installed_version", _installed(
        {"sqlalchemy": "2.0.54", "ruff": "0.16.8", "mypy": "2.3.1"}, []))

    assert vs01.main(["--with-tests"]) == 2
    assert "ruff 0.16.8 is installed" in capsys.readouterr().err


# -- The database-name guard ------------------------------------------------


@pytest.mark.parametrize("configured, expected", [
    ("ai_ceo_layer1", "ai_ceo_layer1_vs01"),
    ("demo", "demo_vs01"),
])
def test_the_acceptance_database_is_the_configured_name_plus_vs01(configured, expected):
    url = vs01.acceptance_url(f"postgresql://user:pw@db.example.invalid:5433/{configured}")

    assert url.database == expected
    assert (url.host, url.port, url.username) == ("db.example.invalid", 5433, "user")


@pytest.mark.parametrize("name, configured", [
    ("Demo_vs01", "Demo"),
    ("ai-ceo_vs01", "ai-ceo"),
    ("1db_vs01", "1db"),
    ("ai_ceo_vs01", "ai_ceo_vs01"),
    ("ai_ceo_test", "ai_ceo"),
    ("ai_ceo_vs01_test", "ai_ceo_vs01"),
    ("ai_ceo", "ai_ceo"),
    (None, None),
])
def test_the_guard_refuses_every_name_it_does_not_admit(name, configured):
    with pytest.raises(EnvironmentRefused, match="refusing acceptance database"):
        vs01.check_acceptance_name(name, configured)


def test_the_guard_admits_a_derived_name():
    assert vs01.check_acceptance_name("ai_ceo_layer1_vs01", "ai_ceo_layer1") == "ai_ceo_layer1_vs01"


@pytest.mark.parametrize("configured_url", [
    "postgresql://user:pw@localhost:5432",
    "postgresql://user:pw@localhost:5432/Upper",
    "postgresql://user:pw@localhost:5432/with-dash",
])
def test_a_configured_database_the_guard_refuses_exits_two(configured_url, monkeypatch, capsys):
    Refuse(monkeypatch, *ENVIRONMENT_STEPS)
    monkeypatch.setattr(vs01, "get_settings", lambda: SimpleNamespace(
        app_log_level="INFO", log_format="json", effective_database_url=configured_url))

    assert vs01.main([]) == 2
    assert "refusing acceptance database" in capsys.readouterr().err


# -- Isolation (R-M9-1) -----------------------------------------------------


def test_an_unreachable_postgresql_exits_two_through_the_maintenance_database(monkeypatch, capsys):
    engines: list[str | None] = []
    real = vs01.create_engine

    def recording(url, **kwargs):
        engines.append(make_url(url).database)
        return real(make_url(url).set(host="127.0.0.1", port=1),
                    connect_args={"connect_timeout": 1}, **kwargs)

    Refuse(monkeypatch, "migrate_to_head", "serving", "run_scenario")
    monkeypatch.setattr(vs01, "create_engine", recording)

    assert vs01.main([]) == 2
    assert engines == ["postgres"]
    err = capsys.readouterr().err
    assert "could not be recreated through the postgres maintenance database" in err
    assert "OperationalError" in err


def test_recreate_refuses_an_unreachable_server():
    url = make_url("postgresql://nobody:nobody@127.0.0.1:1/absent_vs01?connect_timeout=1")

    with pytest.raises(EnvironmentRefused, match=r"\(OperationalError\); is PostgreSQL reachable"):
        vs01.recreate_database(url)


class Environment:
    """Records every step main takes, and fails the one a test names."""

    def __init__(self, monkeypatch, fail: str | None = None) -> None:
        self.fail = fail
        self.events: list[tuple[str, Any]] = []
        for name in ("recreate_database", "migrate_to_head"):
            monkeypatch.setattr(vs01, name, self._step(name))
        monkeypatch.setattr(vs01, "serving", self.serving)
        monkeypatch.setattr(vs01, "create_engine", self.create_engine)
        monkeypatch.setattr(vs01, "run_scenario", self.run_scenario)
        monkeypatch.setattr(vs01.httpx, "Client", self.client)

    def _step(self, name: str):
        def step(url):
            self.events.append((name, url.database))
            if self.fail == name:
                raise EnvironmentRefused(f"{name} failed")
        return step

    def create_engine(self, url, **kwargs):
        self.events.append(("create_engine", make_url(url).database))
        return SimpleNamespace(dispose=lambda: self.events.append(("dispose", None)))

    @contextmanager
    def serving(self, application, timeout):
        self.events.append(("serving", timeout))
        if self.fail == "serving":
            raise EnvironmentRefused("the application did not report itself started within "
                                     f"{timeout:g} seconds")
        yield "http://127.0.0.1:49152"

    @contextmanager
    def client(self, *, base_url, timeout):
        self.events.append(("client", base_url))
        yield SimpleNamespace(base_url=base_url)

    def run_scenario(self, client, sessions, **kwargs):
        self.events.append(("run_scenario", (client.base_url, sessions.kw["bind"] is not None)))
        return Report((Check("A27.1", "clean_dataset", Outcome.PASS, "ok"),))


@pytest.mark.parametrize("fail", ["recreate_database", "migrate_to_head", "serving"])
def test_each_way_the_environment_can_fail_exits_two_before_any_check(fail, monkeypatch, capsys):
    environment = Environment(monkeypatch, fail=fail)

    assert vs01.main([]) == 2
    assert "run_scenario" not in [name for name, _ in environment.events]
    assert f"vs01_acceptance: {fail if fail != 'serving' else 'the application'}" in (
        capsys.readouterr().err)


def test_main_uses_only_the_acceptance_database_and_its_own_loopback_server(monkeypatch, capsys):
    environment = Environment(monkeypatch)
    configured = vs01.get_settings().effective_database_url
    acceptance = f"{make_url(configured).database}_vs01"

    assert vs01.main(["--timeout", "7"]) == 0
    assert environment.events == [
        ("recreate_database", acceptance),
        ("migrate_to_head", acceptance),
        ("create_engine", acceptance),
        ("serving", 7.0),
        ("client", "http://127.0.0.1:49152"),
        ("run_scenario", ("http://127.0.0.1:49152", True)),
        ("dispose", None),
    ]
    assert capsys.readouterr().out.endswith("verify-vs01: 1 passed, 0 failed, 0 skipped, "
                                            "0 operator\n")


def test_the_development_database_is_never_named_to_an_engine(monkeypatch):
    environment = Environment(monkeypatch)
    configured = make_url(vs01.get_settings().effective_database_url).database

    vs01.main([])

    assert configured not in [value for name, value in environment.events
                              if name in {"recreate_database", "migrate_to_head", "create_engine"}]


def test_the_migration_names_the_acceptance_database_only_while_it_runs(monkeypatch):
    seen: list[str | None] = []
    monkeypatch.setattr(vs01.command, "upgrade", lambda config, revision: seen.append(
        vs01.os.environ.get("DATABASE_URL")))
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/dev")
    url = make_url("postgresql://u:p@localhost/dev_vs01")

    vs01.migrate_to_head(url)

    assert seen == ["postgresql://u:p@localhost/dev_vs01"]
    assert vs01.os.environ["DATABASE_URL"] == "postgresql://u:p@localhost/dev"


def test_a_failed_migration_is_refused_and_restores_an_unset_url(monkeypatch):
    def fail(config, revision):
        raise OperationalError("upgrade", {}, Exception("down"))

    monkeypatch.setattr(vs01.command, "upgrade", fail)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(EnvironmentRefused, match=r"could not be migrated to head \(OperationalError\)"):
        vs01.migrate_to_head(make_url("postgresql://u:p@localhost/dev_vs01"))
    assert "DATABASE_URL" not in vs01.os.environ


def test_the_loopback_socket_is_bound_at_an_os_assigned_port():
    sock = vs01.bind_loopback()
    try:
        host, port = sock.getsockname()[:2]
    finally:
        sock.close()

    assert host == "127.0.0.1" and port > 0


def test_a_socket_that_cannot_be_bound_is_refused(monkeypatch):
    # TEST-NET-1 is never an address of this host, so the bind fails for real.
    monkeypatch.setattr(vs01, "LOOPBACK", "192.0.2.1")

    with pytest.raises(EnvironmentRefused, match=r"could not be bound \(OSError\)"):
        vs01.bind_loopback()


def _lifespan_app(startup):
    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            message = await receive()
            if message["type"] == "lifespan.startup":
                ok = await startup()
                await send({"type": "lifespan.startup.complete" if ok
                            else "lifespan.startup.failed"})
            message = await receive()
            await send({"type": "lifespan.shutdown.complete"})
            return
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"served"})
    return app


def test_serving_answers_on_the_loopback_socket_and_stops_afterwards():
    async def ready() -> bool:
        return True

    with vs01.serving(_lifespan_app(ready), 10) as base_url:
        url = httpx.URL(base_url)
        assert url.host == "127.0.0.1" and url.port and url.port > 0
        with httpx.Client(base_url=base_url, timeout=5) as client:
            assert client.get("/").text == "served"

    with pytest.raises(httpx.ConnectError), httpx.Client(base_url=base_url, timeout=1) as client:
        client.get("/")


def test_a_server_that_does_not_start_within_the_timeout_is_refused():
    async def slow() -> bool:
        await asyncio.Event().wait()  # never completes: the thread is a daemon
        return True

    with pytest.raises(EnvironmentRefused, match="did not report itself started within 0.2 "
                                                 "seconds"), vs01.serving(_lifespan_app(slow), 0.2):
        pass


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_server_whose_startup_fails_is_refused():
    async def failing() -> bool:
        return False

    with pytest.raises(EnvironmentRefused, match="did not report itself started"), \
            vs01.serving(_lifespan_app(failing), 10):
        pass


def test_the_served_application_has_csv_demo_alone_over_the_committed_demo_data(monkeypatch):
    built: list[tuple[str, Any]] = []
    monkeypatch.setattr(vs01, "build_connector",
                        lambda source, **kwargs: built.append((source, kwargs)) or object())

    application = vs01.build_app(sessionmaker_stub())
    provider = application.state.connectors

    assert provider.source_names == ("csv_demo",)
    provider.get("csv_demo")
    assert built == [("csv_demo", {"data_directory": vs01.DEMO_DIR})]


def sessionmaker_stub():
    from sqlalchemy.orm import sessionmaker

    return sessionmaker()
