"""
M2 static boundaries: no M4, no derived link, no document edge, no writes.

The M2/M4 boundary is a structural claim, so it is checked structurally.
Plan A9.2 names the trap these guard: policy_documents() means M2 reads the
documents table, and an implementer who notices that can talk themselves
into "M2 already touches documents, so linking them to a customer is in
scope". Prose cannot fail a build. These do.

Invariants asserted here: B3, B4, B6 and B9(a). B1, B2, B5, B7, B8, B9(b)
and B10 need real rows and live in tests/integration/test_m2_relationships.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.intelligence import EdgeBasis
from app.relationships import EDGE_SPECS, ISOLATED_ENTITIES, EdgeType

REPO = Path(__file__).resolve().parents[2]
RELATIONSHIPS_DIR = REPO / "app" / "relationships"

#: The package M2 must never reach, by any import path. app/evidence reads
#: app/relationships; the reverse edge would make the DAG a cycle and would
#: let a signal be derived from a derived document link.
FORBIDDEN_PACKAGES = {"app.evidence", "app.analysts", "app.decisions"}
#: Names that only a linker has. M2 constructs no DerivedLink and invents no
#: linker_version, which does not exist until M4.
FORBIDDEN_LINK_NAMES = {"DerivedLink", "LinkBasis", "LinkConfidence"}
FORBIDDEN_LINK_FIELDS = {"linker_version", "matched_token", "match_start", "match_end"}
#: A relationship query never matches text. A function named for matching in
#: this package is either a linker or a misnomer, and both fail the build.
FORBIDDEN_FUNCTION_STEMS = ("link", "match", "mention", "similar", "embed")
#: Clocks and randomness: a relationship is a pure function of Layer 1 rows.
FORBIDDEN_CLOCKS = {"now", "today", "utcnow", "utcfromtimestamp", "fromtimestamp",
                    "monotonic", "perf_counter"}
FORBIDDEN_NONDETERMINISM = {"random", "secrets", "uuid", "time"}
#: Infrastructure VS-01 states it does not use (plan A13, A22, A31).
FORBIDDEN_INFRASTRUCTURE = {
    "openai", "anthropic", "langchain", "langgraph", "crewai", "llama_index", "transformers",
    "torch", "tensorflow", "sklearn", "sentence_transformers", "neo4j", "py2neo", "redis",
    "chromadb", "qdrant_client", "pinecone", "faiss", "weaviate", "pgvector", "milvus",
    "httpx", "requests", "aiohttp", "urllib3",
}
#: The only surface M2 reads. Widening this set is a deliberate act.
ALLOWED_IMPORTS = {
    "app.intelligence",
    "app.intelligence.errors",
    "app.persistence.models",
    "app.persistence.repositories.canonical",
}
#: Session methods that would write. M2 reads; the caller owns the transaction.
FORBIDDEN_WRITES = {"commit", "rollback", "add", "add_all", "flush", "delete", "merge",
                    "begin", "begin_nested", "close", "bulk_save_objects"}
#: A lookup on the unique source identity returns at most one row, so it has
#: no order to fix. Every other select in the package is explicitly ordered.
UNORDERED_SELECT_EXEMPTIONS = {"queries.py::_require_customer"}


def _modules():
    for path in sorted(RELATIONSHIPS_DIR.rglob("*.py")):
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
            names.update(alias.name for alias in node.names)
    return names


def _transitive_app_imports(start: Path) -> set[str]:
    """Every app.* module reachable from a package, following imports."""
    seen: set[str] = set()
    modules = {path.relative_to(REPO).as_posix().removesuffix(".py").replace("/", ".")
               for path in sorted(start.rglob("*.py"))}
    queue = list(modules)
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        path = REPO / (module.replace(".", "/") + ".py")
        package_init = REPO / (module.replace(".", "/") + "/__init__.py")
        target = path if path.is_file() else package_init
        if not target.is_file():
            continue
        tree = ast.parse(target.read_text(encoding="utf-8"))
        for imported in _imported_modules(tree):
            if imported.startswith("app."):
                queue.append(imported)
    return seen


def test_the_scanned_package_exists_and_is_not_empty():
    """A scan that silently matches nothing proves nothing."""
    scanned = {name for name, _ in _modules()}

    assert scanned == {
        "app/relationships/__init__.py", "app/relationships/model.py",
        "app/relationships/edges.py", "app/relationships/queries.py",
        "app/relationships/errors.py"}


# --- B9(a): no document edge exists -----------------------------------------

def test_no_modelled_edge_touches_a_document():
    """B9(a). Document isolation is the whole M2/M4 boundary, in one assertion."""
    for edge_type, spec in EDGE_SPECS.items():
        assert spec.source_entity not in ISOLATED_ENTITIES, edge_type
        assert spec.target_entity not in ISOLATED_ENTITIES, edge_type
        assert spec.carrier_entity not in ISOLATED_ENTITIES, edge_type


def test_document_owned_by_is_absent_by_name():
    """B9(a). The removed edge must not come back under its own name."""
    names = {str(edge_type) for edge_type in EDGE_SPECS}

    assert "document_owned_by" not in names
    assert not hasattr(EdgeType, "DOCUMENT_OWNED_BY")
    for name, _tree in _modules():
        source = (REPO / name).read_text(encoding="utf-8")
        occurrences = source.count("document_owned_by")
        commentary = sum(1 for line in source.splitlines()
                         if "document_owned_by" in line and line.lstrip().startswith("#"))
        assert occurrences == commentary, f"{name}: document_owned_by outside a comment"


def test_the_edge_inventory_is_exactly_the_seven_the_plan_models():
    """Not a superset and not a subset: an eighth edge is a scope change."""
    assert {str(edge_type) for edge_type in EDGE_SPECS} == {
        "customer_has_ticket", "customer_has_deal", "customer_has_project",
        "customer_owned_by", "ticket_assigned_to", "employee_reports_to", "deal_owned_by"}


def test_deal_owned_by_is_modelled_and_is_a_source_key_join():
    """The v2.2 decision: modelled substrate, not a query's return value."""
    spec = EDGE_SPECS[EdgeType.DEAL_OWNED_BY]

    assert spec.basis is EdgeBasis.SOURCE_KEY_JOIN
    assert spec.carrier_field == "deals.owner_source_id"
    assert (spec.source_entity, spec.target_entity) == ("deals", "employees")


