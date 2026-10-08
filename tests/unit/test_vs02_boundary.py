"""
VS-02 static boundaries (plan A21, A22.4), as far as VS02-M3 has built.

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

VS02-M3 adds view.py, service.py and band_rows, and extends the inventories
M2 wrote (OD-5, OD-M3-4). Each inventory is extended and none is relaxed:

    Where it exists    eight modules, view.py and service.py among them, and
                       no ninth.
    What is read       pipeline_queries.py names three models, each with the
                       columns its read needs and no other, and joins the
                       assessments to their customers. facts.py hands the
                       session to band_rows as well.
    Sessions           two modules accept one (A19 item 5): facts.py, and
                       service.py, which hands it to resolve_scope and to the
                       two readers of facts.py and uses it for nothing else.
    Errors             service.py raises one missing rate, naming every
                       currency, and catches nothing (A7.5 item 4). No other
                       module names that error.
    Output             service.py logs one event through log_event, with its
                       eight fields written out and no other (A20). No other
                       module logs.
    The key ALL        the open pipeline's key is written once, as
                       OPEN_PIPELINE_KEY in aggregation.py, beside the
                       reserved keys (A14.2, OD-8). That one statement is
                       exempt from the no-currency rule and nothing else is.

The rules M2 wrote over the arithmetic are as they were (OD-M3-6): no module
but measures.py rounds to a quantum, converts or imports the arithmetic
context, and measures.py receives no band. view.py answers to them as
aggregation.py does.
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
         "edges_of_type",
         # M3: the band read, the scope and the service itself.
         "read_band_facts", "band_rows", "resolve_scope", "default_risk_rules", "pipeline_view"}

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
        P_AGGREGATION, P_CONFIG, P_MEASURES, P_SERVICE, P_VIEW}
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
    assert {"app.pipeline.view", "app.pipeline.service", "app.core.logging"} <= closure, (
        "from M3 the service and what it logs through are inside it")
    assert {"app.intelligence", "app.intelligence.contract", "app.intelligence.money",
            "app.intelligence.scope", "app.normalization.config",
            "app.persistence.models"} <= closure
    assert "app.api.v1.risk" in APP_SOURCES and "app.api.v1.risk" not in closure


def test_the_closure_reaches_no_connector_ingestion_security_or_api_module():
    assert _executor_violations(APP_SOURCES) == []


def test_no_closure_module_imports_an_outbound_http_smtp_or_socket_module():
    assert _outbound_violations(APP_SOURCES) == []


# ===========================================================================
# VS02-M2 and M3: app/pipeline/ and pipeline_queries.py (plan A21, A21.1, A21.2, A22.4)
# ===========================================================================

PIPELINE_DIR = APP_DIR / "pipeline"
P_PACKAGE, P_AGGREGATION, P_CONFIG, P_ERRORS, P_FACTS, P_MEASURES = (
    "app/pipeline/__init__.py", "app/pipeline/aggregation.py", "app/pipeline/config.py",
    "app/pipeline/errors.py", "app/pipeline/facts.py", "app/pipeline/measures.py")
P_SERVICE, P_VIEW = "app/pipeline/service.py", "app/pipeline/view.py"
#: Plan B1 allows eight modules. M2 built six; M3 builds view.py and service.py (B6).
PIPELINE_MODULES = (P_PACKAGE, P_AGGREGATION, P_CONFIG, P_ERRORS, P_FACTS, P_MEASURES, P_SERVICE,
                    P_VIEW)
#: Plan A16.2: the one persistence module VS-02 adds.
QUERIES = "app/persistence/repositories/pipeline_queries.py"
QUERIES_MODULE = "app.persistence.repositories.pipeline_queries"

#: Plan A22.4's row for app/pipeline/*, exhaustive for first-party imports.
#: The repository module is facts.py's alone, and app.core.logging is
#: service.py's alone: no other module logs, so no other module is granted it.
PIPELINE_ALLOWED_FIRST_PARTY = ("app.pipeline", "app.fx", "app.relationships", "app.intelligence",
                                "app.normalization.config")
SERVICE_ALLOWED_FIRST_PARTY = (*PIPELINE_ALLOWED_FIRST_PARTY, "app.core.logging")
#: The standard-library modules the package imports today, closed as app/fx/'s are.
PIPELINE_ALLOWED_STDLIB = {"__future__", "collections", "dataclasses", "datetime", "decimal",
                           "enum", "functools", "hashlib", "pathlib", "typing"}
#: service.py alone also imports the logging module, to name a logger and a level (A20).
SERVICE_ALLOWED_STDLIB = PIPELINE_ALLOWED_STDLIB | {"logging"}
#: Who may import app.pipeline, and who may import its repository module.
PIPELINE_IMPORTERS = ("app/pipeline/",)
QUERIES_IMPORTERS = (P_FACTS,)

#: Plan A16.2: the models pipeline_queries.py names, and what it reads of each.
#: Of Deal, the nine columns and the two it filters on, as at M2. band_rows
#: adds two models at M3: of RiskAssessment the band, the verdict, the five
#: columns of the identity and the key it is joined on; of Customer the
#: source id, the key it is joined on and, from OD-M3-7, the two columns
#: that confine it to the scope, as the two filters of Deal confine a deal.
QUERY_COLUMNS = {
    "Deal": {"source_id", "stage", "is_active", "amount", "currency", "probability",
             "expected_close_date", "owner_source_id", "customer_source_id",
             "source_system", "source_entity"},
    "RiskAssessment": {"band", "executive_worthy", "customer_id", "source_system", "as_of",
                       "layer1_fingerprint", "rules_version", "linker_version"},
    "Customer": {"id", "source_id", "source_system", "source_entity"},
}
QUERY_MODELS = set(QUERY_COLUMNS)
#: Plan A16.2, OD-M3-7: what band_rows holds of the customer it joins, each
#: as (column, what it equals). The source system is the caller's own, the
#: one the identity is filtered by; the entity is the one module-level name.
BAND_CUSTOMER_FILTERS = (("Customer.source_system", "source_system"),
                         ("Customer.source_entity", "CUSTOMERS"))
BAND_CUSTOMER_ENTITY = "customers"
#: The SQLAlchemy names each module that reaches the database may import.
FACTS_SQLALCHEMY = {("sqlalchemy.orm", "Session")}
QUERY_SQLALCHEMY = {("sqlalchemy", "select"), ("sqlalchemy.orm", "Session")}
#: What a select is built with in pipeline_queries.py. Nothing that locks,
#: hints or changes how a statement runs. M3 adds the one inner join
#: band_rows needs; an outer join would return an assessment with no customer.
QUERY_CHAIN = {"where", "order_by", "join"}
#: The reads facts.py hands the caller's session to (A21.2 item 3). band_rows joined at M3.
SESSION_RECEIVERS = {"deal_rows", "edges_of_type", "band_rows"}
#: What service.py hands it to: the frozen scope resolver and facts.py's two readers.
SERVICE_SESSION_RECEIVERS = {"resolve_scope", "read_deal_facts", "read_band_facts"}
#: Plan A20 item 2: the one event, and its eight fields in order.
EVENT = "vs02.pipeline_view_built"
EVENT_FIELDS = ("source_system", "as_of", "layer1_fingerprint", "pipeline_version",
                "rate_set_version", "open_deal_count", "unvalued_deal_count", "view_hash")
#: Plan A14.2 and OD-8: the one name the key ALL may be written under, beside
#: the reserved keys, and the one module that defines it.
OPEN_PIPELINE_KEY = "OPEN_PIPELINE_KEY"

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
#: Errors no module of the package has any reason to name, but one: from M3
#: service.py raises a missing rate of its own (A7.5 item 4), and it alone
#: names that error, to raise it and never to catch it.
UNNAMED_ERRORS = {"CurrencyMismatchError", "ContractViolationError", "IntelligenceError",
                  "FxRateMissingError", "FxError", "suppress"}
SERVICE_RAISES = "FxRateMissingError"
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


def _handed_on(tree: ast.Module, receivers: set[str]) -> list[str]:
    """The caller's session is only passed, positionally, to the named reads. It is never
    called on, never kept, and none is made here (A21.1 item 5)."""
    passed = {id(argument) for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id in receivers for argument in node.args}
    found = [f"{node.lineno}: the session is used and not handed to a read"
             for node in ast.walk(tree)
             if isinstance(node, ast.Name) and node.id == "session" and id(node) not in passed]
    found += [f"{node.lineno}: {_dotted(node.func)}()" for node in ast.walk(tree)
              if isinstance(node, ast.Call) and _dotted(node.func) in {"Session", "sessionmaker"}]
    found += [f"{node.lineno}: {node.arg}" for node in ast.walk(tree)
              if isinstance(node, ast.arg) and node.arg in {"sessions", "engine", "connection"}]
    return found


def _facts_session_violations(tree: ast.Module) -> list[str]:
    """A21.2 item 3: facts.py is handed the caller's session and only passes it to the reads:
    deal_rows, edges_of_type and, from M3, band_rows."""
    return _handed_on(tree, SESSION_RECEIVERS)


def _service_session_violations(tree: ast.Module) -> list[str]:
    """A21.2 item 3: service.py passes the caller's session to resolve_scope and to facts.py's
    two readers, and to nothing else. It reads through no repository of its own."""
    return _handed_on(tree, SERVICE_SESSION_RECEIVERS)


def _service_first_party_violations(tree: ast.Module) -> list[str]:
    """A22.4: service.py alone also imports app.core.logging. Not the repository module, and
    nothing of the API: giving an error a status is the route's."""
    return _first_party(tree, SERVICE_ALLOWED_FIRST_PARTY)


