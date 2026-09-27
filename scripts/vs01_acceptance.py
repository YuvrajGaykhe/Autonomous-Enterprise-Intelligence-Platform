"""
VS-01 acceptance scenario (plan §A27, §A28; specified in §0.8.4 and §0.8.5).

    python scripts/vs01_acceptance.py                    (make verify-vs01)
    python scripts/vs01_acceptance.py --with-tests       (make verify-vs01 ARGS="--with-tests")

Runs every §A27 criterion as a named check, each with a pass condition and one
line of observed evidence, in scripts/verify_layer1.py's Check/Outcome/Report
style. The checks run in §0.8.5's order: A27.1, A27.1b, A27.2 ... A27.6, A27.9,
A27.8, A27.7, A27.10, A28.citations. A27.9 decides on the brief before A27.8
changes the snapshot, and A27.8 is the last check that writes anything.

**Its own environment, never the development one (R-M9-1).** The command
reads only the PostgreSQL server's address and credentials from the settings
(DATABASE_URL or POSTGRES_*). It drops and recreates <configured database>_vs01
through the server's "postgres" maintenance database, migrates it to the one
head, and serves the real application (app.main.create_app, csv_demo over
data/demo) from an in-process uvicorn server on a loopback socket whose port
the operating system assigns. Every HTTP observation goes to that socket. It
never opens, migrates, seeds or reads the development database, never
contacts another address, starts no container and needs no fixed port. If
that environment cannot start, it exits 2 before any check runs, and it never
falls back to the development stack or database. Importing app.main builds
that module's default application, whose engine is never connected; the
command neither serves nor calls it.

The acceptance database is left in place for inspection, and the next run
replaces it. After A27.8 its snapshot is no longer the clean one, so it is
disposable: nothing uses it as the basis of another acceptance run.

**The pinned run (K1).** A27.1b and A27.8 call Layer 2's assessment run in
process, and every call carries an expected fingerprint: the configured pin,
or A27.1b's and A27.8's deliberate refusals. There is no unpinned fallback. The
one unpinned assessment is A27.8's last step, the published M8 route, which
runs only after the pinned gate has refused the changed snapshot.

**The declared environment (R-M9-3).** Before anything starts, the installed
SQLAlchemy (and, under --with-tests, ruff and mypy) must satisfy the
specifiers pyproject.toml declares; otherwise the command exits 2. The
specifiers are read from pyproject.toml, never copied here.

Exit status:
    0  no executed check failed (SKIPPED and OPERATOR do not fail)
    1  at least one check failed
    2  the scenario could not run: invalid arguments or logging settings, an
       installed version outside pyproject.toml's specifiers, a database name
       the guard refuses, an unreachable PostgreSQL, a failed recreation or
       migration, or a server that did not start

The report goes to stdout and is deterministic: its evidence carries counts,
source ids, hashes, versions and fixed names only, never a UUID, a
timestamp, a duration, a port or a machine-specific path. The run's log
events go to stderr as configured by APP_LOG_LEVEL and LOG_FORMAT
(app.core.logging).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import tomllib
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from importlib import metadata
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import create_engine, delete, func, select, text, update  # noqa: E402
from sqlalchemy.engine import URL, make_url  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

# Registers every table on Base.metadata, for the row counts.
import app.persistence.models  # noqa: E402, F401
from app.api.connectors import ConnectorProvider  # noqa: E402
from app.connectors.registry import build_connector  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.core.logging import configured_logging, resolve_format, resolve_level  # noqa: E402
from app.decisions.assessment import run_assessment  # noqa: E402
from app.ingestion.orchestrator import IngestionRequest, run_ingestion  # noqa: E402
from app.intelligence import FingerprintMismatchError, default_risk_rules  # noqa: E402
from app.main import create_app  # noqa: E402

__all__ = ["Check", "Outcome", "Report", "Scenario", "main", "parse_args", "run_scenario"]

API = "/api/v1"
INGESTION_RUNS = f"{API}/ingestion/runs"
ASSESSMENTS = f"{API}/risk/assessments"
BRIEFS = f"{API}/risk/briefs"
DECISION = BRIEFS + "/{brief_id}/decision"
DECISIONS = BRIEFS + "/{brief_id}/decisions"
DEFAULT_TIMEOUT = 180.0
PAGE_LIMIT = 500

SOURCE_SYSTEM = "csv_demo"
DEMO_DIR = PROJECT_ROOT / "data" / "demo"
GOLDEN = PROJECT_ROOT / "tests" / "golden" / "vs01_cust007_brief.txt"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
#: A27.8's snapshot change: the unresolved_ticket delta of the fixture package
#: (plan §0.8.7), ingested with an entities filter naming the one file it adds to.
UNRESOLVED_TICKET_DIR = PROJECT_ROOT / "tests" / "fixtures" / "vs01" / "unresolved_ticket"
UNRESOLVED_TICKET_ENTITIES = ("support_tickets",)

#: The acceptance database is <configured database>_vs01 (§0.8.4, A5).
ACCEPTANCE_SUFFIX = "_vs01"
ACCEPTANCE_DATABASE = re.compile(r"[a-z][a-z0-9_]*_vs01")
MAINTENANCE_DATABASE = "postgres"
LOOPBACK = "127.0.0.1"

#: The packages the environment check always compares with pyproject.toml, and
#: the two it compares only under --with-tests, because only A27.10 runs them.
ALWAYS_CHECKED = ("sqlalchemy",)
CHECKED_WITH_TESTS = ("ruff", "mypy")

#: A27.1b's deliberate mismatch. It is not a fingerprint any snapshot has.
MISMATCH = "0" * 64
#: A27.9's asserted, unauthenticated approver (§0.7.17).
ACTOR = "verify-vs01"
#: The append-only trigger's SQLSTATE and message (§0.7.5).
APPEND_ONLY_SQLSTATE = "23001"
APPEND_ONLY_MESSAGE = "brief_decisions is append-only"

#: The single migration head (§0.8.13) and the regression baselines of
#: A27.10 (§0.8.14). ruff's and mypy's are baseline finding counts measured
#: with the pinned versions: a no-regression gate, not an acceptance of them.
EXPECTED_HEAD = "070e4968a497"
RUFF_FINDINGS = 69
MYPY_ERRORS = 9
SECRET_FINDINGS = 0

#: §A28's clean full-dataset path (§A27.1).
ENTITY_TYPES = ("organizations", "employees", "customers", "deals",
                "projects", "support_tickets", "documents")
CANONICAL_COUNTS = {"organizations": 1, "employees": 24, "customers": 50, "deals": 44,
                    "projects": 22, "support_tickets": 80, "documents": 12}
DEMO_ROWS = 233
CUSTOMERS = 50
BRIEFS_EXPECTED = 3

MERIDIAN = "CUST-007"
#: M7's measured payload hash for CUST-007's brief (§0.7.13).
MERIDIAN_HASH = "e93c29cfb6094284d7ea6fe84bf966ad0b40995fccdc4e2a671b502a7f16c946"
MERIDIAN_CITATIONS = 36
#: The golden narrative's project-absence line (DR24).
PROJECT_ABSENCE_LINE = "Active projects (S13): none. CUST-007 has no active project."

#: §0.6.13.3's three cited-span targets: document, [start, end) and phrase.
CITED_SPANS = {
    "DOC_003_ESCALATION_RULE": ("DOC-003", 238, 330, "Customers raising three or more tickets "
                                "within 14 days are escalated to their account owner."),
    "DOC_006_TERM_AND_NOTICE": ("DOC-006", 153, 238, "Term: 36 months, renewing annually unless "
                                "either party gives 90 days' written notice."),
    "DOC_009_DEAL_LINKAGE": ("DOC-009", 238, 333, "The customer tied the Meridian Textiles - Seat "
                             "Expansion decision (DEAL-001) to resolving them."),
}
#: The two citations §A28 has a human verify (A12).
HAND_CITATIONS = ("DOC_003_ESCALATION_RULE", "DOC_009_DEAL_LINKAGE")

#: §0.6.9's DR21 fields: a cited field a brief states or derives from must hold a value.
NON_NULL_FIELDS = frozenset({("documents", "body_text"), ("support_tickets", "created_at"),
                             ("deals", "amount"), ("deals", "currency")})

#: The only non-GET requests the command sends: the three writes of §0.7.14.
WRITES = frozenset({("POST", INGESTION_RUNS), ("POST", ASSESSMENTS), ("POST", DECISION)})
#: The six risk operations of §0.7.8.
RISK_OPERATIONS = frozenset({
    ("POST", ASSESSMENTS), ("GET", ASSESSMENTS), ("GET", ASSESSMENTS + "/{assessment_id}"),
    ("GET", BRIEFS + "/{brief_id}"), ("POST", DECISION), ("GET", DECISIONS),
})

#: The §A25 proof corpus (§0.8.6), in its order. A node id without a parameter
#: selects every parametrisation; A25_PROOF_COUNT is the corpus's collected size.
#: Phase 5 added test 10's third node: no mapped test asserted that the four
#: inactive customers are among the fifteen ticketless ones.
A25_PROOFS = (
    # 1 Single-escalation
    "tests/integration/test_m3_signals.py::test_meridian_is_the_only_escalated_customer_in_the_whole_dataset",
    "tests/integration/test_m3_signals.py::test_meridian_is_the_only_critical_customer_in_the_whole_dataset",
    # 2 Conflict
    "tests/integration/test_m6_reconciliation.py::test_the_corpus_holds_exactly_one_conflict_and_no_customer_raises",
    "tests/unit/test_m6_reconciler.py::test_the_dissent_is_the_accelerate_position_whole_with_its_own_citations",
    "tests/integration/test_m7_assessment.py::test_the_golden_brief_states_the_absence_the_conflict_the_policy_and_the_dissent",
    # 3 Conflict-policy liveness
    "tests/integration/test_m6_reconciliation.py::test_flipping_resolve_to_flips_the_outcome_on_the_real_data",
    "tests/unit/test_m6_policy.py::test_flipping_resolve_to_changes_the_winner_and_nothing_else",
    # 4 DOC-005 leave-out (the test §A28's `pytest -k doc005_leave_out` selects)
    "tests/integration/test_m7_assessment.py::test_doc005_leave_out_changes_no_band_signal_escalation_or_resolution",
    # 5 Amount invariance
    "tests/integration/test_m3_signals.py::test_multiplying_every_deal_amount_by_a_thousand_changes_no_band_and_no_order",
    "tests/integration/test_m6_reconciliation.py::test_multiplying_every_amount_by_a_thousand_changes_nothing",
    # 6 Chronic backlog
    "tests/integration/test_m3_signals.py::test_a_backlog_account_does_not_outrank_meridian",
    "tests/integration/test_m3_signals.py::test_a_backlog_account_reports_its_stale_ticket_without_escalating",
    "tests/unit/test_m3_bands.py::test_an_escalated_customer_outranks_a_chronically_backlogged_one",
    # 7 Substring safety
    "tests/integration/test_m4_evidence.py::test_the_other_forty_seven_customers_acquire_no_link",
    "tests/unit/test_m4_linker.py::test_one_customer_never_matches_another_that_shares_a_name_token",
    # 8 Citation resolution
    "tests/integration/test_m7_assessment.py::test_every_citation_of_every_brief_resolves",
    "tests/integration/test_m7_assessment.py::test_every_citation_of_every_assessment_resolves",
    # 9 Scope leakage
    "tests/integration/test_m7_assessment.py::test_no_brief_holds_another_customers_identifiers",
    # 10 Negative cases
    "tests/integration/test_m3_signals.py::test_all_fifteen_ticketless_customers_band_none",
    "tests/integration/test_m6_reconciliation.py::test_only_cust_007_is_executive_worthy",
    "tests/integration/test_vs01_a25_closure.py::test_the_four_inactive_customers_are_ticketless_and_yield_none_not_worthy",
    # 11 Rule liveness
    "tests/integration/test_m3_signals.py::test_raising_doc_003s_threshold_from_three_to_six_de_escalates_meridian",
    # 12 Determinism
    "tests/integration/test_m7_assessment.py::test_the_hash_is_identical_in_another_process",
    "tests/integration/test_m7_assessment.py::test_an_identical_re_run_reads_everything_back_and_inserts_nothing",
    # 13 Fingerprint: content and count
    "tests/integration/test_m7_assessment.py::test_a_synthetic_ticket_mints_new_assessments_on_own_stamp_links_only",
    "tests/integration/test_m1_scope.py::test_adding_a_record_changes_the_fingerprint",
    # 13b Fingerprint: identity
    "tests/integration/test_m1_scope.py::test_a_source_id_rename_that_preserves_sort_position_changes_the_fingerprint",
    # 14 Multi-currency
    "tests/integration/test_m3_signals.py::test_a_multi_currency_customer_reports_every_currency_and_totals_none_of_them",
    "tests/integration/test_m3_signals.py::test_two_currencies_of_one_customer_cannot_be_added_together",
    "tests/integration/test_m5_contexts.py::test_a_two_currency_customer_renders_both_in_the_commercial_context",
    "tests/integration/test_m5_contexts.py::test_summing_two_currencies_raises_rather_than_inventing_a_rate",
)
A25_PROOF_COUNT = 44

#: The fixed argument lists of every subprocess (§0.8.4); none uses a shell.
PYTEST = (sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=")
PROOF_COMMAND = (*PYTEST, *A25_PROOFS)
SUITE_COMMAND = (*PYTEST, "--cov=app", "--cov-report=term")
RUFF_COMMAND = (sys.executable, "-m", "ruff", "check", "app/", "tests/", "scripts/")
MYPY_COMMAND = (sys.executable, "-m", "mypy", "app/")
SECRET_SCAN_COMMAND = (sys.executable, "scripts/secret_scan.py")
REGRESSION_COMMANDS = (SUITE_COMMAND, RUFF_COMMAND, MYPY_COMMAND, SECRET_SCAN_COMMAND)

# §0.6.15 criterion 15a: CUST-007's support and commercial evidence, restated
# from the plan rather than read from the module that builds it.


def _ticket(ticket_id: str, created: str, priority: str, category: str,
            is_open: bool) -> dict[str, Any]:
    return {"id": ticket_id, "created_date": created, "priority": priority,
            "category": category, "is_open": is_open, "breaches_sla": True,
            "evidence": [_fact("support_tickets", ticket_id, field)
                         for field in ("created_at", "priority", "category", "resolved_at")]}


def _fact(entity: str, source_id: str, field: str) -> dict[str, Any]:
    return {"kind": "CANONICAL_FACT",
            "citation": {"kind": "record", "entity": entity, "id": source_id, "field": field}}


MERIDIAN_TICKETS = [
    _ticket("TKT-073", "2026-08-18", "high", "performance", False),
    _ticket("TKT-075", "2026-08-20", "high", "performance", True),
    _ticket("TKT-076", "2026-08-23", "high", "integration", True),
    _ticket("TKT-079", "2026-08-25", "medium", "billing", True),
    _ticket("TKT-080", "2026-08-27", "high", "performance", True),
]
ALL_FIVE = ["TKT-073", "TKT-075", "TKT-076", "TKT-079", "TKT-080"]
OPEN_HIGH = ["TKT-075", "TKT-076", "TKT-080"]
MERIDIAN_WINDOW = {"start": "2026-08-18", "end": "2026-08-31", "count": 5}
MERIDIAN_SPAN = {
    "ticket_ids": ALL_FIVE, "ticket_count": 5, "first_ticket_date": "2026-08-18",
    "last_ticket_date": "2026-08-27", "ticket_span_days": 9,
    "rule": "tickets where escalation_window.start <= created_date <= escalation_window.end; "
            "ticket_span_days = (last_ticket_date - first_ticket_date).days",
}
MERIDIAN_DERIVATIONS = [
    {"fact": "open_ticket_count", "value": 4, "rule": "count of tickets where is_open",
     "ticket_ids": ["TKT-075", "TKT-076", "TKT-079", "TKT-080"]},
    {"fact": "open_high_priority_count", "value": 3,
     "rule": "count of tickets where is_open and priority == 'high'", "ticket_ids": OPEN_HIGH},
    {"fact": "high_priority_total", "value": 4, "rule": "count of tickets where priority == 'high'",
     "ticket_ids": ["TKT-073", "TKT-075", "TKT-076", "TKT-080"]},
    {"fact": "open_sla_breach_high_count", "value": 3,
     "rule": "count of tickets where is_open and priority == 'high' and breaches_sla",
     "ticket_ids": OPEN_HIGH},
    {"fact": "dominant_ticket_category", "value": "performance",
     "rule": "most frequent category among tickets where category is neither null nor empty "
             "and lookback.start <= created_date <= lookback.end; ties go to the smallest "
             "category name in code-point order",
     "lookback": {"start": "2026-06-21", "end": "2026-09-18"},
     "category_counts": {"billing": 1, "integration": 1, "performance": 3},
     "ticket_ids": ALL_FIVE},
]
MERIDIAN_PATH = {"customer": MERIDIAN, "account_owner": "EMP-007",
                 "account_owner_manager": "EMP-002",
                 "assignees": ["EMP-017", "EMP-018", "EMP-020", "EMP-021"],
                 "assignee_managers": ["EMP-004"],
                 "open_tickets": ["TKT-075", "TKT-076", "TKT-079", "TKT-080"]}
MERIDIAN_COMMERCIAL = {"deals": [{
    "id": "DEAL-001", "stage": "negotiation", "probability": "90",
    "amount": {"amount": "5361.44", "currency": "USD"},
    "evidence": [_fact("deals", "DEAL-001", field)
                 for field in ("is_active", "stage", "probability", "amount", "currency")],
}]}
MERIDIAN_CITED_SPANS = [
    {"target": target, "citation": {"kind": "document", "document_id": document,
                                    "start": start, "end": end}}
    for target, (document, start, end, _) in sorted(CITED_SPANS.items())
]
#: §A27.5: the one conflict, its policy, the winner and the dissent's citations.
CONFLICT_OBJECT = "DEAL-001"
CONFLICT_ACTIONS = ["ACCELERATE_DEAL_CLOSE", "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED"]
CONFLICT_POLICY = "CONF-001"
POLICY_VERSION = 1
WINNING_ACTION = "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED"
DISSENT_ACTION = "ACCELERATE_DEAL_CLOSE"
DISSENT_CITATIONS = [_fact("deals", "DEAL-001", field)
                     for field in ("is_active", "stage", "probability")]
DISSENT_HEADING = "6. RECORDED DISSENT"
CONFLICT_LINES = (
    "- Conflict over DEAL-001:",
    "  Resolved by policy CONF-001 (policy version 1): PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED "
    "prevails, as SUPPORT proposed",
    "- Overruled by CONF-001: SALES ADVANCE ACCELERATE_DEAL_CLOSE on DEAL-001",
)


class Outcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    OPERATOR = "OPERATOR"


class CheckFailed(Exception):
    """One acceptance check did not hold; the scenario continues."""


class EnvironmentRefused(Exception):
    """The acceptance environment cannot be used or started (exit status 2)."""


def require(condition: object, message: str) -> None:
    """Fail the current check unless condition holds."""
    if not condition:
        raise CheckFailed(message)


@dataclass(frozen=True)
class Check:
    """One acceptance check: its §A27 label, its name, its outcome and what was observed."""

    label: str
    name: str
    outcome: Outcome
    detail: str

    def __str__(self) -> str:
        return (f"verify-vs01: {self.label:<13} {self.name:<20} "
                f"{self.outcome.value:<9} {self.detail}")


@dataclass(frozen=True)
class Report:
    """Every check the scenario produced, in the order it produced them."""

    checks: tuple[Check, ...]

    def count(self, outcome: Outcome) -> int:
        return sum(1 for check in self.checks if check.outcome is outcome)

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(check for check in self.checks if check.outcome is Outcome.FAIL)

    @property
    def exit_code(self) -> int:
        return 1 if self.failures else 0

    def summary(self) -> str:
        return (f"verify-vs01: {self.count(Outcome.PASS)} passed, "
                f"{self.count(Outcome.FAIL)} failed, {self.count(Outcome.SKIPPED)} skipped, "
                f"{self.count(Outcome.OPERATOR)} operator")


# ---------------------------------------------------------------------------
# Subprocesses (A27.7 and A27.10): fixed argument lists, never a shell
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandResult:
    """A finished command's exit status and standard output."""

    returncode: int
    stdout: str


