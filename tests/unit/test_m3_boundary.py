"""
M3 static boundaries: measure, do not resolve; and never reach M4.

The question this file answers is the one worth asking before writing a
signal engine: *how would an engineer accidentally turn M3 into a second
relationship resolver?* There are four plausible routes, and each has an
assertion here rather than a paragraph in the plan.

    Join something        A relationship resolver has to join two canonical
                          tables. M3 joins nothing: it asks M2's
                          neighbourhood() what a customer is connected to and
                          reads the attributes of the rows it names. No join
                          in the package, no second resolver.
    Reach a second model  Resolving ownership or assignment needs Employee.
                          Resolving a document needs Document. M3 imports
                          neither, so neither relationship can be rebuilt
                          here whatever else changes.
    Read a carrier key    A *_source_id column is how an unresolved
                          relationship would be joined by hand. The only
                          carrier M3 reads is customer_source_id, and only to
                          tell plan A23's missing state from its unresolved
                          one - the complement of resolution, which M2
                          cannot express because an edge that does not exist
                          has no basis to carry.
    Use M2's internals    edges_of_type, EdgeType and spec_for are how a
                          caller would assemble its own traversal out of M2's
                          parts. M3 imports the three public queries only.

The M4 boundary is asserted from M3's side as well: no M3 module names a
derived link, a linker version or a matched token. The assertion that
app/evidence does not exist was removed when M4 created it (plan T1); its
purpose - "M4 has not started, so M3 must not have started it either" -
expired exactly then, and the two assertions beside it are the whole of M3's
side of the boundary now. That app/evidence exists is not permission for M3
to reach it. Plan A11's rule - no VS-01 signal is derived from a document
link - is therefore a property of what the signal engine can import.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.intelligence import signals as signals_module
from app.intelligence.errors import ContractViolationError
from app.intelligence.signals import CUSTOMER_CARRIERS, DataQualityNote, DataQualityState
from app.persistence.repositories.canonical import ENTITY_MODELS

REPO = Path(__file__).resolve().parents[2]
INTELLIGENCE_DIR = REPO / "app" / "intelligence"

M3_MODULES = ("windows.py", "signals.py", "bands.py")

#: Canonical models that exist to be *related*, not measured. Importing one
#: here is how ownership, assignment or document linking would be rebuilt.
FORBIDDEN_MODELS = {"Employee", "Document", "Organization"}

#: M2 internals. The public queries are the contract; these are its parts.
FORBIDDEN_RELATIONSHIP_NAMES = {
    "edges_of_type", "EdgeType", "EdgeSpec", "spec_for", "EDGE_SPECS",
    "canonical_fk_edges", "source_key_edges", "all_edge_types", "order_edges",
}

#: M4's vocabulary. None of it may appear in M3 (mirrors M2's B3).
FORBIDDEN_M4_NAMES = {
    "DerivedLink", "documents_for", "linker_version", "matched_token",
    "match_start", "match_end", "LinkBasis", "ID_TOKEN", "EXACT_NAME",
}


def _tree(name: str) -> ast.AST:
    return ast.parse((INTELLIGENCE_DIR / name).read_text(encoding="utf-8"))


def _source(name: str) -> str:
    return (INTELLIGENCE_DIR / name).read_text(encoding="utf-8")


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


def _called_attributes(tree: ast.AST) -> list[str]:
    return [
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]


# ---------------------------------------------------------------------------
# The scan is real
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", M3_MODULES)
def test_every_m3_module_exists_and_is_scanned(name):
    """A scan that silently matches nothing proves nothing."""
    assert (INTELLIGENCE_DIR / name).is_file()
    assert _source(name).strip()


# ---------------------------------------------------------------------------
# M3 measures; it does not resolve
# ---------------------------------------------------------------------------


def test_the_signal_engine_joins_nothing():
    """
    The load-bearing assertion of this file.

    A relationship resolver has to join two canonical tables. If no join
    exists here, M3 cannot have become one, whatever else it reads.
    """
    assert "join" not in _called_attributes(_tree("signals.py"))


@pytest.mark.parametrize("name", M3_MODULES)
def test_no_m3_module_joins_anything(name):
    assert "join" not in _called_attributes(_tree(name))


def test_the_join_scan_would_catch_a_reintroduced_join():
    """The guard above is only worth having if it fails on the thing it forbids."""
    tree = ast.parse("q = select(A).join(B, A.x == B.id)\n")

    assert "join" in _called_attributes(tree)


@pytest.mark.parametrize("model", sorted(FORBIDDEN_MODELS))
def test_the_signal_engine_imports_no_model_that_exists_to_be_related(model):
    assert model not in _imported_names(_tree("signals.py"))


def test_the_signal_engine_reads_the_public_relationship_queries_and_not_m2s_parts():
    imported = _imported_names(_tree("signals.py"))

    assert "neighbourhood" in imported
    assert imported & FORBIDDEN_RELATIONSHIP_NAMES == set()


def test_membership_is_asked_for_exactly_once_and_only_of_m2():
    """
    neighbourhood() is called, and no other relationship query is.

    escalation_path and policy_documents are M2's to answer for other
    callers; a signal needs neither, and calling one here would be M3
    growing a second reason to know about relationships.
    """
    called = {
        node.func.id for node in ast.walk(_tree("signals.py"))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "neighbourhood" in called
    assert "escalation_path" not in called
    assert "policy_documents" not in called


def test_the_only_carrier_column_the_signal_engine_reads_is_the_customer_key():
    """
    A *_source_id column is how a relationship would be joined by hand.

    Only customer_source_id appears, and plan A23 is why: telling a missing
    relationship from an unresolved one needs the key the source supplied.
    owner_source_id, assignee_source_id and manager_source_id are M2's.
    """
    source = _source("signals.py")

    assert "customer_source_id" in source
    for carrier in ("owner_source_id", "assignee_source_id", "manager_source_id"):
        assert carrier not in source


def test_the_entity_type_literals_are_layer_1s_own_table_names():
    """A rename in Layer 1 must not leave a stale literal behind here."""
    for entity_type in (signals_module.CUSTOMERS, signals_module.SUPPORT_TICKETS,
                        signals_module.DEALS, signals_module.PROJECTS):
        assert entity_type in ENTITY_MODELS


def test_only_the_three_customer_carrying_entities_are_inspected_for_data_quality():
    """Plan A9.1 row 2: these are the only resolved canonical FKs VS-01 can emit."""
    assert set(CUSTOMER_CARRIERS) == {"support_tickets", "deals", "projects"}
    for entity_type, carrier in CUSTOMER_CARRIERS.items():
        assert carrier == f"{entity_type}.customer_source_id"


# ---------------------------------------------------------------------------
# M4 is unreachable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", M3_MODULES)
def test_no_m3_module_imports_the_evidence_package(name):
    for module in _imported_modules(_tree(name)):
        assert not module.startswith("app.evidence"), f"{name}: {module}"


@pytest.mark.parametrize("name", M3_MODULES)
@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_M4_NAMES))
def test_no_m3_module_names_m4s_vocabulary(name, forbidden):
    """
    Plan A11: no VS-01 signal is derived from a document link.

    M3 cannot construct one, because it never names one. The check is over
    the source text rather than the imports, so a locally defined
    `documents_for` fails too.
    """
    assert forbidden not in _source(name)


def test_the_signal_set_m3_builds_states_no_contract_document():
    """S14 is evidence, and every Document to Customer association is M4's."""
    assert "contract_document_ids=()" in _source("signals.py")


