"""
F1 static boundary tests: the API layer never bypasses D1/D2/E1 and stays log/SQL safe.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API_DIR = REPO / "app" / "api"


def _trees():
    for path in sorted(API_DIR.rglob("*.py")):
        yield str(path.relative_to(REPO)), ast.parse(path.read_text(encoding="utf-8"))


def _imported_modules(tree: ast.AST) -> set[str]:
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def test_api_modules_exist():
    assert {name for name, _ in _trees()} >= {
        "app/api/errors.py", "app/api/request_id.py", "app/api/dependencies.py",
        "app/api/v1/router.py", "app/api/v1/health.py", "app/api/v1/schemas.py",
    }


def test_api_never_normalizes_validates_or_reads_source_schemas_itself():
    forbidden = ("app.normalization", "app.validation", "app.schemas.source",
                 "app.ingestion.batch", "app.ingestion.reconciliation",
                 "app.persistence.repositories.canonical", "app.persistence.repositories.raw")
    for name, tree in _trees():
        for module in _imported_modules(tree):
            assert not module.startswith(forbidden), f"{name}: {module}"


def test_api_uses_no_textual_sql_and_does_not_print():
    for name, tree in _trees():
        assert "sqlalchemy.text" not in _imported_modules(tree), name
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"exec_driver_sql", "text"}, f"{name}: .{node.attr}"
            if isinstance(node, ast.Name):
                assert node.id != "print", name


def test_api_has_no_broad_exception_handlers():
    for name, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                assert node.type is not None, f"{name}: bare except"
                types = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
                for handler in types:
                    label = handler.id if isinstance(handler, ast.Name) else getattr(handler, "attr", "")
                    assert label not in {"Exception", "BaseException"}, f"{name}: except {label}"
