"""
M7 static boundaries: three modules, one direction, one impure run (§0.6.2).

§0.6.2 is a table of what each M7 module may import or do, so each row is
checked structurally, on its own and independently of the M6 file (§0.6.1):

    Where M7 exists    assessment, payload and brief beside M6's four modules,
                       and templates/ holding text only. The initialiser
                       re-exports none of it, and nothing outside
                       app/decisions/ imports it.
    Direction          assessment -> payload, assessment -> brief and
                       brief -> payload. Never the reverse, and no M6 module
                       imports M7.
    Imports            each module's first-party imports are exactly its
                       row's grants, M1's read as whole modules (Part B M7,
                       implementation decision 4). Only assessment.py
                       reaches a third-party package, and only SQLAlchemy.
    The run            derive_and_persist once, unconditionally, before any
                       customer is visited; compute_signals read for its two
                       fields only; none of the never-called functions; no
                       session method, write or transaction of its own.
    Pure               payload.py and brief.py hold no session, no ORM model
                       and no log line; payload.py names AnalystContexts and
                       Reconciliation in annotations only.
    Clock, randomness  no clock anywhere. datetime and the UUID type in
                       assessment.py only; no uuid generator, random or
                       secrets anywhere.
    Events             log_event only, the five events of §0.6.13.6 with
                       their fields as explicit keywords, in order, and no
                       money or text among them.
    Files              brief.py reads its one template, and nothing writes.
    Persistence        M7's models, repositories and migration import no
                       Layer 2 package, and the repositories name no domain
                       type (M4's DOMAIN_NAMES scan, mirrored as §0.6.5
                       directs). They own no transaction, use no textual
                       SQL, never update and never log.

Code is scanned with docstrings stripped, using M4's `_code()` technique,
because these modules explain at length what they do not do. Each rule is a
function returning its violations; the real modules must return none, and
`test_every_scan_catches_its_reintroduction` runs the same function over a
small reintroduction of what it forbids, so no scan can pass vacuously.
"""

from __future__ import annotations

import ast
import collections
import importlib
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

import app.persistence.models  # noqa: F401 -- registers every mapper for ORM_MODELS
from app.core.database import Base

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
DECISIONS_DIR = REPO / "app" / "decisions"
TEMPLATES_DIR = DECISIONS_DIR / "templates"
PERSISTENCE_DIR = REPO / "app" / "persistence"

#: §0.6.2: exactly three modules, by the short name each rule uses.
M7_MODULES = {
    "assessment": DECISIONS_DIR / "assessment.py",
    "payload": DECISIONS_DIR / "payload.py",
    "brief": DECISIONS_DIR / "brief.py",
}
M7_DOTTED = {f"app.decisions.{name}" for name in M7_MODULES}

#: The four M6 modules (§0.5.14). None of them may import M7 (§0.6.1 T-M7-1 (d)).
M6_MODULES = tuple(DECISIONS_DIR / name for name in (
    "__init__.py", "policy.py", "conflicts.py", "reconciler.py"))

#: §0.6.5: M7's persistence, and its one migration.
M7_MODELS = tuple(PERSISTENCE_DIR / "models" / name for name in (
    "risk_assessment.py", "risk_position.py", "risk_brief.py"))
M7_REPOSITORIES = tuple(PERSISTENCE_DIR / "repositories" / name for name in (
    "risk_assessments.py", "citation_reads.py"))
M7_MIGRATION = REPO / "migrations" / "versions" / (
    "66eddc6b7136_m7_risk_assessments_positions_briefs.py")
M7_TABLES = {"risk_assessments", "risk_positions", "risk_briefs"}

#: §0.6.2's M1 row, read as a grant of whole modules (Part B M7, implementation
#: decision 4). money, and M3's signals, windows and bands, are not among them.
M1_MODULES = ("app.intelligence.contract", "app.intelligence.scope", "app.intelligence.config",
              "app.intelligence.errors", "app.intelligence.timeutil")

#: §0.6.2's table, per module: each first-party module it may import from, and
#: the names it may take there. None means every name that module defines.
GRANTS: dict[str, dict[str, frozenset[str] | None]] = {
    "assessment": {
        **dict.fromkeys(M1_MODULES),
        "app.intelligence.signals": frozenset({"compute_signals", "customers_in_scope"}),
        "app.relationships": frozenset({"escalation_path"}),
        "app.evidence": frozenset({"derive_and_persist", "documents_for", "citable_text",
                                   "resolve_document_citation", "CitationResolutionError"}),
        "app.analysts": frozenset({"build_contexts"}),
        "app.decisions": frozenset({"reconcile", "order_reconciliations", "ConflictPolicy",
                                    "default_conflict_policy"}),
        "app.decisions.payload": None,
        "app.decisions.brief": None,
        "app.persistence.repositories.risk_assessments": None,
        "app.persistence.repositories.citation_reads": None,
        "app.core.logging": frozenset({"log_event"}),
    },
    "payload": {
        **dict.fromkeys(M1_MODULES),
        "app.analysts": frozenset({"AnalystContexts"}),
        "app.decisions": frozenset({"Reconciliation"}),
    },
    "brief": {
        "app.intelligence.contract": None,
        "app.intelligence.errors": None,
        "app.decisions.payload": None,
    },
}
#: The one third-party package each module may reach: `Session` (type), `sqlalchemy`.
THIRD_PARTY = {"assessment": {"sqlalchemy"}, "payload": set(), "brief": set()}

#: §0.6.2's direction: these edges between M7 modules, and no other.
ALLOWED_EDGES = {("assessment", "payload"), ("assessment", "brief"), ("brief", "payload")}