def _service_stdlib_violations(tree: ast.Module) -> list[str]:
    """Beyond A22.4: service.py's standard library is the package's and the logging module."""
    return [f"{line}: {module}" for module, _, line in _imports(tree)
            if module.split(".")[0] in sys.stdlib_module_names - SERVICE_ALLOWED_STDLIB]


def _raised(tree: ast.Module) -> set[int]:
    """The ids of the names that are called to build the exception of a raise statement."""
    return {id(node.exc.func) for node in ast.walk(tree)
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)}


def _service_error_violations(tree: ast.Module) -> list[str]:
    """A7.5 item 4, A10.5 item 6: service.py raises one missing rate and catches nothing. It
    names no other error, and it names that one only to import it and to raise it."""
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
    unnamed = UNNAMED_ERRORS - {SERVICE_RAISES}
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if name in unnamed or (name == SERVICE_RAISES and module != "app.fx.errors")]
    found += [f"{node.lineno}: {_dotted(node)}" for node in ast.walk(tree)
              if isinstance(node, ast.Name | ast.Attribute)
              and _dotted(node).rsplit(".", 1)[-1] in unnamed]
    raised = _raised(tree)
    found += [f"{node.lineno}: {SERVICE_RAISES} named and not raised" for node in ast.walk(tree)
              if isinstance(node, ast.Name | ast.Attribute)
              and _dotted(node).rsplit(".", 1)[-1] == SERVICE_RAISES and id(node) not in raised]
    return found


def _is_the_event(call: ast.Call) -> bool:
    """log_event(logger, logging.INFO, "vs02.pipeline_view_built", <the eight fields, in order>)."""
    return (len(call.args) == 3 and _dotted(call.args[0]) == "logger"
            and _dotted(call.args[1]) == "logging.INFO"
            and isinstance(call.args[2], ast.Constant) and call.args[2].value == EVENT
            and tuple(keyword.arg for keyword in call.keywords) == EVENT_FIELDS)


def _service_logging_violations(tree: ast.Module) -> list[str]:
    """A20: service.py logs through log_event alone. logging gives it a logger and INFO and
    nothing else, the logger is only handed to log_event, and every log_event call is the one
    event with its eight fields written out: no further field, and none passed as a mapping."""
    found = [f"{node.lineno}: print" for node in ast.walk(tree)
             if isinstance(node, ast.Name) and node.id == "print"]
    found += [f"{line}: {module}" + (f".{name}" if name else "")
              for module, name, line in _imports(tree)
              if module.split(".")[0] == "logging" and (module, name) != ("logging", None)]
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if name == "log_event" and module != "app.core.logging"]
    found += [f"{node.lineno}: logging.{node.attr}" for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and _dotted(node.value) == "logging"
              and node.attr not in {"getLogger", "INFO"}]
    events = [node for node in ast.walk(tree)
              if isinstance(node, ast.Call) and _dotted(node.func) == "log_event"]
    found += [f"{call.lineno}: a log_event call that is not the one event" for call in events
              if not _is_the_event(call)]
    allowed = {id(call.func) for call in events} | {id(call.args[0]) for call in events
                                                    if call.args}
    allowed |= {id(target) for node in tree.body if isinstance(node, ast.Assign)
                for target in node.targets if _dotted(target) == "logger"}
    found += [f"{node.lineno}: {node.id} used beyond naming the logger and logging the event"
              for node in ast.walk(tree)
              if isinstance(node, ast.Name) and node.id in {"logger", "log_event"}
              and id(node) not in allowed]
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
    reserved bucket key ALL, in two statements and no other: where the reserved keys are
    stated, and, from M3, where the open pipeline's key is named (plan A14.2). The second is
    the module-level statement `OPEN_PIPELINE_KEY = "ALL"` exactly: that name alone, and a
    value that is that one string and nothing built around it."""
    docstrings, codes = _docstrings(tree), default_config().currency_codes
    reserved = {id(node) for statement in tree.body if isinstance(statement, ast.Assign)
                and [_dotted(target) for target in statement.targets] == ["RESERVED_KEYS"]
                for node in ast.walk(statement.value)}
    reserved |= {id(statement.value) for statement in tree.body
                 if isinstance(statement, ast.Assign)
                 and [_dotted(target) for target in statement.targets] == [OPEN_PIPELINE_KEY]
                 and isinstance(statement.value, ast.Constant)}
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
    """A16.2: three models and no other table, and of each only the columns its read needs.
    Of Deal the nine columns and the two filters: not the deal's name, and not its resolved
    customer FK. Of RiskAssessment the band, the verdict and the identity: not its signals,
    its satisfied rules or its ranking key. Of Customer its source id: not its name."""
    allowed = MODEL_NAMES - QUERY_MODELS
    found = [f"{node.lineno}: {node.id}" for node in ast.walk(tree)
             if isinstance(node, ast.Name) and node.id in allowed]
    found += [f"{line}: {module}.{name}" for module, name, line in _imports(tree)
              if name in allowed or (module == "app.persistence.models" and name is None)]
    found += [f"{node.lineno}: {_dotted(node)}" for node in ast.walk(tree)
              if isinstance(node, ast.Attribute) and _dotted(node.value) in QUERY_MODELS
              and node.attr not in QUERY_COLUMNS[_dotted(node.value)]]
    # A model is named whole in one place only: as the target of the join band_rows needs.
    # Its columns are still named one by one, and no row is selected whole.
    joined = {id(node.args[0]) for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == "join" and node.args}
    found += [f"{node.lineno}: {node.id} used whole" for node in ast.walk(tree)
              if isinstance(node, ast.Name) and node.id in QUERY_MODELS and id(node) not in {
                  id(attribute.value) for attribute in ast.walk(tree)
                  if isinstance(attribute, ast.Attribute)} | joined]
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
    executed on the caller's session, built with where, order_by and, for the band read, one
    inner join, and ordered in the C collation. The session is used for nothing else, and
    none is made here."""
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


