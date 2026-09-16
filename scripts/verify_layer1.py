"""
Layer 1 acceptance scenario (spec Section 20, steps A-O).

    python scripts/verify_layer1.py                      (make verify-layer1)
    python scripts/verify_layer1.py --base-url http://localhost:8000
    python scripts/verify_layer1.py --with-tests

Drives a running Layer 1 stack the way a reviewer would: every observation is
made through the published API, the committed files, or the existing demo
generator, so the report describes the deployed system rather than re-testing
the code in process. The one exception is the deliberately malformed fixture
(steps K-L): the API refuses to take a data directory from a request, so that
run goes through the same run_ingestion() entry point the API and
scripts/ingest_demo.py use, and is then observed through the API. That
crossing is itself a check - if the API cannot see the run, this script and
the API are talking to different databases.

The scenario writes to the configured database exactly as make ingest-demo
does: it starts real ingestion runs. Repeating it is safe, because ingestion
reconciles on source identity, and it never deletes or edits rows.

Steps N and O are operator steps. N (the full test suite) runs only with
--with-tests, because the suite needs its own database. O (a clean rebuild)
cannot be done by a script talking to the stack it would tear down, so it is
reported with the commands to run.

Exit status:
    0  every executed check passed
    1  at least one check failed
    2  the scenario could not run (unreachable API, invalid arguments or
       logging settings)

The report goes to stdout. The log events of the malformed-fixture run go to
stderr as configured by APP_LOG_LEVEL and LOG_FORMAT (app.core.logging), and
the database comes from DATABASE_URL / POSTGRES_* (app.core.config).

Secrets and source values are never printed: the report carries counts,
identifiers, field names and status values only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
for _entry in (str(PROJECT_ROOT), str(SCRIPTS_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import httpx  # noqa: E402
import seed_demo  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.connectors import ConnectorConfigurationError  # noqa: E402
from app.connectors.csv import CsvConnectorConfig  # noqa: E402
from app.connectors.registry import CONNECTOR_CONFIG_DIR, build_connector  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.logging import configured_logging, resolve_format, resolve_level  # noqa: E402
from app.ingestion.orchestrator import (  # noqa: E402
    MAX_PAGE_SIZE,
    IngestionRequest,
    RunSummary,
    run_ingestion,
)

__all__ = ["Check", "Outcome", "Report", "Scenario", "main", "parse_args", "run_scenario"]

API = "/api/v1"
DEMO_DIR = PROJECT_ROOT / "data" / "demo"
BAD_FIXTURE_DIR = PROJECT_ROOT / "data" / "fixtures" / "csv_demo_bad"
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 180.0
DEFAULT_PAGE_SIZE = 100

#: Every canonical entity type, in dependency order (spec Section 6).
ENTITY_TYPES = ("organizations", "employees", "customers", "deals",
                "projects", "support_tickets", "documents")
#: The entity types the scenario ingests (spec Section 20 step E).
SCENARIO_ENTITIES = ("customers", "employees", "deals", "projects", "support_tickets")
#: The entity types the scenario queries back (spec Section 20 step G).
QUERIED_ENTITIES = ("customers", "deals", "support_tickets")
#: Provenance every accepted record must carry (spec Section 20 step H).
PROVENANCE_FIELDS = ("source_system", "source_entity", "source_id", "ingested_at",
                     "ingestion_run_id", "record_hash")
#: Run statuses step F accepts; NOOP is the same run repeated (steps I-J).
ACCEPTED_RUN_STATUSES = ("SUCCESS", "PARTIAL_SUCCESS", "NOOP")
#: Count fields that must add up to records_fetched.
COUNT_PARTS = ("records_inserted", "records_updated", "records_unchanged",
               "records_rejected", "records_failed")
PAGE_LIMIT = 500


class Outcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    OPERATOR = "OPERATOR"


class CheckFailed(Exception):
    """One acceptance check did not hold; the scenario continues."""


class ScenarioAborted(Exception):
    """The scenario could not be run at all (exit status 2)."""


def require(condition: object, message: str) -> None:
    """Fail the current check unless condition holds."""
    if not condition:
        raise CheckFailed(message)


@dataclass(frozen=True)
class Check:
    """One acceptance check: the spec steps it covers and what was observed."""

    steps: str
    name: str
    outcome: Outcome
    detail: str

    def __str__(self) -> str:
        return (f"verify-layer1: {self.steps:<4} {self.name:<17} "
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
        return (f"verify-layer1: {self.count(Outcome.PASS)} passed, "
                f"{self.count(Outcome.FAIL)} failed, {self.count(Outcome.SKIPPED)} skipped, "
                f"{self.count(Outcome.OPERATOR)} operator")


# ---------------------------------------------------------------------------
# Committed source files
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CsvEntityFile:
    """One entity's committed CSV file name and identifier column."""

    file: str
    id_column: str