#: §0.6.2: named by build_contexts and reconcile, so never called by the run.
NEVER_CALLED = {"derive_links", "persist_links", "assign_band", "SupportRiskAnalyst",
                "CommercialAnalyst", "detect_conflicts", "order_positions", "ranking_key"}
#: §0.6.4: the only two fields the run may read from compute_signals.
SIGNAL_FIELDS = {"escalation_window", "backlog_ticket_ids"}

FORBIDDEN_WRITES = {"commit", "rollback", "add", "add_all", "flush", "delete", "merge",
                    "begin", "begin_nested", "close", "bulk_save_objects"}
SESSION_FACTORIES = {"Session", "sessionmaker", "scoped_session", "create_engine",
                     "get_sessionmaker", "connect"}
FORBIDDEN_CLOCKS = {"now", "today", "utcnow", "utcfromtimestamp", "fromtimestamp", "time",
                    "monotonic", "perf_counter"}
UUID_GENERATORS = {"uuid1", "uuid3", "uuid4", "uuid5"}
#: Standard-library modules no M7 module imports: clocks and randomness (DR5),
#: and the network (§0.6.2's last row).
FORBIDDEN_STDLIB = {"time", "random", "secrets", "socket", "ssl", "urllib", "http", "smtplib",
                    "ftplib", "subprocess"}
FILE_CALLS = {"open", "read_text", "read_bytes", "write_text", "write_bytes", "mkdir", "unlink",
              "touch", "rmdir", "iterdir", "glob", "rglob"}

#: §0.6.13.6's events, each with its fields in their stated order.
EVENTS = {
    "vs01.scope_resolved": ("source_system", "as_of", "layer1_fingerprint", "as_of_source"),
    "vs01.links_derived": ("source_system", "layer1_fingerprint", "linker_version", "inserted"),
    "vs01.conflict_detected": ("customer", "object_ref", "policy_id", "policy_version"),
    "vs01.conflict_resolved": ("customer", "object_ref", "policy_id", "policy_version",
                               "resolved_action"),
    "vs01.brief_generated": ("customer", "payload_hash", "citation_count", "created"),
}
#: §0.6.13.6's "never logged": money, text, timestamps and the payload itself.
NEVER_LOGGED = {"amount", "currency", "exposure_by_currency", "narrative", "rationale",
                "body_text", "title", "phrase", "text", "matched_token", "email", "created_at",
                "resolved_at", "decision_payload"}

#: §0.6.13.5: the exceptions brief.py may catch. The other two modules catch nothing (§0.6.11).
CAUGHT = {"assessment": set(), "payload": set(),
          "brief": {"OSError", "UnicodeDecodeError", "KeyError", "ValueError",
                    "InvalidOperation"}}

LAYER2_PACKAGES = ("app.intelligence", "app.evidence", "app.analysts", "app.decisions",
                   "app.relationships")
#: M4's DOMAIN_NAMES, verbatim (test_m4_boundary.py), mirrored over M7's repositories (§0.6.5).
M4_DOMAIN_NAMES = {
    "DerivedLink", "LinkedDocument", "EntityRef", "Evidence", "EvidenceKind",
    "DocumentCitation", "LinkBasis", "LinkConfidence", "SignalSet", "Scope",
}
#: The domain vocabulary M7 adds or reads, which M7's repositories equally never name.
M7_DOMAIN_NAMES = {
    "Position", "Conflict", "ConflictResolution", "Reconciliation", "Worthiness",
    "AnalystContexts", "CustomerSignals", "Citation", "RecordCitation", "RiskBand",
    "Function", "Stance", "ActionId", "MoneyValue", "RiskRulesConfig", "AssessmentResult",
    "SpanTarget", "CalendarDate",
}

ORM_MODELS = {mapper.class_.__name__ for mapper in Base.registry.mappers}


# ---------------------------------------------------------------------------
# Reading code
# ---------------------------------------------------------------------------


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _code(tree: ast.AST) -> str:
    """The module's code with every docstring removed (M4's technique); unparse drops comments."""
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


def _words(tree: ast.AST) -> set[str]:
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", _code(tree)))