Runner = Callable[[tuple[str, ...]], CommandResult]


def run_command(argv: tuple[str, ...]) -> CommandResult:
    """Run one of the fixed argument lists from the repository root."""
    completed = subprocess.run(list(argv), cwd=PROJECT_ROOT, capture_output=True, text=True,
                               check=False)
    return CommandResult(completed.returncode, completed.stdout)


PYTEST_OUTCOMES = re.compile(
    r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|deselected)\b")


def pytest_outcomes(stdout: str) -> dict[str, int]:
    """The outcome counts of pytest's summary line: its last line naming one."""
    for line in reversed(stdout.splitlines()):
        found = PYTEST_OUTCOMES.findall(line)
        if found:
            counts = {name.rstrip("s") if name.startswith("error") else name: int(count)
                      for count, name in found}
            return counts
    return {}


def _pytest_summary(result: CommandResult, expected: int | None) -> int:
    """The passed count of a pytest run that exited 0 with nothing failed or skipped."""
    outcomes = pytest_outcomes(result.stdout)
    require(outcomes, f"pytest exited {result.returncode} with no summary line")
    problems = {name: count for name, count in outcomes.items()
                if name != "passed" and count}
    require(result.returncode == 0 and not problems,
            f"pytest exited {result.returncode}: "
            + ", ".join(f"{count} {name}" for name, count in sorted(
                {**problems, "passed": outcomes.get("passed", 0)}.items())))
    passed = outcomes.get("passed", 0)
    if expected is not None:
        require(passed == expected, f"{passed} passed, but the corpus collects {expected}")
    return passed