def csv_entities() -> dict[str, CsvEntityFile]:
    """The committed csv_demo entity-to-file mapping (file name and id column)."""
    config = CsvConnectorConfig.from_yaml(CONNECTOR_CONFIG_DIR / "csv_demo.yaml")
    return {entity: CsvEntityFile(spec.file, spec.id_column)
            for entity, spec in config.entities.items()}


def _rows(directory: Path, entity_file: CsvEntityFile) -> list[dict[str, str]]:
    path = directory / entity_file.file
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fixture_source_ids(directory: Path) -> dict[str, set[str]]:
    """The source ids each entity's CSV file holds in directory."""
    return {entity: {row[spec.id_column] for row in _rows(directory, spec)}
            for entity, spec in csv_entities().items()}


def sensitive_values(directory: Path) -> set[str]:
    """Source values that must never reach an error payload: names, emails, free text."""
    values: set[str] = set()
    for entity_file in csv_entities().values():
        for row in _rows(directory, entity_file):
            values.update(value for column, value in row.items()
                          if column != entity_file.id_column and value
                          and ("@" in value or " " in value))
    return values


def source_fingerprints() -> dict[str, str]:
    """SHA-256 of every committed source file the connectors read."""
    return {
        f"{directory.name}/{path.name}": hashlib.sha256(path.read_bytes()).hexdigest()
        for directory in (DEMO_DIR, BAD_FIXTURE_DIR)
        for path in sorted(directory.glob("*.csv"))
    }


# ---------------------------------------------------------------------------
# Step N — the full test suite
# ---------------------------------------------------------------------------


def pytest_runner() -> tuple[int, str]:
    """Run the full suite and return its exit status and last reported line."""
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-o", "addopts="],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=False,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    detail = lines[-1] if lines else f"pytest exited {completed.returncode} with no output"
    return completed.returncode, detail


# ---------------------------------------------------------------------------
# The scenario
# ---------------------------------------------------------------------------