def test_no_query_returns_the_deal_owner():
    """
    The v2.2 decision forbids inventing a VS-01 consumer for deal_owned_by.

    Its correctness is proved by B10 against the edge builder. A query that
    named it would be the retrofit the decision exists to prevent.
    """
    source = (RELATIONSHIPS_DIR / "queries.py").read_text(encoding="utf-8")
    code_lines = [line for line in source.splitlines()
                  if not line.lstrip().startswith("#")]
    body = "\n".join(code_lines).split('"""')
    executable = "".join(body[::2])

    assert "DEAL_OWNED_BY" not in executable
    assert "deal_owned_by" not in executable


# --- B3: no derived link ----------------------------------------------------

def test_no_module_constructs_a_derived_link():
    """B3. A DerivedLink needs a linker_version, which does not exist until M4."""
    for name, tree in _modules():
        imported = _imported_names(tree)
        assert not (imported & FORBIDDEN_LINK_NAMES), f"{name}: {imported & FORBIDDEN_LINK_NAMES}"
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in FORBIDDEN_LINK_NAMES, f"{name}: {node.func.id}()"


def test_no_module_binds_a_linker_field():
    """B3. matched_token, match offsets and linker_version are M4's vocabulary."""
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in FORBIDDEN_LINK_FIELDS, f"{name}: {node.id}"
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_LINK_FIELDS, f"{name}: .{node.attr}"
            if isinstance(node, ast.keyword) and node.arg:
                assert node.arg not in FORBIDDEN_LINK_FIELDS, f"{name}: {node.arg}="


def test_no_module_defines_a_linker_shaped_function():
    """B4. A relationship query never matches text; a name that says it does is wrong."""
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                stem = node.name.lstrip("_").lower()
                for forbidden in FORBIDDEN_FUNCTION_STEMS:
                    assert forbidden not in stem, f"{name}: def {node.name}"


# --- B4: M2 cannot reach M4 -------------------------------------------------

def test_the_package_reads_only_the_named_surface():
    """B4. Every app import is on the allow list, so the read surface cannot widen."""
    for name, tree in _modules():
        for module in _imported_modules(tree):
            if not module.startswith("app.") or module.startswith("app.relationships"):
                continue
            assert module in ALLOWED_IMPORTS, f"{name}: {module}"


