"""
M8 static boundaries (§0.7.4 to §0.7.11).

Each row of M8's dependency boundary, its persistence contract and its
no-executor boundary is checked structurally:

    Where M8 exists    §0.7.4's six new sources: approval.py beside M6's and
                       M7's seven modules, the model, the two repositories,
                       the migration and the route module.
    Persistence        the BriefDecision model, both M8 repositories and the
                       M8 migration import no Layer 2 package. The
                       repositories name no domain type, own no transaction,
                       use no textual SQL, do not log and contain no update or
                       delete construct. No repository or model imports the
                       route, approval or anything under app.api.
    Insert only        brief_decisions.py inserts and does nothing else: no
                       update, no delete, no upsert and no read, and its one
                       ON CONFLICT DO NOTHING names no conflict target, so
                       every unique index, the partial ones included, skips
                       a conflicting row (OPEN-M8-4, §0.7.6).
    Raw DDL            the M8 migration's op.execute calls create and drop
                       its one function and one trigger, and nothing else; no
                       other migration executes raw SQL (OPEN-M8-4).
    No provenance      BriefDecision is not a ProvenanceMixin (§0.7.5).
    Approval           approval.py imports exactly its row, as a closed world,
                       and names datetime, UUID and Session as types only. It
                       reads no clock, generates no id, reaches no random
                       source, calls no session method and holds no try, and
                       it has one vs01.decision_recorded call site with its
                       three fields in order (§0.7.10). Only the risk route
                       imports it; app.decisions neither re-exports nor loads it.
    The route          risk.py imports exactly its row, as a closed world. It
                       reads the clock at its one _utc_now site, and the
                       decision route calls clock() once, before its
                       transaction. Each POST owns one `with sessions() as
                       session, session.begin()` inside a try whose handlers
                       sit outside it; each GET reads one read_snapshot. It
                       handles exactly §0.7.9's five exceptions, never commits,
                       rolls back or logs, and names no ORM model (§0.7.8).
    Schemas            schemas.py imports no Layer 2 package.
    No executor        §0.7.11's static first-party closure from the five Layer
                       2 packages: checks 1-5, with named third-party
                       exemptions, each of which must still be needed.

Code is scanned with docstrings stripped, using M4's `_code()` technique,
because these modules explain at length what they do not do. Each rule is a
function returning its violations; the real files must return none, and
`test_every_scan_catches_its_reintroduction` runs the same function over a
small reintroduction of what it forbids, so no scan can pass vacuously
(M7's REINTRODUCTIONS pattern). The no-executor checks run over a
`{module name: source text}` mapping, the real tree's or a small synthetic
one's, so each companion runs through the same functions (§0.7.11).
"""

from __future__ import annotations

import ast
import importlib.machinery
import importlib.util
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

import app.persistence.models  # noqa: F401 -- registers every mapper for ORM_MODELS
from app.core.database import Base

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
APP_DIR = REPO / "app"
DECISIONS_DIR = APP_DIR / "decisions"
PERSISTENCE_DIR = REPO / "app" / "persistence"
MIGRATIONS_DIR = REPO / "migrations" / "versions"

#: §0.7.4: M8's persistence, and its one migration.
M8_MODEL = PERSISTENCE_DIR / "models" / "brief_decision.py"
M8_REPOSITORY = PERSISTENCE_DIR / "repositories" / "brief_decisions.py"
M8_QUERIES = PERSISTENCE_DIR / "repositories" / "risk_queries.py"
M8_MIGRATION = MIGRATIONS_DIR / "070e4968a497_m8_brief_decisions.py"
M8_PERSISTENCE = (M8_MODEL, M8_REPOSITORY, M8_MIGRATION, M8_QUERIES)
#: §0.7.4: the other two of M8's six new sources, and the schemas it extends.
APPROVAL = DECISIONS_DIR / "approval.py"
RISK_ROUTE = APP_DIR / "api" / "v1" / "risk.py"
SCHEMAS = APP_DIR / "api" / "v1" / "schemas.py"
#: M6's four and M7's three modules, beside which approval.py is M8's one.
EARLIER_DECISION_MODULES = {"__init__.py", "policy.py", "conflicts.py", "reconciler.py",
                            "assessment.py", "payload.py", "brief.py"}

#: §0.7.5: the one function and the one trigger raw DDL may name.
APPEND_ONLY = "brief_decisions_append_only"

LAYER2_PACKAGES = ("app.intelligence", "app.evidence", "app.analysts", "app.decisions",
                   "app.relationships")
#: M4's DOMAIN_NAMES, verbatim (test_m4_boundary.py).
M4_DOMAIN_NAMES = {
    "DerivedLink", "LinkedDocument", "EntityRef", "Evidence", "EvidenceKind",
    "DocumentCitation", "LinkBasis", "LinkConfidence", "SignalSet", "Scope",
}
#: test_m7_boundary.py's M7_DOMAIN_NAMES, verbatim.
M7_DOMAIN_NAMES = {
    "Position", "Conflict", "ConflictResolution", "Reconciliation", "Worthiness",
    "AnalystContexts", "CustomerSignals", "Citation", "RecordCitation", "RiskBand",
    "Function", "Stance", "ActionId", "MoneyValue", "RiskRulesConfig", "AssessmentResult",
    "SpanTarget", "CalendarDate",
}
#: §0.7.7's vocabulary, which M8's repositories equally never name.
M8_DOMAIN_NAMES = {
    "Decision", "DecisionStatus", "HashConflict", "DecisionConflict", "DecisionRecord",
    "ApprovalError", "UnknownBriefError", "PayloadHashConflictError", "DecisionConflictError",
    "record_decision", "decision_history", "decision_status",
}

#: Constructs that change or remove a row, or merge one in.
WRITE_CALLS = {"update", "delete", "merge", "on_conflict_do_update", "bulk_update_mappings",
               "bulk_save_objects"}
#: Constructs that read a table.
READ_CALLS = {"select", "query", "get", "get_one", "scalars", "join", "where", "filter",
              "filter_by", "exists"}

#: A closed world's grants: each module a file may import from, and the names
#: it may take there. None means every name that module defines. `from X
#: import Y` is judged as the module X.Y whenever X.Y is a module, so a grant of
#: X admits X's names and none of its submodules (§0.7.11's convention; the
#: owner's Q3 ruling, 2026-09-26). A first-party module is always imported from
#: by name, never as `import app.x` (M7's convention).
Grants = dict[str, frozenset[str] | None]

#: §0.7.4's row for app/decisions/approval.py.
APPROVAL_GRANTS: Grants = {
    "__future__": None,
    "logging": None,
    "dataclasses": None,
    "enum": None,
    "collections.abc": None,
    "typing": None,
    "datetime": frozenset({"datetime"}),
    "uuid": frozenset({"UUID"}),
    "sqlalchemy.orm": frozenset({"Session"}),
    "app.persistence.repositories.brief_decisions": frozenset({"insert_decision", "NewDecision"}),
    "app.persistence.repositories.risk_queries": frozenset({"get_brief", "decisions_for"}),
    "app.decisions.payload": frozenset({"payload_hash"}),
    "app.intelligence.errors": frozenset({"IntelligenceError", "ContractViolationError"}),
    "app.core.logging": frozenset({"log_event"}),
}
#: §0.7.4: the three names approval.py may use as types, and only as types.
APPROVAL_TYPES = {"datetime", "UUID", "Session"}

#: The models and mirrored enums M8 adds to app/api/v1/schemas.py (§0.7.4, §0.7.8).
M8_SCHEMA_NAMES = frozenset({
    "RiskDecision", "RiskDecisionStatus", "AssessmentRunRequest", "AssessmentRunItem",
    "AssessmentRunResponse", "AssessmentFields", "AssessmentListItem", "AssessmentListResponse",
    "AssessmentPosition", "AssessmentBrief", "AssessmentDetailResponse", "BriefResponse",
    "DecisionRequest", "DecisionResponse", "DecisionHistoryResponse",
})
#: §0.7.4's row for app/api/v1/risk.py, with T-M8-10's two app.intelligence
#: names. `__future__` admits `annotations` only: the compiler directive every
#: route module under app/api carries (the owner's Q1 ruling, 2026-09-26).
ROUTE_GRANTS: Grants = {
    "__future__": frozenset({"annotations"}),
    "fastapi": None,
    "sqlalchemy.orm": frozenset({"Session", "sessionmaker"}),
    "datetime": None,
    "http": None,
    "uuid": None,
    "collections.abc": None,
    "app.api.dependencies": frozenset({"get_sessions", "read_snapshot"}),
    "app.api.errors": frozenset({"ApiError", "ErrorCode", "ErrorResponse"}),
    "app.api.v1.schemas": M8_SCHEMA_NAMES,
    "app.decisions.assessment": frozenset({"run_assessment"}),
    "app.decisions.approval": None,
    "app.decisions.payload": frozenset({"payload_citations"}),
    "app.persistence.repositories.risk_queries": None,
    "app.relationships": frozenset({"UnknownCustomerError"}),
    "app.intelligence": frozenset({"ScopeResolutionError", "RiskBand"}),
}

