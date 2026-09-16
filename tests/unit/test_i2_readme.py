"""
README validation (Task I2).

Spec Section 17 lists what the README must contain, and the Section 20
"Documentation" threshold is that it "enables a new developer to run Layer 1".
A document can only do that while it still describes the system, so these
tests check the README against the code rather than against itself: every
command it prints exists, every route and option it documents is real, every
count it quotes is the count, and every internal link resolves.

They deliberately do not check prose. They check the claims.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

from app.api.errors import ErrorCode
from app.api.v1.schemas import EntityType
from app.main import create_app

REPO = Path(__file__).resolve().parents[2]
README = (REPO / "README.md").read_text(encoding="utf-8")
MAKEFILE = (REPO / "Makefile").read_text(encoding="utf-8")
OPENAPI = create_app().openapi()

#: Every section spec Section 17 requires, plus the prototype's limitations
#: (Section 21: "Claiming production readiness" -> "document limitations").
REQUIRED_SECTIONS = (
    "Architecture",
    "Prerequisites",
    "Environment Setup",
    "Database Migration",
    "Demo Dataset",
    "Ingestion Commands",
    "API Usage Examples",
    "Troubleshooting",
    "Test Commands",
    "Layer 1 Acceptance Checklist",
    "Known Limitations",
)


def _headings() -> list[str]:
    return [line.lstrip("#").strip() for line in README.splitlines() if line.startswith("#")]


def _anchor(heading: str) -> str:
    slug = re.sub(r"[^a-z0-9 -]", "", heading.lower())
    return slug.replace(" ", "-")


def _fenced(language: str = "bash") -> list[str]:
    """Every line inside the README's fenced code blocks of one language."""
    blocks = re.findall(rf"```{language}\n(.*?)```", README, re.DOTALL)
    return [line for block in blocks for line in block.splitlines()]


def verify_layer1_entities() -> tuple[str, ...]:
    """The entity types the acceptance scenario ingests (spec Section 20 step E)."""
    entities: tuple[str, ...] = _load_script("verify_layer1").SCENARIO_ENTITIES
    return entities


