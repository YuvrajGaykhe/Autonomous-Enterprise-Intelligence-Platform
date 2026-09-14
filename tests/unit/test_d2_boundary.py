"""
D2 boundary tests: failure classification, purity, dependencies, determinism.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from d2_support import mixed_customer_fingerprint

import app.validation as validation
from app.normalization import ErrorCode, NormalizationError
from app.validation import DATA_FAILURE_CODES, SYSTEM_FAILURE_CODES, is_data_failure

REPO = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).resolve().parent
D2_DIR = REPO / "app" / "validation"


def test_public_api_exports():
    for name in validation.__all__:
        assert hasattr(validation, name), name


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------


def test_every_d1_error_code_is_classified_exactly_once():
    assert DATA_FAILURE_CODES | SYSTEM_FAILURE_CODES == set(ErrorCode)
    assert not DATA_FAILURE_CODES & SYSTEM_FAILURE_CODES


def test_system_failure_codes_are_the_non_data_codes():
    assert SYSTEM_FAILURE_CODES == {ErrorCode.UNSUPPORTED_SOURCE, ErrorCode.UNSUPPORTED_ENTITY,
                                    ErrorCode.UNEXPECTED_ERROR}


@pytest.mark.parametrize("code", list(ErrorCode))
def test_is_data_failure_follows_classification(code):
    assert is_data_failure(NormalizationError("x", code=code)) is (code in DATA_FAILURE_CODES)


def test_non_normalization_errors_are_never_data_failures():
    assert is_data_failure(ValueError("x")) is False
    error = NormalizationError("x", code=ErrorCode.INVALID_TYPE)
    error.code = "UNKNOWN_FUTURE_CODE"
    assert is_data_failure(error) is False


# ---------------------------------------------------------------------------
# Purity and dependencies
# ---------------------------------------------------------------------------

FORBIDDEN_MODULE_PREFIXES = (
    "sqlalchemy", "psycopg2", "alembic", "httpx", "requests", "urllib3", "aiohttp",
    "fastapi", "starlette", "uvicorn", "pydantic_settings", "dotenv", "openai", "anthropic",
    "langchain", "neo4j", "app.persistence", "app.connectors", "app.core", "app.api",
    "app.ingestion",
)

_IMPORT_SCRIPT = """
import json, sys
sys.path[:0] = [{repo!r}, {tests!r}]
import app.validation as validation
import app.normalization as normalization
loaded = [validation.default_validation_config.cache_info().currsize,
          normalization.default_config.cache_info().currsize]
from d2_support import mixed_customer_fingerprint
mixed_customer_fingerprint()
print(json.dumps({{"loaded_at_import": loaded, "modules": sorted(sys.modules)}}))
"""


def _run_python(code: str, **env: str) -> str:
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=TESTS_DIR,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **env},
    ).stdout


def test_runtime_import_closure_has_no_database_network_llm_or_connector_modules():
    result = json.loads(_run_python(_IMPORT_SCRIPT.format(repo=str(REPO), tests=str(TESTS_DIR))))
    leaked = [m for m in result["modules"] if m.startswith(FORBIDDEN_MODULE_PREFIXES)]
    assert leaked == []
    assert result["loaded_at_import"] == [0, 0]
    app_modules = {m for m in result["modules"] if m.startswith("app.")}
    assert all(m.startswith(("app.validation", "app.normalization", "app.schemas"))
               for m in app_modules)


ALLOWED_IMPORTS = {
    "__future__", "collections", "dataclasses", "datetime", "decimal", "enum", "functools",
    "math", "pathlib", "re", "types", "typing", "uuid", "yaml", "pydantic",
}
FORBIDDEN_NAMES = {"open", "print", "input", "eval", "exec", "__import__"}
FORBIDDEN_ATTRIBUTES = {"environ", "getenv", "now", "utcnow", "today", "uuid1", "uuid4",
                        "random", "urandom", "system", "popen", "sleep"}


def _trees():
    for path in sorted(D2_DIR.glob("*.py")):
        yield path.name, ast.parse(path.read_text(encoding="utf-8"))


def test_d2_imports_are_allowlisted():
    for name, tree in _trees():
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, name
                modules = [node.module]
            for module in modules:
                if module.split(".")[0] == "app":
                    assert module.startswith(("app.validation", "app.normalization",
                                              "app.schemas.canonical")), f"{name}: {module}"
                else:
                    assert module.split(".")[0] in ALLOWED_IMPORTS, f"{name}: {module}"


def test_d2_has_no_side_effecting_or_nondeterministic_calls():
    for name, tree in _trees():
        for node in ast.walk(tree):
            assert not isinstance(node, (ast.Global, ast.Nonlocal)), name
            if isinstance(node, ast.Name):
                assert node.id not in FORBIDDEN_NAMES, f"{name}: {node.id}"
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_ATTRIBUTES, f"{name}: .{node.attr}"


def test_d2_has_no_broad_exception_handlers():
    broad = {"Exception", "BaseException"}
    for name, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            assert node.type is not None, f"{name}: bare except"
            types = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
            for handler_type in types:
                label = handler_type.id if isinstance(handler_type, ast.Name) else handler_type.attr
                assert label not in broad, f"{name}: except {label}"


def test_only_memoization_is_the_immutable_default_config():
    cached = []
    for name, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    target = decorator.func if isinstance(decorator, ast.Call) else decorator
                    label = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
                    if label in {"lru_cache", "cache", "cached_property"}:
                        cached.append((name, node.name))
    assert cached == [("config.py", "default_validation_config")]


def test_filesystem_access_is_confined_to_the_config_loader():
    for name, tree in _trees():
        if name == "config.py":
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"read_text", "read_bytes", "write_text", "glob"}, name


# ---------------------------------------------------------------------------
# Determinism across processes
# ---------------------------------------------------------------------------

_FINGERPRINT_SCRIPT = """
import sys
sys.path[:0] = [{repo!r}, {tests!r}]
from d2_support import mixed_customer_fingerprint
print(mixed_customer_fingerprint())
"""


@pytest.mark.parametrize("hash_seed", ["0", "987654"])
def test_results_are_identical_across_processes(hash_seed):
    code = _FINGERPRINT_SCRIPT.format(repo=str(REPO), tests=str(TESTS_DIR))
    assert _run_python(code, PYTHONHASHSEED=hash_seed).strip() == mixed_customer_fingerprint()