#: §0.7.4's clock names. approval.py uses none; the route reads one, once.
FORBIDDEN_CLOCKS = {"now", "today", "utcnow", "utcfromtimestamp", "fromtimestamp", "time",
                    "monotonic", "perf_counter"}
UUID_GENERATORS = {"uuid1", "uuid3", "uuid4", "uuid5"}
RANDOM_SOURCES = {"random", "secrets"}
#: §0.7.4: approval.py reads and writes through its repositories, so it calls none of these.
SESSION_METHODS = {"commit", "rollback", "begin", "begin_nested", "close", "flush", "add",
                   "add_all", "delete", "merge", "execute"}
#: §0.7.10: the one event and its fields in order, and what approval.py holds
#: but never logs: the actor, the note, the time and every id.
EVENT = "vs01.decision_recorded"
EVENT_FIELDS = ("payload_hash", "decision", "supersedes")
NEVER_LOGGED = {"actor", "note", "decided_at", "brief_id", "identifier", "id"}

#: §0.7.8: each POST's one transaction and each GET's one snapshot, as written.
TRANSACTION = ["sessions() as session", "session.begin()"]
SNAPSHOT = ["read_snapshot(sessions) as session"]
#: The domain operations a POST runs inside its transaction.
DOMAIN_CALLS = {"run_assessment", "record_decision"}
#: §0.7.9: the five exceptions the route maps. Every other one is the existing
#: handler's 500. This is additive to F1's no-broad-except rule, which stands
#: unchanged (the owner's Q4 ruling, 2026-09-26).
MAPPED_EXCEPTIONS = {"UnknownCustomerError", "ScopeResolutionError", "UnknownBriefError",
                     "PayloadHashConflictError", "DecisionConflictError"}

ORM_MODELS = {mapper.class_.__name__ for mapper in Base.registry.mappers}

#: §0.7.11 check 1: the first-party modules no closure may reach, with everything beneath each.
FORBIDDEN_FIRST_PARTY = ("app.connectors", "app.core.security", "app.api", "app.ingestion")
#: §0.7.11 check 2: the outbound clients no closure module imports, nor any submodule of one.
OUTBOUND_MODULES = ("httpx", "requests", "aiohttp", "urllib3", "urllib.request", "http.client",
                    "smtplib", "socket", "ssl", "ftplib", "xmlrpc")
#: §0.7.11 check 3: the third-party packages the closure may import directly,
#: each named for the reason it is needed, in the format of G2's
#: SUBPROCESS_MODULES and HTTP_CLIENT_MODULES (the I1 named-exemption
#: mechanism). Naming a package is what admits it: its internals are not scanned.
#: - sqlalchemy: the ORM models, the repositories' query expressions and the
#:   Session type, through which every Layer 2 read and write goes
#:   (app.persistence, app.core.database).
#: - pydantic: the canonical schemas (app.schemas.canonical), Layer 1's
#:   normalization pipeline and app.core.config's settings model.
#: - pydantic_settings: app.core.config's Settings, from which app.core.database
#:   reads the database URL.
#: - yaml: the configuration that M1 (app.intelligence.config), M6
#:   (app.decisions.policy) and Layer 1's normalization load, with safe_load only.
THIRD_PARTY_EXEMPTIONS = frozenset({"sqlalchemy", "pydantic", "pydantic_settings", "yaml"})


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


def _constants(tree: ast.Module) -> dict[str, str]:
    """The module's top-level string constants, by name."""
    return {
        target.id: node.value.value
        for node in tree.body if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
        for target in node.targets if isinstance(target, ast.Name)
    }


# ---------------------------------------------------------------------------
# The rules, each returning its violations
# ---------------------------------------------------------------------------


def _layer2_violations(tree: ast.AST) -> list[str]:
    """D-M4-B2, §0.6.5 and §0.7.4: persistence stays below every Layer 2 package."""
    return [f"{line}: {imported}" for imported, _, line in _imports(tree)
            if imported.startswith(LAYER2_PACKAGES)]


def _textual_sql_violations(tree: ast.AST) -> list[str]:
    """E1 and G2's rule: no text(), no .text, no driver SQL."""
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


def _domain_violations(tree: ast.AST) -> list[str]:
    """M4's, M7's and M8's vocabularies, by whole word, so BriefDecision is not Decision."""
    return sorted(_words(tree) & (M4_DOMAIN_NAMES | M7_DOMAIN_NAMES | M8_DOMAIN_NAMES))


def _write_violations(tree: ast.AST) -> list[str]:
    """OPEN-M8-4: no update, no delete and no upsert construct, as a call or an attribute."""
    found = sorted(_called_names(tree) & WRITE_CALLS)
    found += [f"{node.lineno}: .{node.attr}" for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and node.attr in WRITE_CALLS
              and not isinstance(node.ctx, ast.Store)]
    found += [f"{line}: {name}" for imported, name, line in _imports(tree)
              if imported.startswith("sqlalchemy") and name in WRITE_CALLS]
    return found


def _read_violations(tree: ast.AST) -> list[str]:
    """§0.7.6: brief_decisions.py reads nothing; every read is risk_queries.py's."""
    found = sorted(_called_names(tree) & READ_CALLS)
    found += [f"{line}: {name}" for imported, name, line in _imports(tree)
              if imported.startswith("sqlalchemy") and name in READ_CALLS]
    return found


def _conflict_violations(tree: ast.AST) -> list[str]:
    """§0.7.6: exactly one insert, and one ON CONFLICT DO NOTHING that names no target."""
    found = []
    inserts, skips = _calls(tree, "insert"), _calls(tree, "on_conflict_do_nothing")
    if len(inserts) != 1:
        found.append(f"{len(inserts)} insert constructs")
    if len(skips) != 1:
        found.append(f"{len(skips)} on_conflict_do_nothing clauses")
    found += [f"{call.lineno}: the conflict target is named" for call in skips
              if call.args or call.keywords]
    return found


def _surface_violations(tree: ast.Module) -> list[str]:
    """The repository's public surface is exactly the row type and the insert."""
    public = {node.name for node in tree.body
              if isinstance(node, ast.FunctionDef | ast.ClassDef) and not node.name.startswith("_")}
    public |= {target.id for node in tree.body if isinstance(node, ast.Assign)
               for target in node.targets
               if isinstance(target, ast.Name) and not target.id.startswith("_")}
    return sorted(public ^ {"NewDecision", "insert_decision"})


def _raw_ddl_violations(tree: ast.Module, *, authorised: bool) -> list[str]:
    """
    OPEN-M8-4: op.execute only in M8's migration, only for its function and
    trigger. Each call's argument is a string, directly or through a module
    constant, that names the function and creates or drops only it or the
    trigger.
    """
    constants, found = _constants(tree), []
    calls = [call for call in ast.walk(tree)
             if isinstance(call, ast.Call) and _dotted(call.func) in {"op.execute", "execute"}]
    if not authorised:
        return [f"{call.lineno}: op.execute" for call in calls]
    for call in calls:
        argument = call.args[0] if len(call.args) == 1 and not call.keywords else None
        if isinstance(argument, ast.Name):
            statement = constants.get(argument.id)
        elif isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            statement = argument.value
        else:
            statement = None
        if statement is None:
            found.append(f"{call.lineno}: an argument that is not a string constant")
            continue
        lead = " ".join(statement.split()[:3]).upper()
        if APPEND_ONLY not in statement or lead not in {
                "CREATE FUNCTION " + APPEND_ONLY.upper() + "()",
                "CREATE TRIGGER " + APPEND_ONLY.upper(),
                "DROP TRIGGER " + APPEND_ONLY.upper(),
                "DROP FUNCTION " + APPEND_ONLY.upper() + "()"}:
            found.append(f"{call.lineno}: {lead}")
    return found


def _upward_violations(tree: ast.AST) -> list[str]:
    """§0.7.4's direction: nothing below the route imports it, approval, or anything under app.api."""
    return [f"{line}: {imported}" for imported, name, line in _imports(tree)
            if imported == "app.api" or imported.startswith("app.api.")
            or imported == "app.decisions.approval"
            or (imported == "app.decisions" and name == "approval")]


# ---------------------------------------------------------------------------
# The closed worlds (§0.7.4)
# ---------------------------------------------------------------------------