class Scenario:
    """The Section 20 scenario as an ordered sequence of independent checks.

    Each check reports its own outcome, so one failure does not hide the rest.
    Checks that need an earlier step's result say so instead of crashing.
    """

    def __init__(
        self,
        client: httpx.Client,
        sessions: sessionmaker[Session],
        *,
        with_tests: bool = False,
        page_size: int = DEFAULT_PAGE_SIZE,
        test_runner: Callable[[], tuple[int, str]] | None = None,
    ) -> None:
        self.client = client
        self.sessions = sessions
        self.with_tests = with_tests
        self.page_size = page_size
        self.test_runner = pytest_runner if test_runner is None else test_runner
        self.fingerprints = source_fingerprints()
        self.state: dict[str, Any] = {}

    def checks(self) -> Iterator[Check]:
        yield self._step("A-C", "stack_ready", self.stack_ready)
        yield self._step("D", "demo_dataset", self.demo_dataset)
        yield self._step("E-F", "ingestion", self.ingestion)
        yield self._step("G-H", "api_query", self.api_query)
        yield self._step("I-J", "idempotency", self.idempotency)
        yield self._step("K-L", "validation", self.validation)
        yield self._step("M", "connector_health", self.connector_health)
        yield self._step("A-M", "read_only", self.read_only)
        yield self.test_suite()
        yield self.clean_rebuild()

    @staticmethod
    def _step(steps: str, name: str, check: Callable[[], str]) -> Check:
        try:
            detail = check()
        except CheckFailed as exc:
            return Check(steps, name, Outcome.FAIL, str(exc))
        return Check(steps, name, Outcome.PASS, detail)

    # -- HTTP ---------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return self.client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise CheckFailed(f"{method} {path} could not be reached "
                              f"({type(exc).__name__})") from None

    def _get(self, path: str, **params: object) -> dict[str, Any]:
        response = self._request("GET", path, params=params)
        require(response.status_code == 200,
                f"GET {path} answered {response.status_code}, not 200")
        body: dict[str, Any] = response.json()
        return body

    def _page(self, entity: str, **params: object) -> dict[str, Any]:
        return self._get(f"{API}/entities/{entity}", **params)

    def _all_records(self, entity: str) -> list[dict[str, Any]]:
        """Every canonical record of one type, read page by page through the API."""
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._page(entity, limit=PAGE_LIMIT, offset=offset)
            items.extend(page["items"])
            require(len(items) <= page["total"],
                    f"paging {entity} returned {len(items)} records for a total of "
                    f"{page['total']}")
            if len(page["items"]) < PAGE_LIMIT:
                require(len(items) == page["total"],
                        f"paging {entity} returned {len(items)} of {page['total']} records")
                return items
            offset += PAGE_LIMIT

    def _canonical_counts(self) -> dict[str, int]:
        counts: dict[str, int] = self._get(f"{API}/metrics/ingestion")["totals"][
            "canonical_records"]
        require(set(counts) == set(ENTITY_TYPES),
                f"the API reports canonical counts for {sorted(counts)}, "
                f"not the seven canonical entity types")
        return counts

    # -- Steps A-C ----------------------------------------------------------

    def stack_ready(self) -> str:
        """The stack is up, the API is ready and PostgreSQL is reachable."""
        health = self._get(f"{API}/health")
        require(health.get("status") == "healthy",
                f"the API reports status {health.get('status')!r}, not 'healthy'")
        database = health.get("checks", {}).get("database")
        require(database == "ok", f"the API reports database {database!r}, not 'ok'")
        counts = self._canonical_counts()
        total = sum(counts.values())
        self.state["counts_before"] = counts
        state = "empty" if total == 0 else f"already holding {total} canonical records"
        return (f"{health.get('service')} {health.get('version')} ready, database ok, "
                f"all {len(counts)} canonical tables queryable, database {state}")

    # -- Step D -------------------------------------------------------------

    def demo_dataset(self) -> str:
        """The committed demo files are exactly what the deterministic generator writes."""
        datasets = {"demo": (DEMO_DIR, seed_demo.build_demo_dataset()),
                    "malformed fixture": (BAD_FIXTURE_DIR, seed_demo.build_bad_fixture())}
        files = 0
        for label, (directory, dataset) in datasets.items():
            rendered = seed_demo.render_dataset(dataset)
            stale = seed_demo.stale_files(rendered, directory)
            require(not stale, f"the committed {label} files differ from the generator: "
                               f"{', '.join(sorted(stale))}")
            files += len(rendered)
        rows = {entity: len(records) for entity, records in datasets["demo"][1].items()}
        self.state["demo_rows"] = rows
        return (f"{files} committed CSV files regenerate byte-identically; demo dataset holds "
                + ", ".join(f"{entity} {count}" for entity, count in sorted(rows.items())))

    # -- Steps E-F ----------------------------------------------------------

    def _start_run(self) -> dict[str, Any]:
        body = {"source": "csv_demo", "entities": list(SCENARIO_ENTITIES),
                "mode": "full", "page_size": self.page_size}
        response = self._request("POST", f"{API}/ingestion/runs", json=body)
        require(response.status_code == 201,
                f"POST {API}/ingestion/runs answered {response.status_code}, not 201")
        run: dict[str, Any] = response.json()
        require(run["status"] in ACCEPTED_RUN_STATUSES,
                f"the run finished {run['status']}, not one of "
                f"{', '.join(ACCEPTED_RUN_STATUSES)}")
        self._require_truthful_counts(run)
        return run

    @staticmethod
    def _require_truthful_counts(run: dict[str, Any]) -> None:
        parts = sum(run[name] for name in COUNT_PARTS)
        require(run["records_fetched"] == parts,
                f"run {run['run_id']} fetched {run['records_fetched']} records but accounts "
                f"for {parts} (inserted + updated + unchanged + rejected + failed)")
        require(run["records_raw_persisted"] == run["records_fetched"],
                f"run {run['run_id']} persisted {run['records_raw_persisted']} raw records "
                f"for {run['records_fetched']} fetched")
        require(run["finished_at"] is not None, f"run {run['run_id']} has no finished_at")
        require(run["batches_failed"] == 0,
                f"run {run['run_id']} rolled back {run['batches_failed']} batches")

    def ingestion(self) -> str:
        """A full CSV ingestion of the five demo entity types, with truthful counts."""
        run = self._start_run()
        self.state["run"] = run
        results = {entity["entity_type"]: entity for entity in run["entities"]}
        require(set(results) == set(SCENARIO_ENTITIES),
                f"the run covered {sorted(results)}, not {sorted(SCENARIO_ENTITIES)}")
        expected = self.state.get("demo_rows", {})
        for entity, result in sorted(results.items()):
            require(result["status"] == "completed",
                    f"entity {entity} finished {result['status']}"
                    + (f" ({result['failure']})" if result["failure"] else ""))
            if entity in expected:
                require(result["records_fetched"] == expected[entity],
                        f"entity {entity} fetched {result['records_fetched']} records, but the "
                        f"committed CSV holds {expected[entity]}")
        self.state["counts_after_run"] = self._canonical_counts()
        return (f"run {run['run_id'][:8]} {run['status']}: fetched {run['records_fetched']} = "
                + " + ".join(f"{run[name]} {name.removeprefix('records_')}"
                             for name in COUNT_PARTS)
                + f", {run['records_raw_persisted']} raw records persisted over "
                  f"{len(results)} entity types")

    # -- Steps G-H ----------------------------------------------------------

    @staticmethod
    def _require_provenance(entity: str, items: Sequence[dict[str, Any]]) -> None:
        for item in items:
            missing = [field for field in PROVENANCE_FIELDS if not item.get(field)]
            require(not missing, f"{entity} record {item.get('source_id')!r} is missing "
                                 f"provenance: {', '.join(missing)}")

    def _completed_run(self, why: str) -> dict[str, Any]:
        """The step E-F run, or a clear failure when that step did not complete."""
        run = self.state.get("run")
        if run is None:
            raise CheckFailed(f"the step E-F ingestion did not complete, {why}")
        return run

    def api_query(self) -> str:
        """Canonical records are queryable with pagination and carry full provenance."""
        self._completed_run("so there is nothing to query")
        totals = {}
        for entity in QUERIED_ENTITIES:
            first = self._page(entity, limit=2, offset=0)
            require(first["total"] > 0, f"the API reports no {entity}")
            require((first["limit"], first["offset"]) == (2, 0),
                    f"{entity} echoed limit {first['limit']} offset {first['offset']}, not 2/0")
            require(len(first["items"]) == min(2, first["total"]),
                    f"{entity} returned {len(first['items'])} items for limit 2")
            self._require_provenance(entity, first["items"])
            second = self._page(entity, limit=2, offset=2)
            require(second["total"] == first["total"],
                    f"{entity} reported total {second['total']} on page 2 and "
                    f"{first['total']} on page 1")
            require({item["id"] for item in first["items"]}.isdisjoint(
                        {item["id"] for item in second["items"]}),
                    f"{entity} pages 1 and 2 return overlapping records")
            record = self._get(f"{API}/entities/{entity}/{first['items'][0]['id']}")
            require(record["source_id"] == first["items"][0]["source_id"],
                    f"{entity} record read by id does not match the page it came from")
            totals[entity] = first["total"]
        return ("full provenance and consistent pagination for "
                + ", ".join(f"{entity} {total}" for entity, total in totals.items()))

    # -- Steps I-J ----------------------------------------------------------

    def idempotency(self) -> str:
        """The identical run again changes nothing and leaves no duplicate source identity."""
        first = self._completed_run("so it cannot repeat")
        before = self.state["counts_after_run"]
        again = self._start_run()
        require(again["run_id"] != first["run_id"],
                "the repeated ingestion reused the first run's id")
        require(again["records_inserted"] == 0 and again["records_updated"] == 0,
                f"repeating the identical run inserted {again['records_inserted']} and updated "
                f"{again['records_updated']} records")
        after = self._canonical_counts()
        changed = sorted(f"{entity} {before[entity]}->{after[entity]}"
                         for entity in after if before.get(entity) != after[entity])
        require(not changed,
                f"canonical counts changed when the identical run repeated: {', '.join(changed)}")
        duplicates = []
        total = 0
        for entity in ENTITY_TYPES:
            identities = [(item["source_system"], item["source_entity"], item["source_id"])
                          for item in self._all_records(entity)]
            total += len(identities)
            if len(set(identities)) != len(identities):
                duplicates.append(f"{entity} ({len(identities) - len(set(identities))})")
        require(not duplicates,
                f"duplicate canonical source identities after repeated ingestion: "
                f"{', '.join(duplicates)}")
        return (f"second run {again['run_id'][:8]} {again['status']} inserted 0 and updated 0, "
                f"canonical counts unchanged, {total} records across {len(ENTITY_TYPES)} entity "
                f"types with {total} distinct source identities")

    # -- Steps K-L ----------------------------------------------------------

    def _ingest_malformed_fixture(self) -> RunSummary:
        try:
            connector = build_connector("csv_demo", data_directory=BAD_FIXTURE_DIR)
            return run_ingestion(connector, self.sessions,
                                 IngestionRequest(page_size=self.page_size))
        except ConnectorConfigurationError as exc:
            raise CheckFailed(f"the malformed fixture could not be read: {exc}") from None
        except SQLAlchemyError as exc:
            raise CheckFailed("the malformed fixture run could not reach the database "
                              f"({type(exc).__name__}); check DATABASE_URL") from None

    def validation(self) -> str:
        """The malformed fixture is quarantined with structured errors; valid rows survive."""
        summary = self._ingest_malformed_fixture()
        run_id = str(summary.run_id)
        require(summary.status.value == "PARTIAL_SUCCESS",
                f"the malformed fixture run finished {summary.status.value}, "
                f"not PARTIAL_SUCCESS")
        rejected = summary.counts.rejected
        require(rejected > 0, "the malformed fixture produced no rejected records")
        run = self._get(f"{API}/ingestion/runs/{run_id}")
        require(run["status"] == "PARTIAL_SUCCESS" and run["records_rejected"] == rejected,
                f"the API reports run {run_id[:8]} as {run['status']} with "
                f"{run['records_rejected']} rejected, but the ingestion reported "
                f"PARTIAL_SUCCESS with {rejected}; the API may use a different database")
        errors = self._get(f"{API}/ingestion/runs/{run_id}/errors", limit=PAGE_LIMIT)
        require(errors["total"] >= rejected,
                f"run {run_id[:8]} rejected {rejected} records but published "
                f"{errors['total']} structured errors")
        rejected_ids = set()
        for item in errors["items"]:
            require(item["code"] and item["message"] and item["findings"],
                    f"an ingestion error of run {run_id[:8]} carries no code, message "
                    f"or findings")
            if item["severity"] == "ERROR" and item["source_id"]:
                rejected_ids.add(item["source_id"])
        payload = json.dumps(errors)
        leaked = [value for value in sensitive_values(BAD_FIXTURE_DIR) if value in payload]
        require(not leaked,
                f"{len(leaked)} source values from the malformed fixture appear in its "
                f"error payload")
        usable = self._require_valid_rows_usable(rejected_ids)
        return (f"run {run_id[:8]} PARTIAL_SUCCESS: {rejected} records quarantined with "
                f"{errors['total']} structured errors over {len(rejected_ids)} source ids, "
                f"{usable} valid fixture records still queryable, no source values disclosed")

    def _require_valid_rows_usable(self, rejected_ids: set[str]) -> int:
        usable = 0
        for entity, ids in sorted(fixture_source_ids(BAD_FIXTURE_DIR).items()):
            expected = ids - rejected_ids
            if not expected:
                continue
            present = {item["source_id"] for item in self._all_records(entity)}
            missing = sorted(expected - present)
            require(not missing, f"valid {entity} rows of the malformed fixture are not "
                                 f"queryable: {', '.join(missing)}")
            usable += len(expected)
        return usable

    # -- Step M -------------------------------------------------------------

    def connector_health(self) -> str:
        """Every configured source answers its health check and declares itself read-only."""
        sources = self._get(f"{API}/sources")["sources"]
        require(sources, "the API reports no configured sources")
        names = []
        for source in sources:
            name = source["source"]
            capabilities = source["capabilities"]
            require(capabilities["read_only"] is True,
                    f"source {name} does not declare itself read-only")
            require(capabilities["supported_entity_types"],
                    f"source {name} declares no supported entity types")
            health = self._get(f"{API}/sources/{name}/health")
            require(health["status"] == "healthy",
                    f"source {name} reports health {health['status']}"
                    + (f" ({health['error_type']})" if health.get("error_type") else ""))
            names.append(name)
        return (f"{len(names)} configured sources healthy and read-only: "
                + ", ".join(sorted(names)))

    # -- Safety -------------------------------------------------------------

    def read_only(self) -> str:
        """No step of the scenario wrote to a source file."""
        current = source_fingerprints()
        changed = sorted(set(self.fingerprints) ^ set(current))
        changed += sorted(name for name, digest in current.items()
                          if name in self.fingerprints and self.fingerprints[name] != digest)
        require(not changed,
                f"source files changed during the scenario: {', '.join(changed)}")
        return f"{len(current)} source files byte-identical (sha256) after the scenario"

    # -- Steps N and O ------------------------------------------------------

    def test_suite(self) -> Check:
        if not self.with_tests:
            return Check("N", "test_suite", Outcome.SKIPPED,
                         "not run; pass --with-tests, or run make test separately")
        code, detail = self.test_runner()
        return Check("N", "test_suite", Outcome.PASS if code == 0 else Outcome.FAIL, detail)

    @staticmethod
    def clean_rebuild() -> Check:
        return Check("O", "clean_rebuild", Outcome.OPERATOR,
                     "operator step: make docker-down && make docker-build && make docker-up, "
                     "then run this script again; the dataset, canonical ids and record hashes "
                     "are deterministic, so the report must be identical")


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def probe(client: httpx.Client) -> None:
    """Fail fast when the API cannot be reached at all."""
    try:
        client.get(f"{API}/health")
    except httpx.HTTPError as exc:
        raise ScenarioAborted(f"the Layer 1 API at {client.base_url} could not be reached "
                              f"({type(exc).__name__}); start it with make docker-up") from None


