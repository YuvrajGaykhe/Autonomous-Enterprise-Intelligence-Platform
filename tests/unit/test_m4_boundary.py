"""
M4 static boundaries: who may construct a link, and who may import whom.

M4 is the first milestone that both reads M1's contract and writes a table,
so it is the first that could quietly collapse the Layer 1 / Layer 2
separation. Four routes exist, and each has an assertion here.

    Persistence learns the domain  If app/persistence built a DerivedLink it
                                   would import app.intelligence, and the M1
                                   importer whitelist would have to grow a
                                   third entry. It does not: the repository
                                   returns rows and app/evidence rebuilds.
                                   (plan §0.3.11 D-M4-B1, D-M4-B2)
    M2 acquires a document edge    B9(a), re-run from M4's side: now that
                                   app/evidence exists, app/relationships
                                   must STILL model no Document edge, so M4
                                   cannot satisfy its own requirement by
                                   adding one to M2's package.
    M3 reaches the evidence layer  app/evidence existing is not permission
                                   for the signal engine to import it. Plan
                                   A11: no VS-01 signal is document-derived.
    TOPIC returns                  §0.3.1 removed it on evidence. The
                                   vocabulary stays in M1's frozen contract
                                   as reserved; M4 never constructs one.

The B6 mirror invariant lives here too, moved whole from M2's file (plan
T3): documents_for exists in app/evidence, and app/relationships still does
not export it. Both halves together make the boundary falsifiable from both
sides, which one half alone does not.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO / "app" / "evidence"
RELATIONSHIPS_DIR = REPO / "app" / "relationships"
PERSISTENCE_DIR = REPO / "app" / "persistence"

M4_MODULES = ("__init__.py", "linker.py", "documents.py", "citations.py")

#: The M4 persistence surface. Infrastructure: it moves rows, not meaning.
LINK_REPOSITORY = PERSISTENCE_DIR / "repositories" / "document_links.py"
LINK_MODEL = PERSISTENCE_DIR / "models" / "document_customer_link.py"

#: Domain vocabulary the repository must never name, because naming it means
#: importing app.intelligence.
DOMAIN_NAMES = {
    "DerivedLink", "LinkedDocument", "EntityRef", "Evidence", "EvidenceKind",
    "DocumentCitation", "LinkBasis", "LinkConfidence", "SignalSet", "Scope",
}


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _code(path: Path) -> str:
    """
    The module's code with every docstring removed.

    These files explain at length why they do NOT name a thing - the
    repository's docstring says it builds no DerivedLink, the linker's says
    TOPIC is never constructed. A raw text scan would fail on the
    explanation rather than on the violation, so the prose is stripped and
    only code is searched. Comments are dropped by unparse.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
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
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


# ---------------------------------------------------------------------------
# The scan is real
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", M4_MODULES)
def test_every_m4_module_exists_and_is_scanned(name):
    """A scan that silently matches nothing proves nothing."""
    assert (EVIDENCE_DIR / name).is_file()
    assert _source(EVIDENCE_DIR / name).strip()


@pytest.mark.parametrize("path", [LINK_REPOSITORY, LINK_MODEL])
def test_the_m4_persistence_modules_exist_and_are_scanned(path):
    assert path.is_file()
    assert _source(path).strip()


# ---------------------------------------------------------------------------
# D-M4-B1 / D-M4-B2: persistence reads, evidence reconstructs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [LINK_REPOSITORY, LINK_MODEL])
@pytest.mark.parametrize("forbidden", ["app.intelligence", "app.evidence"])
def test_the_persistence_layer_imports_neither_layer_2_package(path, forbidden):
    """
    The load-bearing assertion of §0.3.11.

    Importing app.intelligence here is what would force the M1 importer
    whitelist to admit app/persistence; importing app.evidence would invert
    the layering and close a cycle. Neither happens, so the whitelist stays
    at two entries and the graph stays a DAG.
    """
    for module in _imported_modules(_tree(path)):
        assert not module.startswith(forbidden), f"{path.name}: {module}"


@pytest.mark.parametrize("forbidden", sorted(DOMAIN_NAMES))
def test_the_link_repository_never_names_a_domain_type(forbidden):
    """
    Checked over the module's code, not its imports, so a locally redefined
    DerivedLink would fail too. Its docstring names these types to explain
    why it does not use them, so the prose is stripped first. The repository
    returns rows; giving those rows domain meaning is documents.py's alone.
    """
    assert forbidden not in _code(LINK_REPOSITORY), forbidden


def test_the_repository_scan_would_catch_a_reintroduced_domain_import():
    """The guard above is only worth having if it fails on the thing it forbids."""
    tree = ast.parse("from app.intelligence.contract import DerivedLink\n")

    assert any(module.startswith("app.intelligence") for module in _imported_modules(tree))