def test_the_transitive_import_graph_never_reaches_a_later_milestone():
    """B4. Asserted over the transitive graph, not just this package's own imports."""
    reachable = _transitive_app_imports(RELATIONSHIPS_DIR)

    assert reachable, "the transitive scan found nothing, which proves nothing"
    assert "app.relationships.queries" in reachable
    assert "app.intelligence" in reachable
    for module in reachable:
        for forbidden in FORBIDDEN_PACKAGES:
            assert not module.startswith(forbidden), f"reaches {module}"


def test_the_transitive_scan_would_catch_a_reintroduced_evidence_import():
    """The guard above is only worth having if it fails on the thing it forbids."""
    tree = ast.parse("from app.evidence.documents import documents_for\n")
    imported = {module for module in _imported_modules(tree) if module.startswith("app.")}

    assert any(module.startswith("app.evidence") for module in imported)


# --- B6: documents_for does not exist in M2 ---------------------------------

def test_documents_for_does_not_exist_in_the_package():
    """B6. Deleted when M4 adds it to app/evidence/, where a mirror test asserts it does."""
    import app.relationships as package

    assert not hasattr(package, "documents_for")
    assert "documents_for" not in package.__all__
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                assert "documents_for" not in node.name, f"{name}: def {node.name}"
            if isinstance(node, ast.Name):
                assert node.id != "documents_for", name


def test_no_public_traversal_api_exists():
    """Plan A9: three fixed queries, no caller-directed traversal (v2 defect 12)."""
    import app.relationships as package

    for forbidden in ("traverse", "walk", "path_between", "query", "graph"):
        assert not hasattr(package, forbidden), forbidden
        assert forbidden not in package.__all__


def test_the_public_surface_is_exactly_the_declared_one():
    """A name reachable but undeclared is a surface nobody reviewed."""
    import app.relationships as package

    public = {name for name in vars(package) if not name.startswith("_")}
    modules = {"edges", "errors", "model", "queries", "intelligence", "persistence"}

    assert public - modules == set(package.__all__)


# --- Determinism and the read-only contract ---------------------------------

def test_no_module_reads_a_clock_or_a_random_source():
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_CLOCKS, f"{name}: .{node.attr}"
            if isinstance(node, ast.Name):
                assert node.id not in FORBIDDEN_CLOCKS, f"{name}: {node.id}"
        for module in _imported_modules(tree):
            assert module.split(".")[0] not in FORBIDDEN_NONDETERMINISM, f"{name}: {module}"


def test_no_module_reaches_for_a_model_a_graph_database_or_a_vector_store():
    for name, tree in _modules():
        for module in _imported_modules(tree):
            assert module.split(".")[0] not in FORBIDDEN_INFRASTRUCTURE, f"{name}: {module}"


def test_the_package_never_writes_and_never_owns_a_transaction():
    """B8. The caller owns the session, matching the repository convention."""
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_WRITES, f"{name}: .{node.attr}"


def test_the_package_uses_no_textual_sql():
    """Textual SQL would escape both the source-system scope and mypy."""
    for name, tree in _modules():
        assert "text" not in _imported_names(tree), name
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


def test_every_multi_row_select_is_explicitly_ordered():
    """B7. PostgreSQL guarantees no row order, and an unordered result is not reproducible."""
    checked = 0
    for name, tree in _modules():
        basename = Path(name).name
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            selects = sum(
                1 for inner in ast.walk(node)
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
                and inner.func.id == "select"
            )
            if not selects:
                continue
            orders = sum(
                1 for inner in ast.walk(node)
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "order_by"
            )
            checked += 1
            if f"{basename}::{node.name}" in UNORDERED_SELECT_EXEMPTIONS:
                assert orders == 0, f"{name}: {node.name} is exempt but now orders"
                continue
            assert orders == selects, f"{name}: {node.name} has {selects} select, {orders} order_by"

    assert checked >= 4, "the ordering scan found too few selects to be meaningful"


@pytest.mark.parametrize("path", [
    "app/relationships/model.py",
    "app/relationships/edges.py",
    "app/relationships/queries.py",
])
def test_the_package_adds_no_persistence_and_no_migration(path):
    """M2's rollback is deleting the package: it owns no table and no revision."""
    source = (REPO / path).read_text(encoding="utf-8")

    for forbidden in ("Base", "__tablename__", "mapped_column", "alembic", "op.create_table"):
        assert forbidden not in source, f"{path}: {forbidden}"
