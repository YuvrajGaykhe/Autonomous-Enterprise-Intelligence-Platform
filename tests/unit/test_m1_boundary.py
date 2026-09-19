"""
M1 static boundaries: no clock, no model, no writes, no Layer 1 change.

Determinism and the Layer 1 freeze are structural claims, so they are
checked structurally. A later milestone that reaches for datetime.now, an
outbound model client or a session write fails the build here rather than
producing intelligence that two runs disagree about.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INTELLIGENCE_DIR = REPO / "app" / "intelligence"

#: Every clock the package must never read. An assessment is a pure function
#: of its scope, and a clock would make two runs of that scope disagree.
FORBIDDEN_CLOCKS = {"now", "today", "utcnow", "utcfromtimestamp", "fromtimestamp", "time",
                    "monotonic", "perf_counter"}
FORBIDDEN_CLOCK_MODULES = {"time"}
#: Sources of non-determinism other than a clock.
FORBIDDEN_RANDOM_MODULES = {"random", "secrets", "uuid"}
#: Infrastructure VS-01 states it does not use (plan A13, A22, A31). None of
#: it is a dependency of this project, and none may become one by accident.
FORBIDDEN_INFRASTRUCTURE = {
    "openai", "anthropic", "langchain", "langgraph", "crewai", "llama_index", "transformers",
    "torch", "tensorflow", "sklearn", "sentence_transformers", "neo4j", "py2neo", "redis",
    "chromadb", "qdrant_client", "pinecone", "faiss", "weaviate", "pgvector", "milvus",
    "httpx", "requests", "aiohttp", "urllib3",
}
#: The only Layer 1 surface the intelligence foundation is allowed to read.
#: Widening this set is a deliberate act, not a side effect of an import.
ALLOWED_LAYER1_IMPORTS = {
    "app.normalization.config",
    "app.normalization.contract",
    "app.persistence.models",
    "app.persistence.repositories.canonical",
}
#: Session methods that would write. The package reads; the caller owns the
#: transaction, matching the repository convention.
FORBIDDEN_WRITES = {"commit", "rollback", "add", "add_all", "flush", "delete", "merge",
                    "begin", "begin_nested", "close", "bulk_save_objects"}


def _modules():
    for path in sorted(INTELLIGENCE_DIR.rglob("*.py")):
        yield path.relative_to(REPO).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def _imported_modules(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _imported_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_the_scanned_package_exists_and_is_not_empty():
    """A scan that silently matches nothing proves nothing."""
    scanned = {name for name, _ in _modules()}

    assert scanned >= {
        "app/intelligence/__init__.py", "app/intelligence/contract.py",
        "app/intelligence/scope.py", "app/intelligence/money.py",
        "app/intelligence/timeutil.py", "app/intelligence/config.py",
        "app/intelligence/errors.py"}


def test_no_module_reads_a_clock():
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_CLOCKS, f"{name}: .{node.attr}"
            if isinstance(node, ast.Name):
                assert node.id not in FORBIDDEN_CLOCKS, f"{name}: {node.id}"
        for module in _imported_modules(tree):
            assert module.split(".")[0] not in FORBIDDEN_CLOCK_MODULES, f"{name}: {module}"
        for imported in _imported_names(tree):
            assert imported.rsplit(".", 1)[-1] not in FORBIDDEN_CLOCKS, f"{name}: {imported}"


def test_the_clock_scan_would_catch_a_reintroduced_now():
    """The guard above is only worth having if it fails on the thing it forbids."""
    tree = ast.parse("from datetime import datetime\nx = datetime.now()\n")
    offenders = [node.attr for node in ast.walk(tree)
                 if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_CLOCKS]

    assert offenders == ["now"]


def test_no_module_introduces_randomness_or_a_generated_identifier():
    for name, tree in _modules():
        for module in _imported_modules(tree):
            assert module.split(".")[0] not in FORBIDDEN_RANDOM_MODULES, f"{name}: {module}"


def test_no_module_reaches_for_a_model_a_graph_database_or_a_vector_store():
    for name, tree in _modules():
        for module in _imported_modules(tree):
            assert module.split(".")[0] not in FORBIDDEN_INFRASTRUCTURE, f"{name}: {module}"


def test_the_package_reads_only_the_named_layer_1_surface():
    for name, tree in _modules():
        for module in _imported_modules(tree):
            if not module.startswith("app.") or module.startswith("app.intelligence"):
                continue
            assert module in ALLOWED_LAYER1_IMPORTS, f"{name}: {module}"


def test_the_package_never_writes_and_never_owns_a_transaction():
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_WRITES, f"{name}: .{node.attr}"


def test_the_package_uses_no_textual_sql():
    for name, tree in _modules():
        assert "sqlalchemy.text" not in _imported_names(tree), name
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"text", "exec_driver_sql"}, f"{name}: .{node.attr}"


def test_the_package_does_not_print_or_log():
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id != "print", name
        for module in _imported_modules(tree):
            assert module.split(".")[0] != "logging", f"{name}: {module}"


def test_every_read_of_a_canonical_table_is_explicitly_ordered():
    """PostgreSQL guarantees no row order, and an unordered fingerprint is not reproducible."""
    source = (INTELLIGENCE_DIR / "scope.py").read_text(encoding="utf-8")
    selects = source.count("select(")

    assert selects >= 2
    assert source.count(".order_by(") + source.count("func.max(") == selects


def test_nothing_outside_the_package_depends_on_it_yet():
    """M1's rollback is deleting the package, which only holds while nothing imports it."""
    importers = []
    for directory in ("app", "scripts", "migrations", "docker"):
        for path in sorted((REPO / directory).rglob("*.py")):
            if path.is_relative_to(INTELLIGENCE_DIR):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if any(module.startswith("app.intelligence") for module in _imported_modules(tree)):
                importers.append(path.relative_to(REPO).as_posix())

    assert importers == []


@pytest.mark.parametrize("path", [
    "config/mappings/normalization.yaml",
    "config/mappings/csv_demo.yaml",
    "config/validation/quality_gate.yaml",
])
def test_layer_2_configuration_lives_beside_layer_1s_and_does_not_replace_it(path):
    assert (REPO / path).is_file()
    assert (REPO / "config" / "intelligence" / "risk_rules.yaml").is_file()
