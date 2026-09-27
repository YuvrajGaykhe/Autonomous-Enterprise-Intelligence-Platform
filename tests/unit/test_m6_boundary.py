"""
M6 static boundaries: exactly four modules, pure, money-blind, and downstream.

§0.5.13 is a list of structural claims, so each is checked structurally,
mirroring the M1, M4 and M5 scans rather than inventing a style:

    Where M6 exists     app/decisions/ holds exactly policy, conflicts,
                        reconciler and the initialiser -- no M7 module --
                        and nothing outside it imports the package.
    Pure                no session, no ORM model, no SQLAlchemy, no write, no
                        clock, no random source, no log line.
    Downstream only     it reads M1's contract, M3's ranking key and M5's
                        analysts. It never reads M2 or M4: a policy document
                        is cited by id, and membership was settled before
                        the contexts were built. So it cannot derive or
                        persist a link, and cannot build one.
    Money-blind         it reads no amount, currency, exposure, probability,
                        stage, deal list or contract-document id -- the
                        attributes a blended score would need.
    No TOPIC            the reserved M1 vocabulary §0.3.1 removed stays out.

Code is scanned with docstrings stripped (M4's `_code()`), because these
modules explain at length what they do not do. Every scan that could go
vacuous has a companion proving it would catch a reintroduction.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from app.core.database import Base

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
DECISIONS_DIR = REPO / "app" / "decisions"

#: §0.5.14 IN-SCOPE 1: exactly these, and no other.
M6_MODULES = {
    "app/decisions/__init__.py",
    "app/decisions/conflicts.py",
    "app/decisions/policy.py",
    "app/decisions/reconciler.py",
}

#: M7's three modules (§0.6.2). They sit beside M6's in app/decisions/, and
#: every scan below still covers M6's four modules only (§0.6.1 T-M7-1 (a)).
M7_MODULES = {
    "app/decisions/assessment.py",
    "app/decisions/payload.py",
    "app/decisions/brief.py",
}

#: M8's one module (§0.7.4). Like M7's, it sits beside M6's in app/decisions/,
#: and every scan below still covers M6's four modules only (§0.7.12 T-M8-1 (a)).
M8_MODULES = {"app/decisions/approval.py"}

#: Every module named after M6 (Part B). No M6 module may import one, M7's
#: included (§0.6.1 T-M7-1 (d)).
POST_M6_MODULES = ("assessment", "payload", "brief", "templates", "approval")

#: The two configuration files M6 adds.
M6_CONFIG = ("config/intelligence/action_catalogue.yaml",
             "config/intelligence/conflict_policy.yaml")

FORBIDDEN_WRITES = {"commit", "rollback", "add", "add_all", "flush", "delete", "merge",
                    "begin", "begin_nested", "close", "bulk_save_objects"}
FORBIDDEN_LINKER_CALLS = {"derive_and_persist", "derive_links", "persist_links"}
FORBIDDEN_LINK_TYPES = {"DerivedLink", "LinkedDocument"}
FORBIDDEN_CLOCKS = {"now", "today", "utcnow", "utcfromtimestamp", "fromtimestamp", "time",
                    "monotonic", "perf_counter"}
FORBIDDEN_CLOCK_MODULES = {"time", "datetime"}
FORBIDDEN_RANDOM_MODULES = {"random", "secrets", "uuid"}
FORBIDDEN_INFRASTRUCTURE = {
    "openai", "anthropic", "langchain", "langgraph", "crewai", "llama_index", "transformers",
    "torch", "tensorflow", "sklearn", "sentence_transformers", "neo4j", "py2neo", "redis",
    "chromadb", "qdrant_client", "pinecone", "faiss", "weaviate", "pgvector", "milvus",
    "httpx", "requests", "aiohttp", "urllib3", "smtplib",
}
#: Packages M6 must not import: persistence, the database, M2, M4, the API.
FORBIDDEN_PACKAGES = ("sqlalchemy", "app.persistence", "app.core.database",
                      "app.relationships", "app.evidence", "app.api", "app.ingestion",
                      "app.connectors")
#: The deal and money attributes a blended score would need (§0.5.13).
MONEY_ATTRIBUTES = {"amount", "currency", "exposure_by_currency", "probability", "stage",
                    "active_deals", "contract_document_ids"}
#: The TOPIC vocabulary §0.3.1 removed from VS-01.
TOPIC_NAMES = ("TOPIC", "DERIVED_TOPIC_MATCH", "LinkBasis", "SUPPORTING")

ORM_MODELS = {mapper.class_.__name__ for mapper in Base.registry.mappers}


def _modules():
    for name in sorted(M6_MODULES):
        yield name, ast.parse((REPO / name).read_text(encoding="utf-8"))


def _imported_modules(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _imported_names(tree: ast.AST) -> set[tuple[str, str]]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.update((node.module, alias.name) for alias in node.names)
    return names


def _called_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def _attributes(tree: ast.AST) -> set[str]:
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def _code(tree: ast.AST) -> str:
    """The module's code with every docstring removed, so only code is searched."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef
                          | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = node.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