def _load_script(name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_the_readme_still_has_every_section_the_spec_requires():
    headings = _headings()

    missing = [section for section in REQUIRED_SECTIONS
               if not any(section in heading for heading in headings)]
    assert missing == []


def test_no_section_is_left_as_a_placeholder():
    for marker in ("To be completed", "TODO", "TBD", "[STUB", "Coming soon"):
        assert marker not in README, f"the README still carries {marker!r}"


def test_the_architecture_section_carries_a_diagram_and_the_repository_layout():
    architecture = README.split("## Architecture", 1)[1].split("\n## ", 1)[0]

    assert "```" in architecture, "spec Section 17 requires an architecture diagram"
    assert "connector" in architecture and "normalize" in architecture
    assert "validate" in architecture and "persist" in architecture
    for directory in ("app/", "config/", "data/", "migrations/", "scripts/", "tests/"):
        assert directory in architecture


def test_every_internal_link_resolves_to_a_heading():
    anchors = {_anchor(heading) for heading in _headings()}

    broken = sorted({target for target in re.findall(r"\]\(#([a-z0-9-]+)\)", README)
                     if target not in anchors})
    assert broken == []


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def test_every_make_target_the_readme_names_exists():
    named = set(re.findall(r"\bmake ([a-z][a-z0-9-]*)", README))

    assert named, "the README names no make targets"
    for target in sorted(named):
        assert re.search(rf"^{re.escape(target)}:", MAKEFILE, re.MULTILINE), \
            f"the README names make {target}, which the Makefile does not define"


def test_every_script_the_readme_names_exists():
    named = set(re.findall(r"scripts/([a-z0-9_]+\.py)", README))

    assert named >= {"seed_demo.py", "ingest_demo.py", "verify_layer1.py"}
    for script in sorted(named):
        assert (REPO / "scripts" / script).is_file()


def test_every_shell_command_the_readme_prints_names_a_real_tool():
    known = {"make", "docker", "cp", "curl", "alembic", "pytest", "python", "python3", "git",
             "source", "psql", "export", "uvicorn", "pip"}

    continued = False
    for line in _fenced():
        command = line.strip()
        was_continued, continued = continued, command.endswith("\\")
        if not command or command.startswith("#") or was_continued:
            continue
        head = command.split()[0].lstrip("$")
        head = head.rsplit("/", 1)[-1] if head.startswith(".venv/") else head
        assert head in known, f"the README prints an unrecognized command: {command}"


def _section(heading: str) -> str:
    return README.split(f"\n## {heading}", 1)[1].split("\n## ", 1)[0]


def _options_table(heading: str) -> set[str]:
    """The options one section documents, from its `Options (...)` table."""
    table = _section(heading).split('Options (pass through `ARGS="..."` with make):', 1)[1]
    return set(re.findall(r"^\| `(--[a-z-]+)", table.split("\n\n", 2)[1], re.MULTILINE))


@pytest.mark.parametrize("heading, script", [
    ("Layer 1 Acceptance Checklist", "verify_layer1"),
    ("Ingestion Commands", "ingest_demo"),
    ("Demo Dataset", "seed_demo"),
])
def test_each_script_documents_exactly_the_options_it_accepts(heading, script):
    accepted = {f"--{name.replace('_', '-')}"
                for name, _ in _load_script(script).parse_args([])._get_kwargs()}

    assert _options_table(heading) == accepted


# ---------------------------------------------------------------------------
# The API contract
# ---------------------------------------------------------------------------


ENTITY_NAMES = {entity.value for entity in EntityType}


def _generic(path: str) -> str:
    """A route with its entity type and path parameters collapsed, as the README writes them."""
    collapsed = "/".join("{entity_type}" if segment in ENTITY_NAMES else segment
                         for segment in path.split("/"))
    return re.sub(r"\{[a-z_]+\}", "{}", collapsed)


def test_every_published_route_is_documented():
    documented = {_generic(path) for path in re.findall(r"`(/api/v1/[a-z0-9/{}_-]*)`", README)}

    for path in OPENAPI["paths"]:
        assert _generic(path) in documented, f"{path} is not documented in the README"


def test_no_route_the_readme_documents_has_been_removed():
    published = {_generic(path) for path in OPENAPI["paths"]}

    for path in set(re.findall(r"`(/api/v1/[a-z0-9/{}_-]*)`", README)):
        assert _generic(path) in published, f"{path} no longer exists"


def test_every_entity_type_the_readme_lists_is_a_canonical_entity_type():
    sentence = README.split("`entity_type` is one of ", 1)[1].split(".", 1)[0]

    assert set(re.findall(r"`([a-z_]+)`", sentence)) == ENTITY_NAMES


def test_every_error_code_in_a_readme_example_is_a_published_code():
    from app.ingestion.errors import IngestionCode
    from app.normalization.errors import ErrorCode as NormalizationCode
    from app.validation.errors import QualityCode, SystemFailureCode

    published = {code.value for enum in (ErrorCode, IngestionCode, NormalizationCode,
                                         QualityCode, SystemFailureCode) for code in enum}
    shown = set(re.findall(r'"code":\s*"([A-Z_]+)"', README))

    assert shown, "the README shows no error codes"
    assert shown <= published, f"the README shows unpublished codes: {sorted(shown - published)}"


def test_every_published_api_error_code_is_documented():
    errors = README.split("### Error responses", 1)[1].split("\n### ", 1)[0]

    missing = sorted(code.value for code in ErrorCode if code.value not in errors)
    assert missing == []


# ---------------------------------------------------------------------------
# Counts the README quotes
# ---------------------------------------------------------------------------


def _collected(path: str) -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
         "--collect-only", path],
        cwd=REPO, capture_output=True, text=True, check=False)
    match = re.search(r"(\d+) tests? collected", completed.stdout)
    assert match, completed.stdout[-500:]
    return int(match.group(1))


