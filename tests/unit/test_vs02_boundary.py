"""
VS-02 static boundaries (plan A21, A22.4), as far as VS02-M2 has built.

This file grows with each milestone, as its modules arrive. M1 added app/fx/
and its rows. M2 adds app/pipeline/ and pipeline_queries.py, whose rows are
in the second half of this file, and extends three things M1 wrote (OD-5):
app/pipeline/ may import app.fx, the import closure is taken from both
packages, and the check that every rule has a negative control covers the
pipeline's rules as well. No M1 rule over app/fx/ is weakened or removed.

The rows that concern app/fx/:

    Where it exists    plan B1's four modules, A22.1's three and the package
                       itself, and no fifth.
    Imports            A22.4's row for app/fx/*: its own siblings,
                       app.intelligence and app.normalization.config, and no
                       other first-party module. Never VS-01's signal engine,
                       band table or windows (SD-3), and never app.pipeline.
                       No import is aliased or starred, so every rule below
                       sees a name as it is written.
                       Third-party: the packages A22.4 exempts, less
                       SQLAlchemy (A19 item 5); no new dependency (MD-21).
                       The standard library is closed too, to what the
                       package imports today.
    Isolation          no Layer 1 or VS-01 module, script or migration imports
                       app.fx, so nothing that existed before VS-02 can come
                       to depend on a rate. app/main.py is among them.
    No executor        over the static first-party closure of app/fx/: no
                       connector, ingestion, app.core.security or API module,
                       and no outbound HTTP, SMTP or socket module.
    Read-only          no session write method, no Session and no SQLAlchemy
                       name (A19 item 5).
    Determinism        M1's clock and randomness rules, no environment read,
                       and no float: neither float() nor a float literal (A9.1).
                       The process default Decimal context is neither read
                       nor altered, and every context states its limits. No
                       global statement and no mutable module-level state.
    No document text   no Document or SupportTicket model, no repository, and
                       none of app.evidence, app.analysts or app.decisions.
    Loading            yaml.safe_load is the only YAML entry point, and
                       nothing is read while a module is imported (A7.3). The
                       one file is read and nothing is written, listed or
                       statted (A7.6). Only the loader builds a rate set.
    The digest         canonical_json and decimal_text are VS-01's, imported
                       and not copied (A7.4).
    Money              MoneyValue is not altered, no module catches
                       CurrencyMismatchError by name or by a wider handler
                       (A7.5), and no currency code is written into the code:
                       the base currency and every rate are data (SD-1).
    Output             the package neither prints nor logs (A20).

The no-document, no-clock and no-SQLAlchemy rows are rules over what
app/fx/*.py itself imports and names, never over its closure: the frozen
app.intelligence package loads its scope module, and with it SQLAlchemy and
every canonical model, whenever any of its modules is imported.

Each rule is a function returning its violations. The real files must return
none, and each rule is also run over a copy of the real source carrying one
forbidden edit, so no rule can pass vacuously (M8's pattern, with the real
source in place of a synthetic one). The closure rules run over a
`{module name: source text}` mapping: the real tree's, or an edited copy.

The rows that concern app/pipeline/ and pipeline_queries.py (M2):

    Where it exists    the package's six modules of M2 and no seventh;
                       view.py and service.py are M3's (plan B6).
    Imports            A22.4's row for app/pipeline/*, exhaustive: its own
                       siblings, app.fx, app.relationships, app.intelligence
                       less the signal engine, the band table and the
                       windows, and app.normalization.config. facts.py alone
                       reads through the repository module; no M2 module
                       logs. The standard library is closed here too.
    What is read       A21.1: from app.relationships only edges_of_type,
                       EdgeType, Edge and EdgeBasis are named, edges_of_type
                       is called with DEAL_OWNED_BY and CUSTOMER_HAS_DEAL
                       written out, and EdgeType is never called, indexed or
                       iterated. No ORM model and no model registry is named.
                       pipeline_queries.py names the model Deal alone, and of
                       it only the nine columns and its two filters.
    Read-only          A21.2, in every form: no session write method, no DML
                       or DDL construct, no textual SQL, no row lock, no
                       engine or session of VS-02's own. Only
                       pipeline_queries.py executes a statement, and only a
                       select ordered in the C collation. facts.py is handed
                       the caller's session and only passes it on; no other
                       module of the package accepts one (A19 item 5).
    Errors             no module catches the frozen MoneyValue's refusal, a
                       missing rate or its own data error: none is translated
                       and no deal is skipped (A10.1 item 4, A10.5).
    Money              sums go through app.pipeline.measures alone, and no
                       other module converts, rounds or totals (A9). No
                       currency code is written into the code but the
                       reserved bucket key ALL, in the reserved keys (OD-8).
    No band            measures.py receives no band and names no band type
                       (A12.4 item 4).
    Isolation          no module outside app/pipeline/ imports it, and
                       nothing under app/persistence/ imports either package.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

import pytest

from app.normalization.config import default_config

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
APP_DIR = REPO / "app"
FX_DIR = APP_DIR / "fx"

RATES, CONVERT, ERRORS, PACKAGE = (
    "app/fx/rates.py", "app/fx/convert.py", "app/fx/errors.py", "app/fx/__init__.py")
#: Plan B1: the package's modules, A22.1's three and its __init__.
FX_MODULES = (PACKAGE, CONVERT, ERRORS, RATES)
#: Plan A22.4's row for app/fx/*, exhaustive for first-party imports. Each
#: entry admits the module and everything beneath it.
FX_ALLOWED_FIRST_PARTY = ("app.fx", "app.intelligence", "app.normalization.config")
#: SD-3 and A22.4: VS-02 never computes a signal or a band, so it imports none
#: of the three modules that do.
FX_EXCLUDED_FIRST_PARTY = ("app.intelligence.signals", "app.intelligence.bands",
                           "app.intelligence.windows")
#: A22.4 puts the packages VS-01's boundary tests exempt outside its lists:
#: sqlalchemy, pydantic and yaml. A19 item 5 then takes SQLAlchemy away from
#: app/fx/, and MD-21 forbids any new dependency.
FX_ALLOWED_THIRD_PARTY = {"yaml", "pydantic"}
#: The standard-library modules the package imports today. A22.4 leaves the
#: standard library outside its lists; this closes it for app/fx/, as M8's
#: closed worlds do for approval.py, so that a thread, a socket, a database
#: file, a subprocess or a dynamic import arrives as a deliberate edit here.
FX_ALLOWED_STDLIB = {"__future__", "collections", "dataclasses", "datetime", "decimal",
                     "functools", "hashlib", "pathlib", "re", "types"}
#: The directories whose code could import the package (M1's importer scan).
CODE_DIRS = ("app", "scripts", "migrations", "docker")
#: Who may import app.fx. Extended when a milestone legitimately becomes a
#: consumer, never relaxed to a substring. M2: app/pipeline/ (plan A22.4, OD-5).
FX_IMPORTERS = ("app/fx/", "app/pipeline/")

#: M1's clock and randomness rules (tests/unit/test_m1_boundary.py), verbatim.
FORBIDDEN_CLOCKS = {"now", "today", "utcnow", "utcfromtimestamp", "fromtimestamp", "time",
                    "monotonic", "perf_counter"}
FORBIDDEN_CLOCK_MODULES = {"time"}
FORBIDDEN_RANDOM_MODULES = {"random", "secrets", "uuid"}
#: M1's session-write rule, verbatim.
FORBIDDEN_WRITES = {"commit", "rollback", "add", "add_all", "flush", "delete", "merge",
                    "begin", "begin_nested", "close", "bulk_save_objects"}
#: Plan A21's no-executor row; M8's two lists (tests/unit/test_m8_boundary.py), verbatim.
FORBIDDEN_FIRST_PARTY = ("app.connectors", "app.core.security", "app.api", "app.ingestion")
OUTBOUND_MODULES = ("httpx", "requests", "aiohttp", "urllib3", "urllib.request", "http.client",
                    "smtplib", "socket", "ssl", "ftplib", "xmlrpc")
#: Plan A21's no-document row.
FORBIDDEN_TEXT_PACKAGES = ("app.evidence", "app.analysts", "app.decisions", "app.persistence")
FORBIDDEN_TEXT_NAMES = {"Document", "SupportTicket"}
#: Handlers that would catch CurrencyMismatchError, by name or by a base class.
WIDE_HANDLERS = {"CurrencyMismatchError", "IntelligenceError", "Exception", "BaseException"}
#: What touches the filesystem other than the one read of the one file, or
#: asks when a file changed.
FILESYSTEM = {"write_text", "write_bytes", "read_bytes", "mkdir", "touch", "unlink", "rmdir",
              "rename", "iterdir", "glob", "rglob", "stat", "lstat", "getmtime", "st_mtime"}
#: The process's Decimal contexts, which are neither read nor altered.
PROCESS_CONTEXTS = {"getcontext", "setcontext", "DefaultContext", "BasicContext",
                    "ExtendedContext"}
#: What builds a mutable container.
MUTABLE_BUILDERS = {"dict", "list", "set", "bytearray", "defaultdict", "OrderedDict", "Counter",
                    "deque"}
#: What would read the rate file, or anything else, if it ran while a module is imported.
#: M2 adds the rules loader and the three reads of the facts reader.
READS = {"open", "read_text", "read_bytes", "safe_load", "load_rate_set", "default_rate_set",
         "load_pipeline_rules", "default_pipeline_rules", "read_deal_facts", "deal_rows",
         "edges_of_type"}

Rule = Callable[[ast.Module], list[str]]


# ---------------------------------------------------------------------------
# Reading code
# ---------------------------------------------------------------------------


def _source(relative: str) -> str:
    return (REPO / relative).read_text(encoding="utf-8")


def _within(name: str, packages: Iterable[str]) -> bool:
    return any(name == package or name.startswith(package + ".") for package in packages)


def _imports(tree: ast.AST) -> list[tuple[str, str | None, int]]:
    """Every import as (module, name, line): `import x` is (x, None), a relative one is dotted."""
    found: list[tuple[str, str | None, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(alias.name, None, node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            found += [(module, alias.name, node.lineno) for alias in node.names]
    return found


def _imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    """
    Every module an import can reach: `from a import b` is a and a.b, because
    b may be a submodule, so a forbidden module cannot be taken by name from
    its parent.
    """
    found = []
    for module, name, line in _imports(tree):
        found.append((module, line))
        if name is not None:
            found.append((f"{module}.{name}", line))
    return found


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def _callee(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _docstrings(tree: ast.AST) -> set[int]:
    """The ids of the docstring nodes: prose about the rules is not a breach of them."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                found.add(id(body[0].value))
    return found