# ---------------------------------------------------------------------------
# Where M6 exists
# ---------------------------------------------------------------------------


def test_the_decision_layer_is_exactly_m6s_four_modules():
    """A scan that silently matches nothing proves nothing, and a fifth module is unauthorised."""
    assert {name for name, _ in _modules()} == M6_MODULES
    assert {
        path.relative_to(REPO).as_posix() for path in DECISIONS_DIR.rglob("*.py")
    } == M6_MODULES | M7_MODULES | M8_MODULES


def test_the_public_surface_is_exactly_the_declared_one():
    """§0.5.7's public API, no more: helpers stay importable from their modules only."""
    decisions = importlib.import_module("app.decisions")
    for submodule in ("assessment", "payload", "brief", "approval"):
        importlib.import_module(f"app.decisions.{submodule}")

    assert sorted(decisions.__all__) == sorted([
        "ActionCatalogue", "CatalogueEntry", "ConflictPolicy", "ConflictRule",
        "ResolutionCondition", "load_action_catalogue", "default_action_catalogue",
        "load_conflict_policy", "default_conflict_policy", "DecisionConfigError",
        "detect_conflicts", "ReconciliationError", "UnresolvableConflictError",
        "reconcile", "order_reconciliations", "Reconciliation", "Worthiness",
    ])
    assert {name for name in vars(decisions) if not name.startswith("_")} == set(
        decisions.__all__) | {"conflicts", "policy", "reconciler", "assessment", "payload",
                              "brief", "approval"}


def test_no_later_milestone_module_exists():
    """
    §0.7.12 T-M8-1 (b): the only directory under app/decisions/, bytecode
    caches aside, is templates/. That keeps the guard against an approval/
    package and extends it to every name; .py files stay guarded by the
    inventory above.
    """
    directories = {
        path.relative_to(DECISIONS_DIR).as_posix() for path in DECISIONS_DIR.rglob("*")
        if path.is_dir() and "__pycache__" not in path.parts
    }

    assert directories == {"templates"}


@pytest.mark.parametrize("path", M6_CONFIG)
def test_the_decision_configuration_exists_beside_the_risk_rules(path):
    assert (REPO / path).is_file()
    assert (REPO / "config" / "intelligence" / "risk_rules.yaml").is_file()


@pytest.mark.parametrize("name", POST_M6_MODULES)
def test_no_m6_module_imports_a_later_milestone(name):
    for module_name, tree in _modules():
        for module in _imported_modules(tree):
            assert module != f"app.decisions.{name}", f"{module_name}: {module}"