def run_scenario(
    client: httpx.Client,
    sessions: sessionmaker[Session],
    *,
    with_tests: bool = False,
    page_size: int = DEFAULT_PAGE_SIZE,
    test_runner: Callable[[], tuple[int, str]] | None = None,
    report_line: Callable[[Check], None] | None = None,
) -> Report:
    """Run every acceptance check and return the report."""
    probe(client)
    scenario = Scenario(client, sessions, with_tests=with_tests, page_size=page_size,
                        test_runner=test_runner)
    checks = []
    for check in scenario.checks():
        if report_line is not None:
            report_line(check)
        checks.append(check)
    return Report(tuple(checks))


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Layer 1 acceptance scenario.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"running Layer 1 API (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="per-request timeout in seconds (default: %(default)s)")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE,
                        help="ingestion page size (default: %(default)s)")
    parser.add_argument("--with-tests", action="store_true",
                        help="also run the full test suite (spec Section 20 step N)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not 1 <= args.page_size <= MAX_PAGE_SIZE:
        print(f"verify_layer1: --page-size must be between 1 and {MAX_PAGE_SIZE}",
              file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("verify_layer1: --timeout must be greater than zero", file=sys.stderr)
        return 2
    settings = get_settings()
    try:
        resolve_level(settings.app_log_level)
        resolve_format(settings.log_format)
    except ValueError as exc:
        print(f"verify_layer1: invalid logging settings: {exc}", file=sys.stderr)
        return 2
    engine = create_engine(settings.effective_database_url, pool_pre_ping=True)
    try:
        with (configured_logging(settings.app_log_level, settings.log_format),
              httpx.Client(base_url=args.base_url, timeout=args.timeout) as client):
            report = run_scenario(
                client, sessionmaker(bind=engine, expire_on_commit=False),
                with_tests=args.with_tests, page_size=args.page_size,
                report_line=lambda check: print(check, flush=True),
            )
    except ScenarioAborted as exc:
        print(f"verify_layer1: {exc}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()
    print(report.summary())
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