def test_the_test_counts_the_readme_quotes_are_the_counts():
    table = README.split("| Layer | Command | Tests | Needs |", 1)[1].split("\n\n", 1)[0]
    quoted = {command.split()[-1]: int(count) for _, command, count in
              (row.strip("| ").split("|")[:3] for row in table.splitlines() if "pytest tests/" in row)
              for command, count in [(command.strip(" `"), count.strip())]}

    assert quoted, "the README quotes no per-layer test counts"
    for path, count in sorted(quoted.items()):
        assert _collected(path) == count, f"{path} no longer holds {count} tests"

    totals = set(re.findall(r"(\d+) tests in four layers", README))
    assert totals == {str(sum(quoted.values()))}, "the README quotes two different totals"


def test_the_demo_dataset_sizes_the_readme_quotes_are_the_sizes():
    seed_demo = _load_script("seed_demo")
    rows = {entity: len(records) for entity, records in seed_demo.build_demo_dataset().items()}

    quoted = README.split("demo dataset holds ", 1)[1].split("\n", 1)[0]
    ingested = sum(count for entity, count in rows.items()
                   if entity in verify_layer1_entities())

    assert quoted == ", ".join(f"{entity} {count}" for entity, count in sorted(rows.items()))
    assert f"{sum(rows.values())} rows in all" in README
    assert f"ingests the {ingested} belonging to its five entity types" in README


@pytest.mark.parametrize("tool, package, command, quoted", [
    ("ruff", "ruff", ["-m", "ruff", "check", "app/", "tests/", "scripts/"],
     r"`ruff check app/\s+tests/ scripts/` reports (\d+) findings"),
    ("mypy", "mypy", ["-m", "mypy", "app/"], r"`mypy app/` reports (\d+)\s+errors"),
])
def test_the_lint_counts_the_readme_quotes_are_the_counts(tool, package, command, quoted):
    """Quoted with the tool versions they were measured with, so a bump is not a failure."""
    version = importlib.metadata.version(package)
    if f"{tool} {version}" not in README:
        pytest.skip(f"the README quotes a different {tool} version than the installed {version}")

    completed = subprocess.run([sys.executable, *command], cwd=REPO, capture_output=True,
                               text=True, check=False)
    quotation = re.search(quoted, README)
    assert quotation is not None, f"the README no longer quotes a {tool} count"
    found = re.search(r"Found (\d+) (?:errors|error)", completed.stdout)
    assert found is not None, completed.stdout[-500:]

    assert int(found.group(1)) == int(quotation.group(1))


# ---------------------------------------------------------------------------
# The acceptance checklist
# ---------------------------------------------------------------------------


def test_the_example_report_matches_what_the_command_prints():
    verify_layer1 = _load_script("verify_layer1")
    example = [line for line in README.splitlines() if line.startswith("verify-layer1: ")]

    assert len(example) == 11, "the example report must show ten checks and the summary"
    reported = [line.split()[1:3] for line in example[:-1]]
    assert [tuple(pair) for pair in reported] == [
        ("A-C", "stack_ready"), ("D", "demo_dataset"), ("E-F", "ingestion"),
        ("G-H", "api_query"), ("I-J", "idempotency"), ("K-L", "validation"),
        ("M", "connector_health"), ("A-M", "read_only"), ("N", "test_suite"),
        ("O", "clean_rebuild")]
    assert example[-1] == verify_layer1.Report(()).summary().replace(
        "0 passed", "8 passed").replace("0 skipped", "1 skipped").replace(
        "0 operator", "1 operator")


def test_the_acceptance_section_documents_every_threshold_of_the_spec():
    checklist = README.split("## Layer 1 Acceptance Checklist", 1)[1].split("\n## ", 1)[0]

    for threshold in ("Build", "Startup", "Migration", "Ingestion", "Idempotency", "Traceability",
                      "Validation", "API", "Safety", "Tests", "Reproducibility", "Documentation"):
        assert f"| {threshold} |" in checklist, f"the {threshold} threshold is not documented"
    assert "make verify-layer1" in checklist
    assert "`0` every executed check passed" in checklist


def test_the_acceptance_section_does_not_claim_the_two_operator_steps_are_automatic():
    checklist = README.split("## Layer 1 Acceptance Checklist", 1)[1].split("\n## ", 1)[0]

    assert "--with-tests" in checklist
    assert "Steps N and O are the two the command does not perform for you" in checklist