def test_nothing_outside_the_package_imports_it():
    """
    §0.5.13's last row, over every code directory: M1-M5, persistence, the API,
    the scripts, the migrations. The assessment run that will import it is M7's.
    M9's acceptance command is its one importer outside app/ (§0.8.9 T-M9-1).
    """
    importers = []
    for directory in ("app", "scripts", "migrations", "docker"):
        for path in sorted((REPO / directory).rglob("*.py")):
            if path.is_relative_to(DECISIONS_DIR):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if any(module.startswith("app.decisions") for module in _imported_modules(tree)):
                importers.append(path.relative_to(REPO).as_posix())

    assert importers == ["app/api/v1/risk.py", "scripts/vs01_acceptance.py"]


def test_the_importer_scan_would_catch_an_upstream_import():
    tree = ast.parse("from app.decisions import reconcile\n")

    assert any(module.startswith("app.decisions") for module in _imported_modules(tree))


# ---------------------------------------------------------------------------
# Pure: no session, no write, no clock, no randomness, no log
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden", FORBIDDEN_PACKAGES)
def test_no_module_imports_persistence_m2_m4_or_the_api(forbidden):
    for name, tree in _modules():
        for module in _imported_modules(tree):
            assert not module.startswith(forbidden), f"{name}: {module}"


def test_no_module_names_a_session_or_an_orm_model():
    for name, tree in _modules():
        for _, imported in _imported_names(tree):
            assert imported != "Session", name
            assert imported not in ORM_MODELS, f"{name}: {imported}"


def test_no_module_imports_a_session_through_a_package_it_reads():
    """The analysts package holds a Session in its factory; nothing M6 imports is one."""
    for name, tree in _modules():
        for module, imported in _imported_names(tree):
            if not module.startswith("app."):
                continue
            value = getattr(importlib.import_module(module), imported)
            assert getattr(value, "__name__", None) != "Session", f"{name}: {imported}"
            assert getattr(value, "__name__", None) not in ORM_MODELS, f"{name}: {imported}"


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_WRITES))
def test_no_module_writes_or_owns_a_transaction(forbidden):
    for name, tree in _modules():
        assert forbidden not in _called_names(tree), f"{name}: .{forbidden}()"


def test_the_write_scan_would_catch_a_reintroduced_commit():
    assert "commit" in _called_names(ast.parse("def run(session):\n    session.commit()\n"))


def test_no_module_reads_a_clock():
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_CLOCKS, f"{name}: .{node.attr}"
            if isinstance(node, ast.Name):
                assert node.id not in FORBIDDEN_CLOCKS, f"{name}: {node.id}"
        for module in _imported_modules(tree):
            assert module.split(".")[0] not in FORBIDDEN_CLOCK_MODULES, f"{name}: {module}"


def test_the_clock_scan_would_catch_a_reintroduced_now():
    tree = ast.parse("import datetime\nx = datetime.datetime.now()\n")

    assert "now" in _attributes(tree)
    assert "datetime" in _imported_modules(tree)


def test_no_module_reaches_a_random_source():
    for name, tree in _modules():
        for module in _imported_modules(tree):
            assert module.split(".")[0] not in FORBIDDEN_RANDOM_MODULES, f"{name}: {module}"


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_INFRASTRUCTURE))
def test_no_module_reaches_for_infrastructure_vs01_does_not_use(forbidden):
    """§A22's no-executor row, and §A13's "no model, no embeddings, no store"."""
    for name, tree in _modules():
        for module in _imported_modules(tree):
            assert module.split(".")[0] != forbidden, f"{name}: {module}"


def test_no_module_logs_or_prints():
    """§0.5.1: §A21's conflict events are the assessment run's, emitted from the result."""
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id != "print", name
        for module in _imported_modules(tree):
            assert module.split(".")[0] != "logging", f"{name}: {module}"
            assert module != "app.core.logging", f"{name}: {module}"


