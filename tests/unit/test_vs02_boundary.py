"""
VS-02 static boundaries (plan A21, A22.4), as far as VS02-M1 has built.

This file grows with each milestone, as its modules arrive. M1 adds
app/fx/, so these are the rows that concern app/fx/:

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
#: consumer, never relaxed to a substring.
FX_IMPORTERS = ("app/fx/",)

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
READS = {"open", "read_text", "read_bytes", "safe_load", "load_rate_set", "default_rate_set"}

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


FX_RULES: tuple[Rule, ...] = (
    _first_party_violations, _disguise_violations, _pipeline_violations, _third_party_violations,
    _stdlib_violations,
    _filesystem_violations, _context_violations, _state_violations, _clock_violations,
    _randomness_violations, _environment_violations, _float_violations, _session_violations,
    _document_violations, _yaml_violations, _import_time_violations, _serialiser_violations,
    _handler_violations, _money_violations, _currency_violations, _output_violations,
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


def _fx_closure(sources: dict[str, str]) -> set[str]:
    """Every first-party name app/fx/ reaches, statically (M8's closure): nothing is imported."""
    reached: set[str] = set()
    pending = sorted(name for name in sources if _within(name, ("app.fx",)))
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
    """No rule is left without a negative control."""
    assert {rule for _, rule, _ in FORBIDDEN_EDITS} == set(FX_RULES)
    assert {rule for _, rule, _ in FORBIDDEN_TREES} == {_executor_violations, _outbound_violations}


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
    importers = {entry.split(":")[0] for entry in _fx_importers(CODE_SOURCES)}

    assert importers, "the scan found no importer, so it would pass if app.fx were unused"
    assert _outside_importers(CODE_SOURCES) == []
    assert {"app/main.py", "app/intelligence/money.py", "scripts/vs01_acceptance.py",
            "migrations/env.py"} <= CODE_SOURCES.keys(), "the scan must read what it clears"


# ---------------------------------------------------------------------------
# The no-executor boundary (plan A21)
# ---------------------------------------------------------------------------


def test_the_closure_is_static_and_reaches_past_the_package():
    """Read from source, never imported: it follows app.intelligence into the canonical models."""
    closure = _fx_closure(APP_SOURCES)

    assert {"app.fx", "app.fx.rates", "app.fx.convert", "app.fx.errors"} <= closure
    assert {"app.intelligence", "app.intelligence.contract", "app.intelligence.money",
            "app.intelligence.scope", "app.normalization.config",
            "app.persistence.models"} <= closure
    assert "app.api.v1.risk" in APP_SOURCES and "app.api.v1.risk" not in closure


def test_the_closure_reaches_no_connector_ingestion_security_or_api_module():
    assert _executor_violations(APP_SOURCES) == []


def test_no_closure_module_imports_an_outbound_http_smtp_or_socket_module():
    assert _outbound_violations(APP_SOURCES) == []