def _is_module(dotted: str) -> bool:
    """
    Whether a dotted name is a module or a package, found without importing it.

    Names are compared as the directory listing spells them, because a
    case-insensitive filesystem would otherwise take `Session` for session.py.
    """
    parent, _, leaf = dotted.rpartition(".")
    if dotted.split(".")[0] == "app":
        locations = [REPO.joinpath(*parent.split("."))]
    else:
        try:
            spec = importlib.util.find_spec(parent)
        except (ImportError, ValueError):
            return False
        locations = [Path(one) for one in (spec.submodule_search_locations or [])] if spec else []
    for location in locations:
        names = set(os.listdir(location)) if location.is_dir() else set()
        if leaf in names and (location / leaf).is_dir():
            return True
        if any(leaf + suffix in names for suffix in importlib.machinery.all_suffixes()):
            return True
    return False


def _closed_world_violations(tree: ast.AST, grants: Grants) -> list[str]:
    """Every import its grants do not name: the row is a closed world (§0.7.4)."""
    found = []
    for imported, name, line in _imports(tree):
        if imported.startswith("."):
            found.append(f"{line}: relative import {imported}")
        elif name is None:
            if imported.split(".")[0] == "app" or grants.get(imported, frozenset()) is not None:
                found.append(f"{line}: import {imported}")
        elif name == "*":
            found.append(f"{line}: from {imported} import *")
        elif _is_module(f"{imported}.{name}"):
            if grants.get(f"{imported}.{name}", frozenset()) is not None:
                found.append(f"{line}: {imported}.{name}, a module")
        elif imported not in grants:
            found.append(f"{line}: {imported}.{name}")
        elif grants[imported] is not None and name not in grants[imported]:
            found.append(f"{line}: {imported}.{name}")
    return found


def _approval_import_violations(tree: ast.AST) -> list[str]:
    return _closed_world_violations(tree, APPROVAL_GRANTS)


def _route_import_violations(tree: ast.AST) -> list[str]:
    return _closed_world_violations(tree, ROUTE_GRANTS)


# ---------------------------------------------------------------------------
# approval.py (§0.7.4, §0.7.7, §0.7.10)
# ---------------------------------------------------------------------------


def _type_only_violations(tree: ast.AST, names: set[str]) -> list[str]:
    """Where a type granted only as a type is named outside an annotation: called, tested or passed on."""
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


def _clock_violations(tree: ast.AST) -> list[str]:
    """Every clock name, as an attribute or a name: X7 leaves approval.py none."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_CLOCKS:
            found.append(f"{node.lineno}: .{node.attr}")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_CLOCKS:
            found.append(f"{node.lineno}: {node.id}")
    return found


def _generator_violations(tree: ast.AST) -> list[str]:
    """§0.7.4: no uuid generator is called and no random source imported; the id is the repository's."""
    found = sorted(_called_names(tree) & UUID_GENERATORS)
    found += [f"{line}: {imported}" for imported, _, line in _imports(tree)
              if imported.split(".")[0] in RANDOM_SOURCES]
    return found


def _session_violations(tree: ast.AST) -> list[str]:
    """§0.7.4: approval.py hands its session to its repositories and never uses it itself."""
    found = [f"{node.lineno}: session.{node.attr}" for node in ast.walk(tree)
             if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
             and node.value.id == "session"]
    found += [f"calls {name}()" for name in sorted(_called_names(tree) & SESSION_METHODS)]
    return found


def _try_violations(tree: ast.AST) -> list[str]:
    """§0.7.4 and §0.7.10: nothing is caught or retried, around log_event or anything else."""
    return [f"{node.lineno}: try" for node in ast.walk(tree)
            if isinstance(node, ast.Try | ast.TryStar)]


def _event_violations(tree: ast.AST) -> list[str]:
    """
    §0.7.10: one call site, `log_event(logger, logging.INFO,
    "vs01.decision_recorded", payload_hash=..., decision=...,
    supersedes=supersedes_id is not None)`, naming nothing that is never logged.
    """
    calls = _calls(tree, "log_event")
    found = [] if len(calls) == 1 else [f"{len(calls)} log_event call sites"]
    for call in calls:
        args = call.args
        if (len(args) != 3 or [_dotted(args[0]), _dotted(args[1])] != ["logger", "logging.INFO"]
                or not isinstance(args[2], ast.Constant) or args[2].value != EVENT):
            found.append(f"{call.lineno}: not logger, logging.INFO and {EVENT}")
        if tuple(keyword.arg for keyword in call.keywords) != EVENT_FIELDS:
            found.append(f"{call.lineno}: fields {[keyword.arg for keyword in call.keywords]}")
        for keyword in call.keywords:
            named = {node.id for node in ast.walk(keyword.value) if isinstance(node, ast.Name)}
            named |= {node.attr for node in ast.walk(keyword.value)
                      if isinstance(node, ast.Attribute)}
            found += [f"{call.lineno}: {keyword.arg} logs {one}"
                      for one in sorted(named & NEVER_LOGGED)]
        if [ast.unparse(keyword.value) for keyword in call.keywords
                if keyword.arg == "supersedes"] != ["supersedes_id is not None"]:
            found.append(f"{call.lineno}: supersedes is not `supersedes_id is not None`")
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


def _approval_importers(paths: Iterable[Path]) -> list[str]:
    """Every import of approval, by file and line, `from app.decisions import approval` included."""
    found = []
    for path in paths:
        label = path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else path.name
        for imported, name, line in _imports(_tree(path)):
            if imported == "app.decisions.approval" or (
                    imported == "app.decisions" and name == "approval"):
                found.append(f"{label}:{line}")
    return found


# ---------------------------------------------------------------------------
# The route (§0.7.4, §0.7.8, §0.7.9)
# ---------------------------------------------------------------------------


def _body(function: ast.FunctionDef) -> list[ast.stmt]:
    """A function's statements, without its docstring."""
    body = function.body
    if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        return body[1:]
    return body


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


def _routes(tree: ast.Module) -> list[tuple[str, ast.FunctionDef]]:
    """Each route function with its verb, read from its `@router.<verb>(...)` decorator."""
    return [(decorator.func.attr, node) for node in tree.body if isinstance(node, ast.FunctionDef)
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
            and _dotted(decorator.func.value) == "router"]


def _route_clock_violations(tree: ast.Module) -> list[str]:
    """
    §0.7.4 and §0.7.8: one clock read, `datetime.now(UTC)` in _utc_now, which
    get_clock returns and nothing else names. The one route that takes the
    clock calls clock() once, as `decided_at = clock()`, before the try that
    holds its transaction.
    """
    functions, found = _functions(tree), []
    utc_now, getter = functions.get("_utc_now"), functions.get("get_clock")
    if utc_now is None or [ast.unparse(one) for one in _body(utc_now)] != [
            "return datetime.now(UTC)"]:
        found.append("_utc_now is not exactly `return datetime.now(UTC)`")
    elif _clock_violations(tree) != _clock_violations(utc_now):
        found.append(f"a clock read outside _utc_now: {_clock_violations(tree)}")
    if getter is None or [ast.unparse(one) for one in _body(getter)] != ["return _utc_now"]:
        found.append("get_clock does not return _utc_now")
    named = [node.lineno for node in ast.walk(tree)
             if isinstance(node, ast.Name) and node.id == "_utc_now"]
    if len(named) != 1:
        found.append(f"_utc_now is named {len(named)} times, not by get_clock alone")
    calls = [call for call in ast.walk(tree)
             if isinstance(call, ast.Call) and _dotted(call.func) == "clock"]
    takers = [function for function in functions.values() if "clock" in {
        argument.arg for argument in (*function.args.args, *function.args.kwonlyargs)}]
    if len(calls) != 1 or len(takers) != 1:
        found.append(f"{len(calls)} clock() calls, {len(takers)} functions taking the clock")
    else:
        body = _body(takers[0])
        first_try = next((index for index, one in enumerate(body) if isinstance(one, ast.Try)),
                         len(body))
        if "decided_at = clock()" not in [ast.unparse(one) for one in body[:first_try]]:
            found.append(f"{takers[0].name}: clock() is not read before its transaction")
    return found