COVERAGE_TOTAL = re.compile(r"^TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%", re.MULTILINE)
RUFF_FOUND = re.compile(r"Found (\d+) errors?")
MYPY_FOUND = re.compile(r"Found (\d+) errors? in")
SECRET_SCAN_FOUND = re.compile(r"secret-scan: \d+ files scanned, \d+ binary files skipped, "
                               r"(\d+) findings")


# ---------------------------------------------------------------------------
# The declared environment (R-M9-3)
# ---------------------------------------------------------------------------


REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*([^;]*?)\s*(?:;.*)?$")
CLAUSE = re.compile(r"^\s*(==|!=|<=|>=|<|>)\s*(\d+(?:\.\d+)*)\s*$")
RELEASE = re.compile(r"^\d+(?:\.\d+)*$")


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def declared_specifiers(path: Path = PYPROJECT) -> dict[str, str]:
    """Every requirement pyproject.toml declares, runtime and optional, by package name."""
    project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
    requirements = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    declared = {}
    for requirement in requirements:
        match = REQUIREMENT.match(requirement)
        if match is not None:
            declared[normalized(match.group(1))] = match.group(2)
    return declared


def _release(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def satisfies(version: str, specifier: str) -> bool:
    """Whether a plain release version satisfies every clause of a specifier.

    Raises:
        EnvironmentRefused: the version or a clause is not one this check can compare.
    """
    if not RELEASE.match(version):
        raise EnvironmentRefused(f"installed version {version!r} is not a plain release")
    clauses = [CLAUSE.match(clause) for clause in specifier.split(",")]
    if not specifier or any(clause is None for clause in clauses):
        raise EnvironmentRefused(f"specifier {specifier!r} is not one this check can compare")
    installed = _release(version)
    for clause in clauses:
        assert clause is not None
        operator, bound = clause.group(1), _release(clause.group(2))
        width = max(len(installed), len(bound))
        left = installed + (0,) * (width - len(installed))
        right = bound + (0,) * (width - len(bound))
        holds = {"==": left == right, "!=": left != right, "<=": left <= right,
                 ">=": left >= right, "<": left < right, ">": left > right}[operator]
        if not holds:
            return False
    return True


def installed_version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        raise EnvironmentRefused(f"{package} is not installed in {sys.executable}") from None


def check_environment(with_tests: bool, declared: Mapping[str, str] | None = None,
                      ) -> dict[str, str]:
    """The installed versions of the checked packages, each within its declared specifier.

    Raises:
        EnvironmentRefused: a package is undeclared, missing or outside its specifier.
    """
    specifiers = declared_specifiers() if declared is None else declared
    packages = ALWAYS_CHECKED + (CHECKED_WITH_TESTS if with_tests else ())
    versions = {}
    for package in packages:
        specifier = specifiers.get(package, "")
        if not specifier:
            raise EnvironmentRefused(f"pyproject.toml declares no version specifier for {package}")
        version = installed_version(package)
        try:
            ok = satisfies(version, specifier)
        except EnvironmentRefused as exc:
            raise EnvironmentRefused(f"{package}: {exc}") from None
        if not ok:
            raise EnvironmentRefused(f"{package} {version} is installed, but pyproject.toml "
                                     f"declares {package}{specifier}")
        versions[package] = version
    return versions


# ---------------------------------------------------------------------------
# The acceptance database and the served application (R-M9-1, A5)
# ---------------------------------------------------------------------------


def check_acceptance_name(name: str | None, configured: str | None) -> str:
    """Refuse any acceptance database name the guard does not admit (§0.8.4)."""
    if (name is None or not ACCEPTANCE_DATABASE.fullmatch(name) or name == configured
            or name.endswith("_test")):
        raise EnvironmentRefused(f"refusing acceptance database {name!r}: its name must match "
                                 f"[a-z][a-z0-9_]*{ACCEPTANCE_SUFFIX}, differ from the configured "
                                 f"database and not end in _test")
    return name


def acceptance_url(configured_url: str) -> URL:
    """<configured database>_vs01 on the configured server, with its address and credentials."""
    url = make_url(configured_url)
    configured = url.database
    name = None if configured is None else f"{configured}{ACCEPTANCE_SUFFIX}"
    return url.set(database=check_acceptance_name(name, configured))


def recreate_database(url: URL) -> None:
    """Drop and create the acceptance database through the maintenance database."""
    admin = create_engine(url.set(database=MAINTENANCE_DATABASE), isolation_level="AUTOCOMMIT")
    quoted = admin.dialect.identifier_preparer.quote(str(url.database))
    try:
        with admin.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))
            connection.execute(text(f"CREATE DATABASE {quoted}"))
    except SQLAlchemyError as exc:
        raise EnvironmentRefused(f"the acceptance database could not be recreated through the "
                                 f"{MAINTENANCE_DATABASE} maintenance database "
                                 f"({type(exc).__name__}); is PostgreSQL reachable?") from None
    finally:
        admin.dispose()


def alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    return config


def script_heads() -> tuple[str, ...]:
    """The migration history's heads, read in process through Alembic's ScriptDirectory."""
    return tuple(ScriptDirectory.from_config(alembic_config()).get_heads())


def migrate_to_head(url: URL) -> None:
    """Migrate the acceptance database to head with the committed Alembic configuration.

    migrations/env.py takes its URL from the settings, so DATABASE_URL names the
    acceptance database for the migration only, and is restored afterwards.
    """
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    try:
        command.upgrade(alembic_config(), "head")
    except Exception as exc:
        raise EnvironmentRefused(f"the acceptance database could not be migrated to head "
                                 f"({type(exc).__name__})") from None
    finally:
        if previous is None:
            del os.environ["DATABASE_URL"]
        else:
            os.environ["DATABASE_URL"] = previous


def demo_connector(source: str) -> Any:
    """csv_demo over the committed data/demo, the only source the served application has."""
    return build_connector(source, data_directory=DEMO_DIR)


def build_app(sessions: sessionmaker[Session]) -> Any:
    """The real application over the given sessions, with csv_demo as its one source."""
    return create_app(sessions=sessions,
                      connectors=ConnectorProvider(build=demo_connector,
                                                   sources=(SOURCE_SYSTEM,)))


def bind_loopback() -> socket.socket:
    """A listening-ready socket on the loopback address, at a port the OS assigns."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((LOOPBACK, 0))
    except OSError as exc:
        sock.close()
        raise EnvironmentRefused(f"the loopback socket could not be bound "
                                 f"({type(exc).__name__})") from None
    return sock


def _run_server(server: uvicorn.Server, sock: socket.socket) -> None:
    """The server thread. uvicorn exits when the application's startup fails;
    serving() reports that as a server that never started."""
    try:
        server.run(sockets=[sock])
    except SystemExit:
        pass


@contextmanager
def serving(application: Any, timeout: float) -> Iterator[str]:
    """Serve the application in process on a loopback socket; yield its base URL.

    Raises:
        EnvironmentRefused: the socket cannot be bound, or the server does not
            report itself started within timeout seconds.
    """
    sock = bind_loopback()
    host, port = sock.getsockname()[:2]
    server = uvicorn.Server(uvicorn.Config(application, log_config=None, access_log=False,
                                           lifespan="on"))
    thread = threading.Thread(target=_run_server, args=(server, sock),
                              name="verify-vs01-server", daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    try:
        if not server.started:
            raise EnvironmentRefused(f"the application did not report itself started within "
                                     f"{timeout:g} seconds")
        yield f"http://{host}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout)
        sock.close()


# ---------------------------------------------------------------------------
# Database observations (Core, over the sessions the scenario is given)
# ---------------------------------------------------------------------------


def row_counts(sessions: sessionmaker[Session]) -> dict[str, int]:
    """Every table's row count, read through Core."""
    with sessions() as session:
        return {table.name: session.scalar(select(func.count()).select_from(table)) or 0
                for table in Base.metadata.sorted_tables}


def current_heads(sessions: sessionmaker[Session]) -> tuple[str, ...]:
    """The revisions the database's Alembic version table holds."""
    with sessions() as session:
        return tuple(MigrationContext.configure(session.connection()).get_current_heads())


def _changed(before: Mapping[str, int], after: Mapping[str, int]) -> list[str]:
    return sorted(f"{name} {before.get(name)}->{after.get(name)}"
                  for name in set(before) | set(after) if before.get(name) != after.get(name))


def _citations(node: Any) -> Iterator[dict[str, Any]]:
    """Every value stored under a "citation" key, at any depth."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "citation":
                yield value
            else:
                yield from _citations(value)
    elif isinstance(node, list):
        for item in node:
            yield from _citations(item)


def _wire(citation: Mapping[str, Any]) -> str:
    return json.dumps(citation, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# The scenario
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PinnedResult:
    """One result of A27.1b's pinned run, as the assessment run returned it."""

    assessment_id: str
    created: bool
    brief_id: str | None
    payload_hash: str | None