def _imports(tree: ast.AST) -> list[tuple[str, str | None, int]]:
    """Every import as (module, name, line): `import x` is (x, None), a relative one is dotted."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(alias.name, None, node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            found += [(module, alias.name, node.lineno) for alias in node.names]
    return found


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _callee(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call) and _callee(node) == name]


def _called_names(tree: ast.AST) -> set[str]:
    return {_callee(node) for node in ast.walk(tree) if isinstance(node, ast.Call)}


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def _intelligence_exports() -> dict[str, str]:
    """Where each name `app.intelligence` re-exports is defined, from its initialiser."""
    return {
        alias.asname or alias.name: node.module
        for node in _tree(REPO / "app" / "intelligence" / "__init__.py").body
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
    }


INTELLIGENCE_EXPORTS = _intelligence_exports()


# ---------------------------------------------------------------------------
# The rules, each returning its violations
# ---------------------------------------------------------------------------


def _import_violations(module: str, tree: ast.AST) -> list[str]:
    """
    §0.6.2's grants as a closed world.

    A name imported from the `app.intelligence` initialiser is judged by the
    submodule that defines it, so the initialiser cannot launder money or M3.
    """
    grants, third_party = GRANTS[module], THIRD_PARTY[module]
    found = []
    for imported, name, line in _imports(tree):
        root = imported.split(".")[0]
        if imported.startswith("."):
            found.append(f"{line}: relative import {imported}")
        elif root != "app":
            if root not in sys.stdlib_module_names and root not in third_party:
                found.append(f"{line}: third-party {imported}")
        elif name is None:
            found.append(f"{line}: import {imported}")
        else:
            source = (INTELLIGENCE_EXPORTS.get(name, "an unknown module")
                      if imported == "app.intelligence" else imported)
            if source not in grants:
                found.append(f"{line}: {imported}.{name}, defined in {source}")
            elif grants[source] is not None and name not in grants[source]:
                found.append(f"{line}: {imported}.{name}")
    return found


def _stdlib_violations(module: str, tree: ast.AST) -> list[str]:
    """DR5 and the log row: no clock module, randomness or network; datetime, uuid, logging scoped."""
    found = []
    for imported, name, line in _imports(tree):
        root = imported.split(".")[0]
        if root in FORBIDDEN_STDLIB:
            found.append(f"{line}: {imported}")
        elif root == "datetime" and (module != "assessment" or name != "date"):
            found.append(f"{line}: datetime {name}")
        elif root == "uuid" and (module != "assessment" or name != "UUID"):
            found.append(f"{line}: uuid {name}")
        elif root == "logging" and module != "assessment":
            found.append(f"{line}: logging")
    return found


def _clock_violations(tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_CLOCKS:
            found.append(f"{node.lineno}: .{node.attr}")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_CLOCKS:
            found.append(f"{node.lineno}: {node.id}")
    return found


def _generator_violations(tree: ast.AST) -> list[str]:
    """§0.6.2: the UUID type may be named; no uuid generator is ever called."""
    return sorted(_called_names(tree) & UUID_GENERATORS)


def _m7_edges(module: str, tree: ast.AST) -> set[tuple[str, str]]:
    edges = set()
    for imported, name, _ in _imports(tree):
        for target in M7_MODULES:
            if imported == f"app.decisions.{target}" or (
                    imported == "app.decisions" and name == target):
                edges.add((module, target))
    return edges


def _m7_importers(paths: list[Path]) -> list[str]:
    found = []
    for path in paths:
        label = path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else path.name
        for imported, name, line in _imports(_tree(path)):
            if imported in M7_DOTTED or (imported == "app.decisions" and name in M7_MODULES):
                found.append(f"{label}:{line}: {imported} {name}")
    return found


def _derive_violations(tree: ast.AST) -> list[str]:
    """§0.6.3 step 2: one call, unconditional, in run_assessment, after the scope, before customers."""
    calls = _calls(tree, "derive_and_persist")
    if len(calls) != 1:
        return [f"{len(calls)} derive_and_persist call sites"]
    (call,) = calls
    parents, found, node = _parents(tree), [], call
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.For | ast.AsyncFor | ast.While | ast.If | ast.IfExp | ast.Try
                      | ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
                      | ast.Lambda | ast.BoolOp):
            found.append(f"{call.lineno}: inside {type(node).__name__}")
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name != "run_assessment":
                found.append(f"{call.lineno}: in {node.name}, not run_assessment")
            break
    else:
        found.append(f"{call.lineno}: outside any function")
    scope_lines = [one.lineno for one in _calls(tree, "resolve_scope")]
    if not scope_lines or min(scope_lines) > call.lineno:
        found.append(f"{call.lineno}: before the scope is resolved")
    customer_lines = [one.lineno for name in ("customers_in_scope", "build_contexts", "reconcile")
                      for one in _calls(tree, name)]
    if not customer_lines or min(customer_lines) < call.lineno:
        found.append(f"{call.lineno}: after a customer is visited")
    return found


def _compute_signals_violations(tree: ast.AST) -> list[str]:
    """§0.6.4: compute_signals is bound to a name, and only its two fields are ever read."""
    parents, bound, found = _parents(tree), set(), []
    for call in _calls(tree, "compute_signals"):
        parent = parents.get(call)
        if (isinstance(parent, ast.Assign) and len(parent.targets) == 1
                and isinstance(parent.targets[0], ast.Name)):
            bound.add(parent.targets[0].id)
        else:
            found.append(f"{call.lineno}: compute_signals(...) used without a name")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in bound and isinstance(node.ctx, ast.Load):
            parent = parents.get(node)
            if not (isinstance(parent, ast.Attribute) and parent.attr in SIGNAL_FIELDS):
                read = parent.attr if isinstance(parent, ast.Attribute) else "the whole result"
                found.append(f"{node.lineno}: {node.id} read for {read}")
    return found


def _session_violations(tree: ast.AST) -> list[str]:
    """§0.6.2 and §0.6.3: the run calls no session method, writes nothing and opens nothing."""
    found = [
        f"{node.lineno}: session.{node.attr}" for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
        and node.value.id == "session"
    ]
    found += [f"calls {name}()" for name in sorted(
        _called_names(tree) & (FORBIDDEN_WRITES | SESSION_FACTORIES))]
    return found


def _impurity_violations(tree: ast.AST) -> list[str]:
    """payload.py and brief.py: no session, no ORM model, no log line, no print."""
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {name for _, name, _ in _imports(tree) if name is not None}
    found = sorted(names & ({"Session", "log_event", "logger", "print"} | SESSION_FACTORIES
                            | ORM_MODELS))
    found += [f"{node.lineno}: parameter {node.arg}" for node in ast.walk(tree)
              if isinstance(node, ast.arg) and node.arg == "session"]
    return found


def _type_only_violations(tree: ast.AST, names: set[str]) -> list[str]:
    """Where a granted type is named outside an annotation: called, tested or passed on."""
    annotated: set[int] = set()
    for node in ast.walk(tree):
        annotations: list[ast.expr | None] = []
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            arguments = node.args
            annotations += [one.annotation for one in (
                *arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs,
                arguments.vararg, arguments.kwarg) if one is not None]
            annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        for annotation in annotations:
            if annotation is not None:
                annotated |= {id(inner) for inner in ast.walk(annotation)}
    return [f"{node.lineno}: {node.id}" for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id in names and id(node) not in annotated]


def _log_call_violations(tree: ast.AST) -> list[str]:
    """§0.6.13.6: log_event(logger, logging.INFO, "<event>", <its fields as keywords, in order>)."""
    found = []
    for call in _calls(tree, "log_event"):
        args = call.args
        event = args[2].value if len(args) == 3 and isinstance(args[2], ast.Constant) else None
        if len(args) != 3 or any(isinstance(arg, ast.Starred) for arg in args):
            found.append(f"{call.lineno}: positional arguments")
        elif _dotted(args[0]) != "logger" or _dotted(args[1]) != "logging.INFO":
            found.append(f"{call.lineno}: not logger at INFO")
        if event not in EVENTS:
            found.append(f"{call.lineno}: event {event!r}")
        if any(keyword.arg is None for keyword in call.keywords):
            found.append(f"{call.lineno}: **fields")
        elif event in EVENTS and tuple(one.arg for one in call.keywords) != EVENTS[event]:
            found.append(f"{call.lineno}: fields of {event}")
        for keyword in call.keywords:
            read = {node.attr for node in ast.walk(keyword.value) if isinstance(node, ast.Attribute)}
            found += [f"{call.lineno}: {keyword.arg} logs .{attr}" for attr in read & NEVER_LOGGED]
    return found


def _logging_violations(tree: ast.AST) -> list[str]:
    """Log through log_event only: logging gives a logger and INFO, and the logger is only passed."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and _dotted(node.value) == "logging" and node.attr not in {
                "getLogger", "INFO"}:
            found.append(f"{node.lineno}: logging.{node.attr}")
        if isinstance(node, ast.Attribute) and _dotted(node.value) == "logger":
            found.append(f"{node.lineno}: logger.{node.attr}")
        if isinstance(node, ast.Name) and node.id == "print":
            found.append(f"{node.lineno}: print")
    loggers = [node for node in getattr(tree, "body", [])
               if isinstance(node, ast.Assign) and [_dotted(one) for one in node.targets] == ["logger"]]
    if [ast.unparse(node.value) for node in loggers] != ["logging.getLogger(__name__)"]:
        found.append("the module logger is not exactly logging.getLogger(__name__)")
    return found