def _band_scope_violations(tree: ast.Module) -> list[str]:
    """A16.2, OD-M3-7: the band read confines the customer it joins to the scope. Its where()
    holds `Customer.source_system == source_system`, the caller's own, and
    `Customer.source_entity == CUSTOMERS`, and CUSTOMERS is the one module-level string
    `customers`. Neither is left out, and no column of the customer is held to anything else.
    The rule is over the band read: a module that defines none has nothing to confine."""
    readers = [node for node in tree.body
               if isinstance(node, ast.FunctionDef) and node.name == "band_rows"]
    if not readers:
        return []
    named = [statement.value.value for statement in tree.body
             if isinstance(statement, ast.Assign)
             and [_dotted(target) for target in statement.targets] == ["CUSTOMERS"]
             and isinstance(statement.value, ast.Constant)]
    found = [] if named == [BAND_CUSTOMER_ENTITY] else [
        f"CUSTOMERS is {named!r} and not the one name of the entity"]
    held = {(_dotted(test.left), _dotted(test.comparators[0]))
            for reader in readers
            for call in ast.walk(reader)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and call.func.attr == "where"
            for test in call.args
            if isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)}
    found += [f"band_rows does not hold {column} == {value}"
              for column, value in BAND_CUSTOMER_FILTERS if (column, value) not in held]
    found += [f"band_rows holds {column} to {value or 'something else'}"
              for column, value in sorted(held)
              if column.startswith("Customer.") and (column, value) not in BAND_CUSTOMER_FILTERS]
    return found


def _band_precedence_violations(tree: ast.Module) -> list[str]:
    """A16.2, A12.2 item 4, OD-M3-7: where the stored bands are read and held against the
    vocabulary, nothing ranks one against another and nothing picks one of two. No band's
    rank is read, and no largest or smallest is taken. A row is left out because its
    customer is outside the scope, never because another row outranks it."""
    found = [f"{node.lineno}: .{node.attr}" for node in ast.walk(tree)
             if isinstance(node, ast.Attribute) and node.attr in {"rank", "at_least"}]
    found += [f"{node.lineno}: {_callee(node)}()" for node in ast.walk(tree)
              if isinstance(node, ast.Call) and _callee(node) in {"max", "min", "nlargest",
                                                                  "nsmallest"}]
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
#: What service.py answers to in place of three of the shared rules. It alone
#: logs (A20), so it has its own logging rule, which is stricter than "no
#: logging" would be elsewhere only in what it permits: one event. It alone
#: names the missing-rate error, to raise it. And its standard library is
#: the package's and the logging module.
_SERVICE_OWN = {_output_violations: _service_logging_violations,
                _pipeline_stdlib_violations: _service_stdlib_violations,
                _pipeline_handler_violations: _service_error_violations}