def _constructors_of(type_name: str) -> set[str]:
    """Which M4 modules call a given type's constructor."""
    return {
        name
        for name in M4_MODULES
        for node in ast.walk(_tree(EVIDENCE_DIR / name))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == type_name
    }


def test_exactly_one_module_builds_a_linked_document():
    """
    §0.3.10.2's single-place property, asserted rather than promised.

    D-M4-B1 moved WHICH place, not how many: documents.py alone turns
    persisted rows into domain values, so there is no second reconstruction
    path to drift out of step.
    """
    builders = _constructors_of("LinkedDocument")

    assert builders, "the scan found no constructor, so it would pass if M4 built none"
    assert builders == {"documents.py"}, builders


def test_only_deriving_and_reconstructing_build_a_derived_link():
    """
    Two legitimate origins, and no third.

    linker.py builds a link when it MATCHES text; documents.py rebuilds one
    when it READS a persisted row. Those are the only two ways a link comes
    into existence, and neither is the repository.
    """
    builders = _constructors_of("DerivedLink")

    assert builders == {"linker.py", "documents.py"}, builders
    assert "DerivedLink(" not in _code(LINK_REPOSITORY)


def test_the_repository_owns_the_query_and_the_evidence_layer_does_not():
    """
    The other half of the same property: exactly one place runs the read.

    documents.py reconstructs but never selects, so the two responsibilities
    cannot merge back into one module.
    """
    assert "select(" in _source(LINK_REPOSITORY)
    assert "select(" not in _source(EVIDENCE_DIR / "documents.py")


# ---------------------------------------------------------------------------
# B6, moved whole from M2's file (plan T3): the mirror invariant
# ---------------------------------------------------------------------------


def test_documents_for_exists_in_the_evidence_package():
    """B6, positive half. M4 owns documents_for."""
    import app.evidence as package

    assert hasattr(package, "documents_for")
    assert "documents_for" in package.__all__


def test_documents_for_still_does_not_exist_in_the_relationship_package():
    """
    B6, negative half, moved here rather than dropped (plan T3).

    app/relationships/ is untouched by M4 and stays byte-identical to
    bc0525d. A document still reaches no customer through M2.
    """
    import app.relationships as package

    assert not hasattr(package, "documents_for")
    assert "documents_for" not in package.__all__
    for path in sorted(RELATIONSHIPS_DIR.glob("*.py")):
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                assert "documents_for" not in node.name, f"{path.name}: def {node.name}"
            if isinstance(node, ast.Name):
                assert node.id != "documents_for", path.name


def test_the_relationship_package_still_models_no_document_edge():
    """
    B9(a), re-run from M4's side now that app/evidence exists.

    M4 must not satisfy its linking requirement by adding a Document edge to
    M2. A document still has degree zero there, so no path of any length
    reaches a customer through the relationship model.
    """
    from app.relationships import EDGE_SPECS, ISOLATED_ENTITIES

    assert "documents" in ISOLATED_ENTITIES
    for edge_type, spec in EDGE_SPECS.items():
        assert "documents" not in (spec.source_entity, spec.target_entity), edge_type


@pytest.mark.parametrize("path", sorted(RELATIONSHIPS_DIR.glob("*.py")))
def test_no_relationship_module_imports_the_evidence_package(path):
    """The DAG's reverse edge, asserted from M4's side as well as M2's."""
    for module in _imported_modules(_tree(path)):
        assert not module.startswith("app.evidence"), f"{path.name}: {module}"


@pytest.mark.parametrize("name", ["windows.py", "signals.py", "bands.py"])
def test_no_m3_module_imports_the_evidence_package(name):
    """
    app/evidence existing is not permission for M3 to reach it.

    Plan A11: no VS-01 signal is derived from a document link. M3's own
    boundary file asserts this too; it is repeated here so the invariant
    survives either file being rewritten.
    """
    tree = _tree(REPO / "app" / "intelligence" / name)
    for module in _imported_modules(tree):
        assert not module.startswith("app.evidence"), f"{name}: {module}"


def test_the_evidence_package_does_not_import_the_signal_engine():
    """
    §0.3.6: M4's import surface is M1 and M2. A later milestone that needs
    M3's signal engine imports it itself.
    """
    for name in M4_MODULES:
        for module in _imported_modules(_tree(EVIDENCE_DIR / name)):
            assert module not in {
                "app.intelligence.signals",
                "app.intelligence.windows",
                "app.intelligence.bands",
            }, f"{name}: {module}"


# ---------------------------------------------------------------------------
# TOPIC does not return
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", M4_MODULES)
def test_no_m4_module_constructs_a_topic_link(name):
    """
    §0.3.1. TOPIC stays in M1's frozen contract as reserved vocabulary and
    is never built: a topical overlap asserts no token and no span, so it
    cannot satisfy the grounding guarantee every link here carries.
    """
    code = _code(EVIDENCE_DIR / name)

    assert "TOPIC" not in code
    assert "SUPPORTING" not in code