def _file_violations(module: str, tree: ast.AST) -> list[str]:
    """§0.6.10: brief.py reads its template, read-only, as UTF-8. Nothing else touches a file."""
    calls = [call for call in ast.walk(tree)
             if isinstance(call, ast.Call) and _callee(call) in FILE_CALLS]
    if module != "brief":
        return [f"{call.lineno}: {_callee(call)}()" for call in calls]
    found = [f"{call.lineno}: {_callee(call)}()" for call in calls if not (
        _callee(call) == "read_text" and _dotted(call.func) == "TEMPLATE_PATH.read_text"
        and [(one.arg, getattr(one.value, "value", None)) for one in call.keywords]
        == [("encoding", "utf-8")])]
    if len(calls) != 1:
        found.append(f"{len(calls)} file reads")
    return found


def _handler_violations(module: str, tree: ast.AST) -> list[str]:
    """§0.6.11 and §0.6.13.5: brief.py catches its four conditions' exceptions; nothing else catches."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            caught = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
            for one in caught:
                name = "a bare except" if one is None else _dotted(one)
                if name not in CAUGHT[module]:
                    found.append(f"{node.lineno}: catches {name}")
    return found


def _layer2_violations(tree: ast.AST) -> list[str]:
    """D-M4-B2 and §0.6.5: persistence stays below every Layer 2 package."""
    return [f"{line}: {imported}" for imported, _, line in _imports(tree)
            if imported.startswith(LAYER2_PACKAGES)]


def _textual_sql_violations(tree: ast.AST) -> list[str]:
    """E1 and G2's rule, with no exemption in M7's files: no text(), no .text, no driver SQL."""
    found = [f"{line}: imports text from {imported}" for imported, name, line in _imports(tree)
             if imported.startswith("sqlalchemy") and name == "text"]
    found += [f"{node.lineno}: .{node.attr}" for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and node.attr in {"text", "exec_driver_sql"}]
    return found


def _repository_log_violations(tree: ast.AST) -> list[str]:
    found = [f"{line}: {imported}" for imported, _, line in _imports(tree)
             if imported.split(".")[0] == "logging" or imported == "app.core.logging"]
    found += [f"{node.lineno}: {node.id}" for node in ast.walk(tree)
              if isinstance(node, ast.Name) and node.id in {"print", "log_event"}]
    return found


def _transaction_violations(tree: ast.AST) -> list[str]:
    """M4's repository rule, mirrored: the caller owns the session and the transaction."""
    return [f"{node.lineno}: .{node.attr}" for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr in {"commit", "rollback", "begin", "begin_nested", "close", "flush"}]


def _m4_domain_violations(tree: ast.AST) -> list[str]:
    """M4's scan, verbatim in technique: a substring of the docstring-stripped code."""
    code = _code(tree)
    return sorted(name for name in M4_DOMAIN_NAMES if name in code)


def _m7_domain_violations(tree: ast.AST) -> list[str]:
    """M7's vocabulary, by whole word, so RiskPosition and PositionRow are not Position."""
    return sorted(_words(tree) & M7_DOMAIN_NAMES)


# ---------------------------------------------------------------------------
# Every scan fails on the thing it forbids
# ---------------------------------------------------------------------------