PIPELINE_RULES: dict[str, tuple[Rule, ...]] = {
    P_PACKAGE: (*_PIPELINE_PURE, _arithmetic_violations),
    P_AGGREGATION: (*_PIPELINE_PURE, _arithmetic_violations),
    P_CONFIG: (*_PIPELINE_PURE, _arithmetic_violations),
    P_ERRORS: (*_PIPELINE_PURE, _arithmetic_violations),
    P_MEASURES: (*_PIPELINE_PURE, _band_violations),
    P_FACTS: (*_PIPELINE_SHARED, _arithmetic_violations, _facts_first_party_violations,
              _facts_third_party_violations, _facts_sqlalchemy_violations,
              _facts_session_violations, _facts_persistence_violations,
              _band_precedence_violations),
    # M3. The view is pure and answers to what aggregation.py answers to.
    P_VIEW: (*_PIPELINE_PURE, _arithmetic_violations),
    # M3. The service accepts a session, as facts.py does, and reads through no repository.
    P_SERVICE: (*(_SERVICE_OWN.get(rule, rule) for rule in _PIPELINE_SHARED),
                _arithmetic_violations, _document_violations, _service_first_party_violations,
                _facts_third_party_violations, _facts_sqlalchemy_violations,
                _service_session_violations),
}
QUERY_RULES: tuple[Rule, ...] = (
    _disguise_violations, _filesystem_violations, _state_violations, _clock_violations,
    _randomness_violations, _environment_violations, _float_violations, _output_violations,
    _handler_violations, _write_violations, _query_import_violations, _query_model_violations,
    _query_statement_violations, _band_scope_violations, _band_precedence_violations,
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


def _key_definers(sources: dict[str, str]) -> list[str]:
    """A14.2 and OD-8: every module of the two packages that assigns the open pipeline's key."""
    return sorted(path for path in (*FX_MODULES, *PIPELINE_MODULES)
                  for node in ast.walk(ast.parse(sources[path]))
                  for target in (node.targets if isinstance(node, ast.Assign)
                                 else [node.target] if isinstance(
                                     node, ast.AnnAssign | ast.AugAssign | ast.NamedExpr) else [])
                  if _dotted(target) == OPEN_PIPELINE_KEY)


def _session_takers(sources: dict[str, str]) -> list[str]:
    """A19 item 5: every module of the package with a parameter that is a session."""
    return sorted(path for path in PIPELINE_MODULES
                  if any(isinstance(node, ast.arg) and node.arg in {"session", "sessions"}
                         for node in ast.walk(ast.parse(sources[path]))))


# ---------------------------------------------------------------------------
# Every pipeline rule fails on a forbidden edit to a copy of the real source
# ---------------------------------------------------------------------------

_MEASURES_IMPORT = ("from app.pipeline.measures import DealValues, cumulative_share, deal_values, "
                    "hhi, share, total")
_OWNER_READ = "edges_of_type(EdgeType.DEAL_OWNED_BY, session, scope)"
_ORDER = '.order_by(Deal.source_id.collate("C"))'
_LAST_COLUMN = "            Deal.customer_source_id,\n        )"
# M3: anchors in the band read, the view and the service.
_BAND_ORDER = '.order_by(Customer.source_id.collate("C"))'
_BAND_JOIN = ".join(Customer, Customer.id == RiskAssessment.customer_id)"
_BAND_LAST_COLUMN = "            RiskAssessment.executive_worthy,\n        )"
#: OD-M3-7: the two conditions that confine the joined customer, and the entity's name.
_BAND_SYSTEM = "            Customer.source_system == source_system,\n"
_BAND_ENTITY = "            Customer.source_entity == CUSTOMERS,\n"
_BAND_ENTITY_NAME = 'CUSTOMERS = "customers"'
_VIEW_CONTEXT = "Context(prec=digits, Emin=MIN_EMIN, Emax=MAX_EMAX)"
_KEY = 'OPEN_PIPELINE_KEY = "ALL"'
_SCOPE_READ = "resolve_scope(session, source_system=source_system, as_of=as_of)"
_EVENT_HEAD = 'logger, logging.INFO, "vs02.pipeline_view_built",'
_EVENT_TAIL = "        view_hash=built.view_hash,\n    )"
_EVENT_FIRST_TWO = ("        source_system=scope.source_system,\n"
                    "        as_of=scope.as_of.isoformat(),\n")

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
               "from .measures import DealValues, cumulative_share, deal_values, hhi, share, "
               "total")),
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
     _replaced(QUERIES, "from app.persistence.models import Customer, Deal, RiskAssessment",
               "from app.persistence.models import Customer, Deal, Document, RiskAssessment")),
    ("the repository reads a ticket",
     _query_model_violations, _appended(QUERIES, "tickets = SupportTicket\n")),
    ("the repository reads a brief",
     _query_model_violations,
     _appended(QUERIES, "from app.persistence.models import RiskBrief\n")),
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
    # ----------------------------------------------------------------- VS02-M3
    # A16.2: the band read
    ("the repository reads the assessment's signals",
     _query_model_violations,
     _replaced(QUERIES, _BAND_LAST_COLUMN,
               "            RiskAssessment.executive_worthy,\n"
               "            RiskAssessment.signals,\n        )")),
    ("the repository reads the assessment's own id",
     _query_model_violations,
     _replaced(QUERIES, _BAND_LAST_COLUMN,
               "            RiskAssessment.executive_worthy,\n            RiskAssessment.id,\n"
               "        )")),
    ("the repository reads the customer's name",
     _query_model_violations,
     _replaced(QUERIES, _BAND_LAST_COLUMN,
               "            RiskAssessment.executive_worthy,\n            Customer.name,\n"
               "        )")),
    ("the repository reads a position",
     _query_model_violations, _appended(QUERIES, "positions = RiskPosition\n")),
    ("the band read selects the whole assessment",
     _query_model_violations,
     _replaced(QUERIES, "            RiskAssessment.band,\n", "            RiskAssessment,\n")),
    ("the band read returns the customer whole",
     _query_model_violations,
     _appended(QUERIES, "def whole_customer(session):\n    return Customer\n")),
    ("the band read keeps an assessment whose customer is gone",
     _query_statement_violations,
     _replaced(QUERIES, _BAND_JOIN,
               ".outerjoin(Customer, Customer.id == RiskAssessment.customer_id)")),
    ("the band read leaves the order to the database's collation",
     _query_statement_violations,
     _replaced(QUERIES, _BAND_ORDER, ".order_by(Customer.source_id)")),
    ("the band read is left unordered",
     _query_statement_violations, _replaced(QUERIES, _BAND_ORDER, "")),
    ("the band read takes the first rows only",
     _query_statement_violations, _replaced(QUERIES, _BAND_ORDER, _BAND_ORDER + ".limit(50)")),
    ("the band read locks the assessments",
     _write_violations, _replaced(QUERIES, _BAND_ORDER, _BAND_ORDER + ".with_for_update()")),
    # A16.2, OD-M3-7: the joined customer is confined to the scope
    ("the band read joins a customer of any source system",
     _band_scope_violations, _replaced(QUERIES, _BAND_SYSTEM, "")),
    ("the band read joins a customers row of any source entity",
     _band_scope_violations, _replaced(QUERIES, _BAND_ENTITY, "")),
    ("the band read holds the customer's source system to itself",
     _band_scope_violations,
     _replaced(QUERIES, _BAND_SYSTEM,
               "            Customer.source_system == Customer.source_system,\n")),
    ("the band read holds the customer's source system to the assessment's",
     _band_scope_violations,
     _replaced(QUERIES, _BAND_SYSTEM,
               "            Customer.source_system == RiskAssessment.source_system,\n")),
    ("the band read keeps every customer but the scope's",
     _band_scope_violations,
     _replaced(QUERIES, _BAND_SYSTEM, "            Customer.source_system != source_system,\n")),
    ("the band read holds the customer's entity to the deals'",
     _band_scope_violations,
     _replaced(QUERIES, _BAND_ENTITY, "            Customer.source_entity == DEALS,\n")),
    ("the band read names another entity as the customers'",
     _band_scope_violations, _replaced(QUERIES, _BAND_ENTITY_NAME, 'CUSTOMERS = "accounts"')),
    ("the band read confines the customer in a statement it does not run",
     _band_scope_violations,
     _replaced(QUERIES, _BAND_SYSTEM + _BAND_ENTITY, "")
     + "\n\ndef unused(source_system):\n    return (Customer.source_system == source_system,\n"
       "            Customer.source_entity == CUSTOMERS)\n"),
    # OD-M3-7: no precedence and no resolution of two rows, in the statement or after it
    ("the band read keeps one row for each customer id",
     _query_statement_violations,
     _replaced(QUERIES, _BAND_ORDER, _BAND_ORDER + ".distinct(Customer.source_id)")),
    ("the band read folds the rows of one customer id together",
     _query_statement_violations,
     _replaced(QUERIES, _BAND_ORDER, ".group_by(Customer.source_id)" + _BAND_ORDER)),
    ("the band read keeps the gravest band of two",
     _band_precedence_violations,
     _appended(QUERIES, "def gravest(rows):\n    return max(rows, key=lambda row: row.band)\n")),
    ("facts keeps the higher-ranked of two bands for one customer",
     _band_precedence_violations,
     _appended(P_FACTS, "def higher(one, other):\n"
                        "    return one if RiskBand(one.band).rank >= RiskBand(other.band).rank"
                        " else other\n")),
    ("facts keeps the gravest of a customer's bands",
     _band_precedence_violations,
     _appended(P_FACTS, "def gravest(bands):\n    return max(bands, key=_by_customer)\n")),
    ("facts asks whether one band is at least another",
     _band_precedence_violations,
     _appended(P_FACTS, "def outranks(one, other):\n    return one.band.at_least(other.band)\n")),
    # A21.2 item 3: facts.py hands the session to band_rows and to nothing new
    ("facts hands the session to the risk tables' own reader",
     _facts_session_violations,
     _appended(P_FACTS, "def listed(session):\n    return list_assessments(session)\n")),
    ("facts reads the risk tables' own repository",
     _facts_first_party_violations,
     _appended(P_FACTS, "from app.persistence.repositories.risk_queries import "
                        "list_assessments\n")),
    ("facts computes a band instead of reading one",
     _facts_first_party_violations,
     _appended(P_FACTS, "from app.intelligence.bands import assign_band\n")),
    # A22.4: service.py's row
    ("the service reads the repository itself",
     _service_first_party_violations,
     _appended(P_SERVICE, f"from {QUERIES_MODULE} import deal_rows\n")),
    ("the service gives an error an API code",
     _service_first_party_violations,
     _appended(P_SERVICE, "from app.api.errors import ErrorCode\n")),
    ("the service computes a signal",
     _service_first_party_violations,
     _appended(P_SERVICE, "from app.intelligence.signals import compute_all_signals\n")),
    ("the service opens a session factory",
     _service_first_party_violations,
     _appended(P_SERVICE, "from app.core.database import get_session_factory\n")),
    ("the service runs an assessment",
     _service_first_party_violations,
     _appended(P_SERVICE, "from app.decisions.assessment import run_assessment\n")),
    ("the service starts a thread",
     _service_stdlib_violations, _appended(P_SERVICE, "import threading\n")),
    ("the service reaches for the operating system",
     _service_stdlib_violations, _appended(P_SERVICE, "import os\n")),
    ("the service builds a statement of its own",
     _facts_sqlalchemy_violations, _appended(P_SERVICE, "from sqlalchemy import select\n")),
    ("the service fetches a rate over HTTP",
     _facts_third_party_violations, _appended(P_SERVICE, "import httpx\n")),
    # A21.2 item 3: the service only hands the session on
    ("the service commits the caller's transaction",
     _service_session_violations, _appended(P_SERVICE, "def done(session):\n    session.commit()\n")),
    ("the service executes a statement itself",
     _service_session_violations,
     _appended(P_SERVICE, "def count(session):\n    return session.execute(None)\n")),
    ("the service hands the session to a repository",
     _service_session_violations,
     _appended(P_SERVICE, "def more(session):\n    return deal_rows(session, 'csv_demo')\n")),
    ("the service keeps the session",
     _service_session_violations,
     _appended(P_SERVICE, "def keep(session):\n    held = session\n    return held\n")),
    ("the service hands the session on by keyword",
     _service_session_violations,
     _replaced(P_SERVICE, _SCOPE_READ,
               "resolve_scope(session=session, source_system=source_system, as_of=as_of)")),
    ("the service makes a session of its own",
     _service_session_violations, _appended(P_SERVICE, "def own():\n    return Session()\n")),
    ("the service is handed a session factory",
     _service_session_violations, _appended(P_SERVICE, "def bound(sessions):\n    return None\n")),
    # A7.5 item 4, A10.5 item 6: one missing rate raised, and nothing caught
    ("the service answers a missing rate with a partial view",
     _service_error_violations,
     _appended(P_SERVICE, "try:\n    pass\nexcept FxRateMissingError:\n    pass\n")),
    ("the service swallows a data error",
     _service_error_violations,
     _appended(P_SERVICE, "try:\n    pass\nexcept PipelineDataError:\n    pass\n")),
    ("the service translates the frozen type's refusal",
     _service_error_violations,
     _appended(P_SERVICE, "try:\n    pass\nexcept ContractViolationError as exc:\n"
                          "    raise ValueError('x') from exc\n")),
    ("the service catches everything",
     _service_error_violations,
     _appended(P_SERVICE, "try:\n    pass\nexcept Exception:\n    pass\n")),
    ("the service has a bare except",
     _service_error_violations, _appended(P_SERVICE, "try:\n    pass\nexcept:\n    pass\n")),
    ("the service returns the missing rate instead of raising it",
     _service_error_violations,
     _replaced(P_SERVICE, "raise FxRateMissingError(missing",
               "return FxRateMissingError(missing")),
    ("the service names the frozen type's refusal",
     _service_error_violations,
     _appended(P_SERVICE, "from app.intelligence.errors import ContractViolationError\n")),
    ("the service takes the missing-rate error from the package and not its module",
     _service_error_violations,
     _replaced(P_SERVICE, "from app.fx.errors import FxRateMissingError",
               "from app.fx import FxRateMissingError")),
    ("a missing rate is suppressed without a handler",
     _service_error_violations, _appended(P_SERVICE, "from contextlib import suppress\n")),
    # A20: one event, through log_event, with its eight fields written out
    ("the service logs through the logger itself",
     _service_logging_violations, _appended(P_SERVICE, "logger.info('built')\n")),
    ("the service prints the view",
     _service_logging_violations, _appended(P_SERVICE, "print('built')\n")),
    ("the event is given an amount",
     _service_logging_violations,
     _replaced(P_SERVICE, _EVENT_TAIL,
               "        view_hash=built.view_hash,\n"
               "        base_total=view['open_pipeline']['base']['unweighted'],\n    )")),
    ("the event is given the customers at risk",
     _service_logging_violations,
     _replaced(P_SERVICE, _EVENT_TAIL,
               "        view_hash=built.view_hash,\n"
               "        customers=view['risk_coincidence'],\n    )")),
    ("the event's fields are passed as a mapping",
     _service_logging_violations,
     _appended(P_SERVICE, "log_event(logger, logging.INFO, 'vs02.pipeline_view_built', "
                          "**{})\n")),
    ("the event is logged as a warning",
     _service_logging_violations,
     _replaced(P_SERVICE, _EVENT_HEAD,
               'logger, logging.WARNING, "vs02.pipeline_view_built",')),
    ("the event is given another name",
     _service_logging_violations,
     _replaced(P_SERVICE, _EVENT_HEAD, 'logger, logging.INFO, "vs02.view_built",')),
    ("a second event is logged for a failure",
     _service_logging_violations,
     _appended(P_SERVICE, "log_event(logger, logging.INFO, 'vs02.pipeline_view_failed')\n")),
    ("the event loses a field",
     _service_logging_violations,
     _replaced(P_SERVICE, "        rate_set_version=rate_set.rate_set_version,\n", "")),
    ("the event's fields change order",
     _service_logging_violations,
     _replaced(P_SERVICE, _EVENT_FIRST_TWO,
               "        as_of=scope.as_of.isoformat(),\n"
               "        source_system=scope.source_system,\n")),
    ("a level is taken from the logging module by name",
     _service_logging_violations, _appended(P_SERVICE, "from logging import INFO\n")),
    ("the service configures logging",
     _service_logging_violations, _appended(P_SERVICE, "logging.basicConfig()\n")),
    ("the logger is handed to something that is not log_event",
     _service_logging_violations, _appended(P_SERVICE, "def other():\n    return [logger]\n")),
    ("log_event is taken from somewhere else",
     _service_logging_violations,
     _replaced(P_SERVICE, "from app.core.logging import log_event",
               "from app.observability import log_event")),
    # the shared rules, over the service's own source
    ("the service names the assessment model",
     _model_name_violations, _appended(P_SERVICE, "row_type = RiskAssessment\n")),
    ("the service reads a document",
     _document_violations, _appended(P_SERVICE, "from app.evidence import citable_text\n")),
    ("the service reads the canonical models",
     _document_violations, _appended(P_SERVICE, "from app.persistence.models import Deal\n")),
    ("the service stores the view it built",
     _write_violations, _appended(P_SERVICE, "def store(unit, row):\n    unit.add(row)\n")),
    ("the service converts an amount itself",
     _arithmetic_violations, _appended(P_SERVICE, "from app.fx.convert import convert\n")),
    ("the service reads the clock",
     _clock_violations,
     _appended(P_SERVICE, "from datetime import datetime\nbuilt_at = datetime.now()\n")),
    ("the service lets an environment variable choose the rate set",
     _environment_violations,
     _appended(P_SERVICE, "import os\nRATES = os.environ.get('FX_RATES')\n")),
    ("the service loads the rate set when it is imported",
     _import_time_violations, _appended(P_SERVICE, "CURRENT = default_rate_set()\n")),
    ("the service resolves a scope as a default argument",
     _import_time_violations,
     _appended(P_SERVICE, "def later(scope=resolve_scope(None)):\n    return scope\n")),
    ("the service walks to an owner's manager",
     _relationship_violations,
     _appended(P_SERVICE, "from app.relationships import escalation_path\n")),
    ("the service keeps the last view in a module global",
     _state_violations, _appended(P_SERVICE, "_LAST = {}\n")),
    # the shared rules, over the view's own source
    ("the view takes a session",
     _session_violations, _appended(P_VIEW, "def stored(session):\n    return None\n")),
    ("the view reads the repository",
     _pipeline_first_party_violations,
     _appended(P_VIEW, f"from {QUERIES_MODULE} import band_rows\n")),
    ("the view logs through log_event",
     _pipeline_first_party_violations,
     _appended(P_VIEW, "from app.core.logging import log_event\n")),
    ("the view rounds a share itself",
     _arithmetic_violations,
     _appended(P_VIEW, "def rounded(value, quantum, mode):\n"
                       "    return value.quantize(quantum, rounding=mode)\n")),
    ("the view imports the arithmetic context",
     _arithmetic_violations,
     _appended(P_VIEW, "from app.fx.convert import arithmetic_context\n")),
    ("the view converts a native total",
     _arithmetic_violations,
     _appended(P_VIEW, "def base(value, rate_set):\n    return convert(value, rate_set)\n")),
    ("the view adds amounts with the builtin sum",
     _summing_violations, _appended(P_VIEW, "def add_up(amounts):\n    return sum(amounts)\n")),
    ("a text is taken in a copy of the caller's context",
     _context_violations,
     _replaced(P_VIEW, f"with localcontext({_VIEW_CONTEXT}):", "with localcontext():")),
    ("the text's context inherits its exponent limits",
     _context_violations, _replaced(P_VIEW, _VIEW_CONTEXT, "Context(prec=digits)")),
    ("the text's context inherits its precision",
     _context_violations,
     _replaced(P_VIEW, _VIEW_CONTEXT, "Context(Emin=MIN_EMIN, Emax=MAX_EMAX)")),
    ("the view makes the process context precise instead",
     _context_violations,
     _appended(P_VIEW, "from decimal import getcontext\ngetcontext().prec = 50\n")),
    ("the view serialises with json itself",
     _serialiser_violations, _appended(P_VIEW, "import json\n")),
    ("decimal_text is copied into the view",
     _serialiser_violations,
     _appended(P_VIEW, "def decimal_text(value):\n    return str(value)\n")),
    ("the view reads a document",
     _document_violations, _appended(P_VIEW, "from app.evidence import citable_text\n")),
    ("the view logs its figures",
     _output_violations, _appended(P_VIEW, "import logging\n")),
    ("the view names the missing-rate error",
     _pipeline_handler_violations,
     _appended(P_VIEW, "from app.fx.errors import FxRateMissingError\n")),
    ("the view skips a deal whose values cannot be stated",
     _pipeline_handler_violations,
     _appended(P_VIEW, "try:\n    pass\nexcept PipelineDataError:\n    pass\n")),
    ("the view stamps itself with the time",
     _clock_violations,
     _appended(P_VIEW, "from datetime import datetime\nbuilt_at = datetime.now()\n")),
    ("the view gives itself a generated id",
     _randomness_violations, _appended(P_VIEW, "import uuid\n")),
    ("the view writes itself to a table",
     _write_violations, _appended(P_VIEW, "def store(unit, row):\n    unit.add(row)\n")),
    ("the last view is kept in a module global",
     _state_violations, _appended(P_VIEW, "_LAST = {}\n")),
    ("the view states a ratio as a float",
     _float_violations,
     _appended(P_VIEW, "def ratio(part, whole):\n    return float(part) / float(whole)\n")),
    ("the view names the assessment model",
     _model_name_violations, _appended(P_VIEW, "row_type = RiskAssessment\n")),
    ("the view reads a customer's tickets",
     _relationship_violations,
     _appended(P_VIEW, "from app.relationships import neighbourhood\n")),
    ("the view is written to a file",
     _filesystem_violations,
     _appended(P_VIEW, "def store(path, body):\n    path.write_text(body)\n")),
    # A12.4 item 4, OD-M3-6: the arithmetic of A11 joins measures.py, and a band does not
    ("a share is discounted by a band",
     _band_violations,
     _appended(P_MEASURES, "def discounted_share(amount, whole, band):\n"
                           "    return share(amount, whole)\n")),
    ("the measures read a holder's risk band",
     _band_violations,
     _appended(P_MEASURES, "def of(holder):\n    return holder.band\n")),
    ("aggregation rounds a share itself",
     _arithmetic_violations,
     _appended(P_AGGREGATION, "def own_share(amount, whole, quantum, mode):\n"
                              "    return (amount / whole).quantize(quantum, rounding=mode)\n")),
    ("aggregation imports the arithmetic context for a share",
     _arithmetic_violations,
     _appended(P_AGGREGATION, "from app.fx.convert import arithmetic_context\n")),
    # A14.2, OD-8: the one further statement in which the key ALL is written
    ("the open pipeline's key names another currency",
     _pipeline_currency_violations, _replaced(P_AGGREGATION, _KEY, 'OPEN_PIPELINE_KEY = "INR"')),
    ("the open pipeline's key becomes a pair of currencies",
     _pipeline_currency_violations,
     _replaced(P_AGGREGATION, _KEY, 'OPEN_PIPELINE_KEY = ("ALL", "ALL")')),
    ("the key ALL is written under another name",
     _pipeline_currency_violations, _appended(P_AGGREGATION, 'OPEN_PIPELINE = "ALL"\n')),
    ("the key ALL is written inside a function",
     _pipeline_currency_violations,
     _appended(P_AGGREGATION, 'def key():\n    OPEN_PIPELINE_KEY = "ALL"\n'
                              '    return OPEN_PIPELINE_KEY\n')),
    ("the key ALL is written beside a second name",
     _pipeline_currency_violations,
     _replaced(P_AGGREGATION, _KEY, 'OPEN_PIPELINE_KEY = EVERY_CURRENCY = "ALL"')),
    ("the view writes the key ALL itself",
     _pipeline_currency_violations, _appended(P_VIEW, 'def key():\n    return "ALL"\n')),
    ("the service names a default currency",
     _pipeline_currency_violations, _appended(P_SERVICE, 'DEFAULT_CURRENCY = "INR"\n')),
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
    # M3: the service is the package's too. Its one importer, the route, is VS02-M4's.
    ("app/api/v1/risk.py", "from app.pipeline.service import pipeline_view\n"),
    ("app/decisions/assessment.py", "from app.pipeline.service import pipeline_view\n"),
    ("app/main.py", "from app.pipeline.view import build_view\n"),
    ("app/api/v1/router.py", "from app.pipeline import service\n"),
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
    # M3: the band read is facts.py's too.
    (P_SERVICE, f"from {QUERIES_MODULE} import band_rows\n"),
    (P_VIEW, f"from {QUERIES_MODULE} import band_rows\n"),
    ("app/decisions/assessment.py", f"from {QUERIES_MODULE} import band_rows\n"),
]
#: A19 item 5: a module of the package, other than facts.py and service.py, given a session.
FORBIDDEN_SESSION_TAKERS = [
    (P_AGGREGATION, "def stored(session):\n    return None\n"),
    (P_MEASURES, "def stored(amount, *, session=None):\n    return None\n"),
    (P_CONFIG, "def stored(sessions):\n    return None\n"),
    (P_VIEW, "def stored(view, session):\n    return None\n"),
    (P_ERRORS, "def stored(session):\n    return None\n"),
]
#: A14.2, OD-8: a second module that writes the open pipeline's key for itself.
FORBIDDEN_KEY_DEFINERS = [
    (P_VIEW, 'OPEN_PIPELINE_KEY = "ALL"\n'),
    (P_SERVICE, 'OPEN_PIPELINE_KEY = "ALL"\n'),
    (P_MEASURES, 'OPEN_PIPELINE_KEY: str = "ALL"\n'),
    (CONVERT, 'OPEN_PIPELINE_KEY = "ALL"\n'),
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
    # M3: the two new modules, and the logger only the service reaches.
    ("the service reaches the API",
     _executor_violations,
     _with(app__pipeline__service=_appended(P_SERVICE, "from app.api.errors import ErrorCode\n"))),
    ("the service reaches ingestion",
     _executor_violations,
     _with(app__pipeline__service=_appended(
         P_SERVICE, "from app.ingestion.orchestrator import run_ingestion\n"))),
    ("the view reaches a connector",
     _executor_violations,
     _with(app__pipeline__view=_appended(
         P_VIEW, "from app.connectors.registry import build_connector\n"))),
    ("the view opens a socket",
     _outbound_violations, _with(app__pipeline__view=_appended(P_VIEW, "import socket\n"))),
    ("the service posts the view over HTTP",
     _outbound_violations, _with(app__pipeline__service=_appended(P_SERVICE, "import httpx\n"))),
    ("the logger, which only the service reaches, turns outbound",
     _outbound_violations,
     _with(app__core__logging=APP_SOURCES["app.core.logging"] + "\nimport smtplib\n")),
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
def test_the_session_scan_catches_a_third_module_that_accepts_one(path, addition):
    edited = {**CODE_SOURCES, path: CODE_SOURCES[path] + "\n" + addition}

    assert _session_takers(edited) == sorted([P_FACTS, P_SERVICE, path])


@pytest.mark.parametrize(("path", "addition"), FORBIDDEN_KEY_DEFINERS,
                         ids=[path for path, _ in FORBIDDEN_KEY_DEFINERS])
def test_the_key_scan_catches_a_second_module_that_writes_the_open_pipelines_key(path, addition):
    edited = {**CODE_SOURCES, path: CODE_SOURCES[path] + "\n" + addition}

    assert _key_definers(edited) == sorted([P_AGGREGATION, path])


def test_the_pipeline_scans_read_code_and_not_the_docstrings_explaining_it():
    """These modules say at length what they do not do; saying it is not doing it."""
    prose = ast.parse('"""Never session.commit(), insert(Deal) or EdgeType.CUSTOMER_HAS_TICKET; '
                      'never INR; no RiskBand, no sum(), no convert() and no text()."""\nx = 1\n')
    rules = {rule for rules in PIPELINE_RULES.values() for rule in rules} | set(QUERY_RULES)

    assert sorted(rule.__name__ for rule in rules if rule(prose)) == []
    assert _pipeline_currency_violations(ast.parse('RESERVED_KEYS = frozenset({"ALL"})\n')) == []
    assert _pipeline_currency_violations(ast.parse('OTHER_KEYS = frozenset({"ALL"})\n')) == [
        "1: 'ALL'"]
    # M3's one further exemption is one exact statement, and nothing around it.
    assert _pipeline_currency_violations(ast.parse('OPEN_PIPELINE_KEY = "ALL"\n')) == []
    for refused in ('OPEN_PIPELINE_KEY = "USD"\n', 'OPEN_PIPELINE_KEYS = "ALL"\n',
                    'OPEN_PIPELINE_KEY = ["ALL"]\n', 'OPEN_PIPELINE_KEY = "ALL" + ""\n',
                    'class Keys:\n    OPEN_PIPELINE_KEY = "ALL"\n',
                    'OPEN_PIPELINE_KEY = "ALL"\nUSED = "ALL"\n'):
        assert len(_pipeline_currency_violations(ast.parse(refused))) == 1, refused
    assert _service_logging_violations(ast.parse(
        f'log_event(logger, logging.INFO, "{EVENT}", '
        + ", ".join(f"{name}=1" for name in EVENT_FIELDS) + ")\n")) == []
    assert _service_session_violations(ast.parse("resolve_scope(session, as_of=1)\n")) == []
    assert _service_session_violations(ast.parse("resolve_scope(session=session)\n")) != []
    assert _service_error_violations(ast.parse("raise FxRateMissingError({1}, 'v')\n")) == []
    assert _service_error_violations(ast.parse("error = FxRateMissingError({1}, 'v')\n")) != []
    assert _relationship_violations(ast.parse(
        "edges_of_type(EdgeType.CUSTOMER_HAS_DEAL, session, scope)\n")) == []
    assert _facts_session_violations(ast.parse("deal_rows(session, 'x')\n")) == []
    assert _facts_session_violations(ast.parse("deal_rows(unit=session)\n")) != []


# ---------------------------------------------------------------------------
# Where app/pipeline/ exists (plan A22.2, B1, B6)
# ---------------------------------------------------------------------------


def test_the_pipeline_package_holds_exactly_its_eight_modules():
    """A scan that silently matches nothing proves nothing, and a ninth module is a decision.
    Plan B1 names eight: the six of VS02-M2, and view.py and service.py, which VS02-M3 adds."""
    found = sorted(path.relative_to(REPO).as_posix() for path in PIPELINE_DIR.rglob("*.py"))

    assert found == sorted(PIPELINE_MODULES) == sorted(PIPELINE_RULES)
    assert len(found) == 8 and {P_SERVICE, P_VIEW} < set(found)
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


def test_the_band_read_holds_the_five_of_the_identity_and_the_two_of_the_customer():
    """A16.2, A12.2, OD-M3-7. Not vacuous: the repository does define band_rows, and its one
    where() holds seven equalities and nothing else. Five are the identity's, each a column of
    the assessment held to the caller's own value of that name. Two confine the customer it
    joins. The rule over them looks only where a band read is defined, and this is what would
    notice the read being gone."""
    tree = ast.parse(_source(QUERIES))
    [reader] = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "band_rows"]
    [where] = [call for call in ast.walk(reader)
               if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
               and call.func.attr == "where"]

    assert not where.keywords
    assert all(isinstance(test, ast.Compare) and [type(op) for op in test.ops] == [ast.Eq]
               for test in where.args)
    assert [(_dotted(test.left), _dotted(test.comparators[0])) for test in where.args] == [
        *((f"RiskAssessment.{name}", name) for name in (
            "source_system", "as_of", "layer1_fingerprint", "rules_version", "linker_version")),
        *BAND_CUSTOMER_FILTERS]
    assert BAND_CUSTOMER_FILTERS[0][1] == "source_system", (
        "the customer is held to the one source system the identity is filtered by")
    assert _band_scope_violations(ast.parse("x = 1\n")) == []