@pytest.mark.parametrize("name", M4_MODULES)
@pytest.mark.parametrize("forbidden", [
    "embedding", "similarity", "cosine", "fuzzy", "levenshtein", "vector",
])
def test_no_m4_module_reaches_for_a_semantic_mechanism(name, forbidden):
    """Deterministic textual evidence only (plan A13, A31)."""
    assert forbidden not in _code(EVIDENCE_DIR / name).lower()


def test_the_linker_implements_exactly_two_bases():
    """Two mechanisms, and a test that fails if a third is added."""
    from app.evidence import linker

    code = _code(EVIDENCE_DIR / "linker.py")
    assert "LinkBasis.ID_TOKEN" in code
    assert "LinkBasis.EXACT_NAME" in code
    assert "LinkBasis.TOPIC" not in code
    assert hasattr(linker, "find_id_token")
    assert hasattr(linker, "find_exact_name")


# ---------------------------------------------------------------------------
# S14 is defined here and invoked by M5
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", M4_MODULES)
def test_no_m4_module_invokes_the_s14_composition(name):
    """
    §0.3.6 B: M4 owns the function, M5 owns calling it.

    Defining it and calling it are different acts. M4's linker, repository,
    citation builder and migration neither call it nor depend on it.
    """
    called = {
        node.func.id for node in ast.walk(_tree(EVIDENCE_DIR / name))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "with_contract_documents" not in called, name


def test_the_s14_composition_is_nonetheless_defined_and_exported():
    """The negative above would also pass if M4 had simply not built it."""
    import app.evidence as package

    assert hasattr(package, "with_contract_documents")
    assert "with_contract_documents" in package.__all__


def test_m3_still_states_no_contract_document():
    """
    M3 is frozen at 34486eb. M4 does not edit signals.py to populate S14,
    and this pins the literal from M4's side as well as M3's.
    """
    source = _source(REPO / "app" / "intelligence" / "signals.py")

    assert "contract_document_ids=()" in source


# ---------------------------------------------------------------------------
# Transaction and session ownership
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden", [
    "commit", "rollback", "begin", "begin_nested", "close", "flush",
])
def test_the_link_repository_owns_no_transaction(forbidden):
    """
    The caller owns the session and the transaction, matching every Layer 1
    repository. A repository that committed would make a partial derivation
    durable.
    """
    for node in ast.walk(_tree(LINK_REPOSITORY)):
        if isinstance(node, ast.Attribute):
            assert node.attr != forbidden, forbidden


@pytest.mark.parametrize("name", M4_MODULES)
@pytest.mark.parametrize("forbidden", ["commit", "rollback", "begin", "close"])
def test_no_m4_module_owns_a_transaction(name, forbidden):
    for node in ast.walk(_tree(EVIDENCE_DIR / name)):
        if isinstance(node, ast.Attribute):
            assert node.attr != forbidden, f"{name}: .{forbidden}"


def test_the_link_repository_uses_no_textual_sql():
    """E1's rule, which applies to every repository including this one."""
    assert "sqlalchemy.text" not in _imported_names(_tree(LINK_REPOSITORY))
    for node in ast.walk(_tree(LINK_REPOSITORY)):
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"exec_driver_sql", "text"}


def test_the_conflict_behaviour_is_do_nothing_never_do_update():
    """
    §0.3.4: nothing is ever updated in place. Layer 1's canonical upsert
    uses DO UPDATE, and using it here would silently rewrite history.
    """
    source = _source(LINK_REPOSITORY)

    assert "on_conflict_do_nothing" in source
    assert "on_conflict_do_update" not in source


def test_the_link_model_carries_no_provenance_mixin():
    """
    A derived link is not an ingested record: no source system, no ingestion
    run, no record_hash. Its provenance is the two stamps instead.
    """
    from app.persistence.models.document_customer_link import DocumentCustomerLink

    columns = {column.name for column in DocumentCustomerLink.__table__.columns}

    assert columns.isdisjoint({
        "source_system", "source_entity", "source_id",
        "ingested_at", "ingestion_run_id", "record_hash", "source_updated_at",
    })
    assert {"linker_version", "layer1_fingerprint"} <= columns


def test_layer_1_gained_no_reference_to_the_link_table():
    """
    Plan A31: Layer 1 is frozen. The association lives in
    document_customer_links or it does not exist.
    """
    from app.persistence.models import Customer, Document

    for model in (Document, Customer):
        for column in model.__table__.columns:
            assert "link" not in column.name, f"{model.__name__}.{column.name}"
        assert not model.__table__.foreign_keys, model.__name__