REINTRODUCTIONS: list[tuple[str, Callable[[ast.Module], list[str]], str]] = [
    ("the run reads persistence directly",
     lambda tree: _import_violations("assessment", tree),
     "from app.persistence.models import Customer\n"),
    ("the run imports the database",
     lambda tree: _import_violations("assessment", tree),
     "from app.core.database import get_sessionmaker\n"),
    ("the run calls M3's band table",
     lambda tree: _import_violations("assessment", tree),
     "from app.intelligence.bands import ranking_key\n"),
    ("the run names AnalystContexts",
     lambda tree: _import_violations("assessment", tree),
     "from app.analysts import AnalystContexts\n"),
    ("the run reaches past M6's public API",
     lambda tree: _import_violations("assessment", tree),
     "from app.decisions.reconciler import reconcile\n"),
    ("the run imports the API",
     lambda tree: _import_violations("assessment", tree),
     "from app.api.routes import router\n"),
    ("the run reaches for an HTTP client",
     lambda tree: _import_violations("assessment", tree),
     "import httpx\n"),
    ("payload reads M3",
     lambda tree: _import_violations("payload", tree),
     "from app.intelligence.signals import HIGH_PRIORITY\n"),
    ("payload reads M2",
     lambda tree: _import_violations("payload", tree),
     "from app.relationships import escalation_path\n"),
    ("payload reads M4",
     lambda tree: _import_violations("payload", tree),
     "from app.evidence import documents_for\n"),
    ("payload launders money through the initialiser",
     lambda tree: _import_violations("payload", tree),
     "from app.intelligence import MoneyValue\n"),
    ("payload imports SQLAlchemy",
     lambda tree: _import_violations("payload", tree),
     "from sqlalchemy.orm import Session\n"),
    ("brief reads the scope",
     lambda tree: _import_violations("brief", tree),
     "from app.intelligence.scope import Scope\n"),
    ("brief imports a whole package",
     lambda tree: _import_violations("brief", tree),
     "import app.intelligence.contract\n"),
    ("brief imports relatively",
     lambda tree: _import_violations("brief", tree),
     "from .payload import payload_hash\n"),
    ("payload imports datetime",
     lambda tree: _stdlib_violations("payload", tree),
     "from datetime import date\n"),
    ("the run imports datetime beyond date",
     lambda tree: _stdlib_violations("assessment", tree),
     "from datetime import datetime\n"),
    ("the run imports the uuid module",
     lambda tree: _stdlib_violations("assessment", tree),
     "import uuid\n"),
    ("brief imports uuid",
     lambda tree: _stdlib_violations("brief", tree),
     "from uuid import UUID\n"),
    ("brief logs",
     lambda tree: _stdlib_violations("brief", tree),
     "import logging\n"),
    ("the run imports randomness",
     lambda tree: _stdlib_violations("assessment", tree),
     "from secrets import token_hex\n"),
    ("the run reads a clock module",
     lambda tree: _stdlib_violations("assessment", tree),
     "import time\n"),
    ("a clock is read",
     _clock_violations,
     "as_of = date.today()\n"),
    ("an id is generated",
     _generator_violations,
     "from uuid import UUID\nx = uuid.uuid4()\n"),
    ("payload imports brief",
     lambda tree: sorted(_m7_edges("payload", tree) - ALLOWED_EDGES),
     "from app.decisions.brief import render_brief\n"),
    ("brief imports the run",
     lambda tree: sorted(_m7_edges("brief", tree) - ALLOWED_EDGES),
     "from app.decisions import assessment\n"),
    ("links are derived twice",
     _derive_violations,
     "def run_assessment(session):\n    resolve_scope(session)\n"
     "    derive_and_persist(session, scope)\n    derive_and_persist(session, scope)\n"
     "    build_contexts(session, scope, customer)\n"),
    ("links are derived per customer",
     _derive_violations,
     "def run_assessment(session):\n    resolve_scope(session)\n    for customer in customers:\n"
     "        derive_and_persist(session, scope)\n        build_contexts(session, scope, customer)\n"),
    ("links are derived only sometimes",
     _derive_violations,
     "def run_assessment(session):\n    resolve_scope(session)\n    if fresh:\n"
     "        derive_and_persist(session, scope)\n    build_contexts(session, scope, customer)\n"),
    ("links are derived after a context",
     _derive_violations,
     "def run_assessment(session):\n    resolve_scope(session)\n"
     "    build_contexts(session, scope, customer)\n    derive_and_persist(session, scope)\n"),
    ("M3's signals are read",
     _compute_signals_violations,
     "measured = compute_signals(session, scope, customer)\nx = measured.signals\n"),
    ("M3's result is passed on whole",
     _compute_signals_violations,
     "measured = compute_signals(session, scope, customer)\nkeep(measured)\n"),
    ("M3's result is read without a name",
     _compute_signals_violations,
     "x = compute_signals(session, scope, customer).signals\n"),
    ("the run queries its session",
     _session_violations,
     "def f(session):\n    return session.execute(query)\n"),
    ("the run commits",
     _session_violations,
     "def f(s):\n    s.commit()\n"),
    ("the run opens a session",
     _session_violations,
     "def f(engine):\n    return Session(engine)\n"),
    ("payload takes a session",
     _impurity_violations,
     "def build(session, payload):\n    return payload\n"),
    ("brief names an ORM model",
     _impurity_violations,
     "def render(p):\n    return Customer\n"),
    ("brief prints",
     _impurity_violations,
     "print('rendered')\n"),
    ("payload tests a granted type",
     lambda tree: _type_only_violations(tree, {"Reconciliation"}),
     "def f(r: Reconciliation) -> bool:\n    return isinstance(r, Reconciliation)\n"),
    ("an event passes its fields through **",
     _log_call_violations,
     "log_event(logger, logging.INFO, 'vs01.scope_resolved', **fields)\n"),
    ("an event is not the directed one",
     _log_call_violations,
     "log_event(logger, logging.INFO, 'vs01.band_assigned', customer=c)\n"),
    ("an event is logged at WARNING",
     _log_call_violations,
     "log_event(logger, logging.WARNING, 'vs01.links_derived', source_system=s, "
     "layer1_fingerprint=f, linker_version=v, inserted=n)\n"),
    ("an event's fields are out of order",
     _log_call_violations,
     "log_event(logger, logging.INFO, 'vs01.links_derived', layer1_fingerprint=f, "
     "source_system=s, linker_version=v, inserted=n)\n"),
    ("an event logs an amount",
     _log_call_violations,
     "log_event(logger, logging.INFO, 'vs01.brief_generated', customer=c, payload_hash=h, "
     "citation_count=deal.amount, created=True)\n"),
    ("the run logs around log_event",
     _logging_violations,
     "logger = logging.getLogger(__name__)\nlogger.info('done')\n"),
    ("the run logs at warning through the module",
     _logging_violations,
     "logger = logging.getLogger(__name__)\nlogging.warning('done')\n"),
    ("the run names another logger",
     _logging_violations,
     "logger = logging.getLogger('vs01')\n"),
    ("the run reads a file",
     lambda tree: _file_violations("assessment", tree),
     "text = Path('x').read_text()\n"),
    ("brief writes a file",
     lambda tree: _file_violations("brief", tree),
     "TEMPLATE_PATH.read_text(encoding='utf-8')\nTEMPLATE_PATH.write_text(t)\n"),
    ("brief reads without an encoding",
     lambda tree: _file_violations("brief", tree),
     "TEMPLATE_PATH.read_text()\n"),
    ("brief catches everything",
     lambda tree: _handler_violations("brief", tree),
     "try:\n    x()\nexcept Exception:\n    pass\n"),
    ("the run catches",
     lambda tree: _handler_violations("assessment", tree),
     "try:\n    x()\nexcept KeyError:\n    pass\n"),
    ("brief has a bare except",
     lambda tree: _handler_violations("brief", tree),
     "try:\n    x()\nexcept:\n    pass\n"),
    ("persistence imports M1",
     _layer2_violations,
     "from app.intelligence.contract import Position\n"),
    ("persistence imports M7",
     _layer2_violations,
     "from app.decisions.payload import payload_hash\n"),
    ("textual SQL is imported",
     _textual_sql_violations,
     "from sqlalchemy import text\n"),
    ("a .text attribute is read",
     _textual_sql_violations,
     "rows = connection.execute(statement).text\n"),
    ("a repository logs",
     _repository_log_violations,
     "import logging\n"),
    ("a repository flushes",
     _transaction_violations,
     "def f(session):\n    session.flush()\n"),
    ("a repository builds a link",
     _m4_domain_violations,
     "link = DerivedLink(a, b)\n"),
    ("a repository builds a position",
     _m7_domain_violations,
     "row = Position(function, stance)\n"),
]