def test_the_pipeline_imports_what_its_row_grants_and_no_package_beyond_it():
    """The allow-lists are not vacuous: the package does read M1, FX, the relationship model,
    the D1 vocabulary and, in facts.py alone, the repository. From M3 the service also reads
    the logger and the missing-rate error, and it alone does."""
    imported = {relative: {module for module, _, _ in _imports(ast.parse(_source(relative)))}
                for relative in PIPELINE_MODULES}
    every = set().union(*imported.values())

    assert {"app.fx.convert", "app.fx.rates", "app.intelligence", "app.intelligence.contract",
            "app.intelligence.money", "app.normalization.config", "app.relationships",
            "app.pipeline.aggregation", "app.pipeline.config", "app.pipeline.errors",
            "app.pipeline.facts", "app.pipeline.measures", QUERIES_MODULE,
            "app.pipeline.view", "app.core.logging", "app.fx.errors"} == {
        module for module in every if module.split(".")[0] == "app"}
    assert [relative for relative, modules in imported.items() if QUERIES_MODULE in modules] == [
        P_FACTS]
    for service_only in ("app.core.logging", "app.fx.errors", "app.pipeline.view", "logging"):
        assert [relative for relative, modules in imported.items()
                if service_only in modules] == [P_SERVICE], service_only
    assert {module.split(".")[0] for module in every
            if module.split(".")[0] not in {"app"} | sys.stdlib_module_names} == {
        "yaml", "sqlalchemy"}
    assert [relative for relative, modules in imported.items()
            if any(module.split(".")[0] == "sqlalchemy" for module in modules)] == [
        P_FACTS, P_SERVICE]
    assert [relative for relative, modules in imported.items() if "yaml" in modules] == [P_CONFIG]
    assert {module.split(".")[0] for module in every
            if module.split(".")[0] in sys.stdlib_module_names} == SERVICE_ALLOWED_STDLIB
    assert {module.split(".")[0] for relative, modules in imported.items()
            if relative != P_SERVICE for module in modules
            if module.split(".")[0] in sys.stdlib_module_names} == PIPELINE_ALLOWED_STDLIB