def _transaction_shape_violations(tree: ast.Module) -> list[str]:
    """
    §0.7.8. Each POST: one top-level try whose body is one `with sessions() as
    session, session.begin():`, holding the domain call; every handler sits
    outside it and ends in `raise ApiError(...) from None`, so the rollback
    comes first; no other session is opened. Each GET: one
    `with read_snapshot(sessions) as session:`, and sessions() is never called.
    Nothing commits or rolls back.
    """
    found = [f"{node.lineno}: .{node.attr}" for node in ast.walk(tree)
             if isinstance(node, ast.Attribute) and node.attr in {"commit", "rollback"}]
    in_transaction: set[int] = set()
    for verb, function in _routes(tree):
        withs = [node for node in ast.walk(function) if isinstance(node, ast.With)]
        items = [[ast.unparse(item) for item in node.items] for node in withs]
        opened = [call for call in ast.walk(function)
                  if isinstance(call, ast.Call) and _dotted(call.func) == "sessions"]
        if verb != "post":
            if items != [SNAPSHOT] or opened:
                found.append(f"{function.name}: does not read one read_snapshot(sessions)")
            continue
        tries = [node for node in _body(function) if isinstance(node, ast.Try)]
        if not (len(tries) == 1 and len(tries[0].body) == 1
                and isinstance(tries[0].body[0], ast.With)
                and items == [TRANSACTION] and len(opened) == 1):
            found.append(f"{function.name}: not one try around one "
                         "`with sessions() as session, session.begin()`")
            continue
        in_transaction |= {id(node) for node in ast.walk(tries[0].body[0])}
        for handler in tries[0].handlers:
            last = handler.body[-1]
            if not (isinstance(last, ast.Raise) and isinstance(last.exc, ast.Call)
                    and _dotted(last.exc.func) == "ApiError"
                    and isinstance(last.cause, ast.Constant) and last.cause.value is None):
                found.append(f"{function.name}:{handler.lineno}: "
                             "the handler does not raise ApiError(...) from None")
    found += [f"{call.lineno}: {_callee(call)}() outside a POST's transaction"
              for call in ast.walk(tree) if isinstance(call, ast.Call)
              and _callee(call) in DOMAIN_CALLS and id(call) not in in_transaction]
    return found


def _route_handler_violations(tree: ast.AST) -> list[str]:
    """§0.7.9 (the owner's Q4 ruling): the route handles exactly its five mapped exceptions, by name."""
    found, handled = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                found.append(f"{node.lineno}: a bare except")
                continue
            caught = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
            for one in caught:
                handled.add(_dotted(one))
                if _dotted(one) not in MAPPED_EXCEPTIONS:
                    found.append(f"{node.lineno}: catches {ast.unparse(one)}")
    if handled != MAPPED_EXCEPTIONS:
        found.append(f"handles {sorted(handled)}, not the five mapped exceptions")
    return found


def _model_violations(tree: ast.AST) -> list[str]:
    """§0.7.4: the route names no ORM model, and imports neither a model module nor the database."""
    found = [f"{line}: {imported}" for imported, _, line in _imports(tree)
             if imported == "app.core.database" or imported.startswith("app.persistence.models")]
    return found + sorted(_words(tree) & ORM_MODELS)


# ---------------------------------------------------------------------------
# The no-executor boundary (§0.7.11), over a {module name: source text} mapping
# ---------------------------------------------------------------------------


def _module_sources() -> dict[str, str]:
    """Every module under app/, by dotted name (a package by its own name), with its source."""
    sources = {}
    for path in sorted(APP_DIR.rglob("*.py")):
        parts = path.relative_to(REPO).with_suffix("").parts
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        sources[name] = path.read_text(encoding="utf-8")
    return sources


def _within(name: str, packages: Iterable[str]) -> bool:
    return any(name == package or name.startswith(package + ".") for package in packages)


def _roots(sources: dict[str, str]) -> list[str]:
    """Rule 1: every module of the five Layer 2 packages (X5)."""
    return sorted(name for name in sources if _within(name, LAYER2_PACKAGES))