@pytest.mark.parametrize(("label", "scan", "source"), REINTRODUCTIONS,
                         ids=[label for label, _, _ in REINTRODUCTIONS])
def test_every_scan_catches_its_reintroduction(label, scan, source):
    assert scan(ast.parse(source)), label


def test_the_code_scan_reads_code_and_not_the_docstrings_explaining_it():
    assert _m4_domain_violations(ast.parse('"""Builds no DerivedLink."""\nx = 1\n')) == []
    assert _m7_domain_violations(ast.parse("RiskPosition = PositionRow\n")) == []


# ---------------------------------------------------------------------------
# Where M7 exists
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [*M7_MODULES.values(), *M7_MODELS, *M7_REPOSITORIES,
                                  M7_MIGRATION], ids=lambda path: path.name)
def test_every_m7_file_exists_and_is_scanned(path):
    """A scan that silently matches nothing proves nothing."""
    assert path.is_file()
    assert _code(_tree(path)).strip()


def test_the_decision_layer_is_exactly_m6_and_m7s_seven_modules():
    """§0.6.1 T-M7-1 (b), asserted from M7's side: no other .py file anywhere under app/decisions/."""
    assert set(DECISIONS_DIR.rglob("*.py")) == {*M6_MODULES, *M7_MODULES.values()}


def test_the_templates_directory_holds_the_one_template_as_utf8_text():
    """§0.6.10: `brief.txt`, UTF-8 plain text, and no Python."""
    from app.decisions import brief

    assert sorted(path.name for path in TEMPLATES_DIR.iterdir()) == ["brief.txt"]
    assert brief.TEMPLATE_PATH == TEMPLATES_DIR / "brief.txt"
    assert brief.TEMPLATE_PATH.read_bytes().decode("utf-8")


# ---------------------------------------------------------------------------
# Direction, and who may import M7
# ---------------------------------------------------------------------------


def test_the_direction_is_assessment_to_payload_and_brief_and_brief_to_payload():
    edges = set().union(*(_m7_edges(name, _tree(path)) for name, path in M7_MODULES.items()))

    assert edges <= ALLOWED_EDGES, sorted(edges - ALLOWED_EDGES)
    assert {("assessment", "payload"), ("assessment", "brief")} <= edges


def test_no_m6_module_imports_an_m7_module():
    """§0.6.2's first bullet, independently of T-M7-1 (d) in the M6 file."""
    assert _m7_importers(list(M6_MODULES)) == []


def test_nothing_outside_the_package_imports_m7():
    """M1-M5, persistence, the API, scripts and migrations: M8's routes need their own evolution."""
    paths = [path for directory in ("app", "scripts", "migrations", "docker")
             for path in sorted((REPO / directory).rglob("*.py"))
             if not path.is_relative_to(DECISIONS_DIR)]

    assert paths
    assert _m7_importers(paths) == []