def test_the_repository_imports_three_models_and_two_sqlalchemy_names():
    """Plan A16.2: Deal at M2; RiskAssessment and Customer with band_rows at M3; no fourth."""
    imported = {(module, name) for module, name, _ in _imports(ast.parse(_source(QUERIES)))}

    assert {pair for pair in imported if pair[0].split(".")[0] in {"app", "sqlalchemy"}} == {
        ("app.persistence.models", "Customer"), ("app.persistence.models", "Deal"),
        ("app.persistence.models", "RiskAssessment"), *QUERY_SQLALCHEMY}


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
        "band_rows", "deal_rows", "edges_of_type", "edges_of_type"]


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
    assert QUERY_MODELS < MODEL_NAMES and QUERY_MODELS == {"Deal", "RiskAssessment", "Customer"}
    for model, columns in QUERY_COLUMNS.items():
        assert columns <= set(getattr(models, model).__table__.columns.keys()), model
    assert "name" in models.Deal.__table__.columns.keys()
    assert "name" not in QUERY_COLUMNS["Deal"] and "customer_id" not in QUERY_COLUMNS["Deal"]
    assert len(QUERY_COLUMNS["Deal"]) == 11, "the nine columns and the two filters, as at M2"
    # What band_rows must not read exists, so the rule that refuses it is not vacuous.
    assert {"signals", "satisfied_rules", "ranking_key", "id"} <= set(
        models.RiskAssessment.__table__.columns.keys())
    assert not {"signals", "satisfied_rules", "ranking_key", "id"} & QUERY_COLUMNS["RiskAssessment"]
    assert "name" in models.Customer.__table__.columns.keys()
    assert QUERY_COLUMNS["Customer"] == {"id", "source_id", "source_system", "source_entity"}


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