def _imports_of(name: str, sources: dict[str, str]) -> list[tuple[str, list[str]]]:
    """
    One module's imports as (module, names), a relative one resolved against
    the importing package. A name is a package when the mapping holds a module
    beneath it.
    """
    package = name if any(other.startswith(name + ".") for other in sources) else (
        name.rpartition(".")[0])
    found: list[tuple[str, list[str]]] = []
    for node in ast.walk(ast.parse(sources[name])):
        if isinstance(node, ast.Import):
            found += [(alias.name, []) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                base = package
                for _ in range(node.level - 1):
                    base = base.rpartition(".")[0]
                module = f"{base}.{module}" if module else base
            found.append((module, [alias.name for alias in node.names]))
    return found


def _edges(name: str, sources: dict[str, str]) -> set[str]:
    """
    Rule 2: `import a.b.c` reaches a, a.b and a.b.c; `from a.b import c`
    reaches a and a.b, and a.b.c when that is a module. Only app.* is followed.
    """
    reached = set()
    for module, names in _imports_of(name, sources):
        if module.split(".")[0] != "app":
            continue
        parts = module.split(".")
        reached |= {".".join(parts[:end]) for end in range(1, len(parts) + 1)}
        reached |= {f"{module}.{one}" for one in names if f"{module}.{one}" in sources}
    return reached


def _closure(sources: dict[str, str], roots: Iterable[str]) -> set[str]:
    """
    Every first-party name the roots reach, statically: nothing is imported.
    A name without source, such as a namespace package, is reached but has
    nothing to follow.
    """
    reached: set[str] = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name not in reached:
            reached.add(name)
            if name in sources:
                pending += sorted(_edges(name, sources) - reached)
    return reached


def _read_modules(sources: dict[str, str]) -> list[str]:
    """The closure's modules that have source to read."""
    return sorted(_closure(sources, _roots(sources)) & sources.keys())


def _forbidden_first_party(sources: dict[str, str]) -> list[str]:
    """Check 1: the closure reaches no connector, app.core.security, API or ingestion module."""
    return sorted(name for name in _closure(sources, _roots(sources))
                  if _within(name, FORBIDDEN_FIRST_PARTY))


def _outbound_violations(sources: dict[str, str]) -> list[str]:
    """Check 2: no closure module imports an outbound client; `from X import Y` is X and X.Y."""
    found = []
    for name in _read_modules(sources):
        for module, names in _imports_of(name, sources):
            found += [f"{name}: {candidate}"
                      for candidate in (module, *(f"{module}.{one}" for one in names))
                      if _within(candidate, OUTBOUND_MODULES)]
    return found


def _third_party(sources: dict[str, str]) -> set[str]:
    """Each top-level package a closure module imports directly: not app, __future__ or stdlib."""
    return {root for name in _read_modules(sources)
            for root in (module.split(".")[0] for module, _ in _imports_of(name, sources))
            if root and root not in {"app", "__future__"} and root not in sys.stdlib_module_names}


def _unexempted(sources: dict[str, str]) -> list[str]:
    """Check 3: every third-party package the closure imports is a named exemption."""
    return sorted(_third_party(sources) - THIRD_PARTY_EXEMPTIONS)


def _stale_exemptions(sources: dict[str, str]) -> list[str]:
    """Check 4: every exemption is still imported by a closure module, as G2 requires of its own."""
    return sorted(THIRD_PARTY_EXEMPTIONS - _third_party(sources))


def _evidence_from_relationships(sources: dict[str, str]) -> list[str]:
    """Check 5, §A9's direction: the closure of app/relationships/ alone holds no app.evidence."""
    roots = [name for name in sources if _within(name, ("app.relationships",))]
    return sorted(name for name in _closure(sources, roots) if _within(name, ("app.evidence",)))


APP_SOURCES = _module_sources()


# ---------------------------------------------------------------------------
# Every scan fails on the thing it forbids
# ---------------------------------------------------------------------------


#: A small route module shaped as §0.7.8 requires. Every route scan passes it
#: (test_the_synthetic_route_and_event_pass_their_scans), so each route
#: companion below fails for the one thing it changes.
ROUTE = (
    "def _utc_now():\n"
    "    return datetime.now(UTC)\n"
    "\n"
    "\n"
    "def get_clock():\n"
    "    return _utc_now\n"
    "\n"
    "\n"
    "@router.post('/assessments')\n"
    "def run(body, sessions=Depends(get_sessions)):\n"
    "    try:\n"
    "        with sessions() as session, session.begin():\n"
    "            results = run_assessment(session, as_of=body.as_of)\n"
    "    except UnknownCustomerError:\n"
    "        raise ApiError(422, 'CUSTOMER_NOT_FOUND', 'unknown') from None\n"
    "    except ScopeResolutionError:\n"
    "        raise ApiError(422, 'SCOPE_UNRESOLVED', 'unresolved') from None\n"
    "    return results\n"
    "\n"
    "\n"
    "@router.get('/briefs/{brief_id}')\n"
    "def read(brief_id, sessions=Depends(get_sessions)):\n"
    "    with read_snapshot(sessions) as session:\n"
    "        brief = risk_queries.get_brief(session, brief_id)\n"
    "    return brief\n"
    "\n"
    "\n"
    "@router.post('/briefs/{brief_id}/decision')\n"
    "def decide(brief_id, body, sessions=Depends(get_sessions), clock=Depends(get_clock)):\n"
    "    decided_at = clock()\n"
    "    try:\n"
    "        with sessions() as session, session.begin():\n"
    "            record = record_decision(session, brief_id=brief_id, decided_at=decided_at)\n"
    "    except UnknownBriefError:\n"
    "        raise ApiError(404, 'BRIEF_NOT_FOUND', 'missing') from None\n"
    "    except PayloadHashConflictError:\n"
    "        raise ApiError(409, 'PAYLOAD_HASH_CONFLICT', 'hash') from None\n"
    "    except DecisionConflictError:\n"
    "        raise ApiError(409, 'DECISION_CONFLICT', 'history') from None\n"
    "    return record\n"
)
ROUTE_SCANS = (_route_import_violations, _route_clock_violations, _transaction_shape_violations,
               _route_handler_violations, _repository_log_violations, _model_violations)
#: §0.7.10's one event call, as approval.py writes it; _event_violations passes it.
EVENT_CALL = ("log_event(logger, logging.INFO, 'vs01.decision_recorded', "
              "payload_hash=payload_hash, decision=chosen.value, "
              "supersedes=supersedes_id is not None)\n")


def _route_with(old: str, new: str) -> str:
    """ROUTE with exactly one change."""
    assert ROUTE.count(old) == 1, old
    return ROUTE.replace(old, new)


def _event_with(old: str, new: str) -> str:
    assert EVENT_CALL.count(old) == 1, old
    return EVENT_CALL.replace(old, new)


REINTRODUCTIONS: list[tuple[str, Callable[[ast.Module], list[str]], str]] = [
    ("persistence imports M8's approval",
     _layer2_violations,
     "from app.decisions.approval import Decision\n"),
    ("persistence imports M1",
     _layer2_violations,
     "from app.intelligence.errors import IntelligenceError\n"),
    ("textual SQL is imported",
     _textual_sql_violations,
     "from sqlalchemy import text\n"),
    ("a .text attribute is read",
     _textual_sql_violations,
     "rows = connection.execute(statement).text\n"),
    ("a repository logs",
     _repository_log_violations,
     "import logging\n"),
    ("a repository emits an event",
     _repository_log_violations,
     "log_event(logger, 20, 'vs01.decision_recorded')\n"),
    ("a repository commits",
     _transaction_violations,
     "def f(session):\n    session.commit()\n"),
    ("a repository flushes",
     _transaction_violations,
     "def f(session):\n    session.flush()\n"),
    ("a repository builds a decision record",
     _domain_violations,
     "record = DecisionRecord(identifier, brief)\n"),
    ("a repository names the decision vocabulary",
     _domain_violations,
     "value = Decision.APPROVED\n"),
    ("a repository names a position",
     _domain_violations,
     "row = Position(function, stance)\n"),
    ("a repository updates a decision",
     _write_violations,
     "session.execute(update(BriefDecision).values(note=None))\n"),
    ("a repository deletes a decision",
     _write_violations,
     "session.execute(delete(BriefDecision))\n"),
    ("a repository deletes through the session",
     _write_violations,
     "def f(session, row):\n    session.delete(row)\n"),
    ("a repository upserts",
     _write_violations,
     "statement = insert(BriefDecision).on_conflict_do_update(set_={'note': None})\n"),
    ("a repository imports update",
     _write_violations,
     "from sqlalchemy import update\n"),
    ("a repository reads a decision",
     _read_violations,
     "rows = session.execute(select(BriefDecision.id))\n"),
    ("a repository reads through the session",
     _read_violations,
     "row = session.get(BriefDecision, identifier)\n"),
    ("the conflict target is named",
     _conflict_violations,
     "insert(BriefDecision).on_conflict_do_nothing(index_elements=['brief_id'])\n"),
    ("a conflict is not skipped",
     _conflict_violations,
     "insert(BriefDecision).values(id=1)\n"),
    ("the repository inserts twice",
     _conflict_violations,
     "insert(A).on_conflict_do_nothing()\ninsert(B)\n"),
    ("the repository grows an update function",
     _surface_violations,
     "class NewDecision: pass\ndef insert_decision(): pass\ndef update_decision(): pass\n"),
    ("the repository grows a reader",
     _surface_violations,
     "class NewDecision: pass\ndef insert_decision(): pass\nlatest = None\n"),
    ("another migration executes raw SQL",
     lambda tree: _raw_ddl_violations(tree, authorised=False),
     "op.execute('CREATE INDEX x ON y (z)')\n"),
    ("the M8 migration alters another table",
     lambda tree: _raw_ddl_violations(tree, authorised=True),
     "op.execute('ALTER TABLE risk_briefs DISABLE TRIGGER ALL')\n"),
    ("the M8 migration creates a second function",
     lambda tree: _raw_ddl_violations(tree, authorised=True),
     "SQL = 'CREATE FUNCTION other() RETURNS trigger AS $$ brief_decisions_append_only $$'\n"
     "op.execute(SQL)\n"),
    ("the M8 migration builds its SQL",
     lambda tree: _raw_ddl_violations(tree, authorised=True),
     "op.execute('DROP TRIGGER ' + name)\n"),
    ("a repository imports the API",
     _upward_violations,
     "from app.api.errors import ErrorCode\n"),
    ("a repository imports the route",
     _upward_violations,
     "from app.api.v1.risk import router\n"),
    ("a model imports approval",
     _upward_violations,
     "from app.decisions import approval\n"),
    # approval.py's row, a closed world
    ("approval imports the assessment run",
     _approval_import_violations,
     "from app.decisions.assessment import run_assessment\n"),
    ("approval imports the brief renderer",
     _approval_import_violations,
     "from app.decisions.brief import render_brief\n"),
    ("approval imports an M6 module",
     _approval_import_violations,
     "from app.decisions.reconciler import Reconciliation\n"),
    ("approval imports an ORM model",
     _approval_import_violations,
     "from app.persistence.models import BriefDecision\n"),
    ("approval imports the database",
     _approval_import_violations,
     "from app.core.database import get_sessionmaker\n"),
    ("approval imports the API",
     _approval_import_violations,
     "from app.api.errors import ErrorCode\n"),
    ("approval imports ingestion",
     _approval_import_violations,
     "from app.ingestion.orchestrator import run_ingestion\n"),
    ("approval imports a connector",
     _approval_import_violations,
     "from app.connectors import CsvConnector\n"),
    ("approval takes more of the payload than its hash",
     _approval_import_violations,
     "from app.decisions.payload import canonical_json\n"),
    ("approval imports the payload module whole",
     _approval_import_violations,
     "from app.decisions import payload\n"),
    ("approval imports a repository module whole",
     _approval_import_violations,
     "from app.persistence.repositories import brief_decisions\n"),
    ("approval reads a repository beyond its two reads",
     _approval_import_violations,
     "from app.persistence.repositories.risk_queries import list_assessments\n"),
    ("approval reads M1 beyond its errors",
     _approval_import_violations,
     "from app.intelligence.scope import resolve_scope\n"),
    ("approval imports a first-party package by name",
     _approval_import_violations,
     "import app.decisions.payload\n"),
    ("approval imports relatively",
     _approval_import_violations,
     "from .payload import payload_hash\n"),
    ("approval imports a clock module",
     _approval_import_violations,
     "import time\n"),
    ("approval imports randomness",
     _approval_import_violations,
     "import random\n"),
    ("approval takes datetime beyond the type",
     _approval_import_violations,
     "from datetime import UTC\n"),
    ("approval takes a uuid generator",
     _approval_import_violations,
     "from uuid import uuid4\n"),
    ("approval imports another standard-library module",
     _approval_import_violations,
     "import json\n"),
    ("approval takes SQLAlchemy beyond the Session type",
     _approval_import_violations,
     "from sqlalchemy import select\n"),
    ("approval reaches for an HTTP client",
     _approval_import_violations,
     "import httpx\n"),
    ("approval imports everything a module holds",
     _approval_import_violations,
     "from app.core.logging import *\n"),
    # approval.py's may-nots
    ("approval builds a UUID",
     lambda tree: _type_only_violations(tree, APPROVAL_TYPES),
     "supersedes_id = UUID(int=0)\n"),
    ("approval tests for a datetime",
     lambda tree: _type_only_violations(tree, APPROVAL_TYPES),
     "def f(x: datetime) -> bool:\n    return isinstance(x, datetime)\n"),
    ("approval opens a Session",
     lambda tree: _type_only_violations(tree, APPROVAL_TYPES),
     "def f(engine) -> Session:\n    return Session(engine)\n"),
    ("approval reads the wall clock",
     _clock_violations,
     "decided_at = datetime.now(UTC)\n"),
    ("approval reads a monotonic clock",
     _clock_violations,
     "started = time.monotonic()\n"),
    ("approval generates an id",
     _generator_violations,
     "identifier = uuid.uuid4()\n"),
    ("approval reaches a random source",
     _generator_violations,
     "from secrets import token_hex\n"),
    ("approval executes on its session",
     _session_violations,
     "def f(session):\n    return session.execute(statement)\n"),
    ("approval adds a row itself",
     _session_violations,
     "def f(session, row):\n    session.add(row)\n"),
    ("approval commits under another name",
     _session_violations,
     "def f(unit):\n    unit.commit()\n"),
    ("approval flushes",
     _session_violations,
     "def f(unit):\n    unit.flush()\n"),
    ("approval catches",
     _try_violations,
     "try:\n    insert()\nexcept KeyError:\n    pass\n"),
    ("approval retries in a finally",
     _try_violations,
     "try:\n    insert()\nfinally:\n    insert()\n"),
    # approval.py's one event (§0.7.10)
    ("a second event call site",
     _event_violations,
     EVENT_CALL + EVENT_CALL),
    ("another event is emitted",
     _event_violations,
     _event_with("vs01.decision_recorded", "vs01.decision_refused")),
    ("the event is logged at WARNING",
     _event_violations,
     _event_with("logging.INFO", "logging.WARNING")),
    ("the event's fields are out of order",
     _event_violations,
     _event_with("payload_hash=payload_hash, decision=chosen.value",
                 "decision=chosen.value, payload_hash=payload_hash")),
    ("the event's fields pass through **",
     _event_violations,
     "log_event(logger, logging.INFO, 'vs01.decision_recorded', **fields)\n"),
    ("the event logs the actor",
     _event_violations,
     _event_with("supersedes_id is not None)", "supersedes_id is not None, actor=actor)")),
    ("the event logs the note as its hash",
     _event_violations,
     _event_with("payload_hash=payload_hash", "payload_hash=note")),
    ("the event logs an id as supersedes",
     _event_violations,
     _event_with("supersedes=supersedes_id is not None", "supersedes=supersedes_id")),
    ("approval logs around log_event",
     _logging_violations,
     "logger = logging.getLogger(__name__)\nlogger.info('recorded')\n"),
    ("approval logs through the logging module",
     _logging_violations,
     "logger = logging.getLogger(__name__)\nlogging.warning('recorded')\n"),
    ("approval names another logger",
     _logging_violations,
     "logger = logging.getLogger('vs01')\n"),
    ("approval prints",
     _logging_violations,
     "logger = logging.getLogger(__name__)\nprint(actor)\n"),
    # risk.py's row, a closed world
    ("the route imports an ORM model",
     _route_import_violations,
     "from app.persistence.models import RiskBrief\n"),
    ("the route imports the database",
     _route_import_violations,
     "from app.core.database import Base\n"),
    ("the route reaches an M2 internal",
     _route_import_violations,
     "from app.relationships.queries import neighbourhood\n"),
    ("the route imports logging",
     _route_import_violations,
     "import logging\n"),
    ("the route imports a clock module",
     _route_import_violations,
     "import time\n"),
    ("the route imports an HTTP client",
     _route_import_violations,
     "import httpx\n"),
    ("the route takes http's client module by name",
     _route_import_violations,
     "from http import client\n"),
    ("the route imports http's client module",
     _route_import_violations,
     "import http.client\n"),
    ("the route takes a fastapi submodule",
     _route_import_violations,
     "from fastapi import testclient\n"),
    ("the route imports the brief renderer",
     _route_import_violations,
     "from app.decisions.brief import render_brief\n"),
    ("the route takes more of the run than its entry point",
     _route_import_violations,
     "from app.decisions.assessment import AssessmentResult\n"),
    ("the route takes the payload hash",
     _route_import_violations,
     "from app.decisions.payload import payload_hash\n"),
    ("the route takes M1 beyond its two names",
     _route_import_violations,
     "from app.intelligence import MoneyValue\n"),
    ("the route reads an M1 submodule",
     _route_import_violations,
     "from app.intelligence.bands import RiskBand\n"),
    ("the route takes a Layer 1 schema",
     _route_import_violations,
     "from app.api.v1.schemas import EntityType\n"),
    ("the route builds SQLAlchemy expressions",
     _route_import_violations,
     "from sqlalchemy import select\n"),
    ("the route imports another repository",
     _route_import_violations,
     "from app.persistence.repositories import run_queries\n"),
    ("the route writes through M7's repository",
     _route_import_violations,
     "from app.persistence.repositories.risk_assessments import insert_brief\n"),
    ("the route takes more of the API's dependencies",
     _route_import_violations,
     "from app.api.dependencies import get_connectors\n"),
    ("the route imports randomness",
     _route_import_violations,
     "import secrets\n"),
    ("the route imports a first-party package by name",
     _route_import_violations,
     "import app.decisions.approval\n"),
    ("the route imports relatively",
     _route_import_violations,
     "from .schemas import BriefResponse\n"),
    # risk.py's one clock (§0.7.8)
    ("the route reads a second clock",
     _route_clock_violations,
     _route_with("        brief = risk_queries.get_brief(session, brief_id)\n",
                 "        brief = risk_queries.get_brief(session, brief_id)\n"
                 "        stamp = datetime.now(UTC)\n")),
    ("the decision route bypasses the injected clock",
     _route_clock_violations,
     _route_with("    decided_at = clock()\n", "    decided_at = _utc_now()\n")),
    ("the clock is read inside the transaction",
     _route_clock_violations,
     _route_with("    decided_at = clock()\n    try:\n"
                 "        with sessions() as session, session.begin():\n",
                 "    try:\n        with sessions() as session, session.begin():\n"
                 "            decided_at = clock()\n")),
    ("the clock is read twice",
     _route_clock_violations,
     _route_with("    decided_at = clock()\n",
                 "    decided_at = clock()\n    decided_at = clock()\n")),
    ("the one clock reads local time",
     _route_clock_violations,
     _route_with("    return datetime.now(UTC)\n", "    return datetime.now()\n")),
    ("get_clock returns a clock of its own",
     _route_clock_violations,
     _route_with("    return _utc_now\n", "    return datetime.utcnow\n")),
    # risk.py's transactions (§0.7.8)
    ("a POST commits itself",
     _transaction_shape_violations,
     _route_with("            results = run_assessment(session, as_of=body.as_of)\n",
                 "            results = run_assessment(session, as_of=body.as_of)\n"
                 "            session.commit()\n")),
    ("a POST rolls back before it maps a failure",
     _transaction_shape_violations,
     _route_with("    except UnknownCustomerError:\n",
                 "    except UnknownCustomerError:\n        session.rollback()\n")),
    ("a POST maps a failure inside its transaction",
     _transaction_shape_violations,
     _route_with("    try:\n        with sessions() as session, session.begin():\n"
                 "            results = run_assessment(session, as_of=body.as_of)\n"
                 "    except UnknownCustomerError:\n"
                 "        raise ApiError(422, 'CUSTOMER_NOT_FOUND', 'unknown') from None\n"
                 "    except ScopeResolutionError:\n"
                 "        raise ApiError(422, 'SCOPE_UNRESOLVED', 'unresolved') from None\n",
                 "    with sessions() as session, session.begin():\n        try:\n"
                 "            results = run_assessment(session, as_of=body.as_of)\n"
                 "        except UnknownCustomerError:\n"
                 "            raise ApiError(422, 'CUSTOMER_NOT_FOUND', 'unknown') from None\n"
                 "        except ScopeResolutionError:\n"
                 "            raise ApiError(422, 'SCOPE_UNRESOLVED', 'unresolved') from None\n")),
    ("a POST keeps the failure as the cause",
     _transaction_shape_violations,
     _route_with("'unknown') from None\n", "'unknown')\n")),
    ("a POST swallows a failure",
     _transaction_shape_violations,
     _route_with("        raise ApiError(404, 'BRIEF_NOT_FOUND', 'missing') from None\n",
                 "        record = None\n")),
    ("a POST opens a second session",
     _transaction_shape_violations,
     _route_with("    decided_at = clock()\n",
                 "    decided_at = clock()\n    with sessions() as probe, probe.begin():\n"
                 "        risk_queries.get_brief(probe, brief_id)\n")),
    ("a GET reads outside the snapshot",
     _transaction_shape_violations,
     _route_with("    with read_snapshot(sessions) as session:\n",
                 "    with sessions() as session:\n")),
    ("a GET opens a write transaction",
     _transaction_shape_violations,
     _route_with("    with read_snapshot(sessions) as session:\n",
                 "    with sessions() as session, session.begin():\n")),
    ("a decision is recorded outside the transaction",
     _transaction_shape_violations,
     _route_with("    decided_at = clock()\n",
                 "    decided_at = clock()\n    record_decision(None, decided_at=decided_at)\n")),
    # risk.py's handlers (§0.7.9; the owner's Q4 ruling)
    ("the route maps an unexpected failure to 409",
     _route_handler_violations,
     _route_with("    except DecisionConflictError:\n",
                 "    except (DecisionConflictError, RuntimeError):\n")),
    ("the route maps M1's base error to 422",
     _route_handler_violations,
     _route_with("    except ScopeResolutionError:\n", "    except IntelligenceError:\n")),
    ("the route catches everything",
     _route_handler_violations,
     _route_with("    except UnknownCustomerError:\n", "    except Exception:\n")),
    ("the route has a bare except",
     _route_handler_violations,
     _route_with("    except DecisionConflictError:\n", "    except:\n")),
    ("the route stops mapping one of its five exceptions",
     _route_handler_violations,
     _route_with("    except DecisionConflictError:\n"
                 "        raise ApiError(409, 'DECISION_CONFLICT', 'history') from None\n", "")),
    # risk.py never logs and names no model
    ("the route prints",
     _repository_log_violations,
     "print(body)\n"),
    ("the route names an ORM model",
     _model_violations,
     "brief = RiskBrief(id=1)\n"),
    ("the route names the database",
     _model_violations,
     "from app.core.database import get_sessionmaker\n"),
    ("the route imports a model module",
     _model_violations,
     "from app.persistence.models.risk_brief import RiskBrief\n"),
]


def _mapping(**modules: str) -> dict[str, str]:
    """A synthetic tree: each keyword a dotted name with its double underscores as dots."""
    return {name.replace("__", "."): source for name, source in modules.items()}


#: §0.7.11's seven companions, then three proving rule 2's edges, each run
#: through the check functions the real tree runs through.
NO_EXECUTOR_COMPANIONS: list[tuple[str, Callable[[dict[str, str]], list[str]], dict[str, str]]] = [
    ("a leaf imports httpx",
     _outbound_violations,
     _mapping(app__intelligence="", app__intelligence__leaf="import httpx\n")),
    ("a leaf takes urllib's request module",
     _outbound_violations,
     _mapping(app__evidence="", app__evidence__leaf="from urllib import request\n")),
    ("a leaf takes http's client module",
     _outbound_violations,
     _mapping(app__analysts="", app__analysts__leaf="from http import client\n")),
    ("a leaf reaches the connector registry through a first-party helper",
     _forbidden_first_party,
     _mapping(app__decisions="", app__decisions__leaf="from app.core.helper import go\n",
              app__core="",
              app__core__helper="from app.connectors.registry import build_connector\n")),
    ("an unexempted third-party package",
     _unexempted,
     _mapping(app__analysts="", app__analysts__leaf="import boto3\n")),
    ("an exemption no closure module imports",
     _stale_exemptions,
     _mapping(app__decisions="", app__decisions__leaf="from sqlalchemy.orm import Session\n",
              app__core="", app__core__config="import pydantic\nimport pydantic_settings\n")),
    ("app.relationships reaches app.evidence through one hop",
     _evidence_from_relationships,
     _mapping(app__relationships="", app__relationships__graph="from app.core.bridge import go\n",
              app__core="", app__core__bridge="from app.evidence import documents_for\n")),
    ("`import a.b.c` reaches the initialiser a.b",
     _outbound_violations,
     _mapping(app__evidence="", app__evidence__leaf="import app.core.bridge.inner\n",
              app__core="", app__core__bridge="import socket\n", app__core__bridge__inner="")),
    ("`from a.b import c` reaches the module a.b.c",
     _outbound_violations,
     _mapping(app__decisions="", app__decisions__leaf="from app.core import helper\n",
              app__core="", app__core__helper="import ssl\n")),
    ("a relative import is resolved against its package",
     _outbound_violations,
     _mapping(app__evidence="", app__evidence__leaf="from ..core.helper import go\n",
              app__core="", app__core__helper="import smtplib\n")),
]


@pytest.mark.parametrize(("label", "scan", "source"), REINTRODUCTIONS,
                         ids=[label for label, _, _ in REINTRODUCTIONS])
def test_every_scan_catches_its_reintroduction(label, scan, source):
    assert scan(ast.parse(source)), label


def test_the_code_scan_reads_code_and_not_the_docstrings_explaining_it():
    assert _domain_violations(ast.parse('"""Builds no DecisionRecord."""\nx = 1\n')) == []
    assert _domain_violations(ast.parse("BriefDecision = NewDecision\n")) == []
    assert _write_violations(ast.parse('"""Has no update, no delete."""\nx = 1\n')) == []


# ---------------------------------------------------------------------------
# Where M8's persistence exists
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", M8_PERSISTENCE, ids=lambda path: path.name)
def test_every_m8_persistence_file_exists_and_is_scanned(path):
    """A scan that silently matches nothing proves nothing."""
    assert path.is_file()
    assert _code(_tree(path)).strip()


# ---------------------------------------------------------------------------
# Persistence (§0.7.4, §0.7.5, §0.7.6)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", M8_PERSISTENCE, ids=lambda path: path.name)
def test_m8_persistence_imports_no_layer_2_package(path):
    """D-M4-B2, mirrored as in M7: no repository, model or migration reaches Layer 2."""
    assert _layer2_violations(_tree(path)) == []


@pytest.mark.parametrize("path", [M8_MODEL, M8_REPOSITORY, M8_QUERIES], ids=lambda path: path.name)
def test_no_m8_persistence_module_uses_textual_sql(path):
    assert _textual_sql_violations(_tree(path)) == []


def test_the_repository_never_names_a_domain_type():
    """M4's, M7's and M8's vocabularies: the repository takes and returns plain data."""
    assert _domain_violations(_tree(M8_REPOSITORY)) == []


def test_the_repository_owns_no_transaction_and_does_not_log():
    tree = _tree(M8_REPOSITORY)

    assert _transaction_violations(tree) == []
    assert _repository_log_violations(tree) == []


def test_the_repository_inserts_and_never_updates_deletes_or_upserts():
    """OPEN-M8-4: append-only in the repository, as the trigger makes it in the database."""
    tree = _tree(M8_REPOSITORY)

    assert _write_violations(tree) == []
    assert "insert" in _called_names(tree)


def test_the_repository_reads_nothing():
    """§0.7.6: every M8 read is risk_queries.py's; RETURNING the new id is not a read."""
    assert _read_violations(_tree(M8_REPOSITORY)) == []


def test_the_one_insert_skips_every_conflict_and_names_no_target():
    """§0.7.6: no conflict target, so both partial unique indexes are covered."""
    assert _conflict_violations(_tree(M8_REPOSITORY)) == []


def test_the_repository_exposes_the_row_type_and_the_insert_only():
    tree = _tree(M8_REPOSITORY)

    assert _surface_violations(tree) == []
    assert ("app.persistence.models", "BriefDecision") in {
        (imported, name) for imported, name, _ in _imports(tree)}


def test_the_m8_migration_executes_only_its_function_and_trigger_ddl():
    """OPEN-M8-4: the create and drop of each, four statements, and nothing else raw."""
    tree = _tree(M8_MIGRATION)
    calls = [call for call in ast.walk(tree)
             if isinstance(call, ast.Call) and _dotted(call.func) == "op.execute"]

    assert len(calls) == 4
    assert _raw_ddl_violations(tree, authorised=True) == []


def test_no_other_migration_executes_raw_sql():
    """The trigger's raw DDL is authorised once and is not generalised (OPEN-M8-4)."""
    others = [path for path in sorted(MIGRATIONS_DIR.glob("*.py")) if path != M8_MIGRATION]

    assert others
    for path in others:
        assert _raw_ddl_violations(_tree(path), authorised=False) == [], path.name


def test_the_m8_model_carries_no_provenance_mixin():
    """§0.7.5: a decision is not an ingested record."""
    from app.persistence.models import BriefDecision, Customer
    from app.persistence.models.mixins import ProvenanceMixin

    assert BriefDecision.__table__.name == "brief_decisions"
    assert not issubclass(BriefDecision, ProvenanceMixin)
    assert "source_system" not in BriefDecision.__table__.columns
    assert issubclass(Customer, ProvenanceMixin), "the check must be able to fail"


def test_the_query_repository_never_names_a_domain_type():
    """§0.7.4 and §0.7.6: risk_queries.py returns plain rows; giving them meaning is the caller's."""
    assert _domain_violations(_tree(M8_QUERIES)) == []


def test_the_query_repository_owns_no_transaction_and_does_not_log():
    tree = _tree(M8_QUERIES)

    assert _transaction_violations(tree) == []
    assert _repository_log_violations(tree) == []


def test_the_query_repository_contains_no_update_or_delete_construct():
    """§0.7.13: M8's repositories never change a row; risk_queries.py only reads."""
    tree = _tree(M8_QUERIES)

    assert _write_violations(tree) == []
    assert "select" in _called_names(tree)


def test_no_repository_or_model_imports_the_route_approval_or_the_api():
    """§0.7.4's direction, over every persistence module, Layer 1's and M8's alike."""
    paths = sorted(PERSISTENCE_DIR.rglob("*.py"))

    assert {M8_MODEL, M8_REPOSITORY, M8_QUERIES} <= set(paths)
    for path in paths:
        assert _upward_violations(_tree(path)) == [], path.name


def test_the_schemas_import_no_layer_2_package():
    """§0.7.4: the mirrored enums keep schemas.py outside every importer whitelist."""
    tree = _tree(SCHEMAS)

    assert _layer2_violations(tree) == []
    assert {"RiskDecision", "RiskDecisionStatus"} <= {
        node.name for node in tree.body if isinstance(node, ast.ClassDef)}


# ---------------------------------------------------------------------------
# Where M8's modules exist (§0.7.4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [APPROVAL, RISK_ROUTE], ids=lambda path: path.name)
def test_every_m8_module_exists_and_is_scanned(path):
    """With M8_PERSISTENCE, §0.7.4's six new sources: a scan that matches nothing proves nothing."""
    assert path.is_file()
    assert _code(_tree(path)).strip()


def test_the_decision_layer_holds_approval_beside_m6_and_m7s_seven_modules():
    """§0.7.4, asserted from M8's side: approval.py is the one module M8 adds to app/decisions/."""
    modules = {path.relative_to(DECISIONS_DIR).as_posix() for path in DECISIONS_DIR.rglob("*.py")}

    assert modules == EARLIER_DECISION_MODULES | {"approval.py"}


# ---------------------------------------------------------------------------
# approval.py (§0.7.4, §0.7.7, §0.7.10)
# ---------------------------------------------------------------------------


def test_approval_imports_exactly_its_row():
    """§0.7.4's row as a closed world: its repositories, M7's hash, M1's errors, log_event."""
    tree = _tree(APPROVAL)

    assert _approval_import_violations(tree) == []
    assert ("app.decisions.payload", "payload_hash") in {
        (imported, name) for imported, name, _ in _imports(tree)}


def test_approval_names_datetime_uuid_and_session_as_types_only():
    tree = _tree(APPROVAL)

    assert _type_only_violations(tree, APPROVAL_TYPES) == []
    assert APPROVAL_TYPES <= {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def test_approval_reads_no_clock():
    """X7: decided_at is the caller's argument, so the clock scan finds nothing in approval.py."""
    assert _clock_violations(_tree(APPROVAL)) == []


def test_approval_generates_no_id_and_reaches_no_random_source():
    """The decision's id is the repository's uuid4 (§0.7.5)."""
    assert _generator_violations(_tree(APPROVAL)) == []


def test_approval_writes_only_through_its_repositories():
    """§0.7.4: no session method; the caller owns the session and the transaction (§0.7.7)."""
    tree = _tree(APPROVAL)

    assert _session_violations(tree) == []
    assert {"insert_decision", "get_brief", "decisions_for"} <= _called_names(tree)


def test_approval_holds_no_try():
    assert _try_violations(_tree(APPROVAL)) == []


def test_approval_emits_its_one_event_with_its_three_fields_in_order():
    assert _event_violations(_tree(APPROVAL)) == []


def test_approval_logs_through_log_event_only():
    assert _logging_violations(_tree(APPROVAL)) == []


# ---------------------------------------------------------------------------
# Who may import approval (§0.7.4, OPEN-M8-17)
# ---------------------------------------------------------------------------


def test_only_the_risk_route_imports_approval():
    """No M1-M7 module, repository, model, script or migration imports it: only risk.py."""
    paths = [path for directory in ("app", "scripts", "migrations", "docker")
             for path in sorted((REPO / directory).rglob("*.py"))]

    assert paths
    assert {entry.split(":", 1)[0] for entry in _approval_importers(paths)} == {
        "app/api/v1/risk.py"}


@pytest.mark.parametrize("source", [
    "from app.decisions.approval import record_decision\n",
    "from app.decisions import approval\n",
    "import app.decisions.approval\n",
])
def test_the_approval_importer_scan_would_catch_an_outside_import(tmp_path, source):
    importer = tmp_path / "importer.py"
    importer.write_text(source, encoding="utf-8")

    assert _approval_importers([importer]), source


def test_the_initialiser_re_exports_nothing_of_approval():
    """§0.7.4: app/decisions/__init__.py is unchanged, so approval is imported by its path."""
    decisions = importlib.import_module("app.decisions")
    tree = _tree(APPROVAL)
    public = {node.name for node in tree.body
              if isinstance(node, ast.FunctionDef | ast.ClassDef) and not node.name.startswith("_")}
    public |= {target.id for node in tree.body if isinstance(node, ast.Assign)
               for target in node.targets
               if isinstance(target, ast.Name) and not target.id.startswith("_")}

    assert {"record_decision", "decision_history", "decision_status", "DecisionRecord",
            "Decision", "ApprovalError"} <= public
    assert public.isdisjoint(decisions.__all__)
    assert [name for name in sorted(public) if hasattr(decisions, name)] == []


def test_importing_the_package_does_not_load_approval():
    """In a fresh interpreter, so no earlier import in this process can hide a re-export."""
    completed = subprocess.run(
        [sys.executable, "-c", "import sys, app.decisions; print(' '.join(sorted("
         "name for name in sys.modules if name.startswith('app.decisions.'))))"],
        cwd=REPO, capture_output=True, text=True, check=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    loaded = completed.stdout.split()

    assert "app.decisions.reconciler" in loaded, "the probe must see the package's own modules"
    assert "app.decisions.approval" not in loaded


# ---------------------------------------------------------------------------
# The route (§0.7.4, §0.7.8, §0.7.9)
# ---------------------------------------------------------------------------


def test_the_route_imports_exactly_its_row():
    """§0.7.4's row as a closed world, with T-M8-10's app.intelligence import read by name."""
    tree = _tree(RISK_ROUTE)

    assert _route_import_violations(tree) == []
    assert ("app.intelligence", "ScopeResolutionError") in {
        (imported, name) for imported, name, _ in _imports(tree)}


def test_the_route_module_holds_the_six_routes_the_scans_read():
    """The route scans find their routes by decorator; this keeps them from matching nothing."""
    assert sorted(verb for verb, _ in _routes(_tree(RISK_ROUTE))) == ["get"] * 4 + ["post"] * 2


def test_the_route_reads_the_clock_once_at_its_one_site():
    """§0.7.8: the only clock read M8 adds, overridable through get_clock."""
    assert _route_clock_violations(_tree(RISK_ROUTE)) == []


def test_each_post_owns_one_transaction_and_each_get_reads_one_snapshot():
    """OPEN-M8-16: the route owns its transactions and never commits or rolls back itself."""
    assert _transaction_shape_violations(_tree(RISK_ROUTE)) == []


def test_the_route_handles_exactly_the_five_mapped_exceptions():
    """§0.7.9, additive to F1's rule: anything else reaches the existing 500 handler."""
    assert _route_handler_violations(_tree(RISK_ROUTE)) == []


def test_the_route_never_logs():
    """§0.7.4 and §0.7.10: the routes emit nothing of their own."""
    assert _repository_log_violations(_tree(RISK_ROUTE)) == []


def test_the_route_never_names_an_orm_model_or_the_database():
    assert _model_violations(_tree(RISK_ROUTE)) == []
    assert {"RiskBrief", "BriefDecision"} <= ORM_MODELS, "the scan must know the models"


def test_the_synthetic_route_and_event_pass_their_scans():
    """So each companion built from ROUTE or EVENT_CALL fails for the one thing it changes."""
    for scan in ROUTE_SCANS:
        assert scan(ast.parse(ROUTE)) == [], scan.__name__
    assert _event_violations(ast.parse(EVENT_CALL)) == []


# ---------------------------------------------------------------------------
# The no-executor boundary (§0.7.11; X5; §A22)
# ---------------------------------------------------------------------------


def test_the_closure_is_static_and_reaches_past_the_five_packages():
    """Read from source, never imported (OPEN-M8-2); risk.py is outside it by design."""
    closure = _closure(APP_SOURCES, _roots(APP_SOURCES))

    assert set(_roots(APP_SOURCES)) <= closure
    assert {"app.decisions.approval", "app.persistence.repositories.risk_queries",
            "app.persistence.models", "app.core.database"} <= closure
    assert "app.api.v1.risk" in APP_SOURCES and "app.api.v1.risk" not in closure


def test_check_1_the_closure_reaches_no_connector_security_api_or_ingestion_module():
    assert _forbidden_first_party(APP_SOURCES) == []


def test_check_2_no_closure_module_imports_an_outbound_client():
    assert _outbound_violations(APP_SOURCES) == []


def test_check_3_every_third_party_package_the_closure_imports_is_a_named_exemption():
    assert _unexempted(APP_SOURCES) == []


def test_check_4_no_exemption_is_stale():
    """G2's rule for its own exemptions: an exemption no longer needed must be removed."""
    assert _stale_exemptions(APP_SOURCES) == []


def test_check_5_app_relationships_never_reaches_app_evidence():
    """§A9's direction, pinned by the same closure."""
    assert _evidence_from_relationships(APP_SOURCES) == []


@pytest.mark.parametrize(("label", "check", "sources"), NO_EXECUTOR_COMPANIONS,
                         ids=[label for label, _, _ in NO_EXECUTOR_COMPANIONS])
def test_every_no_executor_check_catches_its_companion(label, check, sources):
    assert check(sources), label