@pytest.mark.parametrize("source", [
    "from app.decisions.assessment import run_assessment\n",
    "from app.decisions import payload\n",
    "import app.decisions.brief\n",
])
def test_the_importer_scan_would_catch_an_outside_import(tmp_path, source):
    importer = tmp_path / "importer.py"
    importer.write_text(source, encoding="utf-8")

    assert _m7_importers([importer]), source


def test_the_initialiser_re_exports_nothing_of_m7():
    """§0.6.2: M7 is imported by submodule path, as the M3 modules are."""
    decisions = importlib.import_module("app.decisions")
    defined: set[str] = set()
    for path in M7_MODULES.values():
        for node in _tree(path).body:
            if isinstance(node, ast.FunctionDef | ast.ClassDef):
                defined.add(node.name)
            elif isinstance(node, ast.Assign):
                defined |= {target.id for target in node.targets if isinstance(target, ast.Name)}
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                defined.add(node.target.id)
    public = {name for name in defined if not name.startswith("_")}

    assert {"run_assessment", "AssessmentResult", "build_payload", "payload_hash",
            "render_brief", "BriefRenderError", "TEMPLATE_VERSION"} <= public
    assert public.isdisjoint(decisions.__all__)
    assert [name for name in sorted(public) if hasattr(decisions, name)] == []


def test_importing_the_package_loads_no_m7_module():
    """In a fresh interpreter, so no earlier import in this process can hide a re-export."""
    completed = subprocess.run(
        [sys.executable, "-c", "import sys, app.decisions; print(' '.join(sorted("
         "name for name in sys.modules if name.startswith('app.decisions.'))))"],
        cwd=REPO, capture_output=True, text=True, check=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )

    assert completed.stdout.split() == [
        "app.decisions.conflicts", "app.decisions.policy", "app.decisions.reconciler"]


# ---------------------------------------------------------------------------
# Imports: each module's row of §0.6.2, as a closed world
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", sorted(M7_MODULES))
def test_each_module_imports_exactly_what_its_row_grants(module):
    assert _import_violations(module, _tree(M7_MODULES[module])) == []


@pytest.mark.parametrize("module", sorted(M7_MODULES))
def test_each_module_imports_no_clock_module_randomness_or_network(module):
    """DR5: datetime for `as_of` and the UUID type in assessment.py only; logging there only."""
    assert _stdlib_violations(module, _tree(M7_MODULES[module])) == []


def test_the_initialiser_map_resolves_the_names_the_modules_import():
    """A root import must resolve to its defining module, or the closed world is a guess."""
    for path in (M7_MODULES["assessment"], M7_MODULES["payload"]):
        for imported, name, _ in _imports(_tree(path)):
            if imported == "app.intelligence":
                assert INTELLIGENCE_EXPORTS[name] in M1_MODULES, name
    assert INTELLIGENCE_EXPORTS["MoneyValue"] == "app.intelligence.money"


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def test_links_are_derived_once_unconditionally_after_the_scope_and_before_any_customer():
    """§0.6.3 step 2 and §0.4.3: S14 reads the links it writes, so they come first."""
    assert _derive_violations(_tree(M7_MODULES["assessment"])) == []


def test_compute_signals_is_read_for_its_two_fields_only():
    """§0.6.4's authority rule: the contexts' signals, never compute_signals(...).signals."""
    tree = _tree(M7_MODULES["assessment"])

    assert _calls(tree, "compute_signals")
    assert _compute_signals_violations(tree) == []


@pytest.mark.parametrize("forbidden", sorted(NEVER_CALLED))
def test_the_run_calls_none_of_the_functions_its_callees_own(forbidden):
    """§0.6.2: build_contexts and reconcile own these, so calling one would duplicate M3-M6."""
    tree = _tree(M7_MODULES["assessment"])

    assert forbidden not in _called_names(tree)
    assert forbidden not in {name for _, name, _ in _imports(tree)}


def test_the_run_writes_only_through_its_repositories_and_owns_no_transaction():
    """No session method at all: every read and write is a repository's (§0.6.2, §0.6.3)."""
    tree = _tree(M7_MODULES["assessment"])

    assert _session_violations(tree) == []
    assert {"insert_assessment", "insert_positions", "insert_brief"} <= _called_names(tree)


# ---------------------------------------------------------------------------
# Pure: payload.py and brief.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", ["payload", "brief"])
def test_the_pure_modules_hold_no_session_model_or_log_line(module):
    assert _impurity_violations(_tree(M7_MODULES[module])) == []


def test_payload_names_its_two_granted_types_in_annotations_only():
    """§0.6.2 grants AnalystContexts and Reconciliation to payload.py as types, and only as types."""
    tree = _tree(M7_MODULES["payload"])
    granted = {"AnalystContexts", "Reconciliation"}

    assert _type_only_violations(tree, granted) == []
    assert granted <= {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


# ---------------------------------------------------------------------------
# Clock and randomness, in all three modules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", sorted(M7_MODULES))
def test_no_module_reads_a_clock(module):
    assert _clock_violations(_tree(M7_MODULES[module])) == []


@pytest.mark.parametrize("module", sorted(M7_MODULES))
def test_no_module_generates_an_id(module):
    """Database-generated ids are the repositories'; no M7 module mints one."""
    assert _generator_violations(_tree(M7_MODULES[module])) == []


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def test_every_event_is_log_event_at_info_with_its_fields_as_explicit_keywords():
    assert _log_call_violations(_tree(M7_MODULES["assessment"])) == []


def test_the_run_emits_exactly_the_five_events_each_from_one_call_site():
    """§0.6.13.6: no other event type; signals_computed and band_assigned stay deferred."""
    emitted = collections.Counter(
        call.args[2].value for call in _calls(_tree(M7_MODULES["assessment"]), "log_event"))

    assert emitted == dict.fromkeys(EVENTS, 1)


def test_the_run_logs_through_log_event_only():
    assert _logging_violations(_tree(M7_MODULES["assessment"])) == []


def test_the_run_increments_no_counter():
    """DR13: log_event exclusively; no existing counter describes an assessment run."""
    assert not any(imported.startswith("app.observability")
                   for imported, _, _ in _imports(_tree(M7_MODULES["assessment"])))


# ---------------------------------------------------------------------------
# Files and exceptions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", sorted(M7_MODULES))
def test_only_brief_reads_a_file_and_nothing_writes(module):
    assert _file_violations(module, _tree(M7_MODULES[module])) == []


@pytest.mark.parametrize("module", sorted(M7_MODULES))
def test_nothing_is_caught_but_the_rendering_conditions(module):
    """§0.6.11: nothing caught, retried or wrapped, but §0.6.13.5's four conditions in brief.py."""
    assert _handler_violations(module, _tree(M7_MODULES[module])) == []


# ---------------------------------------------------------------------------
# Textual SQL, over every M7 file
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [*M7_MODULES.values(), *M7_MODELS, *M7_REPOSITORIES],
                         ids=lambda path: path.name)