# ---------------------------------------------------------------------------
# Troubleshooting and limitations
# ---------------------------------------------------------------------------


def test_troubleshooting_describes_failures_the_system_can_actually_produce():
    section = README.split("## Troubleshooting", 1)[1].split("\n## ", 1)[0]

    assert section.count("| Symptom | Cause | Fix |") >= 3
    for message in ("could not be reached (ConnectError)",
                    "invalid logging settings: APP_LOG_LEVEL must be one of",
                    "connector health check failed",
                    "uq_customers_source_identity",
                    "No such file or directory"):
        assert message in section, f"troubleshooting no longer mentions {message!r}"


@pytest.mark.parametrize("message, module", [
    ("could not be reached (ConnectError)", "scripts/verify_layer1.py"),
    ("invalid logging settings", "scripts/verify_layer1.py"),
    ("connector health check failed", "app/ingestion/orchestrator.py"),
])
def test_every_quoted_failure_message_is_one_the_code_emits(message, module):
    assert message.replace("(ConnectError)", "").strip() in (
        REPO / module).read_text(encoding="utf-8")


def test_the_readme_calls_layer_1_a_prototype_and_lists_its_limits():
    """Spec Section 21 rejects "claiming production readiness"."""
    limitations = README.split("## Known Limitations", 1)[1].split("\n## ", 1)[0]

    assert "prototype" in limitations
    assert "No authentication" in limitations
    assert "Full sync only" in limitations
    assert "No LLM is used" in limitations
    assert "production" in limitations


# ---------------------------------------------------------------------------
# The examples
# ---------------------------------------------------------------------------


def _query_parameters(path: str) -> set[str]:
    operation = OPENAPI["paths"][path]["get"]
    return {parameter["name"] for parameter in operation.get("parameters", [])
            if parameter["in"] == "query"}


def test_every_query_parameter_a_readme_example_uses_is_a_real_parameter():
    by_generic = {_generic(path): path for path in OPENAPI["paths"]}
    examples = re.findall(r"curl '?http://localhost:8000(/api/v1/[^\s'?]+)\?([^\s']+)'?", README)

    assert examples, "the README shows no parameterised requests"
    for path, query in examples:
        # README examples abbreviate identifiers, e.g. /ingestion/runs/5f0c.../errors.
        concrete = "/".join("{id}" if "..." in segment else segment
                            for segment in path.split("/"))
        published = by_generic.get(_generic(concrete))
        assert published is not None, f"{path} is not a published route"
        for parameter in (pair.split("=")[0] for pair in query.split("&")):
            assert parameter in _query_parameters(published), \
                f"{path} has no {parameter} parameter"


def test_the_health_example_shows_the_fields_the_api_answers_with():
    from fastapi.testclient import TestClient

    example = re.search(r"# (\{\"status\": \"healthy\".*?\})\n", README)
    assert example is not None, "the README no longer shows a health response"

    with TestClient(create_app(sessions=_no_database())) as client:
        schema = OPENAPI["components"]["schemas"]["HealthResponse"]
        assert set(re.findall(r'"([a-z_]+)":', example.group(1))) == (
            set(schema["properties"]) | {"database"})
        assert client.get("/api/v1/health").status_code in (200, 503)


def _no_database():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=create_engine("postgresql://nobody:nobody@127.0.0.1:1/absent",
                                           connect_args={"connect_timeout": 1}))


def test_every_make_recipe_that_runs_python_uses_the_project_virtualenv():
    """The README's local-development flow is make install and then any other target."""
    tools = ("python", "python3", "pytest", "alembic", "ruff", "mypy", "black", "pip")

    for line in MAKEFILE.splitlines():
        if not line.startswith("\t"):
            continue
        command = line.lstrip("\t").lstrip("@").split()
        if command and command[0] in tools:
            assert command[0] == "python3" and "venv" in line, \
                f"the Makefile runs {command[0]} outside the project virtualenv: {line.strip()}"