def test_facts_and_the_service_are_the_two_modules_of_the_package_that_accept_a_session():
    """A19 item 5: exactly two. facts.py reads, and from M3 service.py hands the session on."""
    assert _session_takers(CODE_SOURCES) == [P_FACTS, P_SERVICE]


def test_the_service_hands_the_session_to_the_scope_and_the_two_readers_and_nothing_else():
    """A21.2 item 3, not vacuously: service.py does call all three, once each."""
    tree = ast.parse(_source(P_SERVICE))

    assert sorted(node.func.id for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                  and node.func.id in SERVICE_SESSION_RECEIVERS) == [
        "read_band_facts", "read_deal_facts", "resolve_scope"]
    assert len([node for node in ast.walk(tree)
                if isinstance(node, ast.Name) and node.id == "session"]) == 3
    assert not SERVICE_SESSION_RECEIVERS & SESSION_RECEIVERS, (
        "the service reads through facts.py and through no repository of its own")


def test_the_service_logs_the_one_event_and_no_other_module_logs():
    """A20: one log_event call in the two packages, with the eight fields of the plan."""
    calls = {relative: [node for node in ast.walk(ast.parse(_source(relative)))
                        if isinstance(node, ast.Call) and _dotted(node.func) == "log_event"]
             for relative in (*FX_MODULES, *PIPELINE_MODULES, QUERIES)}

    assert {relative: len(found) for relative, found in calls.items() if found} == {P_SERVICE: 1}
    [call] = calls[P_SERVICE]
    assert _is_the_event(call)
    assert EVENT == "vs02.pipeline_view_built" and len(EVENT_FIELDS) == 8
    assert not [name for name in EVENT_FIELDS
                if any(word in name for word in ("amount", "total", "customer", "base"))]