def test_no_m7_file_uses_textual_sql_or_a_text_attribute(path):
    assert _textual_sql_violations(_tree(path)) == []


# ---------------------------------------------------------------------------
# Persistence (§0.6.5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [*M7_MODELS, *M7_REPOSITORIES, M7_MIGRATION],
                         ids=lambda path: path.name)
def test_m7_persistence_imports_no_layer_2_package(path):
    """
    D-M4-B2, mirrored: importing app.intelligence here would force M1's
    importer whitelist to admit app/persistence, and importing app.decisions
    would close a cycle. The migration stands alone.
    """
    assert _layer2_violations(_tree(path)) == []


def test_the_migration_imports_nothing_from_the_application():
    """Hand-written DDL, like M4's: alembic, SQLAlchemy and typing only."""
    roots = {imported.split(".")[0] for imported, _, _ in _imports(_tree(M7_MIGRATION))}

    assert roots <= {"__future__", "typing", "alembic", "sqlalchemy"}, roots


@pytest.mark.parametrize("path", M7_REPOSITORIES, ids=lambda path: path.name)
def test_the_repositories_never_name_an_m4_domain_type(path):
    """M4's DOMAIN_NAMES scan, mirrored as §0.6.5 directs."""
    assert _m4_domain_violations(_tree(path)) == []


@pytest.mark.parametrize("path", M7_REPOSITORIES, ids=lambda path: path.name)
def test_the_repositories_never_name_an_m7_domain_type(path):
    """The repositories take and return plain data; giving it meaning is the run's."""
    assert _m7_domain_violations(_tree(path)) == []


@pytest.mark.parametrize("path", M7_REPOSITORIES, ids=lambda path: path.name)
def test_the_repositories_own_no_transaction_and_do_not_log(path):
    tree = _tree(path)

    assert _transaction_violations(tree) == []
    assert _repository_log_violations(tree) == []


def test_the_writes_are_append_or_read_and_never_update():
    """§0.6.6: ON CONFLICT DO NOTHING on each of the three identities, and never DO UPDATE."""
    tree = _tree(M7_REPOSITORIES[0])
    code = _code(tree)

    assert code.count("on_conflict_do_nothing(") == 3
    assert "on_conflict_do_update" not in code
    assert _called_names(tree).isdisjoint({"update", "delete", "merge"})


def test_the_citation_reads_only_read_through_entity_models():
    """§0.6.5: ENTITY_MODELS from canonical.py, no ORM model import, and no write."""
    tree = _tree(M7_REPOSITORIES[1])

    assert ("app.persistence.repositories.canonical", "ENTITY_MODELS") in {
        (imported, name) for imported, name, _ in _imports(tree)}
    assert not any(imported.startswith("app.persistence.models")
                   for imported, _, _ in _imports(tree))
    assert _called_names(tree).isdisjoint({"insert", "update", "delete", "on_conflict_do_nothing"})
    assert "select" in _called_names(tree)


def test_the_m7_models_carry_no_provenance_mixin():
    """§0.6.5: "None uses ProvenanceMixin". An assessment is not an ingested record."""
    from app.persistence.models import Customer, RiskAssessment, RiskBrief, RiskPosition
    from app.persistence.models.mixins import ProvenanceMixin

    models = (RiskAssessment, RiskPosition, RiskBrief)

    assert {model.__table__.name for model in models} == M7_TABLES
    for model in models:
        assert not issubclass(model, ProvenanceMixin), model.__name__
    assert issubclass(Customer, ProvenanceMixin), "the check must be able to fail"


def test_no_layer_1_or_m4_table_references_an_m7_table():
    """
    Layer 1 and M4 are frozen, so none of their tables gained a reference to an M7 table.

    The frozen models are named, as M4's own check names its models, so a later
    milestone's table that references an M7 table is not this file's concern.
    """
    from app.persistence.models import (
        ConnectorConfig,
        Customer,
        Deal,
        Document,
        DocumentCustomerLink,
        Employee,
        IngestionCursor,
        IngestionError,
        IngestionRun,
        Organization,
        Project,
        SourceRecord,
        SupportTicket,
    )

    frozen = (Organization, Employee, Customer, Deal, Project, SupportTicket, Document,
              IngestionRun, IngestionError, SourceRecord, ConnectorConfig, IngestionCursor,
              DocumentCustomerLink)
    referencing = sorted(
        f"{model.__table__.name}.{key.parent.name}"
        for model in frozen
        for key in model.__table__.foreign_keys
        if key.column.table.name in M7_TABLES
    )

    assert any(model.__table__.foreign_keys for model in frozen), "the scan must reach a key"
    assert referencing == []