def _at_import(node: ast.AST) -> Iterator[ast.AST]:
    """
    Every node that runs while the module is imported: the module's and each
    class's body, and a function's decorators and defaults, but no function's
    body and no lambda's.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            for early in (*child.decorator_list, *child.args.defaults,
                          *(default for default in child.args.kw_defaults if default)):
                yield early
                yield from _at_import(early)
        elif not isinstance(child, ast.Lambda):
            yield child
            yield from _at_import(child)


# ---------------------------------------------------------------------------
# The rules, each returning its violations
# ---------------------------------------------------------------------------


def _first_party_violations(tree: ast.Module) -> list[str]:
    """A22.4: app/fx/* imports its siblings, app.intelligence and app.normalization.config."""
    found = [f"{line}: relative import {module}" for module, _, line in _imports(tree)
             if module.startswith(".")]
    found += [f"{line}: {module}" for module, _, line in _imports(tree)
              if _within(module, ("app",)) and not _within(module, FX_ALLOWED_FIRST_PARTY)]
    found += [f"{line}: {module}" for module, line in _imported_modules(tree)
              if _within(module, FX_EXCLUDED_FIRST_PARTY)]
    return found


def _disguise_violations(tree: ast.Module) -> list[str]:
    """Every rule here looks for a name as it is written, so no import renames one or stars."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            found += [f"{node.lineno}: {alias.name} as {alias.asname}" for alias in node.names
                      if alias.asname]
            found += [f"{node.lineno}: import *" for alias in node.names if alias.name == "*"]
    return found


def _pipeline_violations(tree: ast.Module) -> list[str]:
    """A22.4, the reverse direction: the shared package never imports the slice built on it."""
    return [f"{line}: {module}" for module, line in _imported_modules(tree)
            if _within(module, ("app.pipeline",))]


def _third_party_violations(tree: ast.Module) -> list[str]:
    """A22.4, A19 item 5 and MD-21: no SQLAlchemy, and no package the project did not already use."""
    return [f"{line}: {module}" for module, _, line in _imports(tree)
            if not module.startswith(".") and module.split(".")[0] not in (
                {"app", *FX_ALLOWED_THIRD_PARTY} | sys.stdlib_module_names)]


def _stdlib_violations(tree: ast.Module) -> list[str]:
    """Beyond A22.4: the standard library is closed to what the package imports today."""
    return [f"{line}: {module}" for module, _, line in _imports(tree)
            if module.split(".")[0] in sys.stdlib_module_names - FX_ALLOWED_STDLIB]


def _filesystem_violations(tree: ast.Module) -> list[str]:
    """A7.6: the rate set is read from configuration and written nowhere. A19: no file's age is a clock."""
    found = [f"{node.lineno}: open()" for node in ast.walk(tree)
             if isinstance(node, ast.Call) and _callee(node) == "open"]
    found += [f"{node.lineno}: .{node.attr}" for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and node.attr in FILESYSTEM]
    return found


def _context_violations(tree: ast.Module) -> list[str]:
    """A9.1 items 2 and 3: the process default context is never read or altered, each
    context states its precision and its exponent limits instead of inheriting them, and
    each quantize states its rounding."""
    found = [f"{node.lineno}: {name}" for node in ast.walk(tree)
             for name in [node.id if isinstance(node, ast.Name)
                          else node.attr if isinstance(node, ast.Attribute) else ""]
             if name in PROCESS_CONTEXTS]
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if name in PROCESS_CONTEXTS]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        stated = {keyword.arg for keyword in node.keywords}
        if _callee(node) == "localcontext" and not (node.args or node.keywords):
            found.append(f"{node.lineno}: localcontext() copies the caller's context")
        if _callee(node) == "Context" and (node.args or not {"prec", "Emin", "Emax"} <= stated):
            found.append(f"{node.lineno}: Context() leaves a limit to the process default")
        if _callee(node) == "quantize" and "rounding" not in stated:
            found.append(f"{node.lineno}: quantize() leaves its rounding to the context")
    return found


def _state_violations(tree: ast.Module) -> list[str]:
    """A19 item 1: a pure function of its inputs. No global statement, and no mutable
    module-level container but __all__."""
    found = [f"{node.lineno}: {type(node).__name__.lower()} statement" for node in ast.walk(tree)
             if isinstance(node, ast.Global | ast.Nonlocal)]
    found += [f"{node.lineno}: globals()" for node in ast.walk(tree)
              if isinstance(node, ast.Call) and _callee(node) == "globals"]
    for node in tree.body:
        if not isinstance(node, ast.Assign | ast.AnnAssign) or node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        mutable = isinstance(node.value, ast.List | ast.Dict | ast.Set | ast.ListComp
                             | ast.DictComp | ast.SetComp) or (
            isinstance(node.value, ast.Call) and _callee(node.value) in MUTABLE_BUILDERS)
        if mutable and [_dotted(target) for target in targets] != ["__all__"]:
            found.append(f"{node.lineno}: a mutable module-level {_dotted(targets[0])}")
    return found


def _clock_violations(tree: ast.Module) -> list[str]:
    """M1's rule: no clock name as an attribute, a name or an import, and no clock module."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_CLOCKS:
            found.append(f"{node.lineno}: .{node.attr}")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_CLOCKS:
            found.append(f"{node.lineno}: {node.id}")
    for module, name, line in _imports(tree):
        if module.split(".")[0] in FORBIDDEN_CLOCK_MODULES or name in FORBIDDEN_CLOCKS:
            found.append(f"{line}: {module}" + (f".{name}" if name else ""))
    return found


def _randomness_violations(tree: ast.Module) -> list[str]:
    """M1's rule: no random source and no generated identifier. Nor hash() or id(), which
    depend on the hash seed and on an address."""
    found = [f"{line}: {module}" for module, _, line in _imports(tree)
             if module.split(".")[0] in FORBIDDEN_RANDOM_MODULES]
    found += [f"{node.lineno}: {_callee(node)}()" for node in ast.walk(tree)
              if isinstance(node, ast.Call) and _dotted(node.func) in {"hash", "id"}]
    return found


def _environment_violations(tree: ast.Module) -> list[str]:
    """A19 item 2 and A22.5: no environment read, so no variable can select a rate set."""
    found = [f"{line}: {module}" for module, line in _imported_modules(tree)
             if module.split(".")[0] in {"dotenv", "pydantic_settings"}
             or module in {"os.environ", "os.getenv"}]
    found += [f"{node.lineno}: .{node.attr}" for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}]
    found += [f"{node.lineno}: {node.id}" for node in ast.walk(tree)
              if isinstance(node, ast.Name) and node.id in {"environ", "getenv"}]
    return found


def _float_violations(tree: ast.Module) -> list[str]:
    """A9.1 item 1: no float() and no float literal. A binary float is never a rate or an amount."""
    found = [f"{node.lineno}: {node.value!r}" for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and isinstance(node.value, float)]
    found += [f"{node.lineno}: float()" for node in ast.walk(tree)
              if isinstance(node, ast.Call) and _dotted(node.func) == "float"]
    return found


def _session_violations(tree: ast.Module) -> list[str]:
    """A19 item 5 and A21's read-only row: no Session, no SQLAlchemy name, no session write."""
    found = [f"{line}: {module}" for module, _, line in _imports(tree)
             if module.split(".")[0] == "sqlalchemy"]
    found += [f"{node.lineno}: {node.id}" for node in ast.walk(tree)
              if isinstance(node, ast.Name) and node.id in {"Session", "sessionmaker"}]
    found += [f"{node.lineno}: {node.arg}" for node in ast.walk(tree)
              if isinstance(node, ast.arg) and node.arg in {"session", "sessions"}]
    found += [f"{node.lineno}: .{node.attr}" for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_WRITES]
    return found


def _document_violations(tree: ast.Module) -> list[str]:
    """A21: no document text and no ticket attribute can reach a rate or a converted amount."""
    found = [f"{line}: {module}" for module, line in _imported_modules(tree)
             if _within(module, FORBIDDEN_TEXT_PACKAGES)]
    found += [f"{node.lineno}: {node.id}" for node in ast.walk(tree)
              if isinstance(node, ast.Name) and node.id in FORBIDDEN_TEXT_NAMES]
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if name in FORBIDDEN_TEXT_NAMES]
    found += [f"{node.lineno}: .{node.attr}" for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_TEXT_NAMES]
    return found


def _yaml_violations(tree: ast.Module) -> list[str]:
    """A7.3 item 1: yaml.safe_load only. The module gives its loader and its error, nothing else."""
    found = [f"{node.lineno}: yaml.{node.attr}" for node in ast.walk(tree)
             if isinstance(node, ast.Attribute) and _dotted(node.value) == "yaml"
             and node.attr not in {"safe_load", "YAMLError"}]
    found += [f"{line}: {module}" + (f".{name}" if name else "")
              for module, name, line in _imports(tree)
              if module.split(".")[0] == "yaml" and (module, name) != ("yaml", None)]
    return found


def _import_time_violations(tree: ast.Module) -> list[str]:
    """A7.3 item 3: nothing is read while a module is imported, by a call, a default or a class."""
    return [f"{node.lineno}: {_callee(node)}()" for node in _at_import(tree)
            if isinstance(node, ast.Call) and _callee(node) in READS]


def _serialiser_violations(tree: ast.Module) -> list[str]:
    """A7.4: canonical_json and decimal_text are VS-01's. No copy of either, and no json of its own."""
    found = [f"{node.lineno}: def {node.name}" for node in ast.walk(tree)
             if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
             and node.name in {"canonical_json", "decimal_text"}]
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if name in {"canonical_json", "decimal_text"}
              and module != "app.intelligence.contract"]
    found += [f"{line}: {module}" for module, _, line in _imports(tree)
              if module.split(".")[0] == "json"]
    return found


def _handler_violations(tree: ast.Module) -> list[str]:
    """A7.5 item 5: nothing catches CurrencyMismatchError, by name, by a base class or bare."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            found.append(f"{node.lineno}: a bare except")
            continue
        caught = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
        found += [f"{node.lineno}: catches {_dotted(one)}" for one in caught
                  if _dotted(one).rsplit(".", 1)[-1] in WIDE_HANDLERS]
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if name in {"CurrencyMismatchError", "suppress"}]
    found += [f"{node.lineno}: {_dotted(node)}" for node in ast.walk(tree)
              if isinstance(node, ast.Name | ast.Attribute)
              and _dotted(node).rsplit(".", 1)[-1] in {"CurrencyMismatchError", "suppress"}]
    return found


def _money_violations(tree: ast.Module) -> list[str]:
    """A7.1 item 4 and A7.5 item 1: MoneyValue and its operators are untouched."""
    found = []
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign | ast.AnnAssign):
            targets = [node.target]
        found += [f"{node.lineno}: assigns {_dotted(target)}" for target in targets
                  if _dotted(target).startswith("MoneyValue.")]
        if isinstance(node, ast.Call) and _callee(node) in {"setattr", "delattr", "__setattr__"}:
            found.append(f"{node.lineno}: {_callee(node)}()")
        if isinstance(node, ast.ClassDef) and "MoneyValue" in map(_dotted, node.bases):
            found.append(f"{node.lineno}: class {node.name}(MoneyValue)")
    return found


def _currency_violations(tree: ast.Module) -> list[str]:
    """SD-1 and A7.5 item 3: the base currency and every rate are data. No code names a currency."""
    docstrings, codes = _docstrings(tree), default_config().currency_codes
    return [f"{node.lineno}: {node.value!r}" for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings and node.value in codes]


def _output_violations(tree: ast.Module) -> list[str]:
    """A20: no monetary value reaches a log line, because the package neither prints nor logs."""
    found = [f"{line}: {module}" for module, _, line in _imports(tree)
             if module.split(".")[0] == "logging"]
    found += [f"{node.lineno}: {node.id}" for node in ast.walk(tree)
              if isinstance(node, ast.Name) and node.id in {"print", "log_event"}]
    return found


# --- M2: two rules plan A21.1 item 7 asserts over every production module that
# --- exists, so over app/fx/ as well as app/pipeline/ ------------------------

#: Plan A22.4, "Names": what a module of app/pipeline/ may name from
#: app.relationships, and the two members of EdgeType it may write (A21.1 item 2).
RELATIONSHIP_NAMES = {"edges_of_type", "EdgeType", "Edge", "EdgeBasis"}
EDGE_TYPES = {"DEAL_OWNED_BY", "CUSTOMER_HAS_DEAL"}
#: Everything else app.relationships exports or defines that reads or
#: enumerates: none is named in any form.
FORBIDDEN_RELATIONSHIP_NAMES = {
    "neighbourhood", "escalation_path", "policy_documents", "canonical_fk_edges",
    "source_key_edges", "all_edge_types", "EDGE_SPECS", "spec_for", "order_edges", "EdgeSpec",
    "Neighbourhood", "EscalationPath", "ISOLATED_ENTITIES"}
#: Plan A21.1 item 4: every ORM model, the model registry and the declarative base.
MODEL_NAMES = frozenset({
    "BriefDecision", "ConnectorConfig", "Customer", "Deal", "Document", "DocumentCustomerLink",
    "Employee", "IngestionCursor", "IngestionError", "IngestionRun", "Organization", "Project",
    "RiskAssessment", "RiskBrief", "RiskPosition", "SourceRecord", "SupportTicket",
    "ENTITY_MODELS", "Base"})

def _model_name_violations(tree: ast.Module) -> list[str]:
    """A21.1 item 4: no ORM model and no model registry is named, however it is reached."""
    found = [f"{node.lineno}: {node.id}" for node in ast.walk(tree)
             if isinstance(node, ast.Name) and node.id in MODEL_NAMES]
    found += [f"{node.lineno}: .{node.attr}" for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and node.attr in MODEL_NAMES]
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if name in MODEL_NAMES]
    return found


def _relationship_violations(tree: ast.Module) -> list[str]:
    """A21.1 item 2 and A22.4's names: edges_of_type with two edge types written out, and
    nothing else of the relationship model. EdgeType is not called, indexed or iterated."""
    found = [f"{line}: import {module}" for module, name, line in _imports(tree)
             if _within(module, ("app.relationships",)) and name is None]
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if _within(module, ("app.relationships",)) and name is not None
              and (module != "app.relationships" or name not in RELATIONSHIP_NAMES)]
    found += [f"{node.lineno}: {name}" for node in ast.walk(tree)
              for name in [node.id if isinstance(node, ast.Name)
                           else node.attr if isinstance(node, ast.Attribute) else ""]
              if name in FORBIDDEN_RELATIONSHIP_NAMES]
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if name in FORBIDDEN_RELATIONSHIP_NAMES]
    members = {id(node.value): node for node in ast.walk(tree)
               if isinstance(node, ast.Attribute) and node.attr in EDGE_TYPES}
    found += [f"{node.lineno}: EdgeType used as a value" for node in ast.walk(tree)
              if isinstance(node, ast.Name) and node.id == "EdgeType" and id(node) not in members]
    found += [f"{node.lineno}: EdgeType.{node.attr}" for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and _dotted(node.value) == "EdgeType"
              and node.attr not in EDGE_TYPES]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _callee(node) == "edges_of_type":
            first = node.args[0] if node.args else None
            if not (isinstance(first, ast.Attribute) and _dotted(first.value) == "EdgeType"
                    and first.attr in EDGE_TYPES):
                found.append(f"{node.lineno}: edges_of_type() with an edge type not written out")
    return found


#: The rules over app/fx/. M1's twenty-one stand as they were. M2 adds the last
#: two, A21.1 items 2 and 4, which bind every production module of VS-02.
FX_RULES: tuple[Rule, ...] = (
    _first_party_violations, _disguise_violations, _pipeline_violations, _third_party_violations,
    _stdlib_violations,
    _filesystem_violations, _context_violations, _state_violations, _clock_violations,
    _randomness_violations, _environment_violations, _float_violations, _session_violations,
    _document_violations, _yaml_violations, _import_time_violations, _serialiser_violations,
    _handler_violations, _money_violations, _currency_violations, _output_violations,
    _relationship_violations, _model_name_violations,
)


def _constructions(sources: dict[str, str]) -> list[str]:
    """Every place a RateSet is built, as `path:line`."""
    return sorted(f"{path}:{node.lineno}" for path, source in sources.items()
                  for node in ast.walk(ast.parse(source))
                  if isinstance(node, ast.Call) and _callee(node) == "RateSet")


def _outside_constructions(sources: dict[str, str]) -> list[str]:
    """A7.6: a rate set is the loaded, validated content of the authored file, and nothing
    else. Only the loader builds one."""
    return [entry for entry in _constructions(sources) if entry.split(":")[0] != RATES]


def _fx_importers(sources: dict[str, str]) -> list[str]:
    """A21's isolation row: every import of app.fx, once each, as `path:line`."""
    return sorted({f"{path}:{line}" for path, source in sources.items()
                   for module, name, line in _imports(ast.parse(source))
                   for absolute in _absolute(path, module, name)
                   if _within(absolute, ("app.fx",))})


def _absolute(path: str, module: str, name: str | None) -> list[str]:
    """An import as dotted names, a relative one resolved against the importing file's package."""
    level, rest = len(module) - len(module.lstrip(".")), module.lstrip(".")
    if level:
        package = path.split("/")[:-1]
        module = ".".join([*package[:len(package) - (level - 1)], *([rest] if rest else [])])
    return [module, *([f"{module}.{name}"] if name else [])]


def _outside_importers(sources: dict[str, str]) -> list[str]:
    return [entry for entry in _fx_importers(sources) if not entry.startswith(FX_IMPORTERS)]


# ---------------------------------------------------------------------------
# The no-executor closure (plan A21), over a {module name: source text} mapping
# ---------------------------------------------------------------------------


def _module_sources() -> dict[str, str]:
    """Every module under app/, by dotted name (a package by its own name), with its source."""
    sources = {}
    for path in sorted(APP_DIR.rglob("*.py")):
        parts = path.relative_to(REPO).with_suffix("").parts
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        sources[name] = path.read_text(encoding="utf-8")
    return sources


def _imports_of(name: str, sources: dict[str, str]) -> list[tuple[str, list[str]]]:
    """One module's imports as (module, names), a relative one resolved against its package."""
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
    """`import a.b.c` reaches a, a.b and a.b.c; `from a.b import c` reaches a.b.c when a module."""
    reached = set()
    for module, names in _imports_of(name, sources):
        if module.split(".")[0] != "app":
            continue
        parts = module.split(".")
        reached |= {".".join(parts[:end]) for end in range(1, len(parts) + 1)}
        reached |= {f"{module}.{one}" for one in names if f"{module}.{one}" in sources}
    return reached


#: The packages the no-executor closure starts from (plan A21). M2 adds the
#: second (OD-5): the closure is taken from both.
CLOSURE_ROOTS = ("app.fx", "app.pipeline")


def _fx_closure(sources: dict[str, str]) -> set[str]:
    """Every first-party name app/fx/ and app/pipeline/ reach, statically (M8's closure):
    nothing is imported."""
    reached: set[str] = set()
    pending = sorted(name for name in sources if _within(name, CLOSURE_ROOTS))
    while pending:
        name = pending.pop()
        if name not in reached:
            reached.add(name)
            if name in sources:
                pending += sorted(_edges(name, sources) - reached)
    return reached


def _executor_violations(sources: dict[str, str]) -> list[str]:
    """A21: the closure reaches no connector, ingestion, security or API module."""
    return sorted(name for name in _fx_closure(sources) if _within(name, FORBIDDEN_FIRST_PARTY))


def _outbound_violations(sources: dict[str, str]) -> list[str]:
    """A21: no closure module imports an outbound HTTP, SMTP or socket module."""
    found = []
    for name in sorted(_fx_closure(sources) & sources.keys()):
        for module, names in _imports_of(name, sources):
            found += [f"{name}: {candidate}"
                      for candidate in (module, *(f"{module}.{one}" for one in names))
                      if _within(candidate, OUTBOUND_MODULES)]
    return found


APP_SOURCES = _module_sources()
CODE_SOURCES = {path.relative_to(REPO).as_posix(): path.read_text(encoding="utf-8")
                for directory in CODE_DIRS for path in sorted((REPO / directory).rglob("*.py"))}


# ---------------------------------------------------------------------------
# Every rule fails on a forbidden edit to a copy of the real source
# ---------------------------------------------------------------------------


def _replaced(relative: str, old: str, new: str) -> str:
    """The real source with exactly one change."""
    source = _source(relative)
    assert source.count(old) == 1, f"{relative}: {old!r} occurs {source.count(old)} times"
    return source.replace(old, new)


def _appended(relative: str, addition: str) -> str:
    """The real source with one statement added."""
    return _source(relative) + "\n" + addition


#: (what was done, the rule that must object, the edited copy of a real module).
FORBIDDEN_EDITS: list[tuple[str, Rule, str]] = [
    # A21.1 items 2 and 4 (M2): the relationship model and the ORM models, over app/fx/ too
    ("conversion reads a customer's neighbourhood",
     _relationship_violations,
     _appended(CONVERT, "from app.relationships import neighbourhood\n")),
    ("the loader names an edge type",
     _relationship_violations,
     _appended(RATES, "OWNED = EdgeType.DEAL_OWNED_BY\nEVERY = list(EdgeType)\n")),
    ("the loader names the model registry through a module it may import",
     _model_name_violations,
     _appended(RATES, "from app.intelligence.scope import ENTITY_MODELS\n")),
    ("conversion names the Deal model",
     _model_name_violations,
     _appended(CONVERT, "import app.intelligence.scope\nmodel = app.intelligence.scope.Deal\n")),
    # A22.4: the allow-list
    ("the loader reads the database settings",
     _first_party_violations, _appended(RATES, "from app.core.config import get_settings\n")),
    ("the loader reads a canonical model",
     _first_party_violations, _appended(RATES, "from app.persistence.models import Deal\n")),
    ("the loader logs through log_event",
     _first_party_violations, _appended(RATES, "from app.core.logging import log_event\n")),
    ("conversion reads the relationship model",
     _first_party_violations, _appended(CONVERT, "from app.relationships import edges_of_type\n")),
    ("conversion takes Layer 1 beyond its configuration",
     _first_party_violations,
     _appended(CONVERT, "from app.normalization.contract import BUSINESS_FIELDS\n")),
    ("conversion takes the normalization package whole",
     _first_party_violations, _appended(CONVERT, "from app.normalization import normalize\n")),
    ("the package is imported by its top name",
     _first_party_violations, _appended(PACKAGE, "import app\n")),
    ("a first-party module is imported by name",
     _first_party_violations, _appended(CONVERT, "import app.api.errors\n")),
    ("the yaml module is renamed, so its loaders are not seen by name",
     _disguise_violations, _appended(RATES, "import yaml as y\n")),
    ("a clock is imported under another name",
     _disguise_violations, _appended(RATES, "from datetime import datetime as moment\n")),
    ("everything a module holds is imported",
     _disguise_violations, _appended(CONVERT, "from decimal import *\n")),
    ("a sibling is imported relatively",
     _first_party_violations,
     _replaced(CONVERT, "from app.fx.rates import RateSet", "from .rates import RateSet")),
    ("a parent is reached relatively",
     _first_party_violations, _appended(RATES, "from ..pipeline import measures\n")),
    ("the package computes a signal",
     _first_party_violations,
     _appended(RATES, "from app.intelligence.signals import compute_signals\n")),
    ("the package reads the band table",
     _first_party_violations, _appended(CONVERT, "from app.intelligence.bands import BandRule\n")),
    ("the package takes the windows module by name",
     _first_party_violations, _appended(CONVERT, "from app.intelligence import windows\n")),
    ("the shared package imports the slice",
     _pipeline_violations, _appended(CONVERT, "from app.pipeline.measures import weigh\n")),
    ("the shared package imports the slice whole",
     _pipeline_violations, _appended(RATES, "import app.pipeline\n")),
    ("the shared package takes the slice by name",
     _pipeline_violations, _appended(PACKAGE, "from app import pipeline\n")),
    # A22.4, A19 item 5, MD-21: third-party packages
    ("the loader imports SQLAlchemy",
     _third_party_violations, _appended(RATES, "from sqlalchemy import select\n")),
    ("a rate is fetched over HTTP",
     _third_party_violations, _appended(RATES, "import httpx\n")),
    ("rates are held in a data frame",
     _third_party_violations, _appended(CONVERT, "import pandas\n")),
    ("a model is asked for a rate",
     _third_party_violations, _appended(RATES, "import anthropic\n")),
    ("the rate file comes from the settings class",
     _third_party_violations, _appended(RATES, "from pydantic_settings import BaseSettings\n")),
    # beyond A22.4: the standard library is closed
    ("the loader starts a thread",
     _stdlib_violations, _appended(RATES, "import threading\n")),
    ("the loader schedules a refresh",
     _stdlib_violations, _appended(RATES, "import asyncio\n")),
    ("the rates are kept in a database file",
     _stdlib_violations, _appended(RATES, "import sqlite3\n")),
    ("a module is imported by name at run time",
     _stdlib_violations, _appended(RATES, "import importlib\n")),
    ("conversion shells out",
     _stdlib_violations, _appended(CONVERT, "import subprocess\n")),
    ("the loader reaches for the operating system",
     _stdlib_violations, _appended(RATES, "import os\n")),
    ("a temporary copy of the rates is kept",
     _stdlib_violations, _appended(RATES, "from tempfile import NamedTemporaryFile\n")),
    # A7.6: nothing is written, and no file's age is read
    ("the loaded rate set is written back",
     _filesystem_violations,
     _appended(RATES, "def store(path, text):\n    path.write_text(text, encoding='utf-8')\n")),
    ("the file is opened for writing",
     _filesystem_violations,
     _appended(RATES, "def store(path):\n    return open(path, 'w', encoding='utf-8')\n")),
    ("the cache is refreshed when the file changes",
     _filesystem_violations,
     _appended(RATES, "def changed(path):\n    return path.stat().st_mtime\n")),
    ("every rate file in the directory is loaded",
     _filesystem_violations,
     _appended(RATES, "def every(directory):\n    return sorted(directory.glob('*.yaml'))\n")),
    ("a stale rate file is removed",
     _filesystem_violations, _appended(RATES, "def forget(path):\n    path.unlink()\n")),
    # A9.1 item 2: the process default context
    ("the process context is made precise instead",
     _context_violations,
     _appended(CONVERT, "from decimal import getcontext\ngetcontext().prec = 50\n")),
    ("the process context is replaced",
     _context_violations,
     _appended(CONVERT, "import decimal\ndecimal.setcontext(arithmetic_context())\n")),
    ("the default context is edited",
     _context_violations,
     _appended(CONVERT, "import decimal\ndecimal.DefaultContext.prec = 50\n")),
    ("conversion runs in a copy of the caller's context",
     _context_violations,
     _replaced(CONVERT, "with localcontext(arithmetic_context()):", "with localcontext():")),
    ("the arithmetic context inherits its exponent limits",
     _context_violations,
     _replaced(CONVERT, "rounding=ROUNDING_MODE, Emin=MIN_EMIN, Emax=MAX_EMAX,",
               "rounding=ROUNDING_MODE,")),
    ("the arithmetic context inherits its precision",
     _context_violations,
     _replaced(CONVERT, "Context(prec=ARITHMETIC_PRECISION, rounding=ROUNDING_MODE,",
               "Context(rounding=ROUNDING_MODE,")),
    ("the digest's context inherits its exponent limits",
     _context_violations,
     _replaced(RATES, "Context(prec=digits, Emin=MIN_EMIN, Emax=MAX_EMAX)",
               "Context(prec=digits)")),
    ("an amount is quantized in whatever rounding the context has",
     _context_violations,
     _replaced(CONVERT, ".quantize(BASE_QUANTUM, rounding=ROUNDING_MODE)",
               ".quantize(BASE_QUANTUM)")),
    # A19 item 1: no hidden state
    ("the current rate set is kept in a module global",
     _state_violations,
     _appended(RATES, "def remember(rate_set):\n    global _CURRENT\n    _CURRENT = rate_set\n")),
    ("rate sets are registered by version",
     _state_violations, _appended(RATES, "_REGISTRY = {}\n")),
    ("an override list is kept for tests",
     _state_violations, _appended(RATES, "_OVERRIDES: list[RateSet] = []\n")),
    ("converted amounts are cached in a dict",
     _state_violations, _appended(CONVERT, "_CACHE = dict()\n")),
    ("the module's globals are rewritten",
     _state_violations, _appended(RATES, "globals()['DEFAULT_RATE_SET_PATH'] = None\n")),
    # A21: no clock, no randomness, no environment
    ("the rate set is stamped with today's date",
     _clock_violations,
     _replaced(RATES, 'as_of_date=_plain_date(data["as_of_date"], f"{where}: as_of_date")',
               "as_of_date=date.today()")),
    ("the loader reads the wall clock",
     _clock_violations, _appended(RATES, "loaded_at = datetime.now()\n")),
    ("conversion times itself",
     _clock_violations, _appended(CONVERT, "import time\n")),
    ("conversion imports a clock by name",
     _clock_violations, _appended(CONVERT, "from time import monotonic\n")),
    ("a rate set gets a generated id",
     _randomness_violations, _appended(RATES, "import uuid\n")),
    ("a rate is jittered",
     _randomness_violations, _appended(CONVERT, "from random import random\n")),
    ("an identifier is drawn from the secrets module",
     _randomness_violations, _appended(RATES, "import secrets\n")),
    ("rates are ordered by their hash",
     _randomness_violations, _appended(RATES, "order = sorted([], key=lambda code: hash(code))\n")),
    ("a rate set is identified by its address",
     _randomness_violations, _appended(RATES, "def identity(rate_set):\n    return id(rate_set)\n")),
    ("an environment variable selects the rate file",
     _environment_violations,
     _appended(RATES, "import os\nDEFAULT_RATE_SET_PATH = Path(os.environ['FX_RATES'])\n")),
    ("the environment is read through getenv",
     _environment_violations, _appended(RATES, "import os\noverride = os.getenv('FX_RATES')\n")),
    ("the environment is imported by name",
     _environment_violations, _appended(RATES, "from os import environ\n")),
    ("a dotenv file is loaded",
     _environment_violations, _appended(RATES, "from dotenv import load_dotenv\n")),
    # A9.1: no float
    ("the quantum is built from a float",
     _float_violations, _replaced(CONVERT, 'Decimal("0.01")', "Decimal(0.01)")),
    ("a rate is taken through float()",
     _float_violations,
     _replaced(RATES, "return Decimal(value)", "return Decimal(float(value))")),
    ("an amount is multiplied by a float",
     _float_violations, _appended(CONVERT, "margin = 1.5\n")),
    ("a float is written with an exponent",
     _float_violations, _appended(CONVERT, "scale = 1e2\n")),
    # A19 item 5, A21: read-only
    ("conversion takes a session",
     _session_violations,
     _appended(CONVERT, "def stored_rate(session, currency):\n    return None\n")),
    ("the loader imports the Session type",
     _session_violations, _appended(RATES, "from sqlalchemy.orm import Session\n")),
    ("the rate set is written to a table",
     _session_violations, _appended(RATES, "def register(unit, row):\n    unit.add(row)\n")),
    ("the package commits",
     _session_violations, _appended(RATES, "def register(unit):\n    unit.commit()\n")),
    ("the package flushes",
     _session_violations, _appended(RATES, "def register(unit):\n    unit.flush()\n")),
    ("conversion is typed against a Session",
     _session_violations,
     _appended(CONVERT, "def owned(unit: Session) -> None:\n    return None\n")),
    # A21: no document text, no ticket attribute
    ("a rate is read from a document",
     _document_violations, _appended(RATES, "from app.evidence import citable_text\n")),
    ("the loader names the Document model",
     _document_violations, _appended(RATES, "from app.persistence.models import Document\n")),
    ("conversion names a ticket",
     _document_violations, _appended(CONVERT, "ticket = SupportTicket\n")),
    ("conversion reads a repository",
     _document_violations,
     _appended(CONVERT, "from app.persistence.repositories import citation_reads\n")),
    ("conversion reads the decision layer",
     _document_violations, _appended(CONVERT, "from app.decisions import reconcile\n")),
    ("conversion reads an analyst",
     _document_violations, _appended(CONVERT, "from app import analysts\n")),
    ("conversion takes the ticket model from a module it may import",
     _document_violations,
     _appended(CONVERT, "from app.intelligence.scope import SupportTicket\n")),
    ("conversion reaches the document model as an attribute",
     _document_violations,
     _appended(CONVERT, "import app.intelligence.scope\nmodel = app.intelligence.scope.Document\n")),
    # A7.3: yaml.safe_load only, and nothing read at import
    ("the file is loaded with the unsafe loader",
     _yaml_violations, _replaced(RATES, "yaml.safe_load(", "yaml.load(")),
    ("the file is loaded with full_load",
     _yaml_violations, _replaced(RATES, "yaml.safe_load(", "yaml.full_load(")),
    ("every document of the file is loaded",
     _yaml_violations, _replaced(RATES, "yaml.safe_load(", "yaml.safe_load_all(")),
    ("the document is composed before it is loaded",
     _yaml_violations, _appended(RATES, "node = yaml.compose('', Loader=yaml.SafeLoader)\n")),
    ("a loader is taken from the yaml module by name",
     _yaml_violations, _appended(RATES, "from yaml import load\n")),
    ("the yaml module is imported under another name",
     _yaml_violations, _appended(RATES, "import yaml.loader\n")),
    ("the rate set is loaded when the module is imported",
     _import_time_violations, _appended(RATES, "CURRENT = default_rate_set()\n")),
    ("the file is read when the module is imported",
     _import_time_violations,
     _appended(RATES, "_TEXT = DEFAULT_RATE_SET_PATH.read_text(encoding='utf-8')\n")),
    ("the rate set is loaded as a default argument",
     _import_time_violations,
     _appended(RATES, "def later(rate_set=default_rate_set()):\n    return rate_set\n")),
    ("the rate set is loaded in a class body",
     _import_time_violations,
     _appended(RATES, "class Eager:\n    current = load_rate_set(DEFAULT_RATE_SET_PATH)\n")),
    ("the package loads the rate set for its importers",
     _import_time_violations, _appended(PACKAGE, "CURRENT = default_rate_set()\n")),
    # A7.4: VS-01's serialisers, imported and not copied
    ("canonical_json is copied into the package",
     _serialiser_violations,
     _appended(RATES, "def canonical_json(payload):\n    return repr(payload)\n")),
    ("decimal_text is copied into the package",
     _serialiser_violations, _appended(RATES, "def decimal_text(value):\n    return str(value)\n")),
    ("the digest serialises with json itself",
     _serialiser_violations, _appended(RATES, "import json\n")),
    ("canonical_json is Layer 1's and not VS-01's",
     _serialiser_violations,
     _replaced(RATES, "from app.intelligence.contract import canonical_json, decimal_text",
               "from app.intelligence.contract import decimal_text\n"
               "from app.persistence.repositories.raw import canonical_json")),
    # A7.5 item 5: nothing catches CurrencyMismatchError
    ("conversion catches a currency mismatch",
     _handler_violations,
     _appended(CONVERT, "try:\n    pass\nexcept CurrencyMismatchError:\n    pass\n")),
    ("conversion catches M1's base error",
     _handler_violations,
     _appended(CONVERT, "try:\n    pass\nexcept (KeyError, IntelligenceError):\n    pass\n")),
    ("the loader catches everything",
     _handler_violations,
     _replaced(RATES, "except (yaml.YAMLError, ValueError) as exc:", "except Exception as exc:")),
    ("the loader catches BaseException",
     _handler_violations,
     _replaced(RATES, "except (yaml.YAMLError, ValueError) as exc:",
               "except BaseException as exc:")),
    ("a currency mismatch is suppressed without a handler",
     _handler_violations,
     _appended(CONVERT, "from contextlib import suppress\nwith suppress(Exception):\n    pass\n")),
    ("the mismatch error is imported to be handled",
     _handler_violations,
     _appended(CONVERT, "from app.intelligence.errors import CurrencyMismatchError\n")),
    ("the loader has a bare except",
     _handler_violations,
     _replaced(RATES, "except (yaml.YAMLError, ValueError) as exc:", "except:")),
    # A7.1 item 4: MoneyValue is untouched
    ("addition is taught to convert",
     _money_violations, _appended(CONVERT, "MoneyValue.__add__ = lambda left, right: left\n")),
    ("a conversion method is attached to MoneyValue",
     _money_violations, _appended(CONVERT, "setattr(MoneyValue, 'to_base', convert)\n")),
    ("a frozen amount is overwritten in place",
     _money_violations,
     _appended(CONVERT, "def rewrite(value, amount):\n"
                        "    object.__setattr__(value, 'amount', amount)\n")),
    ("MoneyValue is subclassed",
     _money_violations, _appended(CONVERT, "class BaseMoney(MoneyValue):\n    pass\n")),
    ("a method is removed from MoneyValue",
     _money_violations, _appended(CONVERT, "delattr(MoneyValue, 'total')\n")),
    ("a MoneyValue attribute is rebound in place",
     _money_violations, _appended(CONVERT, "MoneyValue.total += 1\n")),
    ("a MoneyValue attribute is declared and set",
     _money_violations, _appended(CONVERT, "MoneyValue.rate: Decimal = Decimal(1)\n")),
    # SD-1, A7.5 item 3: no currency and no rate in code
    ("the base currency is written into the code",
     _currency_violations, _appended(CONVERT, 'BASE_CURRENCY = "INR"\n')),
    ("a fallback rate is written into the code",
     _currency_violations, _appended(CONVERT, 'FALLBACK = {"USD": Decimal("85")}\n')),
    ("a missing rate defaults to another currency's",
     _currency_violations,
     _replaced(CONVERT, "rate = rate_set.rates.get(value.currency)",
               'rate = rate_set.rates.get(value.currency, rate_set.rates.get("EUR"))')),
    # A20: no output
    ("conversion prints an amount",
     _output_violations, _appended(CONVERT, "print(BASE_QUANTUM)\n")),
    ("the loader logs the rates",
     _output_violations, _appended(RATES, "import logging\n")),
    ("an error is logged through log_event",
     _output_violations, _appended(ERRORS, "log_event(None, 20, 'fx.rate_missing')\n")),
]


def _with(**modules: str) -> dict[str, str]:
    """The real tree with the named modules replaced or added; double underscores are dots."""
    return {**APP_SOURCES, **{name.replace("__", "."): source for name, source in modules.items()}}


#: The closure rules, over the real tree with one forbidden edit.
FORBIDDEN_TREES: list[tuple[str, Callable[[dict[str, str]], list[str]], dict[str, str]]] = [
    ("the loader opens a socket",
     _outbound_violations, _with(app__fx__rates=_appended(RATES, "import socket\n"))),
    ("the loader fetches a rate over HTTP",
     _outbound_violations, _with(app__fx__rates=_appended(RATES, "import httpx\n"))),
    ("conversion takes urllib's request module by name",
     _outbound_violations,
     _with(app__fx__convert=_appended(CONVERT, "from urllib import request\n"))),
    ("an error is mailed",
     _outbound_violations, _with(app__fx__errors=_appended(ERRORS, "import smtplib\n"))),
    ("a module the package already reaches turns outbound",
     _outbound_violations,
     _with(app__intelligence__money=APP_SOURCES["app.intelligence.money"]
           + "\nimport http.client\n")),
    ("the loader reaches a connector",
     _executor_violations,
     _with(app__fx__rates=_appended(
         RATES, "from app.connectors.registry import build_connector\n"))),
    ("conversion reaches the API",
     _executor_violations,
     _with(app__fx__convert=_appended(CONVERT, "from app.api.errors import ErrorCode\n"))),
    ("the package reaches the outbound client factory",
     _executor_violations,
     _with(app__fx=_appended(PACKAGE, "from app.core.security import build_client\n"))),
    ("the package reaches ingestion through a module it already imports",
     _executor_violations,
     _with(app__normalization__config=APP_SOURCES["app.normalization.config"]
           + "\nfrom app.ingestion.orchestrator import run_ingestion\n")),
    ("the package reaches a connector through a new helper",
     _executor_violations,
     _with(app__fx__convert=_appended(CONVERT, "from app.core.helper import go\n"),
           app__core__helper="from app.connectors.registry import build_connector\n")),
]

#: A21's isolation row: an edited copy of a real file that existed before VS-02.
FORBIDDEN_IMPORTERS = [
    ("app/intelligence/money.py", "from app.fx import convert\n"),
    ("app/intelligence/money.py", "from app.fx.convert import convert\n"),
    ("app/intelligence/money.py", "import app.fx.rates\n"),
    ("app/intelligence/money.py", "from app import fx\n"),
    ("app/main.py", "from app.fx import default_rate_set\n"),
    ("app/persistence/repositories/canonical.py", "from app.fx import rates\n"),
    ("app/normalization/config.py", "from app.fx.errors import FxError\n"),
    ("scripts/vs01_acceptance.py", "from app.fx import convert\n"),
    ("migrations/env.py", "import app.fx\n"),
    ("app/intelligence/money.py", "from ..fx import convert\n"),
    ("app/intelligence/money.py", "from .. import fx\n"),
    ("app/main.py", "def later():\n    from .fx.convert import convert\n    return convert\n"),
]


#: A7.6: a rate set built anywhere but in the loader, in an edited copy of a real file.
FORBIDDEN_CONSTRUCTIONS = [
    (CONVERT, "FALLBACK = RateSet('0', 'INR', None, 'built in code', {})\n"),
    (PACKAGE, "CURRENT = RateSet('0', 'INR', None, 'built in code', {})\n"),
    ("app/main.py", "from app.fx import RateSet\nRATES = RateSet('0', 'INR', None, 'n', {})\n"),
    ("scripts/vs01_acceptance.py", "RATES = RateSet('0', 'INR', None, 'n', {})\n"),
]


@pytest.mark.parametrize(("label", "rule", "source"), FORBIDDEN_EDITS,
                         ids=[label for label, _, _ in FORBIDDEN_EDITS])
def test_every_rule_catches_a_forbidden_edit_to_a_copy_of_the_real_source(label, rule, source):
    assert rule(ast.parse(source)), label


@pytest.mark.parametrize(("label", "rule", "sources"), FORBIDDEN_TREES,
                         ids=[label for label, _, _ in FORBIDDEN_TREES])
def test_every_closure_rule_catches_a_forbidden_edit_to_a_copy_of_the_real_tree(
        label, rule, sources):
    assert rule(sources), label


@pytest.mark.parametrize(("path", "addition"), FORBIDDEN_IMPORTERS,
                         ids=[f"{path}: {addition.strip()}" for path, addition in FORBIDDEN_IMPORTERS])
def test_the_importer_scan_catches_an_import_from_outside_the_package(path, addition):
    edited = {**CODE_SOURCES, path: CODE_SOURCES[path] + "\n" + addition}

    assert [entry.split(":")[0] for entry in _outside_importers(edited)] == [path]


@pytest.mark.parametrize(("path", "addition"), FORBIDDEN_CONSTRUCTIONS,
                         ids=[path for path, _ in FORBIDDEN_CONSTRUCTIONS])
def test_the_construction_scan_catches_a_rate_set_built_outside_the_loader(path, addition):
    edited = {**CODE_SOURCES, path: CODE_SOURCES[path] + "\n" + addition}

    assert [entry.split(":")[0] for entry in _outside_constructions(edited)] == [path]


def test_every_rule_has_a_forbidden_edit_it_is_proved_against():
    """No rule is left without a negative control: M1's, and from M2 the pipeline's (OD-5)."""
    assert {rule for _, rule, _ in FORBIDDEN_EDITS} == set(FX_RULES)
    assert {rule for _, rule, _ in FORBIDDEN_TREES} == {_executor_violations, _outbound_violations}
    assert {rule for _, rule, _ in PIPELINE_FORBIDDEN_EDITS} == {
        rule for rules in PIPELINE_RULES.values() for rule in rules} | set(QUERY_RULES)
    assert set(FX_RULES) & {rule for _, rule, _ in PIPELINE_FORBIDDEN_EDITS}, (
        "the rules the two packages share are proved against the pipeline's source too")


def test_the_scans_read_code_and_not_the_docstrings_explaining_it():
    """These modules say at length what they do not do; saying it is not doing it."""
    prose = ast.parse('"""Never float(x) or 0.01, never INR, and yaml.load is refused."""\nx = 1\n')
    a_code = '"""INR"""\nclass Named:\n    """USD"""\n    def of(self):\n        """EUR"""\n'

    assert [rule.__name__ for rule in FX_RULES if rule(prose)] == []
    assert _currency_violations(ast.parse(a_code)) == []
    assert _currency_violations(ast.parse(a_code + "        return 'EUR'\n")) == ["6: 'EUR'"]
    assert _float_violations(ast.parse("ok = isinstance(value, float)\n")) == []


# ---------------------------------------------------------------------------
# Where app/fx/ exists (plan A22.1)
# ---------------------------------------------------------------------------


def test_the_fx_package_holds_exactly_its_four_modules():
    """A scan that silently matches nothing proves nothing, and a fifth module is a decision."""
    found = sorted(path.relative_to(REPO).as_posix() for path in FX_DIR.rglob("*.py"))

    assert found == sorted(FX_MODULES)
    for relative in FX_MODULES:
        assert [node for node in ast.parse(_source(relative)).body
                if not isinstance(node, ast.Expr)], f"{relative} holds no code"


# ---------------------------------------------------------------------------
# The rules over the real files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", FX_MODULES)
@pytest.mark.parametrize("rule", FX_RULES, ids=lambda rule: rule.__name__.strip("_"))
def test_no_fx_module_breaks_a_rule(relative, rule):
    assert rule(ast.parse(_source(relative))) == []


def test_the_package_imports_what_its_row_grants_and_no_package_beyond_it():
    """The allow-lists are not vacuous: the package does read M1, the D1 vocabulary and YAML."""
    imported = {module for relative in FX_MODULES
                for module, _, _ in _imports(ast.parse(_source(relative)))}

    assert {"app.intelligence.contract", "app.intelligence.money", "app.normalization.config",
            "app.fx.errors", "app.fx.rates", "app.fx.convert"} <= imported
    assert {"yaml"} <= {module.split(".")[0] for module in imported
                        if module.split(".")[0] not in {"app"} | sys.stdlib_module_names} <= (
        FX_ALLOWED_THIRD_PARTY)
    assert {module.split(".")[0] for module in imported
            if module.split(".")[0] in sys.stdlib_module_names} == FX_ALLOWED_STDLIB


def test_the_digest_imports_vs01s_two_serialisers():
    """Plan A7.4: imported, so a digest and a VS-01 payload hash cannot disagree about a number."""
    assert {("app.intelligence.contract", "canonical_json"),
            ("app.intelligence.contract", "decimal_text")} <= {
        (module, name) for module, name, _ in _imports(ast.parse(_source(RATES)))}


def test_only_the_loader_builds_a_rate_set():
    """Plan A7.6: the rate set is the loaded, validated content of the authored file."""
    built = _constructions(CODE_SOURCES)

    assert [entry.split(":")[0] for entry in built] == [RATES], built
    assert _outside_constructions(CODE_SOURCES) == []


def test_the_loader_reads_one_file_one_way():
    """One read, as UTF-8, through yaml.safe_load, behind one cache: no locale and no second path."""
    source = _source(RATES)

    assert source.count('read_text(encoding="utf-8")') == source.count("read_text(") == 1
    assert source.count("yaml.safe_load(") == 1
    assert source.count("lru_cache") == source.count("__file__") == 1


# ---------------------------------------------------------------------------
# Isolation (plan A21, A22.4): nothing that existed before VS-02 imports app.fx
# ---------------------------------------------------------------------------


def test_only_the_fx_package_imports_app_fx():
    """From M2 the pipeline package is a consumer too, and is the only other one (OD-5)."""
    importers = {entry.split(":")[0] for entry in _fx_importers(CODE_SOURCES)}

    assert importers, "the scan found no importer, so it would pass if app.fx were unused"
    assert _outside_importers(CODE_SOURCES) == []
    assert {path for path in importers if not path.startswith("app/fx/")} == {
        P_AGGREGATION, P_CONFIG, P_MEASURES}
    assert {"app/main.py", "app/intelligence/money.py", "scripts/vs01_acceptance.py",
            "migrations/env.py"} <= CODE_SOURCES.keys(), "the scan must read what it clears"


# ---------------------------------------------------------------------------
# The no-executor boundary (plan A21)
# ---------------------------------------------------------------------------


def test_the_closure_is_static_and_reaches_past_the_package():
    """Read from source, never imported: it follows app.intelligence into the canonical models."""
    closure = _fx_closure(APP_SOURCES)

    assert {"app.fx", "app.fx.rates", "app.fx.convert", "app.fx.errors"} <= closure
    assert {"app.pipeline", "app.pipeline.aggregation", "app.pipeline.config",
            "app.pipeline.errors", "app.pipeline.facts", "app.pipeline.measures",
            "app.persistence.repositories.pipeline_queries", "app.relationships",
            "app.relationships.edges", "app.relationships.queries"} <= closure, (
        "from M2 the closure is taken from both packages")
    assert {"app.intelligence", "app.intelligence.contract", "app.intelligence.money",
            "app.intelligence.scope", "app.normalization.config",
            "app.persistence.models"} <= closure
    assert "app.api.v1.risk" in APP_SOURCES and "app.api.v1.risk" not in closure


def test_the_closure_reaches_no_connector_ingestion_security_or_api_module():
    assert _executor_violations(APP_SOURCES) == []


def test_no_closure_module_imports_an_outbound_http_smtp_or_socket_module():
    assert _outbound_violations(APP_SOURCES) == []


# ===========================================================================
# VS02-M2: app/pipeline/ and pipeline_queries.py (plan A21, A21.1, A21.2, A22.4)
# ===========================================================================

PIPELINE_DIR = APP_DIR / "pipeline"
P_PACKAGE, P_AGGREGATION, P_CONFIG, P_ERRORS, P_FACTS, P_MEASURES = (
    "app/pipeline/__init__.py", "app/pipeline/aggregation.py", "app/pipeline/config.py",
    "app/pipeline/errors.py", "app/pipeline/facts.py", "app/pipeline/measures.py")
#: Plan B1 allows eight modules. M2 builds six; view.py and service.py are M3's (B6).
PIPELINE_MODULES = (P_PACKAGE, P_AGGREGATION, P_CONFIG, P_ERRORS, P_FACTS, P_MEASURES)
#: Plan A16.2: the one persistence module VS-02 adds.
QUERIES = "app/persistence/repositories/pipeline_queries.py"
QUERIES_MODULE = "app.persistence.repositories.pipeline_queries"

#: Plan A22.4's row for app/pipeline/*, exhaustive for first-party imports.
#: The repository module is facts.py's alone, and app.core.logging is
#: service.py's alone: no M2 module logs, so no M2 module is granted it.
PIPELINE_ALLOWED_FIRST_PARTY = ("app.pipeline", "app.fx", "app.relationships", "app.intelligence",
                                "app.normalization.config")
#: The standard-library modules the package imports today, closed as app/fx/'s are.
PIPELINE_ALLOWED_STDLIB = {"__future__", "collections", "dataclasses", "datetime", "decimal",
                           "enum", "functools", "hashlib", "pathlib", "typing"}
#: Who may import app.pipeline, and who may import its repository module.
PIPELINE_IMPORTERS = ("app/pipeline/",)
QUERIES_IMPORTERS = (P_FACTS,)

#: Plan A16.2: the model pipeline_queries.py names at M2, and what it reads of
#: it: the nine columns and the two it filters on. band_rows adds
#: RiskAssessment and Customer at M3.
QUERY_MODELS = {"Deal"}
QUERY_COLUMNS = {"source_id", "stage", "is_active", "amount", "currency", "probability",
                 "expected_close_date", "owner_source_id", "customer_source_id",
                 "source_system", "source_entity"}
#: The SQLAlchemy names each module that reaches the database may import.
FACTS_SQLALCHEMY = {("sqlalchemy.orm", "Session")}
QUERY_SQLALCHEMY = {("sqlalchemy", "select"), ("sqlalchemy.orm", "Session")}
#: What a select is built with in pipeline_queries.py. Nothing that locks,
#: hints or changes how a statement runs.
QUERY_CHAIN = {"where", "order_by"}
#: The reads facts.py hands the caller's session to (A21.2 item 3). band_rows joins at M3.
SESSION_RECEIVERS = {"deal_rows", "edges_of_type"}

#: Plan A21.2 item 2: every form a change can take. Session and connection
#: methods, statement methods, and schema methods, by attribute name.
WRITE_ATTRIBUTES = FORBIDDEN_WRITES | {
    "bulk_insert_mappings", "bulk_update_mappings", "exec_driver_sql", "with_for_update",
    "execution_options", "create_all", "drop_all", "create", "drop", "savepoint", "get_bind",
    "connection", "connect", "on_conflict_do_update", "on_conflict_do_nothing", "returning",
    "refresh", "expunge", "expire", "prefix_with"}
#: DML and DDL constructs, textual SQL, and what makes an engine or a session.
WRITE_NAMES = {"insert", "update", "delete", "merge", "text", "DDL", "MetaData", "Table", "Index",
               "CreateTable", "DropTable", "create_engine", "sessionmaker", "scoped_session",
               "inspect", "event"}
#: What executes a statement. Only pipeline_queries.py does (A21.2 item 3).
EXECUTION = {"execute", "scalars", "scalar", "exec_driver_sql", "query", "stream"}
#: What the pipeline neither catches nor translates: the frozen MoneyValue's
#: refusals (A10.1 item 4), a missing rate (A7.5 item 3) and its own data
#: error (A10.5 item 4), by name or by a base class.
PIPELINE_WIDE_HANDLERS = WIDE_HANDLERS | {"ContractViolationError", "FxRateMissingError", "FxError",
                                          "PipelineDataError", "PipelineError"}
#: Errors no M2 module of the package has any reason to name. M3's service
#: raises a missing rate of its own and joins this file's rows then.
UNNAMED_ERRORS = {"CurrencyMismatchError", "ContractViolationError", "IntelligenceError",
                  "FxRateMissingError", "FxError", "suppress"}
#: What sums outside MoneyValue.total, which states the currency it totals.
SUMMING = {"sum", "fsum", "reduce", "accumulate"}


def _first_party(tree: ast.Module, allowed: tuple[str, ...]) -> list[str]:
    found = [f"{line}: relative import {module}" for module, _, line in _imports(tree)
             if module.startswith(".")]
    found += [f"{line}: {module}" for module, _, line in _imports(tree)
              if _within(module, ("app",)) and not _within(module, allowed)]
    found += [f"{line}: {module}" for module, line in _imported_modules(tree)
              if _within(module, FX_EXCLUDED_FIRST_PARTY)]
    return found


def _pipeline_first_party_violations(tree: ast.Module) -> list[str]:
    """A22.4: app/pipeline/*'s row, for every module but facts.py. No repository, no logger."""
    return _first_party(tree, PIPELINE_ALLOWED_FIRST_PARTY)


def _facts_first_party_violations(tree: ast.Module) -> list[str]:
    """A22.4: facts.py alone also imports the repository module, by its own name."""
    return _first_party(tree, (*PIPELINE_ALLOWED_FIRST_PARTY, QUERIES_MODULE))


def _facts_third_party_violations(tree: ast.Module) -> list[str]:
    """A19 item 5: facts.py accepts a Session, so SQLAlchemy is within its reach and nothing new is."""
    return [f"{line}: {module}" for module, _, line in _imports(tree)
            if not module.startswith(".") and module.split(".")[0] not in (
                {"app", "sqlalchemy", *FX_ALLOWED_THIRD_PARTY} | sys.stdlib_module_names)]


def _facts_sqlalchemy_violations(tree: ast.Module) -> list[str]:
    """A21.2: of SQLAlchemy, facts.py imports the Session type and no construct of any kind."""
    return [f"{line}: {module}" + (f".{name}" if name else "")
            for module, name, line in _imports(tree)
            if module.split(".")[0] == "sqlalchemy" and (module, name) not in FACTS_SQLALCHEMY]


def _pipeline_stdlib_violations(tree: ast.Module) -> list[str]:
    """Beyond A22.4: the standard library is closed to what the package imports today."""
    return [f"{line}: {module}" for module, _, line in _imports(tree)
            if module.split(".")[0] in sys.stdlib_module_names - PIPELINE_ALLOWED_STDLIB]


def _facts_session_violations(tree: ast.Module) -> list[str]:
    """A21.2 item 3: facts.py is handed the caller's session and only passes it to the reads.
    It never calls a method on it, never keeps it, and never makes one of its own (A21.1 item 5)."""
    passed = {id(argument) for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id in SESSION_RECEIVERS for argument in node.args}
    found = [f"{node.lineno}: the session is used and not handed to a read"
             for node in ast.walk(tree)
             if isinstance(node, ast.Name) and node.id == "session" and id(node) not in passed]
    found += [f"{node.lineno}: {_dotted(node.func)}()" for node in ast.walk(tree)
              if isinstance(node, ast.Call) and _dotted(node.func) in {"Session", "sessionmaker"}]
    found += [f"{node.lineno}: {node.arg}" for node in ast.walk(tree)
              if isinstance(node, ast.arg) and node.arg in {"sessions", "engine", "connection"}]
    return found


def _facts_persistence_violations(tree: ast.Module) -> list[str]:
    """A21 and A21.1 item 4: of app.persistence, facts.py reaches the one repository module."""
    found = [f"{line}: {module}" for module, line in _imported_modules(tree)
             if _within(module, FORBIDDEN_TEXT_PACKAGES) and not _within(module, (QUERIES_MODULE,))]
    found += [f"{node.lineno}: {node.id}" for node in ast.walk(tree)
              if isinstance(node, ast.Name) and node.id in FORBIDDEN_TEXT_NAMES]
    return found


def _pipeline_handler_violations(tree: ast.Module) -> list[str]:
    """A10.1 item 4, A7.5 item 3, A10.5 item 4: no refusal is caught, translated or suppressed."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            found.append(f"{node.lineno}: a bare except")
            continue
        caught = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
        found += [f"{node.lineno}: catches {_dotted(one)}" for one in caught
                  if _dotted(one).rsplit(".", 1)[-1] in PIPELINE_WIDE_HANDLERS]
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if name in UNNAMED_ERRORS]
    found += [f"{node.lineno}: {_dotted(node)}" for node in ast.walk(tree)
              if isinstance(node, ast.Name | ast.Attribute)
              and _dotted(node).rsplit(".", 1)[-1] in UNNAMED_ERRORS]
    return found


def _pipeline_currency_violations(tree: ast.Module) -> list[str]:
    """SD-1 and OD-8: no currency code is written into the code. The one exception is the
    reserved bucket key ALL, and only where the reserved keys are stated."""
    docstrings, codes = _docstrings(tree), default_config().currency_codes
    reserved = {id(node) for statement in tree.body if isinstance(statement, ast.Assign)
                and [_dotted(target) for target in statement.targets] == ["RESERVED_KEYS"]
                for node in ast.walk(statement.value)}
    return [f"{node.lineno}: {node.value!r}" for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings and node.value in codes
            and not (node.value == "ALL" and id(node) in reserved)]


def _write_violations(tree: ast.Module) -> list[str]:
    """A21.2 items 1 and 2: nothing can change a row, a schema or a transaction, whether by a
    session method, a statement construct, textual SQL or an ORM call."""
    found = [f"{node.lineno}: .{node.attr}" for node in ast.walk(tree)
             if isinstance(node, ast.Attribute) and node.attr in WRITE_ATTRIBUTES]
    found += [f"{node.lineno}: {node.id}" for node in ast.walk(tree)
              if isinstance(node, ast.Name) and node.id in WRITE_NAMES]
    found += [f"{line}: {module}" + (f".{name}" if name else "")
              for module, name, line in _imports(tree)
              if name in WRITE_NAMES or module.split(".")[0] == "alembic"
              or _within(module, ("sqlalchemy.dialects", "sqlalchemy.schema", "sqlalchemy.sql",
                                  "sqlalchemy.engine", "sqlalchemy.event"))]
    return found


def _execution_violations(tree: ast.Module) -> list[str]:
    """A21.2 item 3: no module of app/pipeline/ executes a statement or builds one."""
    found = [f"{node.lineno}: .{node.attr}" for node in ast.walk(tree)
             if isinstance(node, ast.Attribute) and node.attr in EXECUTION]
    found += [f"{node.lineno}: {node.id}" for node in ast.walk(tree)
              if isinstance(node, ast.Name) and node.id == "select"]
    return found


def _summing_violations(tree: ast.Module) -> list[str]:
    """A7.5 item 5: amounts are summed with MoneyValue.total, which names its currency. The
    builtin sum starts from an integer that is money in no currency."""
    return [f"{node.lineno}: {_callee(node)}()" for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _callee(node) in SUMMING]


def _arithmetic_violations(tree: ast.Module) -> list[str]:
    """A9.4 item 3: outside measures.py nothing converts, rounds or totals. A figure is a sum
    of per-deal values taken through measures.total, and is computed no other way."""
    found = [f"{node.lineno}: {_callee(node)}()" for node in ast.walk(tree)
             if isinstance(node, ast.Call) and _callee(node) in {"convert", "quantize"}]
    found += [f"{node.lineno}: MoneyValue.total" for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and node.attr == "total"
              and _dotted(node.value) == "MoneyValue"]
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if name in {"convert", "arithmetic_context"}]
    return found


def _band_violations(tree: ast.Module) -> list[str]:
    """A12.4 item 4: measures.py holds every arithmetic rule, receives no band and names no
    band type, so no amount can be multiplied, discounted or weighted by one."""
    found = [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
             if name == "RiskBand"]
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else node.attr
                if isinstance(node, ast.Attribute) else node.arg
                if isinstance(node, ast.arg) else "")
        if "band" in name.lower():
            found.append(f"{node.lineno}: {name}")
    return found


def _query_import_violations(tree: ast.Module) -> list[str]:
    """A16.2 and A22.4: app.persistence.models and app.core.database, and no Layer 2 module.
    Nothing of app.core.database that opens an engine or a session."""
    found = [f"{line}: relative import {module}" for module, _, line in _imports(tree)
             if module.startswith(".")]
    found += [f"{line}: {module}" for module, _, line in _imports(tree)
              if _within(module, ("app",))
              and module not in ("app.persistence.models", "app.core.database")]
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if module == "app.core.database" and name != "Base"]
    found += [f"{line}: {module}" for module, _, line in _imports(tree)
              if not module.startswith(".") and module.split(".")[0] not in (
                  {"app", "sqlalchemy"} | sys.stdlib_module_names)]
    return found


def _query_model_violations(tree: ast.Module) -> list[str]:
    """A16.2: the model Deal alone, and of it the nine columns and the two filters. Not the
    deal's name, not its resolved customer FK, and no other table."""
    allowed = MODEL_NAMES - QUERY_MODELS
    found = [f"{node.lineno}: {node.id}" for node in ast.walk(tree)
             if isinstance(node, ast.Name) and node.id in allowed]
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if name in allowed or (module == "app.persistence.models" and name is None)]
    found += [f"{node.lineno}: {_dotted(node)}" for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and _dotted(node.value) in QUERY_MODELS
              and node.attr not in QUERY_COLUMNS]
    found += [f"{node.lineno}: {node.id} used whole" for node in ast.walk(tree)
              if isinstance(node, ast.Name) and node.id in QUERY_MODELS and id(node) not in {
                  id(attribute.value) for attribute in ast.walk(tree)
                  if isinstance(attribute, ast.Attribute)}]
    return found


def _chain(node: ast.AST) -> tuple[str, list[ast.Call]]:
    """A statement built as select(...).a(...).b(...): what it starts from, and each step."""
    steps = []
    while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        steps.append(node)
        node = node.func.value
    root = node.func.id if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) else ""
    return root, steps


def _in_c_collation(step: ast.Call) -> bool:
    return any(isinstance(node, ast.Call) and _callee(node) == "collate"
               and [getattr(argument, "value", None) for argument in node.args] == ["C"]
               for argument in step.args for node in ast.walk(argument))


def _query_statement_violations(tree: ast.Module) -> list[str]:
    """A16.2 and A21.2 item 3: the module holds select statements and nothing else. Each is
    executed on the caller's session, built with where and order_by alone, and ordered in the
    C collation. The session is used for nothing else, and none is made here."""
    found = [f"{line}: {module}" + (f".{name}" if name else "")
             for module, name, line in _imports(tree)
             if module.split(".")[0] == "sqlalchemy" and (module, name) not in QUERY_SQLALCHEMY]
    executing = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "execute" and _dotted(node.func.value) == "session"):
            executing[id(node.func.value)] = node
    found += [f"{node.lineno}: the session is used for more than executing a select"
              for node in ast.walk(tree)
              if isinstance(node, ast.Name) and node.id == "session" and id(node) not in executing]
    executed = set()
    for call in executing.values():
        root, steps = _chain(call.args[0]) if len(call.args) == 1 and not call.keywords else (
            "", [])
        if root != "select":
            found.append(f"{call.lineno}: session.execute() of something that is not a select")
            continue
        executed.add(id(steps[-1].func.value) if steps else id(call.args[0]))
        found += [f"{step.lineno}: .{step.func.attr}()" for step in steps
                  if step.func.attr not in QUERY_CHAIN]
        if not any(step.func.attr == "order_by" and _in_c_collation(step) for step in steps):
            found.append(f"{call.lineno}: a select that is not ordered in the C collation")
    found += [f"{node.lineno}: a select that is built and not executed here"
              for node in ast.walk(tree)
              if isinstance(node, ast.Call) and _dotted(node.func) == "select"
              and id(node) not in executed]
    found += [f"{node.lineno}: {_dotted(node.func)}()" for node in ast.walk(tree)
              if isinstance(node, ast.Call) and _dotted(node.func) in {
                  "Session", "sessionmaker", "create_engine", "scoped_session"}]
    return found


#: The rules every module of the package answers to.
_PIPELINE_SHARED: tuple[Rule, ...] = (
    _disguise_violations, _filesystem_violations, _context_violations, _state_violations,
    _clock_violations, _randomness_violations, _environment_violations, _float_violations,
    _yaml_violations, _import_time_violations, _serialiser_violations, _money_violations,
    _output_violations, _pipeline_stdlib_violations, _pipeline_handler_violations,
    _pipeline_currency_violations, _relationship_violations, _model_name_violations,
    _write_violations, _execution_violations, _summing_violations,
)
#: The modules that accept no session (A19 item 5): M1's session and document
#: rules apply to them as they do to app/fx/.
_PIPELINE_PURE: tuple[Rule, ...] = (
    *_PIPELINE_SHARED, _pipeline_first_party_violations, _third_party_violations,
    _session_violations, _document_violations,
)
PIPELINE_RULES: dict[str, tuple[Rule, ...]] = {
    P_PACKAGE: (*_PIPELINE_PURE, _arithmetic_violations),
    P_AGGREGATION: (*_PIPELINE_PURE, _arithmetic_violations),
    P_CONFIG: (*_PIPELINE_PURE, _arithmetic_violations),
    P_ERRORS: (*_PIPELINE_PURE, _arithmetic_violations),
    P_MEASURES: (*_PIPELINE_PURE, _band_violations),
    P_FACTS: (*_PIPELINE_SHARED, _arithmetic_violations, _facts_first_party_violations,
              _facts_third_party_violations, _facts_sqlalchemy_violations,
              _facts_session_violations, _facts_persistence_violations),
}
QUERY_RULES: tuple[Rule, ...] = (
    _disguise_violations, _filesystem_violations, _state_violations, _clock_violations,
    _randomness_violations, _environment_violations, _float_violations, _output_violations,
    _handler_violations, _write_violations, _query_import_violations, _query_model_violations,
    _query_statement_violations,
)


def _importers_of(sources: dict[str, str], packages: tuple[str, ...]) -> list[str]:
    """Every import of the named modules, once each, as `path:line`."""
    return sorted({f"{path}:{line}" for path, source in sources.items()
                   for module, name, line in _imports(ast.parse(source))
                   for absolute in _absolute(path, module, name)
                   if _within(absolute, packages)})


def _outside_pipeline_importers(sources: dict[str, str]) -> list[str]:
    """A21's isolation row: who imports app.pipeline from outside it."""
    return [entry for entry in _importers_of(sources, ("app.pipeline",))
            if not entry.startswith(PIPELINE_IMPORTERS)]


def _outside_query_importers(sources: dict[str, str]) -> list[str]:
    """A22.4: who imports the repository module, other than facts.py."""
    return [entry for entry in _importers_of(sources, (QUERIES_MODULE,))
            if entry.split(":")[0] not in QUERIES_IMPORTERS]


def _session_takers(sources: dict[str, str]) -> list[str]:
    """A19 item 5: every module of the package with a parameter that is a session."""
    return sorted(path for path in PIPELINE_MODULES
                  if any(isinstance(node, ast.arg) and node.arg in {"session", "sessions"}
                         for node in ast.walk(ast.parse(sources[path]))))


# ---------------------------------------------------------------------------
# Every pipeline rule fails on a forbidden edit to a copy of the real source
# ---------------------------------------------------------------------------

_MEASURES_IMPORT = "from app.pipeline.measures import DealValues, deal_values, total"
_OWNER_READ = "edges_of_type(EdgeType.DEAL_OWNED_BY, session, scope)"
_ORDER = '.order_by(Deal.source_id.collate("C"))'
_LAST_COLUMN = "            Deal.customer_source_id,\n        )"

#: (what was done, the rule that must object, the edited copy of a real module).
PIPELINE_FORBIDDEN_EDITS: list[tuple[str, Rule, str]] = [
    # A22.4: the allow-list of the modules that accept no session
    ("aggregation reads the repository",
     _pipeline_first_party_violations,
     _appended(P_AGGREGATION, f"from {QUERIES_MODULE} import deal_rows\n")),
    ("measures computes a signal",
     _pipeline_first_party_violations,
     _appended(P_MEASURES, "from app.intelligence.signals import compute_all_signals\n")),
    ("aggregation reads the band table",
     _pipeline_first_party_violations,
     _appended(P_AGGREGATION, "from app.intelligence.bands import assign_band\n")),
    ("aggregation takes the windows module by name",
     _pipeline_first_party_violations,
     _appended(P_AGGREGATION, "from app.intelligence import windows\n")),
    ("the rules loader logs through log_event",
     _pipeline_first_party_violations,
     _appended(P_CONFIG, "from app.core.logging import log_event\n")),
    ("aggregation reads the database settings",
     _pipeline_first_party_violations,
     _appended(P_AGGREGATION, "from app.core.config import get_settings\n")),
    ("an error is given an API code",
     _pipeline_first_party_violations, _appended(P_ERRORS, "from app.api.errors import ErrorCode\n")),
    ("the rules loader takes Layer 1 beyond its configuration",
     _pipeline_first_party_violations,
     _appended(P_CONFIG, "from app.normalization.contract import BUSINESS_FIELDS\n")),
    ("aggregation reads a document link",
     _pipeline_first_party_violations,
     _appended(P_AGGREGATION, "from app.evidence import documents_for\n")),
    ("a sibling is imported relatively",
     _pipeline_first_party_violations,
     _replaced(P_AGGREGATION, _MEASURES_IMPORT,
               "from .measures import DealValues, deal_values, total")),
    ("the package is imported by its top name",
     _pipeline_first_party_violations, _appended(P_PACKAGE, "import app\n")),
    # A22.4: facts.py's row
    ("facts reads the risk tables' repository",
     _facts_first_party_violations,
     _appended(P_FACTS, "from app.persistence.repositories.risk_queries import get_brief\n")),
    ("facts takes the repository module from its package",
     _facts_first_party_violations,
     _appended(P_FACTS, "from app.persistence.repositories import pipeline_queries\n")),
    ("facts computes a signal",
     _facts_first_party_violations,
     _appended(P_FACTS, "from app.intelligence.signals import compute_signals\n")),
    ("facts opens a session factory",
     _facts_first_party_violations,
     _appended(P_FACTS, "from app.core.database import get_session_factory\n")),
    ("facts logs a deal",
     _facts_first_party_violations, _appended(P_FACTS, "from app.core.logging import log_event\n")),
    # A22.4, A19 item 5, MD-21: third-party packages
    ("aggregation imports SQLAlchemy",
     _third_party_violations, _appended(P_AGGREGATION, "from sqlalchemy import select\n")),
    ("the measures hold their values in a data frame",
     _third_party_violations, _appended(P_MEASURES, "import pandas\n")),
    ("facts fetches a deal over HTTP",
     _facts_third_party_violations, _appended(P_FACTS, "import httpx\n")),
    ("facts asks a model about a deal",
     _facts_third_party_violations, _appended(P_FACTS, "import anthropic\n")),
    ("facts builds a statement of its own",
     _facts_sqlalchemy_violations, _appended(P_FACTS, "from sqlalchemy import select\n")),
    ("facts takes SQLAlchemy whole",
     _facts_sqlalchemy_violations, _appended(P_FACTS, "import sqlalchemy\n")),
    ("facts takes a second name from the ORM",
     _facts_sqlalchemy_violations, _appended(P_FACTS, "from sqlalchemy.orm import aliased\n")),
    # beyond A22.4: the standard library is closed
    ("aggregation starts a thread",
     _pipeline_stdlib_violations, _appended(P_AGGREGATION, "import threading\n")),
    ("the facts are kept in a database file",
     _pipeline_stdlib_violations, _appended(P_FACTS, "import sqlite3\n")),
    ("the rules loader reaches for the operating system",
     _pipeline_stdlib_violations, _appended(P_CONFIG, "import os\n")),
    ("a module is imported by name at run time",
     _pipeline_stdlib_violations, _appended(P_AGGREGATION, "import importlib\n")),
    ("the measures shell out",
     _pipeline_stdlib_violations, _appended(P_MEASURES, "import subprocess\n")),
    # A19 item 5: only facts.py accepts a session
    ("aggregation takes a session",
     _session_violations,
     _appended(P_AGGREGATION, "def stored(session, key):\n    return None\n")),
    ("the measures are typed against a Session",
     _session_violations,
     _appended(P_MEASURES, "def owned(unit: Session) -> None:\n    return None\n")),
    ("the rules loader commits",
     _session_violations, _appended(P_CONFIG, "def register(unit):\n    unit.commit()\n")),
    # A21.2 item 3: facts.py only passes the session on
    ("facts executes a statement itself",
     _facts_session_violations,
     _appended(P_FACTS, "def count(session):\n    return session.execute(None)\n")),
    ("facts commits the caller's transaction",
     _facts_session_violations, _appended(P_FACTS, "def done(session):\n    session.commit()\n")),
    ("facts loads a row through the ORM",
     _facts_session_violations,
     _appended(P_FACTS, "def one(session, key):\n    return session.get(object, key)\n")),
    ("facts hands the session to another reader",
     _facts_session_violations,
     _appended(P_FACTS, "def more(session, scope):\n    return other_rows(session, scope)\n")),
    ("facts keeps the session",
     _facts_session_violations,
     _appended(P_FACTS, "def keep(session):\n    held = session\n    return held\n")),
    ("facts makes a session of its own",
     _facts_session_violations, _appended(P_FACTS, "def own():\n    return Session()\n")),
    ("facts is handed an engine",
     _facts_session_violations, _appended(P_FACTS, "def bound(engine):\n    return None\n")),
    # A21: no document text, no ticket attribute
    ("aggregation reads a document",
     _document_violations, _appended(P_AGGREGATION, "from app.evidence import citable_text\n")),
    ("aggregation names the Document model",
     _document_violations, _appended(P_AGGREGATION, "model = Document\n")),
    ("the measures read the decision layer",
     _document_violations, _appended(P_MEASURES, "from app.decisions import reconcile\n")),
    ("aggregation reads an analyst",
     _document_violations, _appended(P_AGGREGATION, "from app import analysts\n")),
    ("facts imports the canonical models",
     _facts_persistence_violations,
     _appended(P_FACTS, "from app.persistence.models import Deal\n")),
    ("facts reads the citation repository",
     _facts_persistence_violations,
     _appended(P_FACTS, "from app.persistence.repositories.citation_reads import "
                        "document_texts\n")),
    ("facts reads a document through the evidence package",
     _facts_persistence_violations, _appended(P_FACTS, "from app.evidence import citable_text\n")),
    ("facts names a ticket",
     _facts_persistence_violations, _appended(P_FACTS, "ticket = SupportTicket\n")),
    # A21.1 item 4: no ORM model, however it is reached
    ("facts takes the ticket model from a module it may import",
     _model_name_violations,
     _appended(P_FACTS, "from app.intelligence.scope import SupportTicket\n")),
    ("facts names the model registry",
     _model_name_violations,
     _appended(P_FACTS, "import app.intelligence.scope\n"
                        "models = app.intelligence.scope.ENTITY_MODELS\n")),
    ("aggregation names the Deal model",
     _model_name_violations, _appended(P_AGGREGATION, "row_type = Deal\n")),
    ("aggregation names the assessment model",
     _model_name_violations, _appended(P_AGGREGATION, "bands = RiskAssessment\n")),
    # A21.1 item 2: the relationship model
    ("facts reads the policy documents",
     _relationship_violations,
     _appended(P_FACTS, "from app.relationships import policy_documents\n")),
    ("facts names another edge type",
     _relationship_violations,
     _appended(P_FACTS, "TICKETS = EdgeType.CUSTOMER_HAS_TICKET\n")),
    ("facts walks to an owner's manager",
     _relationship_violations,
     _replaced(P_FACTS, _OWNER_READ,
               "edges_of_type(EdgeType.EMPLOYEE_REPORTS_TO, session, scope)")),
    ("facts iterates the edge types",
     _relationship_violations,
     _appended(P_FACTS, "EVERY = [edge_type for edge_type in EdgeType]\n")),
    ("facts calls EdgeType with a value",
     _relationship_violations, _appended(P_FACTS, "OWNED = EdgeType('customer_has_ticket')\n")),
    ("facts indexes EdgeType by name",
     _relationship_violations, _appended(P_FACTS, "OWNED = EdgeType['CUSTOMER_HAS_TICKET']\n")),
    ("facts reaches a member through getattr",
     _relationship_violations,
     _appended(P_FACTS, "TICKETS = getattr(EdgeType, 'CUSTOMER_HAS_TICKET')\n")),
    ("facts lists every edge type",
     _relationship_violations, _appended(P_FACTS, "from app.relationships import all_edge_types\n")),
    ("facts reads a customer's neighbourhood from the submodule",
     _relationship_violations,
     _appended(P_FACTS, "from app.relationships.queries import neighbourhood\n")),
    ("facts takes the relationship package whole",
     _relationship_violations, _appended(P_FACTS, "import app.relationships\n")),
    ("facts takes the edge specifications",
     _relationship_violations, _appended(P_FACTS, "from app.relationships import EDGE_SPECS\n")),
    ("facts reads edges of a type it is handed",
     _relationship_violations,
     _appended(P_FACTS, "def any_edges(edge_type, session, scope):\n"
                        "    return edges_of_type(edge_type, session, scope)\n")),
    ("facts builds edges through the source-key builder",
     _relationship_violations,
     _appended(P_FACTS, "from app.relationships.edges import source_key_edges\n")),
    ("aggregation reads an escalation path",
     _relationship_violations,
     _appended(P_AGGREGATION, "from app.relationships import escalation_path\n")),
    # A10.1 item 4, A7.5 item 3, A10.5 item 4: nothing is caught or translated
    ("aggregation skips a deal whose currency has no rate",
     _pipeline_handler_violations,
     _appended(P_AGGREGATION, "try:\n    pass\nexcept FxRateMissingError:\n    pass\n")),
    ("aggregation translates the frozen type's refusal",
     _pipeline_handler_violations,
     _appended(P_AGGREGATION, "try:\n    pass\nexcept ContractViolationError as exc:\n"
                              "    raise PipelineDataError('x') from exc\n")),
    ("aggregation swallows its own data error",
     _pipeline_handler_violations,
     _appended(P_AGGREGATION, "try:\n    pass\nexcept PipelineDataError:\n    pass\n")),
    ("the measures catch everything",
     _pipeline_handler_violations,
     _appended(P_MEASURES, "try:\n    pass\nexcept Exception:\n    pass\n")),
    ("the rules loader has a bare except",
     _pipeline_handler_violations,
     _replaced(P_CONFIG, "except (yaml.YAMLError, ValueError) as exc:", "except:")),
    ("a missing rate is suppressed without a handler",
     _pipeline_handler_violations,
     _appended(P_AGGREGATION, "from contextlib import suppress\n")),
    ("the missing-rate error is imported to be handled",
     _pipeline_handler_violations,
     _appended(P_AGGREGATION, "from app.fx.errors import FxRateMissingError\n")),
    ("a mixed-currency sum is caught",
     _pipeline_handler_violations,
     _appended(P_MEASURES, "try:\n    pass\nexcept (KeyError, CurrencyMismatchError):\n"
                           "    pass\n")),
    # SD-1, OD-8: no currency in code but the reserved key ALL, where it is reserved
    ("the base currency is written into the code",
     _pipeline_currency_violations, _appended(P_AGGREGATION, 'BASE_CURRENCY = "INR"\n')),
    ("a fallback rate is written into the code",
     _pipeline_currency_violations, _appended(P_MEASURES, 'FALLBACK = {"USD": Decimal("85")}\n')),
    ("a deal without a currency is given one",
     _pipeline_currency_violations, _appended(P_FACTS, 'DEFAULT_CURRENCY = "EUR"\n')),
    ("the currency ALL is singled out to be skipped",
     _pipeline_currency_violations, _appended(P_AGGREGATION, 'SKIPPED_CURRENCY = "ALL"\n')),
    # A21.2 items 1 and 2: every form of write
    ("facts inserts a row",
     _write_violations, _appended(P_FACTS, "from sqlalchemy import insert\n")),
    ("aggregation stores a bucket",
     _write_violations, _appended(P_AGGREGATION, "def store(unit, row):\n    unit.add(row)\n")),
    ("aggregation bulk-inserts its buckets",
     _write_violations,
     _appended(P_AGGREGATION, "def store(unit, rows):\n"
                              "    unit.bulk_insert_mappings(None, rows)\n")),
    ("facts locks the deals it reads",
     _write_violations,
     _appended(P_FACTS, "def locked(statement):\n    return statement.with_for_update()\n")),
    ("facts runs textual SQL",
     _write_violations, _appended(P_FACTS, "from sqlalchemy import text\n")),
    ("facts creates an engine of its own",
     _write_violations, _appended(P_FACTS, "from sqlalchemy import create_engine\n")),
    ("aggregation is pointed at a database by a session factory",
     _write_violations,
     _appended(P_AGGREGATION, "def bound(url):\n    return sessionmaker(bind=url)\n")),
    ("facts opens a transaction",
     _write_violations, _appended(P_FACTS, "def opened(unit):\n    return unit.begin()\n")),
    ("the rules are kept in a table",
     _write_violations, _appended(P_CONFIG, "from sqlalchemy import MetaData\n")),
    ("the package creates its tables",
     _write_violations,
     _appended(P_PACKAGE, "def install(metadata, bind):\n    metadata.create_all(bind)\n")),
    ("facts changes the isolation level",
     _write_violations,
     _appended(P_FACTS, "def relaxed(unit):\n"
                        "    return unit.connection().execution_options(isolation_level='X')\n")),
    ("facts upserts through the dialect",
     _write_violations,
     _appended(P_FACTS, "from sqlalchemy.dialects.postgresql import insert\n")),
    ("the repository locks the rows it selects",
     _write_violations, _replaced(QUERIES, _ORDER, _ORDER + ".with_for_update()")),
    ("the repository closes the caller's session",
     _write_violations, _appended(QUERIES, "def finished(unit):\n    unit.close()\n")),
    ("the repository migrates",
     _write_violations, _appended(QUERIES, "from alembic import op\n")),
    # A21.2 item 3: only the repository executes
    ("aggregation executes a statement",
     _execution_violations,
     _appended(P_AGGREGATION, "def run(unit, statement):\n    return unit.execute(statement)\n")),
    ("facts reads scalars itself",
     _execution_violations,
     _appended(P_FACTS, "def ids(unit, statement):\n    return unit.scalars(statement)\n")),
    ("the measures build a select",
     _execution_violations, _appended(P_MEASURES, "statement = select\n")),
    # A7.5 item 5, A9.4 item 3: sums and arithmetic
    ("aggregation adds amounts with the builtin sum",
     _summing_violations,
     _appended(P_AGGREGATION, "def add_up(amounts):\n    return sum(amounts)\n")),
    ("the measures fold amounts together",
     _summing_violations,
     _appended(P_MEASURES, "def add_up(amounts):\n    return reduce(None, amounts)\n")),
    ("aggregation converts a bucket's native total",
     _arithmetic_violations,
     _appended(P_AGGREGATION, "def bucket_base(value, rate_set):\n"
                              "    return convert(value, rate_set)\n")),
    ("aggregation imports convert",
     _arithmetic_violations, _appended(P_AGGREGATION, "from app.fx.convert import convert\n")),
    ("aggregation rounds a bucket as a whole",
     _arithmetic_violations,
     _appended(P_AGGREGATION, "def rounded(value, quantum, mode):\n"
                              "    return value.quantize(quantum, rounding=mode)\n")),
    ("aggregation totals in the caller's context",
     _arithmetic_violations,
     _appended(P_AGGREGATION, "def raw_total(currency, values):\n"
                              "    return MoneyValue.total(currency, values)\n")),
    ("facts weighs a deal while classifying it",
     _arithmetic_violations,
     _appended(P_FACTS, "from app.fx.convert import arithmetic_context\n")),
    # A12.4 item 4: no band reaches the arithmetic
    ("the measures import the band type",
     _band_violations, _appended(P_MEASURES, "from app.intelligence import RiskBand\n")),
    ("a weight is discounted by a band",
     _band_violations,
     _appended(P_MEASURES, "def discounted(amount, band):\n    return amount\n")),
    ("the measures read a deal's risk band",
     _band_violations, _appended(P_MEASURES, "def of(deal):\n    return deal.risk_band\n")),
    # the rules the two packages share, over the pipeline's own source
    ("a sibling's name is renamed on import",
     _disguise_violations,
     _appended(P_AGGREGATION, "from app.pipeline.facts import valued_deal as usable\n")),
    ("the partitions are written to a file",
     _filesystem_violations,
     _appended(P_AGGREGATION, "def store(path, text):\n    path.write_text(text)\n")),
    ("a weight is quantized in whatever rounding the context has",
     _context_violations,
     _replaced(P_MEASURES, "            WEIGHT_QUANTUM, rounding=ROUNDING_MODE)",
               "            WEIGHT_QUANTUM)")),
    ("a total is taken in a copy of the caller's context",
     _context_violations,
     _replaced(P_MEASURES, "    with localcontext(arithmetic_context()):\n"
                           "        return MoneyValue.total(currency, values)",
               "    with localcontext():\n"
               "        return MoneyValue.total(currency, values)")),
    ("the digest's context inherits its exponent limits",
     _context_violations,
     _replaced(P_CONFIG, "Context(prec=digits, Emin=MIN_EMIN, Emax=MAX_EMAX)",
               "Context(prec=digits)")),
    ("the last partitions are kept in a module global",
     _state_violations, _appended(P_AGGREGATION, "_LAST = {}\n")),
    ("a deal with no close date is placed by today's date",
     _clock_violations,
     _replaced(P_AGGREGATION, "    if expected < as_of:", "    if expected < date.today():")),
    ("a fact is given a generated id",
     _randomness_violations, _appended(P_FACTS, "import uuid\n")),
    ("an environment variable selects the rules file",
     _environment_violations,
     _appended(P_CONFIG, "import os\nDEFAULT_PIPELINE_RULES_PATH = Path(os.environ['RULES'])\n")),
    ("the weight quantum is built from a float",
     _float_violations, _replaced(P_MEASURES, 'WEIGHT_QUANTUM = Decimal("0.01")',
                                  "WEIGHT_QUANTUM = Decimal(0.01)")),
    ("a probability is taken through float()",
     _float_violations,
     _appended(P_MEASURES, "def fraction(probability):\n    return float(probability) / 100\n")),
    ("the rules file is loaded with the unsafe loader",
     _yaml_violations, _replaced(P_CONFIG, "yaml.safe_load(", "yaml.load(")),
    ("the rules are loaded when the module is imported",
     _import_time_violations, _appended(P_CONFIG, "CURRENT = default_pipeline_rules()\n")),
    ("the package loads the rules for its importers",
     _import_time_violations, _appended(P_PACKAGE, "CURRENT = default_pipeline_rules()\n")),
    ("the facts are read as a default argument",
     _import_time_violations,
     _appended(P_FACTS, "def later(rows=deal_rows(None, 'csv_demo')):\n    return rows\n")),
    ("the methodology is serialised with json itself",
     _serialiser_violations, _appended(P_CONFIG, "import json\n")),
    ("canonical_json is copied into the package",
     _serialiser_violations,
     _appended(P_CONFIG, "def canonical_json(payload):\n    return repr(payload)\n")),
    ("a total is taught to convert",
     _money_violations,
     _appended(P_MEASURES, "MoneyValue.__add__ = lambda left, right: left\n")),
    ("aggregation prints a bucket",
     _output_violations, _appended(P_AGGREGATION, "print(RESERVED_KEYS)\n")),
    ("a data error is logged through log_event",
     _output_violations, _appended(P_ERRORS, "log_event(None, 40, 'vs02.data_error')\n")),
    # A16.2, A22.4: the repository module
    ("the repository names a domain type",
     _query_import_violations, _appended(QUERIES, "from app.intelligence import Scope\n")),
    ("the repository builds a deal fact",
     _query_import_violations, _appended(QUERIES, "from app.pipeline.facts import DealFact\n")),
    ("the repository converts an amount",
     _query_import_violations, _appended(QUERIES, "from app.fx import convert\n")),
    ("the repository reads through the model registry's module",
     _query_import_violations,
     _appended(QUERIES, "from app.persistence.repositories.canonical import ENTITY_MODELS\n")),
    ("the repository opens a session factory",
     _query_import_violations,
     _appended(QUERIES, "from app.core.database import get_session_factory\n")),
    ("the repository reads an edge",
     _query_import_violations, _appended(QUERIES, "from app.relationships import edges_of_type\n")),
    ("the repository reads the settings",
     _query_import_violations, _appended(QUERIES, "from app.core.config import get_settings\n")),
    ("the repository fetches over HTTP",
     _query_import_violations, _appended(QUERIES, "import httpx\n")),
    ("the repository reads a document",
     _query_model_violations,
     _replaced(QUERIES, "from app.persistence.models import Deal",
               "from app.persistence.models import Deal, Document")),
    ("the repository reads a ticket",
     _query_model_violations, _appended(QUERIES, "tickets = SupportTicket\n")),
    ("the repository reads the assessments before M3",
     _query_model_violations,
     _appended(QUERIES, "from app.persistence.models import RiskAssessment\n")),
    ("the repository reads the deal's name",
     _query_model_violations,
     _replaced(QUERIES, _LAST_COLUMN,
               "            Deal.customer_source_id,\n            Deal.name,\n        )")),
    ("the repository reads the resolved customer key",
     _query_model_violations,
     _replaced(QUERIES, _LAST_COLUMN,
               "            Deal.customer_source_id,\n            Deal.customer_id,\n        )")),
    ("the repository selects the whole deal",
     _query_model_violations, _appended(QUERIES, "def whole(session):\n    return Deal\n")),
    ("the repository takes the models package whole",
     _query_model_violations, _appended(QUERIES, "import app.persistence.models\n")),
    ("the repository leaves the order to the database's collation",
     _query_statement_violations, _replaced(QUERIES, _ORDER, ".order_by(Deal.source_id)")),
    ("the repository leaves the rows unordered",
     _query_statement_violations, _replaced(QUERIES, _ORDER, "")),
    ("the repository locks what it selects",
     _query_statement_violations, _replaced(QUERIES, _ORDER, _ORDER + ".with_for_update()")),
    ("the repository runs textual SQL",
     _query_statement_violations, _appended(QUERIES, "from sqlalchemy import text\n")),
    ("the repository executes an insert",
     _query_statement_violations,
     _appended(QUERIES, "from sqlalchemy import insert\n\n\ndef keep(session, row):\n"
                        "    session.execute(insert(Deal).values(row))\n")),
    ("the repository executes whatever it is handed",
     _query_statement_violations,
     _appended(QUERIES, "def run(session, statement):\n    return session.execute(statement)\n")),
    ("the repository commits",
     _query_statement_violations, _appended(QUERIES, "def done(session):\n    session.commit()\n")),
    ("the repository makes a session of its own",
     _query_statement_violations, _appended(QUERIES, "def own():\n    return Session()\n")),
    ("the repository creates an engine",
     _query_statement_violations, _appended(QUERIES, "from sqlalchemy import create_engine\n")),
    ("the repository hands a statement back unexecuted",
     _query_statement_violations,
     _appended(QUERIES, "def statement():\n    return select(Deal.source_id)\n")),
    ("the repository aggregates in SQL",
     _query_statement_violations, _appended(QUERIES, "from sqlalchemy import func\n")),
    ("the repository logs the rows it read",
     _output_violations, _appended(QUERIES, "import logging\n")),
    ("the repository catches everything",
     _handler_violations,
     _appended(QUERIES, "try:\n    pass\nexcept Exception:\n    pass\n")),
    ("the repository stamps its rows with the time",
     _clock_violations, _appended(QUERIES, "from datetime import datetime\nread_at = datetime.now()\n")),
]

#: A21's isolation row for app.pipeline: an edited copy of a real file outside the package.
FORBIDDEN_PIPELINE_IMPORTERS = [
    ("app/fx/convert.py", "from app.pipeline.measures import weigh\n"),
    ("app/intelligence/money.py", "from app.pipeline import build_partitions\n"),
    ("app/intelligence/money.py", "from .. import pipeline\n"),
    ("app/relationships/edges.py", "import app.pipeline.facts\n"),
    (QUERIES, "from app.pipeline.facts import DealFact\n"),
    ("app/persistence/repositories/canonical.py", "from app import pipeline\n"),
    ("app/main.py", "from app.pipeline import default_pipeline_rules\n"),
    ("app/api/v1/risk.py", "from app.pipeline.config import default_pipeline_rules\n"),
    ("scripts/vs01_acceptance.py", "from app.pipeline import read_deal_facts\n"),
    ("migrations/env.py", "import app.pipeline\n"),
]
#: A22.4: the repository module is facts.py's alone.
FORBIDDEN_QUERY_IMPORTERS = [
    (P_AGGREGATION, f"from {QUERIES_MODULE} import deal_rows\n"),
    (P_MEASURES, f"import {QUERIES_MODULE}\n"),
    (P_CONFIG, "from app.persistence.repositories import pipeline_queries\n"),
    ("app/fx/rates.py", f"from {QUERIES_MODULE} import deal_rows\n"),
    ("app/api/v1/risk.py", f"from {QUERIES_MODULE} import deal_rows\n"),
    ("app/intelligence/signals.py", "from ..persistence.repositories.pipeline_queries import "
                                    "deal_rows\n"),
]
#: A19 item 5: a module of the package, other than facts.py, given a session.
FORBIDDEN_SESSION_TAKERS = [
    (P_AGGREGATION, "def stored(session):\n    return None\n"),
    (P_MEASURES, "def stored(amount, *, session=None):\n    return None\n"),
    (P_CONFIG, "def stored(sessions):\n    return None\n"),
]

#: The closure rules, over the real tree with one forbidden edit that only
#: the pipeline's half of the closure reaches (OD-5).
PIPELINE_FORBIDDEN_TREES: list[tuple[str, Callable[[dict[str, str]], list[str]],
                                     dict[str, str]]] = [
    ("the facts reader opens a socket",
     _outbound_violations, _with(app__pipeline__facts=_appended(P_FACTS, "import socket\n"))),
    ("the repository fetches over HTTP",
     _outbound_violations,
     _with(app__persistence__repositories__pipeline_queries=_appended(QUERIES, "import httpx\n"))),
    ("the relationship model, which only the pipeline reaches, turns outbound",
     _outbound_violations,
     _with(app__relationships__edges=APP_SOURCES["app.relationships.edges"]
           + "\nimport smtplib\n")),
    ("aggregation reaches a connector",
     _executor_violations,
     _with(app__pipeline__aggregation=_appended(
         P_AGGREGATION, "from app.connectors.registry import build_connector\n"))),
    ("the rules loader reaches the API",
     _executor_violations,
     _with(app__pipeline__config=_appended(P_CONFIG, "from app.api.errors import ErrorCode\n"))),
    ("the repository reaches ingestion",
     _executor_violations,
     _with(app__persistence__repositories__pipeline_queries=_appended(
         QUERIES, "from app.ingestion.orchestrator import run_ingestion\n"))),
    ("the relationship model, which only the pipeline reaches, reaches the outbound client",
     _executor_violations,
     _with(app__relationships__queries=APP_SOURCES["app.relationships.queries"]
           + "\nfrom app.core.security import build_client\n")),
]


@pytest.mark.parametrize(("label", "rule", "source"), PIPELINE_FORBIDDEN_EDITS,
                         ids=[label for label, _, _ in PIPELINE_FORBIDDEN_EDITS])
def test_every_pipeline_rule_catches_a_forbidden_edit_to_a_copy_of_the_real_source(
        label, rule, source):
    assert rule(ast.parse(source)), label


@pytest.mark.parametrize(("label", "rule", "sources"), PIPELINE_FORBIDDEN_TREES,
                         ids=[label for label, _, _ in PIPELINE_FORBIDDEN_TREES])
def test_every_closure_rule_catches_a_forbidden_edit_only_the_pipeline_reaches(
        label, rule, sources):
    assert rule(sources), label


def test_the_closure_edits_through_the_relationship_model_are_out_of_app_fxs_reach():
    """The control for OD-5: seeded from app.fx alone, the closure never met those modules."""
    from_fx: set[str] = set()
    pending = sorted(name for name in APP_SOURCES if _within(name, ("app.fx",)))
    while pending:
        name = pending.pop()
        if name not in from_fx:
            from_fx.add(name)
            if name in APP_SOURCES:
                pending += sorted(_edges(name, APP_SOURCES) - from_fx)

    assert "app.fx.convert" in from_fx
    assert not {"app.relationships.edges", "app.relationships.queries", QUERIES_MODULE,
                "app.pipeline.facts"} & from_fx
    assert {"app.relationships.edges", "app.relationships.queries", QUERIES_MODULE,
            "app.pipeline.facts"} <= _fx_closure(APP_SOURCES)


@pytest.mark.parametrize(("path", "addition"), FORBIDDEN_PIPELINE_IMPORTERS,
                         ids=[f"{path}: {addition.strip()}"
                              for path, addition in FORBIDDEN_PIPELINE_IMPORTERS])
def test_the_importer_scan_catches_an_import_of_the_pipeline_from_outside_it(path, addition):
    edited = {**CODE_SOURCES, path: CODE_SOURCES[path] + "\n" + addition}

    assert [entry.split(":")[0] for entry in _outside_pipeline_importers(edited)] == [path]


@pytest.mark.parametrize(("path", "addition"), FORBIDDEN_QUERY_IMPORTERS,
                         ids=[f"{path}: {addition.strip()}"
                              for path, addition in FORBIDDEN_QUERY_IMPORTERS])
def test_the_importer_scan_catches_a_second_reader_of_the_repository(path, addition):
    edited = {**CODE_SOURCES, path: CODE_SOURCES[path] + "\n" + addition}

    assert [entry.split(":")[0] for entry in _outside_query_importers(edited)] == [path]


@pytest.mark.parametrize(("path", "addition"), FORBIDDEN_SESSION_TAKERS,
                         ids=[path for path, _ in FORBIDDEN_SESSION_TAKERS])
def test_the_session_scan_catches_a_second_module_that_accepts_one(path, addition):
    edited = {**CODE_SOURCES, path: CODE_SOURCES[path] + "\n" + addition}

    assert _session_takers(edited) == sorted([P_FACTS, path])


def test_the_pipeline_scans_read_code_and_not_the_docstrings_explaining_it():
    """These modules say at length what they do not do; saying it is not doing it."""
    prose = ast.parse('"""Never session.commit(), insert(Deal) or EdgeType.CUSTOMER_HAS_TICKET; '
                      'never INR; no RiskBand, no sum(), no convert() and no text()."""\nx = 1\n')
    rules = {rule for rules in PIPELINE_RULES.values() for rule in rules} | set(QUERY_RULES)

    assert sorted(rule.__name__ for rule in rules if rule(prose)) == []
    assert _pipeline_currency_violations(ast.parse('RESERVED_KEYS = frozenset({"ALL"})\n')) == []
    assert _pipeline_currency_violations(ast.parse('OTHER_KEYS = frozenset({"ALL"})\n')) == [
        "1: 'ALL'"]
    assert _relationship_violations(ast.parse(
        "edges_of_type(EdgeType.CUSTOMER_HAS_DEAL, session, scope)\n")) == []
    assert _facts_session_violations(ast.parse("deal_rows(session, 'x')\n")) == []
    assert _facts_session_violations(ast.parse("deal_rows(unit=session)\n")) != []


# ---------------------------------------------------------------------------
# Where app/pipeline/ exists (plan A22.2, B1, B6)
# ---------------------------------------------------------------------------


def test_the_pipeline_package_holds_exactly_the_six_modules_of_m2():
    """A scan that silently matches nothing proves nothing, and a seventh module is a decision.
    view.py and service.py are VS02-M3's: this list gains them then, and loses nothing."""
    found = sorted(path.relative_to(REPO).as_posix() for path in PIPELINE_DIR.rglob("*.py"))

    assert found == sorted(PIPELINE_MODULES) == sorted(PIPELINE_RULES)
    assert (REPO / QUERIES).is_file()
    for relative in (*PIPELINE_MODULES, QUERIES):
        assert [node for node in ast.parse(_source(relative)).body
                if not isinstance(node, ast.Expr)], f"{relative} holds no code"


def test_vs02_added_one_repository_module_and_no_model_or_migration():
    """SD-2 and A16.2: no table, no model and no migration. risk_queries.py is not edited."""
    repositories = sorted(path.name for path in (APP_DIR / "persistence" / "repositories").glob(
        "*.py"))

    assert "pipeline_queries.py" in repositories and "risk_queries.py" in repositories
    assert not [name for name in repositories if "fx" in name or "rate" in name]
    assert not [path for path in (APP_DIR / "persistence" / "models").glob("*.py")
                if "fx" in path.name or "pipeline" in path.name or "rate" in path.name]
    assert not [path for path in (REPO / "migrations").rglob("*.py")
                if "fx" in path.name or "pipeline" in path.name]


# ---------------------------------------------------------------------------
# The rules over the real files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("relative", "rule"),
                         [(relative, rule) for relative, rules in PIPELINE_RULES.items()
                          for rule in rules],
                         ids=[f"{relative.rsplit('/', 1)[-1]}-{rule.__name__.strip('_')}"
                              for relative, rules in PIPELINE_RULES.items() for rule in rules])
def test_no_pipeline_module_breaks_a_rule(relative, rule):
    assert rule(ast.parse(_source(relative))) == []


@pytest.mark.parametrize("rule", QUERY_RULES, ids=lambda rule: rule.__name__.strip("_"))
def test_the_repository_module_breaks_no_rule(rule):
    assert rule(ast.parse(_source(QUERIES))) == []


def test_the_pipeline_imports_what_its_row_grants_and_no_package_beyond_it():
    """The allow-lists are not vacuous: the package does read M1, FX, the relationship model,
    the D1 vocabulary and, in facts.py alone, the repository."""
    imported = {relative: {module for module, _, _ in _imports(ast.parse(_source(relative)))}
                for relative in PIPELINE_MODULES}
    every = set().union(*imported.values())

    assert {"app.fx.convert", "app.fx.rates", "app.intelligence", "app.intelligence.contract",
            "app.intelligence.money", "app.normalization.config", "app.relationships",
            "app.pipeline.aggregation", "app.pipeline.config", "app.pipeline.errors",
            "app.pipeline.facts", "app.pipeline.measures", QUERIES_MODULE} == {
        module for module in every if module.split(".")[0] == "app"}
    assert [relative for relative, modules in imported.items() if QUERIES_MODULE in modules] == [
        P_FACTS]
    assert {module.split(".")[0] for module in every
            if module.split(".")[0] not in {"app"} | sys.stdlib_module_names} == {
        "yaml", "sqlalchemy"}
    assert [relative for relative, modules in imported.items()
            if any(module.split(".")[0] == "sqlalchemy" for module in modules)] == [P_FACTS]
    assert [relative for relative, modules in imported.items() if "yaml" in modules] == [P_CONFIG]
    assert {module.split(".")[0] for module in every
            if module.split(".")[0] in sys.stdlib_module_names} == PIPELINE_ALLOWED_STDLIB


def test_the_repository_imports_one_model_and_two_sqlalchemy_names():
    imported = {(module, name) for module, name, _ in _imports(ast.parse(_source(QUERIES)))}

    assert {pair for pair in imported if pair[0].split(".")[0] in {"app", "sqlalchemy"}} == {
        ("app.persistence.models", "Deal"), *QUERY_SQLALCHEMY}


def test_the_facts_reader_names_only_what_a21_1_allows_of_the_relationship_model():
    """Not vacuous: facts.py does call edges_of_type, twice, with the two edge types."""
    tree = ast.parse(_source(P_FACTS))
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and _callee(node) == "edges_of_type"]
    named = {name for module, name, _ in _imports(tree) if module == "app.relationships"}

    assert sorted(call.args[0].attr for call in calls) == sorted(EDGE_TYPES)
    assert named == {"edges_of_type", "EdgeType", "EdgeBasis"} <= RELATIONSHIP_NAMES
    assert sorted(node.func.id for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                  and node.func.id in SESSION_RECEIVERS) == [
        "deal_rows", "edges_of_type", "edges_of_type"]


def test_the_edge_types_and_names_this_file_allows_exist_in_the_frozen_model():
    """The rule is written against names; this pins them to the frozen package."""
    import app.relationships as relationships

    assert EDGE_TYPES <= {member.name for member in relationships.EdgeType}
    assert RELATIONSHIP_NAMES <= set(relationships.__all__)
    assert (FORBIDDEN_RELATIONSHIP_NAMES - {"Neighbourhood", "EscalationPath", "order_edges",
                                            "EdgeSpec", "ISOLATED_ENTITIES"}) <= {
        *relationships.__all__, *(name for name in vars(relationships))}
    assert not RELATIONSHIP_NAMES & FORBIDDEN_RELATIONSHIP_NAMES


def test_the_model_names_this_file_refuses_are_every_model_there_is():
    import app.persistence.models as models

    assert MODEL_NAMES == {*models.__all__, "ENTITY_MODELS", "Base"}
    assert QUERY_MODELS < MODEL_NAMES
    assert QUERY_COLUMNS <= set(models.Deal.__table__.columns.keys())
    assert "name" in models.Deal.__table__.columns.keys() and "name" not in QUERY_COLUMNS


def test_each_loader_reads_one_file_one_way():
    """One read, as UTF-8, through yaml.safe_load, behind one cache: no locale and no second path."""
    source = _source(P_CONFIG)

    assert source.count('read_text(encoding="utf-8")') == source.count("read_text(") == 1
    assert source.count("yaml.safe_load(") == 1
    assert source.count("lru_cache") == source.count("__file__") == 1
    for relative in PIPELINE_MODULES:
        if relative != P_CONFIG:
            assert "yaml" not in {module for module, _, _ in _imports(ast.parse(
                _source(relative)))}, relative


# ---------------------------------------------------------------------------
# Sessions and isolation (plan A19 item 5, A21, A22.4)
# ---------------------------------------------------------------------------


def test_facts_is_the_only_module_of_the_package_that_accepts_a_session():
    """A19 item 5: at M2 exactly one. service.py is the second, at M3."""
    assert _session_takers(CODE_SOURCES) == [P_FACTS]


def test_only_the_pipeline_package_imports_app_pipeline():
    importers = {entry.split(":")[0] for entry in _importers_of(CODE_SOURCES, ("app.pipeline",))}

    assert importers, "the scan found no importer, so it would pass if the package were unused"
    assert importers <= set(PIPELINE_MODULES)
    assert _outside_pipeline_importers(CODE_SOURCES) == []
    assert {"app/main.py", "app/fx/convert.py", "app/api/v1/risk.py", QUERIES,
            "scripts/vs01_acceptance.py", "migrations/env.py"} <= CODE_SOURCES.keys(), (
        "the scan must read what it clears")


def test_only_facts_reads_through_the_repository_module():
    importers = [entry.split(":")[0] for entry in _importers_of(CODE_SOURCES, (QUERIES_MODULE,))]

    assert importers == [P_FACTS]
    assert _outside_query_importers(CODE_SOURCES) == []


def test_nothing_under_app_persistence_imports_either_package():
    """A22.4, the reverse direction: persistence stays below Layer 2."""
    importers = [entry for entry in _importers_of(CODE_SOURCES, ("app.fx", "app.pipeline"))
                 if entry.startswith("app/persistence/")]

    assert importers == []
    assert [path for path in CODE_SOURCES if path.startswith("app/persistence/")]
