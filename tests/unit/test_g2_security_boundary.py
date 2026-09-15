"""
G2 static security boundaries (spec Section 14).

Repository-wide structural guarantees that complement the behavioural tests:
no code that executes or unsafely deserializes content, one place that builds
HTTP clients, connectors that only GET, logging only through log_event with no
credential-named fields or exception text, no textual SQL, and an API contract
and settings model that expose no credential-shaped fields.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.main import create_app

REPO = Path(__file__).resolve().parents[2]
CODE_DIRS = ("app", "scripts", "docker", "migrations")
SECURITY_MODULE = "app/core/security.py"
LOGGING_MODULE = "app/core/logging.py"
SCANNER_MODULE = "scripts/secret_scan.py"
SENSITIVE_NAME = re.compile(
    r"(?i)(password|passwd|secret|token|api_?key|authorization|credential|cookie|base_url|"
    r"database_url|dsn|header|env_var)")
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}


def _trees(*directories: str):
    for directory in directories:
        for path in sorted((REPO / directory).rglob("*.py")):
            relative = path.relative_to(REPO).as_posix()
            yield relative, ast.parse(path.read_text(encoding="utf-8"))


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def test_the_scanned_code_directories_exist():
    assert {name for name, _ in _trees(*CODE_DIRS)} >= {
        SECURITY_MODULE, LOGGING_MODULE, SCANNER_MODULE, "app/connectors/rest.py",
        "docker/mock_source.py", "migrations/env.py"}


def test_no_code_executes_or_unsafely_deserializes_content():
    forbidden_calls = {"eval", "exec", "compile", "__import__", "yaml.load", "yaml.unsafe_load",
                       "yaml.full_load", "os.system", "os.popen", "pickle.load", "pickle.loads",
                       "marshal.load", "marshal.loads"}
    forbidden_modules = {"pickle", "marshal", "shelve", "dill", "subprocess"}
    for name, tree in _trees(*CODE_DIRS):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                assert _dotted(node.func) not in forbidden_calls, f"{name}: {_dotted(node.func)}"
                for keyword in node.keywords:
                    assert not (keyword.arg == "shell" and getattr(keyword.value, "value", False)), name
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module.split(".")[0]]
            for module in modules:
                if module == "subprocess" and name == SCANNER_MODULE:
                    continue  # runs "git ls-files" with a fixed argument list, no shell
                assert module not in forbidden_modules, f"{name}: import {module}"


def test_only_the_security_module_builds_http_clients():
    for name, tree in _trees("app", "scripts"):
        if name == SECURITY_MODULE:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                assert _dotted(node.func) not in {"httpx.Client", "httpx.AsyncClient", "httpx.get",
                                                  "httpx.post", "httpx.request", "httpx.stream"}, name
            if isinstance(node, ast.ImportFrom) and node.module == "httpx":
                assert not {alias.name for alias in node.names} & {"Client", "AsyncClient"}, name
            if isinstance(node, ast.Import | ast.ImportFrom):
                modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) \
                    else [node.module or ""]
                for module in modules:
                    assert not module.startswith(("requests", "urllib.request", "http.client",
                                                  "aiohttp")), f"{name}: {module}"


def test_connectors_only_get_through_their_client():
    for name, tree in _trees("app/connectors"):
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and _dotted(node.value) == "self._client":
                assert node.attr in {"get", "headers"}, f"{name}: self._client.{node.attr}"


def test_application_logging_goes_through_log_event():
    for name, tree in _trees("app"):
        if name == LOGGING_MODULE:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                receiver = _dotted(node.func.value)
                if receiver in {"logger", "logging", "log"} or receiver.endswith("logger"):
                    assert node.func.attr not in LOG_METHODS, f"{name}: {receiver}.{node.func.attr}"
            if isinstance(node, ast.Name):
                assert node.id != "print", f"{name}: print"


def _log_event_calls():
    for name, tree in _trees("app", "scripts"):
        parents = _parents(tree)
        handler_names = {node.name for node in ast.walk(tree)
                         if isinstance(node, ast.ExceptHandler) and node.name}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _dotted(node.func) == "log_event":
                yield name, node, parents, handler_names


def test_log_events_exist_to_be_checked():
    # 18 call sites at G2; the floor guards against the scan silently matching nothing.
    assert sum(1 for _ in _log_event_calls()) >= 18


def test_log_event_fields_are_never_credential_named():
    for name, call, _, _ in _log_event_calls():
        for keyword in call.keywords:
            assert keyword.arg is not None, f"{name}: **fields"
            assert not SENSITIVE_NAME.search(keyword.arg), f"{name}: {keyword.arg}"


def test_log_event_fields_carry_exception_classes_never_exceptions():
    for name, call, parents, handler_names in _log_event_calls():
        for keyword in call.keywords:
            for node in ast.walk(keyword.value):
                if not (isinstance(node, ast.Name) and node.id in handler_names):
                    continue
                call_node = parents.get(node)
                attribute = parents.get(call_node)
                assert isinstance(call_node, ast.Call) and _dotted(call_node.func) == "type" \
                    and isinstance(attribute, ast.Attribute) and attribute.attr == "__name__", \
                    f"{name}:{node.lineno}: {keyword.arg} uses {node.id} beyond type({node.id}).__name__"


def test_the_application_uses_no_textual_sql():
    for name, tree in _trees("app"):
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("sqlalchemy"):
                assert "text" not in {alias.name for alias in node.names}, f"{name}: import text"
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"exec_driver_sql", "text"} or _dotted(node) in {
                    "resp.text", "response.text"}, f"{name}: .{node.attr}"


def test_the_api_contract_has_no_credential_shaped_fields():
    schema = create_app(sessions=sessionmaker()).openapi()
    names = set()

    def collect(value: object) -> None:
        if isinstance(value, dict):
            names.update(value.get("properties", {}))
            names.update(parameter["name"] for parameter in value.get("parameters", [])
                         if isinstance(parameter, dict) and "name" in parameter)
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(schema)
    assert {"run_id", "source", "error_type"} <= names
    assert sorted(name for name in names if SENSITIVE_NAME.search(name)) == []


def test_credential_settings_are_hidden_from_repr():
    # Credentials only: service addresses such as mock_source_base_url stay visible.
    credential = re.compile(r"(?i)(password|passwd|secret|token|api_?key|credential|database_url|dsn)")
    sensitive = {name for name in Settings.model_fields if credential.search(name)}
    assert sensitive >= {"postgres_password", "database_url"}
    assert {name for name in sensitive if Settings.model_fields[name].repr} == set()
