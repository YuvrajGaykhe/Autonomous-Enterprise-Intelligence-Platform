"""
M5 static boundaries: no writes, no clock, no linker, no decision layer.

§0.4.3 says "M5 never persists" and §0.4.7 says the factory owns no
transaction. Both are structural claims, so both are checked structurally,
mirroring M1's and M2's scans rather than inventing a style: a later edit that
reaches for `session.commit`, `datetime.now` or `derive_and_persist` fails the
build here instead of producing an assessment that writes, drifts or derives
evidence twice.

The scans that matter carry a companion test proving they would catch a
reintroduction, because a scan that silently matches nothing proves nothing.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from app.core.database import Base

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
ANALYSTS_DIR = REPO / "app" / "analysts"

#: Every module of the package, so the scans below cannot go vacuous.
M5_MODULES = {
    "app/analysts/__init__.py",
    "app/analysts/base.py",
    "app/analysts/commercial.py",
    "app/analysts/context.py",
    "app/analysts/support_risk.py",
}

#: The one module §0.4.7 permits a Session or an ORM model.
FACTORY_MODULE = "app/analysts/context.py"

#: The two modules §A14 gives a context and nothing else.
ANALYST_MODULES = ("app/analysts/commercial.py", "app/analysts/support_risk.py")

#: Session methods that would write or own a transaction. The package reads;
#: the caller owns the transaction, matching the repository convention and
#: M1's own scan (test_m1_boundary.py).
FORBIDDEN_WRITES = {"commit", "rollback", "add", "add_all", "flush", "delete", "merge",
                    "begin", "begin_nested", "close", "bulk_save_objects"}

#: Deriving links is the assessment run's, which is M7's (§0.4.3). This is
#: what makes "M5 never derives and never writes" executable rather than
#: promised, and it mirrors test_no_m4_module_invokes_the_s14_composition.
FORBIDDEN_LINKER_CALLS = {"derive_and_persist", "derive_links", "persist_links"}

#: M4 owns building both, and test_m4_boundary.py pins the single place each
#: is built. M5 reads LinkedDocument values; it constructs neither (§0.4.7).
FORBIDDEN_CONSTRUCTIONS = {"DerivedLink", "LinkedDocument"}

#: Every clock the package must never read: an assessment is a function of
#: its scope, and a clock would make two runs of that scope disagree (§A24).
FORBIDDEN_CLOCKS = {"now", "today", "utcnow", "utcfromtimestamp", "fromtimestamp", "time",
                    "monotonic", "perf_counter"}
FORBIDDEN_CLOCK_MODULES = {"time"}
FORBIDDEN_RANDOM_MODULES = {"random", "secrets", "uuid"}

#: Infrastructure VS-01 states it does not use (§A13, §A22, §A31), and the
#: outbound clients §A22's no-executor row forbids this package.
FORBIDDEN_INFRASTRUCTURE = {
    "openai", "anthropic", "langchain", "langgraph", "crewai", "llama_index", "transformers",
    "torch", "tensorflow", "sklearn", "sentence_transformers", "neo4j", "py2neo", "redis",
    "chromadb", "qdrant_client", "pinecone", "faiss", "weaviate", "pgvector", "milvus",
    "httpx", "requests", "aiohttp", "urllib3", "smtplib",
}

#: M5 is upstream of the decision layer. Importing it would reverse the DAG.
FORBIDDEN_DOWNSTREAM = {"app.decisions"}

#: The packages that must not learn about M5. M2's is already asserted from
#: its own side (test_m2_boundary.py:30); M1, M3 and M4 gain the mirror here.
UPSTREAM_DIRS = ("app/intelligence", "app/relationships", "app/evidence", "app/persistence")

#: Every Layer 1 ORM model, read off the registry rather than listed, so a
#: model added later is covered without editing this test.
ORM_MODELS = {mapper.class_.__name__ for mapper in Base.registry.mappers}


def _modules():
    for path in sorted(ANALYSTS_DIR.rglob("*.py")):
        yield path.relative_to(REPO).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def _imported_modules(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _imported_names(tree: ast.AST) -> set[tuple[str, str]]:
    """(module, name) for every from-import, so a re-export can be followed."""
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


def _tree_of(name: str) -> ast.AST:
    return ast.parse((REPO / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Non-vacuity
# ---------------------------------------------------------------------------


def test_the_scanned_package_exists_and_is_not_empty():
    """A scan that silently matches nothing proves nothing."""
    assert {name for name, _ in _modules()} == M5_MODULES


# ---------------------------------------------------------------------------
# No writes, no transaction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_WRITES))
def test_no_module_writes_or_owns_a_transaction(forbidden):
    """
    §0.4.7: the factory receives a session and never creates, opens, commits,
    rolls back or closes one. M5's *Non-goals* name persistence, so this is
    the assertion that makes them executable.
    """
    for name, tree in _modules():
        assert forbidden not in _called_names(tree), f"{name}: .{forbidden}()"


def test_the_write_scan_would_catch_a_reintroduced_commit():
    assert "commit" in _called_names(ast.parse("def run(session):\n    session.commit()\n"))


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_LINKER_CALLS))
def test_no_module_invokes_the_linker(forbidden):
    """
    §0.4.8 criterion 12. Deriving is the assessment run's, which is M7's
    (§0.4.3); a factory that derived would make every M5 read a write.
    """
    for name, tree in _modules():
        assert forbidden not in _called_names(tree), f"{name}: {forbidden}()"
        for module, imported in _imported_names(tree):
            assert imported != forbidden, f"{name}: imports {forbidden} from {module}"


def test_the_linker_scan_would_catch_a_reintroduced_derivation():
    tree = ast.parse("from app.evidence import derive_and_persist\nderive_and_persist(s, k)\n")

    assert "derive_and_persist" in _called_names(tree)
    assert ("app.evidence", "derive_and_persist") in _imported_names(tree)


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_CONSTRUCTIONS))
def test_no_module_constructs_an_m4_link_type(forbidden):
    """
    M4 owns building both, and its own boundary test pins the single place
    each is built. M5 reads what documents_for() returns and builds neither.
    """
    for name, tree in _modules():
        assert forbidden not in _called_names(tree), f"{name}: {forbidden}(...)"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_no_module_reads_a_clock():
    """§A24: two runs of one scope must not disagree."""
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_CLOCKS, f"{name}: .{node.attr}"
            if isinstance(node, ast.Name):
                assert node.id not in FORBIDDEN_CLOCKS, f"{name}: {node.id}"
        for module in _imported_modules(tree):
            assert module.split(".")[0] not in FORBIDDEN_CLOCK_MODULES, f"{name}: {module}"
        for _, imported in _imported_names(tree):
            assert imported not in FORBIDDEN_CLOCKS, f"{name}: {imported}"


def test_the_clock_scan_would_catch_a_reintroduced_now():
    tree = ast.parse("import datetime\nx = datetime.datetime.now()\n")

    assert any(
        isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_CLOCKS
        for node in ast.walk(tree)
    )


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


# ---------------------------------------------------------------------------
# The dependency direction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_DOWNSTREAM))
def test_no_module_imports_the_decision_layer(forbidden):
    """
    §0.4.5: M5 is upstream of M6 and M7. app.decisions does not exist yet, so
    this assertion is what keeps it from arriving by accident.
    """
    for name, tree in _modules():
        for module in _imported_modules(tree):
            assert not module.startswith(forbidden), f"{name}: {module}"


def test_the_decision_layer_does_not_exist_yet():
    """M5 ends before M6 begins; the scan above would otherwise read as moot."""
    assert not (REPO / "app" / "decisions").exists()


@pytest.mark.parametrize("directory", UPSTREAM_DIRS)
def test_no_upstream_package_imports_the_analyst_package(directory):
    """
    The mirror of M2's own FORBIDDEN_PACKAGES assertion, extended to M1, M3,
    M4 and Layer 1's persistence. app.analysts is a leaf: nothing imports it,
    so adding it reverses no edge and creates no cycle (§0.4.5).
    """
    for path in sorted((REPO / directory).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _imported_modules(tree):
            assert not module.startswith("app.analysts"), f"{path}: {module}"


def test_the_package_reads_m3_by_submodule_and_not_through_the_initialiser():
    """
    §0.2.3's import-initialiser rule: M3 is reached as
    app.intelligence.signals, and app.intelligence's __init__ must continue
    not to re-export it.
    """
    intelligence = importlib.import_module("app.intelligence")

    assert not hasattr(intelligence, "compute_signals")
    assert not hasattr(intelligence, "NEGOTIATION_STAGE")
    for name, tree in _modules():
        for module, imported in _imported_names(tree):
            if imported in {"compute_signals", "NEGOTIATION_STAGE", "assign_band"}:
                assert module.startswith("app.intelligence."), f"{name}: {module}"


# ---------------------------------------------------------------------------
# The analysts get a context and nothing else
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ANALYST_MODULES)
def test_an_analyst_module_imports_neither_a_session_nor_an_orm_model(name):
    """
    §A14: "constructed with a pre-built, typed context object and never given
    a database session". Scope is enforced by construction, so the assertion
    is on the import graph rather than on a runtime check.
    """
    tree = _tree_of(name)

    for module in _imported_modules(tree):
        assert not module.startswith("sqlalchemy"), f"{name}: {module}"
        assert not module.startswith("app.persistence"), f"{name}: {module}"
    for _, imported in _imported_names(tree):
        assert imported != "Session", name
        assert imported not in ORM_MODELS, f"{name}: {imported}"


@pytest.mark.parametrize("name", ANALYST_MODULES)
def test_an_analyst_module_imports_no_session_through_a_sibling(name):
    """
    §0.4.5's "directly or transitively through an app.analysts sibling". The
    analyst modules do import context.py -- they must, for the context types
    -- so the check follows each imported name to what it is actually bound
    to rather than forbidding the import.
    """
    for module, imported in _imported_names(_tree_of(name)):
        if not module.startswith("app.analysts"):
            continue
        value = getattr(importlib.import_module(module), imported)
        assert getattr(value, "__name__", None) != "Session", f"{name}: {imported}"
        assert getattr(value, "__name__", None) not in ORM_MODELS, f"{name}: {imported}"


def test_only_the_factory_module_reaches_layer_1_persistence():
    """
    §0.4.7: context.py is the one module permitted a Session or an ORM model,
    and the allowance is named per module rather than granted to the package.
    """
    reaching = [
        name for name, tree in _modules()
        if any(
            module.startswith(("sqlalchemy", "app.persistence"))
            for module in _imported_modules(tree)
        )
    ]

    assert reaching == [FACTORY_MODULE]


def test_no_module_reads_a_tickets_status_column():
    """
    §0.4.2: open-ness is the resolution date's answer, never `status`'s. M2's
    status-based rule is as_of-insensitive and would disagree with the
    signals beside it, so this package must not reach for it even once.
    """
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr != "status", f"{name}: .status"
        for _, imported in _imported_names(tree):
            assert imported != "OPEN_TICKET_STATUS", f"{name}: {imported}"