class Scenario:
    """§A27's criteria as an ordered sequence of independent checks (§0.8.5).

    Each check reports its own outcome, so one failure hides no other. A check
    that needs an earlier check's result names that check when it fails.
    """

    def __init__(
        self,
        client: httpx.Client,
        sessions: sessionmaker[Session],
        *,
        with_tests: bool = False,
        proof_runner: Runner | None = None,
        regression_runner: Runner | None = None,
    ) -> None:
        self.client = client
        self.sessions = sessions
        self.with_tests = with_tests
        self.proof_runner = run_command if proof_runner is None else proof_runner
        self.regression_runner = run_command if regression_runner is None else regression_runner
        self.rules = default_risk_rules()
        self.pin = self.rules.pinned_fingerprint(SOURCE_SYSTEM)
        self.as_of = self.rules.acceptance_as_of
        self.state: dict[str, Any] = {}

    def checks(self) -> Iterator[Check]:
        yield self._step("A27.1", "clean_dataset", self.clean_dataset)
        yield self._step("A27.1b", "pinned_fingerprint", self.pinned_fingerprint)
        yield self._step("A27.2", "single_escalation", self.single_escalation)
        yield self._step("A27.3", "brief_facts", self.brief_facts)
        yield self._step("A27.4", "no_active_project", self.no_active_project)
        yield self._step("A27.5", "conflict_and_dissent", self.conflict_and_dissent)
        yield self._step("A27.6", "citations_resolve", self.citations_resolve)
        yield self._step("A27.9", "approval_boundary", self.approval_boundary)
        yield self._step("A27.8", "determinism", self.determinism)
        yield self._step("A27.7", "named_tests", self.named_tests)
        yield self.regression()
        yield self.hand_citations()

    @staticmethod
    def _step(label: str, name: str, check: Callable[[], str]) -> Check:
        try:
            detail = check()
        except CheckFailed as exc:
            return Check(label, name, Outcome.FAIL, str(exc))
        except Exception as exc:  # a check never crashes the report; see the class docstring
            return Check(label, name, Outcome.FAIL, f"the check raised {type(exc).__name__}")
        return Check(label, name, Outcome.PASS, detail)

    # -- HTTP ---------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return self.client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise CheckFailed(f"{method} {path} could not be reached "
                              f"({type(exc).__name__})") from None

    def _get(self, path: str, **params: object) -> Any:
        response = self._request("GET", path, params=params)
        require(response.status_code == 200,
                f"GET {path} answered {response.status_code}, not 200")
        return response.json()

    def _post(self, path: str, body: Mapping[str, Any]) -> httpx.Response:
        return self._request("POST", path, json=dict(body))

    def _canonical_counts(self) -> dict[str, int]:
        counts: dict[str, int] = self._get(f"{API}/metrics/ingestion")["totals"][
            "canonical_records"]
        return counts

    def _all_records(self, entity: str) -> list[dict[str, Any]]:
        """Every canonical record of one type, read page by page through the API."""
        items: list[dict[str, Any]] = []
        while True:
            page = self._get(f"{API}/entities/{entity}", limit=PAGE_LIMIT, offset=len(items))
            items.extend(page["items"])
            if len(page["items"]) < PAGE_LIMIT:
                require(len(items) == page["total"],
                        f"paging {entity} returned {len(items)} of {page['total']} records")
                return items

    # -- Earlier results ----------------------------------------------------

    def _pinned(self, why: str) -> list[PinnedResult]:
        """A27.1b's pinned results, or a failure naming A27.1b."""
        results: list[PinnedResult] | None = self.state.get("pinned")
        if results is None:
            raise CheckFailed(f"A27.1b did not pass, so {why}")
        return results

    def _meridian_brief(self, why: str) -> dict[str, Any]:
        meridian = self._pinned(why)[0]
        require(meridian.brief_id is not None, f"CUST-007's pinned result has no brief, so {why}")
        brief: dict[str, Any] = self._get(f"{BRIEFS}/{meridian.brief_id}")
        return brief

    # -- The pinned run (K1) ------------------------------------------------

    def _pinned_run(self, expected_fingerprint: str, *, keep: bool) -> list[PinnedResult]:
        """One pinned assessment run in its own transaction; committed only when keep is true."""
        with self.sessions() as session:
            transaction = session.begin()
            try:
                results = run_assessment(session, as_of=self.as_of, source_system=SOURCE_SYSTEM,
                                         expected_fingerprint=expected_fingerprint)
            except BaseException:
                transaction.rollback()
                raise
            if keep:
                transaction.commit()
            else:
                transaction.rollback()
        return [PinnedResult(str(result.assessment_id), result.created,
                             None if result.brief_id is None else str(result.brief_id),
                             result.payload_hash) for result in results]

    def _refused(self, expected_fingerprint: str, what: str) -> FingerprintMismatchError:
        """A pinned run that must be refused; it is always rolled back, and writes nothing."""
        before = row_counts(self.sessions)
        try:
            self._pinned_run(expected_fingerprint, keep=False)
        except FingerprintMismatchError as refused:
            changed = _changed(before, row_counts(self.sessions))
            require(not changed, f"the refused {what} changed row counts: {', '.join(changed)}")
            return refused
        raise CheckFailed(f"the {what} was not refused")

    # -- A27.1 --------------------------------------------------------------

    def clean_dataset(self) -> str:
        """§A28's clean full-dataset path, through the ingestion route, on an empty database."""
        heads = script_heads()
        require(heads == (EXPECTED_HEAD,),
                f"the migration history has heads {', '.join(heads)}, not {EXPECTED_HEAD}")
        current = current_heads(self.sessions)
        require(current == heads, f"the database is at {', '.join(current) or 'no revision'}, "
                                  f"not the head {EXPECTED_HEAD}")
        occupied = {name: count for name, count in row_counts(self.sessions).items() if count}
        require(not occupied, "the database is not empty before the scenario: " + ", ".join(
            f"{name} {count}" for name, count in sorted(occupied.items())))
        first = self._post(INGESTION_RUNS, {"source": SOURCE_SYSTEM})
        require(first.status_code == 201,
                f"POST {INGESTION_RUNS} answered {first.status_code}, not 201")
        run = first.json()
        require((run["status"], run["records_fetched"], run["records_rejected"])
                == ("SUCCESS", DEMO_ROWS, 0),
                f"the ingestion finished {run['status']} with {run['records_fetched']} fetched "
                f"and {run['records_rejected']} rejected, not SUCCESS with {DEMO_ROWS} and 0")
        again = self._post(INGESTION_RUNS, {"source": SOURCE_SYSTEM})
        require(again.status_code == 201,
                f"the repeated POST {INGESTION_RUNS} answered {again.status_code}, not 201")
        repeat = again.json()
        require((repeat["status"], repeat["records_inserted"], repeat["records_updated"])
                == ("NOOP", 0, 0),
                f"the repeated ingestion finished {repeat['status']} with "
                f"{repeat['records_inserted']} inserted and {repeat['records_updated']} updated, "
                f"not NOOP with 0 and 0")
        counts = self._canonical_counts()
        require(counts == CANONICAL_COUNTS, "the canonical counts are " + ", ".join(
            f"{entity} {counts.get(entity)}" for entity in ENTITY_TYPES))
        return (f"sqlalchemy {installed_version('sqlalchemy')}; head {EXPECTED_HEAD}; "
                + ", ".join(f"{entity} {counts[entity]}" for entity in ENTITY_TYPES)
                + f"; {DEMO_ROWS} fetched, 0 rejected: SUCCESS then NOOP")

    # -- A27.1b -------------------------------------------------------------

    def pinned_fingerprint(self) -> str:
        """A deliberate mismatch is refused and writes nothing; the pinned run then succeeds."""
        refused = self._refused(MISMATCH, "deliberately mismatched run")
        require(refused.computed == self.pin, str(FingerprintMismatchError(
            SOURCE_SYSTEM, self.pin, refused.computed)))
        try:
            results = self._pinned_run(self.pin, keep=True)
        except FingerprintMismatchError as mismatch:
            raise CheckFailed(str(mismatch)) from None
        briefed = [result for result in results if result.brief_id is not None]
        require(len(results) == CUSTOMERS and all(result.created for result in results),
                f"the pinned run returned {len(results)} results, "
                f"{sum(result.created for result in results)} created, not {CUSTOMERS} created")
        require(len(briefed) == BRIEFS_EXPECTED,
                f"the pinned run wrote {len(briefed)} briefs, not {BRIEFS_EXPECTED}")
        self.state["pinned"] = results
        return (f"pinned {self.pin[:8]} matched; deliberate mismatch refused, 0 rows written; "
                f"{len(results)} assessments, {len(briefed)} briefs")

    # -- A27.2 --------------------------------------------------------------

    def single_escalation(self) -> str:
        """Exactly one customer is CRITICAL and executive-worthy: CUST-007."""
        pinned = self._pinned("there is no assessment to list")
        as_of = self.as_of.isoformat()
        listed = self._get(ASSESSMENTS, as_of=as_of)
        require(listed["total"] == CUSTOMERS,
                f"GET {ASSESSMENTS} reports {listed['total']} assessments, not {CUSTOMERS}")
        for name, value in (("executive_worthy", "true"), ("band", "CRITICAL")):
            page = self._get(ASSESSMENTS, as_of=as_of, **{name: value})
            customers = [item["customer_source_id"] for item in page["items"]]
            require(page["total"] == 1 and customers == [MERIDIAN],
                    f"{name}={value} lists {page['total']} assessments "
                    f"({', '.join(map(str, customers)) or 'none'}), not CUST-007 alone")
            require(page["items"][0]["id"] == pinned[0].assessment_id,
                    f"{name}={value} lists an assessment that is not the pinned run's first "
                    f"result; the command and the server read different databases")
        return f"{CUSTOMERS} assessments; CUST-007 alone is CRITICAL and executive-worthy"

    # -- A27.3 --------------------------------------------------------------

    def brief_facts(self) -> str:
        """CUST-007's brief, its golden narrative and the ten facts of §A27.3."""
        brief = self._meridian_brief("there is no brief to read")
        golden = GOLDEN.read_bytes()
        require(brief["payload_hash"] == MERIDIAN_HASH,
                f"the brief's payload_hash is {brief['payload_hash'][:8]}, not {MERIDIAN_HASH[:8]}")
        require(brief["narrative"].encode("utf-8") == golden,
                "the narrative differs from tests/golden/vs01_cust007_brief.txt")
        require((brief["status"], brief["decision_status"]) == ("DRAFT", "PENDING"),
                f"the brief is {brief['status']}/{brief['decision_status']}, not DRAFT/PENDING")
        require(len(brief["citations"]) == MERIDIAN_CITATIONS,
                f"the brief carries {len(brief['citations'])} citations, "
                f"not {MERIDIAN_CITATIONS}")
        payload = brief["payload"]
        support = payload["support_evidence"]
        path = support["escalation_path"]
        facts: tuple[tuple[str, Any, Any], ...] = (
            ("support_evidence.tickets", support["tickets"], MERIDIAN_TICKETS),
            ("support_evidence.escalation_window", support["escalation_window"], MERIDIAN_WINDOW),
            ("support_evidence.ticket_span (5 tickets in a 9-day span)", support["ticket_span"],
             MERIDIAN_SPAN),
            ("support_evidence.derivations (4 open; 3 open high-priority; 4 high-priority; "
             "3 open high-priority SLA breaches; dominant performance)", support["derivations"],
             MERIDIAN_DERIVATIONS),
            ("support_evidence.backlog_ticket_ids", support["backlog_ticket_ids"], []),
            ("support_evidence.escalation_path", {
                "customer": path["customer"]["id"],
                "account_owner": path["account_owner"]["id"],
                "account_owner_manager": path["account_owner_manager"]["id"],
                "assignees": sorted(ref["id"] for ref in path["assignees"]),
                "assignee_managers": sorted(ref["id"] for ref in path["assignee_managers"]),
                "open_tickets": sorted(ref["id"] for ref in path["open_tickets"]),
            }, MERIDIAN_PATH),
            ("commercial_evidence (DEAL-001 negotiation at 90% for USD 5361.44)",
             payload["commercial_evidence"], MERIDIAN_COMMERCIAL),
            ("cited_spans (DOC-003's rule; DOC-006's term and notice; DOC-009's linkage)",
             payload["cited_spans"], MERIDIAN_CITED_SPANS),
        )
        for name, found, expected in facts:
            require(found == expected, f"{name} differs from the plan's expected value")
        return (f"payload_hash {MERIDIAN_HASH[:8]}; narrative equals the golden file "
                f"({len(golden)} bytes); the 10 facts of A27.3; {MERIDIAN_CITATIONS} citations")

    # -- A27.4 --------------------------------------------------------------

    def no_active_project(self) -> str:
        """The payload and the narrative both state that CUST-007 has no active project."""
        brief = self._meridian_brief("there is no brief to read")
        payload = brief["payload"]
        counts = (payload["signals"]["active_project_count"],
                  payload["reconciliation"]["worthiness"]["active_project_count"])
        require(counts == (0, 0),
                f"the payload records {counts[0]} active projects in signals and {counts[1]} in "
                f"worthiness, not 0")
        require(PROJECT_ABSENCE_LINE in GOLDEN.read_text(encoding="utf-8").splitlines(),
                "the golden file no longer carries the project-absence line")
        require(PROJECT_ABSENCE_LINE in brief["narrative"].splitlines(),
                "the narrative does not carry the project-absence line")
        return "no active project, in the payload and the narrative"

    # -- A27.5 --------------------------------------------------------------

    def conflict_and_dissent(self) -> str:
        """One conflict under CONF-001, its winner and its dissent, in the payload and prose."""
        brief = self._meridian_brief("there is no brief to read")
        reconciliation = brief["payload"]["reconciliation"]
        conflicts = reconciliation["conflicts"]
        require(len(conflicts) == 1, f"the payload holds {len(conflicts)} conflicts, not 1")
        (conflict,) = conflicts
        require(conflict["object_ref"] == CONFLICT_OBJECT
                and [position["proposed_action"] for position in conflict["positions"]]
                == CONFLICT_ACTIONS,
                "the conflict is not ACCELERATE_DEAL_CLOSE against "
                "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED over DEAL-001")
        resolutions = reconciliation["resolutions"]
        require(len(resolutions) == 1, f"the payload holds {len(resolutions)} resolutions, not 1")
        (resolution,) = resolutions
        require((resolution["policy_id"], reconciliation["policy_version"],
                 brief["policy_version"]) == (CONFLICT_POLICY, POLICY_VERSION, POLICY_VERSION),
                f"the conflict is resolved by {resolution['policy_id']} at policy_version "
                f"{reconciliation['policy_version']}, not CONF-001 at 1")
        require(resolution["resolved_action"] == WINNING_ACTION
                and resolution["prevailing"]["proposed_action"] == WINNING_ACTION,
                f"{resolution['resolved_action']} wins, not {WINNING_ACTION}")
        for where, dissent in (("reconciliation", reconciliation["dissent"]),
                               ("the resolution", resolution["dissent"])):
            require([(one["function"], one["proposed_action"], one["object_ref"])
                     for one in dissent] == [("SALES", DISSENT_ACTION, CONFLICT_OBJECT)],
                    f"the dissent in {where} is not SALES ACCELERATE_DEAL_CLOSE on DEAL-001")
            require(dissent[0]["evidence"] == DISSENT_CITATIONS,
                    f"the dissent in {where} does not carry its three citations "
                    f"(is_active, stage, probability)")
        narrative = brief["narrative"].splitlines()
        for line in CONFLICT_LINES:
            require(line in narrative, f"the narrative does not state {line.strip()!r}")
        require(DISSENT_HEADING in narrative, "the narrative has no recorded-dissent section")
        dissent_section = brief["narrative"].split(DISSENT_HEADING, 1)[1].split("\n7. ", 1)[0]
        for fact in DISSENT_CITATIONS:
            citation = fact["citation"]
            line = (f"  - CANONICAL_FACT record deals {citation['id']} {citation['field']}")
            require(line in dissent_section.splitlines(),
                    f"the narrative's dissent does not cite deals DEAL-001 {citation['field']}")
        return (f"{CONFLICT_POLICY} over {CONFLICT_OBJECT}: {WINNING_ACTION} wins; "
                f"{DISSENT_ACTION} dissents with {len(DISSENT_CITATIONS)} citations")

    # -- A27.6 --------------------------------------------------------------

    def _resolves(self, citation: Mapping[str, Any],
                  records: Mapping[tuple[str, str], dict[str, Any]]) -> bool:
        """§0.6.9's rule, restated from the plan over the records the API serves."""
        if citation.get("kind") == "document":
            document = records.get(("documents", citation["document_id"]))
            if document is None:
                return False
            text_ = (document["title"] or "") + "\n" + (document["body_text"] or "")
            return 0 <= citation["start"] < citation["end"] <= len(text_)
        record = records.get((citation.get("entity", ""), citation.get("id", "")))
        if record is None or citation.get("field") not in record:
            return False
        return (record[citation["field"]] is not None
                or (citation["entity"], citation["field"]) not in NON_NULL_FIELDS)

    def citations_resolve(self) -> str:
        """Every citation of every assessment and every brief resolves against Layer 1."""
        pinned = self._pinned("there are no citations to resolve")
        records = {}
        for entity in ENTITY_TYPES:
            for item in self._all_records(entity):
                if item["source_system"] == SOURCE_SYSTEM and item["source_entity"] == entity:
                    records[(entity, item["source_id"])] = item
        citations: dict[str, dict[str, Any]] = {}
        for result in pinned:
            detail = self._get(f"{ASSESSMENTS}/{result.assessment_id}")
            for position in detail["positions"]:
                for citation in _citations(position["citations"]):
                    citations[_wire(citation)] = citation
        briefs = [result for result in pinned if result.brief_id is not None]
        spans: dict[str, tuple[str, int, int, str]] = {}
        for result in briefs:
            brief = self._get(f"{BRIEFS}/{result.brief_id}")
            for citation in [*brief["citations"], *_citations(brief["payload"])]:
                citations[_wire(citation)] = citation
            for entry in brief["payload"]["cited_spans"]:
                citation = entry["citation"]
                document = records.get(("documents", citation["document_id"]))
                read = "" if document is None else (
                    (document["title"] or "") + "\n" + (document["body_text"] or ""))[
                        citation["start"]:citation["end"]]
                spans[entry["target"]] = (citation["document_id"], citation["start"],
                                          citation["end"], read)
        for wire in sorted(citations):
            require(self._resolves(citations[wire], records), f"citation {wire} does not resolve")
        require(sorted(spans) == sorted(CITED_SPANS),
                f"the briefs cite spans for {', '.join(sorted(spans)) or 'no target'}, not the "
                f"three targets")
        for target, (named, _, _, phrase) in sorted(CITED_SPANS.items()):
            found, _, _, read = spans[target]
            require(found == named and read == phrase,
                    f"{target} does not read back its phrase from {named}")
        self.state["spans"] = spans
        return (f"{len(citations)} distinct citations across {len(pinned)} assessments and "
                f"{len(briefs)} briefs resolve; {len(spans)} cited spans read back exactly")

    # -- A27.9 --------------------------------------------------------------

    def _decide(self, brief_id: str, payload_hash: str, decision: str,
                supersedes_id: str | None) -> httpx.Response:
        return self._post(DECISION.format(brief_id=brief_id), {
            "actor": ACTOR, "decision": decision, "payload_hash": payload_hash,
            "supersedes_id": supersedes_id})

    def _one_decision_row(self, before: Mapping[str, int], step: str) -> dict[str, int]:
        after = row_counts(self.sessions)
        expected = {**before, "brief_decisions": before["brief_decisions"] + 1}
        changed = _changed(expected, after)
        require(not changed, f"{step} did not write exactly one brief_decisions row: "
                             f"{', '.join(changed)}")
        return after

    def _refused_statement(self, statement: Any, what: str) -> None:
        before = row_counts(self.sessions)
        try:
            with self.sessions.begin() as session:
                session.execute(statement)
        except SQLAlchemyError as exc:
            original = getattr(exc, "orig", None)
            code = getattr(original, "pgcode", None)
            message = getattr(getattr(original, "diag", None), "message_primary", None)
            require((code, message) == (APPEND_ONLY_SQLSTATE, APPEND_ONLY_MESSAGE),
                    f"the {what} failed with SQLSTATE {code}, not the append-only trigger's "
                    f"{APPEND_ONLY_SQLSTATE}")
        else:
            raise CheckFailed(f"an {what} on brief_decisions was not refused")
        changed = _changed(before, row_counts(self.sessions))
        require(not changed, f"the refused {what} changed row counts: {', '.join(changed)}")

    def approval_boundary(self) -> str:
        """M8's decision contract on CUST-007's brief (R-M9-6), then nothing is executable."""
        meridian = self._pinned("there is no brief to decide on")[0]
        require(meridian.brief_id is not None and meridian.payload_hash is not None,
                "CUST-007's pinned result has no brief to decide on")
        brief_id, payload_hash = str(meridian.brief_id), str(meridian.payload_hash)
        before = row_counts(self.sessions)
        rejected = self._decide(brief_id, payload_hash, "REJECTED", None)
        require(rejected.status_code == 201,
                f"(i) REJECTED answered {rejected.status_code}, not 201")
        after_first = self._one_decision_row(before, "(i) REJECTED")
        refused = self._decide(brief_id, payload_hash, "APPROVED", None)
        body = refused.json() if refused.status_code == 409 else {}
        error = body.get("error", {})
        require((refused.status_code, error.get("code"), (error.get("details") or {}).get("reason"))
                == (409, "DECISION_CONFLICT", "SUPERSEDES_REQUIRED"),
                f"(ii) APPROVED without supersedes_id answered {refused.status_code}, not "
                f"409 DECISION_CONFLICT SUPERSEDES_REQUIRED")
        changed = _changed(after_first, row_counts(self.sessions))
        require(not changed, f"(ii) the refused decision changed row counts: {', '.join(changed)}")
        first_id = rejected.json()["id"]
        approved = self._decide(brief_id, payload_hash, "APPROVED", first_id)
        require(approved.status_code == 201,
                f"(iii) APPROVED superseding (i) answered {approved.status_code}, not 201")
        self._one_decision_row(after_first, "(iii) APPROVED")
        history = self._get(DECISIONS.format(brief_id=brief_id))["items"]
        require([(one["id"], one["decision"], one["supersedes_id"]) for one in history]
                == [(first_id, "REJECTED", None), (approved.json()["id"], "APPROVED", first_id)],
                "(iv) the history is not REJECTED then APPROVED, in chain order")
        state = self._get(f"{BRIEFS}/{brief_id}")
        require((state["status"], state["decision_status"]) == ("DRAFT", "APPROVED"),
                f"(iv) the brief is {state['status']}/{state['decision_status']}, "
                f"not DRAFT/APPROVED")
        decisions = Base.metadata.tables["brief_decisions"]
        self._refused_statement(update(decisions).values(note=None), "UPDATE")
        self._refused_statement(delete(decisions), "DELETE")
        operations = {(method.upper(), path)
                      for path, methods in self._get("/openapi.json")["paths"].items()
                      for method in methods}
        writes = {operation for operation in operations if operation[0] != "GET"}
        risk = {operation for operation in operations if operation[1].startswith(f"{API}/risk/")}
        require(writes == WRITES, f"(vi) the API publishes {len(writes)} non-GET operations, "
                                  f"not the three writes of 0.7.14")
        require(risk == RISK_OPERATIONS,
                f"(vi) the API publishes {len(risk)} risk operations, not the six of 0.7.8")
        return ("REJECTED recorded; a second decision without supersedes_id refused "
                "(409 SUPERSEDES_REQUIRED); APPROVED supersedes it; history of 2 in chain order; "
                "status DRAFT; append-only held; 3 writes, 6 risk operations")

    # -- A27.8 --------------------------------------------------------------

    def _assess_unpinned(self) -> httpx.Response:
        return self._post(ASSESSMENTS, {"as_of": self.as_of.isoformat(),
                                        "source_system": SOURCE_SYSTEM,
                                        "customer_source_id": None})

    def determinism(self) -> str:
        """An identical re-run writes nothing; a changed snapshot mints new assessments."""
        pinned = self._pinned("there is nothing to re-run")
        before = row_counts(self.sessions)
        rerun = self._assess_unpinned()
        require(rerun.status_code == 200, f"(i) the re-run answered {rerun.status_code}, not 200")
        require(rerun.json()["items"] == [
            {"assessment_id": result.assessment_id, "created": False,
             "brief_id": result.brief_id, "payload_hash": result.payload_hash}
            for result in pinned], "(i) the re-run's results are not the pinned run's")
        changed = _changed(before, row_counts(self.sessions))
        require(not changed, f"(i) the re-run changed row counts: {', '.join(changed)}")
        summary = run_ingestion(
            build_connector(SOURCE_SYSTEM, data_directory=UNRESOLVED_TICKET_DIR), self.sessions,
            IngestionRequest(entities=list(UNRESOLVED_TICKET_ENTITIES)))
        require((summary.counts.inserted, summary.counts.rejected) == (1, 0),
                f"(ii) the unresolved_ticket fixture inserted {summary.counts.inserted} and "
                f"rejected {summary.counts.rejected} rows, not 1 and 0")
        refused = self._refused(self.pin, "pinned run on the changed snapshot")
        require(refused.computed != self.pin, "(iii) the snapshot did not change")
        changed_before = row_counts(self.sessions)
        fresh = self._assess_unpinned()
        require(fresh.status_code == 201,
                f"(iv) the run on the changed snapshot answered {fresh.status_code}, not 201")
        items = fresh.json()["items"]
        earlier = {result.assessment_id for result in pinned}
        require(len(items) == CUSTOMERS and all(item["created"] for item in items)
                and not earlier & {item["assessment_id"] for item in items},
                f"(iv) the changed snapshot answered {len(items)} results, not {CUSTOMERS} new "
                f"assessments")
        require(row_counts(self.sessions)["risk_assessments"]
                == changed_before["risk_assessments"] + CUSTOMERS,
                "(iv) the earlier assessments were not all retained beside the new ones")
        listed = self._get(ASSESSMENTS, as_of=self.as_of.isoformat(), limit=PAGE_LIMIT)
        fingerprints = {item["layer1_fingerprint"] for item in listed["items"]}
        require(listed["total"] == 2 * CUSTOMERS and fingerprints == {self.pin, refused.computed},
                f"(iv) the listing holds {listed['total']} assessments under "
                f"{len(fingerprints)} fingerprints, not {2 * CUSTOMERS} under two")
        return ("re-run 200: identical hashes, 0 rows; one extra ticket: pinned run refused, "
                f"unpinned run 201 with {len(items)} new assessments")

    # -- A27.7 --------------------------------------------------------------

    def named_tests(self) -> str:
        """The §A25 proof corpus, run by pytest on the suite's own test database."""
        passed = _pytest_summary(self.proof_runner(PROOF_COMMAND), A25_PROOF_COUNT)
        return f"{passed} passed: A25 tests 1-14 and 13b"

    # -- A27.10 -------------------------------------------------------------

    def regression(self) -> Check:
        if not self.with_tests:
            return Check("A27.10", "regression", Outcome.SKIPPED, "not run; pass --with-tests")
        return self._step("A27.10", "regression", self._regression)

    def _regression(self) -> str:
        suite = self.regression_runner(SUITE_COMMAND)
        passed = _pytest_summary(suite, None)
        coverage = COVERAGE_TOTAL.search(suite.stdout)
        require(coverage is not None, "the suite printed no coverage total")
        assert coverage is not None
        statements, percent = int(coverage.group(1)), int(coverage.group(3))
        require(percent == 100, f"app/ coverage is {percent}%, not 100%")
        ruff = self.regression_runner(RUFF_COMMAND)
        found = RUFF_FOUND.search(ruff.stdout)
        ruff_count = int(found.group(1)) if found else (
            0 if ruff.returncode == 0 and "All checks passed" in ruff.stdout else None)
        require(ruff_count == RUFF_FINDINGS,
                f"ruff check app/ tests/ scripts/ reports {ruff_count}, not {RUFF_FINDINGS}")
        mypy = self.regression_runner(MYPY_COMMAND)
        found = MYPY_FOUND.search(mypy.stdout)
        mypy_count = int(found.group(1)) if found else (
            0 if mypy.returncode == 0 and mypy.stdout.startswith("Success") else None)
        require(mypy_count == MYPY_ERRORS, f"mypy app/ reports {mypy_count}, not {MYPY_ERRORS}")
        scan = self.regression_runner(SECRET_SCAN_COMMAND)
        found = SECRET_SCAN_FOUND.search(scan.stdout)
        findings = int(found.group(1)) if found else None
        require(scan.returncode == 0 and findings == SECRET_FINDINGS,
                f"the secret scan exited {scan.returncode} with {findings} findings, not 0")
        heads = script_heads()
        require(heads == (EXPECTED_HEAD,),
                f"the migration history has heads {', '.join(heads)}, not {EXPECTED_HEAD}")
        return (f"{passed} passed; coverage 100% over {statements} statements; "
                f"ruff {installed_version('ruff')}: {ruff_count}; "
                f"mypy {installed_version('mypy')}: {mypy_count}; "
                f"secret scan {findings}; head {EXPECTED_HEAD}")

    # -- A28.citations ------------------------------------------------------

    def hand_citations(self) -> Check:
        """§A28's two citations are for a human to read; the command reads nothing here."""
        spans: dict[str, tuple[str, int, int, str]] | None = self.state.get("spans")
        if spans is None:
            detail = ("operator step: A27.6 did not prove the cited spans, so there is nothing "
                      "to read by hand until it passes")
        else:
            detail = "operator step: in data/demo/documents.csv, confirm " + "; ".join(
                f"{spans[target][0]} [{spans[target][1]}, {spans[target][2]}) reads "
                f"\"{spans[target][3]}\"" for target in HAND_CITATIONS
            ) + "; DOC-003 states the escalation rule, and DOC-009 ties DEAL-001 to the tickets"
        return Check("A28.citations", "hand_citations", Outcome.OPERATOR, detail)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def run_scenario(
    client: httpx.Client,
    sessions: sessionmaker[Session],
    *,
    with_tests: bool = False,
    proof_runner: Runner | None = None,
    regression_runner: Runner | None = None,
    report_line: Callable[[Check], None] | None = None,
) -> Report:
    """Run every acceptance check, in §0.8.5's order, and return the report."""
    scenario = Scenario(client, sessions, with_tests=with_tests, proof_runner=proof_runner,
                        regression_runner=regression_runner)
    checks = []
    for check in scenario.checks():
        if report_line is not None:
            report_line(check)
        checks.append(check)
    return Report(tuple(checks))


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the VS-01 acceptance scenario on its own recreated database.")
    parser.add_argument("--with-tests", action="store_true",
                        help="also run A27.10: the full suite, ruff, mypy and the secret scan")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="per-request and server-start timeout in seconds "
                             "(default: %(default)s)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.timeout <= 0:
        print("vs01_acceptance: --timeout must be greater than zero", file=sys.stderr)
        return 2
    settings = get_settings()
    try:
        resolve_level(settings.app_log_level)
        resolve_format(settings.log_format)
    except ValueError as exc:
        print(f"vs01_acceptance: invalid logging settings: {exc}", file=sys.stderr)
        return 2
    try:
        check_environment(args.with_tests)
        url = acceptance_url(settings.effective_database_url)
        recreate_database(url)
        migrate_to_head(url)
    except EnvironmentRefused as exc:
        print(f"vs01_acceptance: {exc}", file=sys.stderr)
        return 2
    engine = create_engine(url, hide_parameters=True, pool_pre_ping=True)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with (configured_logging(settings.app_log_level, settings.log_format),
              serving(build_app(sessions), args.timeout) as base_url,
              httpx.Client(base_url=base_url, timeout=args.timeout) as client):
            report = run_scenario(client, sessions, with_tests=args.with_tests,
                                  report_line=lambda check: print(check, flush=True))
    except EnvironmentRefused as exc:
        print(f"vs01_acceptance: {exc}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()
    print(report.summary())
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