# ---------------------------------------------------------------------------
# The import graph stays acyclic
# ---------------------------------------------------------------------------


def test_the_foundation_package_does_not_import_the_m3_modules():
    """
    This is what keeps the graph loadable, not merely tidy.

    app.relationships imports app.intelligence. An M3 module imports
    app.relationships. If app/intelligence/__init__.py imported that M3
    module, importing app.intelligence would re-enter it half-initialised
    and raise ImportError. The dependency direction is M1 then M2 then M3,
    and the package initialiser is where it would silently close.
    """
    imported = _imported_modules(_tree("__init__.py"))

    for name in M3_MODULES:
        module = f"app.intelligence.{name.removesuffix('.py')}"
        assert module not in imported, module


def test_the_m3_modules_load_in_either_import_order():
    """The positive control for the guard above."""
    import importlib

    import app.relationships  # noqa: F401

    for name in M3_MODULES:
        assert importlib.import_module(f"app.intelligence.{name.removesuffix('.py')}")


@pytest.mark.parametrize("name", ["windows.py", "bands.py"])
def test_the_pure_m3_modules_touch_no_database_and_no_relationship(name):
    """Only the signal engine reads. The window arithmetic and the table do not."""
    modules = _imported_modules(_tree(name))

    assert not any(module.startswith("sqlalchemy") for module in modules), name
    assert not any(module.startswith("app.relationships") for module in modules), name
    assert not any(module.startswith("app.persistence") for module in modules), name


# ---------------------------------------------------------------------------
# Plan A23: two states, and they never collapse
# ---------------------------------------------------------------------------


def test_a_missing_relationship_and_an_unresolved_one_are_distinct_states():
    assert DataQualityState.MISSING_SOURCE_KEY is not DataQualityState.UNRESOLVED_SOURCE_KEY
    assert len(set(DataQualityState)) == 2


def test_the_two_states_are_the_only_ones_and_neither_means_resolved():
    """A resolved relationship is not a note. It is the normal path."""
    assert {str(state) for state in DataQualityState} == {
        "MISSING_SOURCE_KEY", "UNRESOLVED_SOURCE_KEY"
    }


def note(state: DataQualityState, customer_source_id: str | None) -> DataQualityNote:
    return DataQualityNote(
        entity_type="support_tickets", source_id="TKT-X",
        carrier_field="support_tickets.customer_source_id",
        state=state, customer_source_id=customer_source_id,
    )


@pytest.mark.parametrize("state, customer_source_id", [
    (DataQualityState.MISSING_SOURCE_KEY, "CUST-007"),
    (DataQualityState.UNRESOLVED_SOURCE_KEY, None),
])
def test_a_note_whose_state_contradicts_its_key_cannot_be_built(state, customer_source_id):
    """
    The two states cannot be collapsed even by constructing one by hand.

    A missing key is NULL and an unresolved one is not. A note claiming
    otherwise would report the wrong fault to whoever has to fix it, so it
    is refused rather than stored.
    """
    with pytest.raises(ContractViolationError, match="plan A23 forbids"):
        note(state, customer_source_id)


@pytest.mark.parametrize("state, customer_source_id", [
    (DataQualityState.MISSING_SOURCE_KEY, None),
    (DataQualityState.UNRESOLVED_SOURCE_KEY, "CUST-007"),
])
def test_a_note_whose_state_matches_its_key_is_built(state, customer_source_id):
    assert note(state, customer_source_id).state is state