# ---------------------------------------------------------------------------
# No linker, no link, no TOPIC
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_LINKER_CALLS))
def test_no_module_invokes_the_linker(forbidden):
    """§0.4.3: deriving links is the assessment run's, which is M7's."""
    for name, tree in _modules():
        assert forbidden not in _called_names(tree), f"{name}: {forbidden}()"
        for module, imported in _imported_names(tree):
            assert imported != forbidden, f"{name}: imports {forbidden} from {module}"


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_LINK_TYPES))
def test_no_module_names_an_m4_link_type(forbidden):
    """§0.5.4: a policy citation is not a derived link, and M4 alone builds those."""
    for name, tree in _modules():
        assert forbidden not in _code(tree), name


@pytest.mark.parametrize("forbidden", TOPIC_NAMES)
def test_no_module_names_the_topic_vocabulary(forbidden):
    for name, tree in _modules():
        assert forbidden not in _code(tree), name


def test_the_linker_scan_would_catch_a_reintroduced_derivation():
    tree = ast.parse("from app.evidence import derive_and_persist\nderive_and_persist(s, k)\n")

    assert "derive_and_persist" in _called_names(tree)
    assert ("app.evidence", "derive_and_persist") in _imported_names(tree)


def test_the_code_scan_reads_code_and_not_the_docstrings_explaining_it():
    tree = ast.parse('"""No DerivedLink and no TOPIC here."""\nx = DerivedLink(TOPIC)\n')

    assert "DerivedLink" in _code(tree)
    assert "No DerivedLink" not in _code(ast.parse('"""No DerivedLink."""\nx = 1\n'))


# ---------------------------------------------------------------------------
# Money-blind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden", sorted(MONEY_ATTRIBUTES))
def test_no_module_reads_a_monetary_or_deal_attribute(forbidden):
    """
    §0.5.8 and §0.5.9: worthiness reads S11 and S13 as counts, ordering reads
    band, S8 and S4. None of them needs an amount, a currency, a probability,
    a stage, the deal list or a contract document.
    """
    for name, tree in _modules():
        assert forbidden not in _attributes(tree), f"{name}: .{forbidden}"


def test_the_money_scan_would_catch_a_reintroduced_amount():
    tree = ast.parse("key = sum(deal.amount.amount for deal in signals.active_deals)\n")

    assert {"amount", "active_deals"} <= _attributes(tree)


# ---------------------------------------------------------------------------
# One definition of each order
# ---------------------------------------------------------------------------


def test_the_orders_are_called_and_not_restated():
    """
    §0.5.9: M5's position order and M3's customer order are reused, so the
    codebase holds one definition of each and M6 cannot drift from either.
    """
    tree = ast.parse((DECISIONS_DIR / "reconciler.py").read_text(encoding="utf-8"))
    conflicts = ast.parse((DECISIONS_DIR / "conflicts.py").read_text(encoding="utf-8"))

    assert ("app.intelligence.bands", "ranking_key") in _imported_names(tree)
    assert ("app.analysts.base", "order_positions") in _imported_names(tree)
    assert ("app.analysts.base", "order_positions") in _imported_names(conflicts)
    for name, module in _modules():
        defined = {node.name for node in ast.walk(module) if isinstance(node, ast.FunctionDef)}
        assert not defined & {"ranking_key", "order_positions"}, name


def test_m3_is_read_by_submodule_and_not_through_the_initialiser():
    """§0.2.3's import-initialiser rule, which M5 follows too."""
    intelligence = importlib.import_module("app.intelligence")

    assert not hasattr(intelligence, "ranking_key")
    for name, tree in _modules():
        for module, imported in _imported_names(tree):
            if imported in {"ranking_key", "BandAssignment"}:
                assert module == "app.intelligence.bands", f"{name}: {module}"


def test_the_thresholds_stay_m5s():
    """§0.5.2: neither moved nor copied. No M6 module names one."""
    for name, tree in _modules():
        code = _code(tree)
        for threshold in ("ACCELERATE_PROBABILITY_THRESHOLD", "DEDICATED_OWNER_BREACH_THRESHOLD",
                          "PAUSE_BREACH_THRESHOLD"):
            assert threshold not in code, f"{name}: {threshold}"