def test_only_the_service_names_the_missing_rate_error_and_it_only_raises_it():
    """A7.5 item 4: the check of every currency is the service's, and its alone."""
    named = {relative: [node for node in ast.walk(ast.parse(_source(relative)))
                        if isinstance(node, ast.Name) and node.id == SERVICE_RAISES]
             for relative in PIPELINE_MODULES}

    assert {relative: len(found) for relative, found in named.items() if found} == {P_SERVICE: 1}
    tree = ast.parse(_source(P_SERVICE))
    assert len([node for node in ast.walk(tree) if isinstance(node, ast.Raise)]) == 1
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Try)]


def test_the_open_pipelines_key_is_written_once_beside_the_reserved_keys():
    """A14.2, OD-8: one module, one statement, and the value is a reserved key."""
    from app.pipeline import aggregation

    assert _key_definers(CODE_SOURCES) == [P_AGGREGATION]
    assert aggregation.OPEN_PIPELINE_KEY == "ALL"
    assert aggregation.OPEN_PIPELINE_KEY in aggregation.RESERVED_KEYS
    assert aggregation.OPEN_PIPELINE_KEY in default_config().currency_codes, (
        "the exemption exists because the key is also a currency Layer 1 admits")
    literals = {relative: [node for node in ast.walk(ast.parse(_source(relative)))
                           if isinstance(node, ast.Constant) and node.value == "ALL"]
                for relative in (*FX_MODULES, *PIPELINE_MODULES, QUERIES)}
    assert {relative: len(found) for relative, found in literals.items() if found} == {
        P_AGGREGATION: 2}


def test_the_arithmetic_rules_of_m2_stand_as_m2_wrote_them():
    """OD-M3-6: measures.py gained the arithmetic of A11 under the rules, not by an exception
    to them. No module but measures.py rounds, converts or imports the arithmetic context, and
    measures.py is still the one module the no-band rule is over."""
    for relative, rules in PIPELINE_RULES.items():
        assert (_arithmetic_violations in rules) is (relative != P_MEASURES), relative
        assert (_band_violations in rules) is (relative == P_MEASURES), relative
        assert _summing_violations in rules, relative
    rounding = {relative: [node for node in ast.walk(ast.parse(_source(relative)))
                           if isinstance(node, ast.Call) and _callee(node) == "quantize"]
                for relative in PIPELINE_MODULES}
    assert {relative for relative, found in rounding.items() if found} == {P_MEASURES}
    assert [relative for relative in PIPELINE_MODULES
            if "arithmetic_context" in {name for _, name, _ in _imports(ast.parse(
                _source(relative)))}] == [P_MEASURES]
    measures = ast.parse(_source(P_MEASURES))
    assert {node.name for node in measures.body if isinstance(node, ast.FunctionDef)} == {
        "weigh", "deal_values", "total", "share", "cumulative_share", "hhi"}
    assert not [argument.arg for node in ast.walk(measures) if isinstance(node, ast.FunctionDef)
                for argument in node.args.args
                if argument.arg in {"customer", "holder", "key", "bucket", "kind"}]


def test_vs02_m3_builds_no_route_no_response_model_and_no_error_code():
    """Plan B6: the route, its response models, the ErrorCode member and the router
    registration are VS02-M4's. M3 leaves every one of them as it was."""
    api = APP_DIR / "api"

    assert not [path.name for path in api.rglob("*.py") if "pipeline" in path.name]
    assert "FX_RATE_MISSING" not in _source("app/api/errors.py")
    assert "pipeline" not in _source("app/api/v1/router.py")
    assert not (REPO / "scripts" / "vs02_acceptance.py").exists()


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
