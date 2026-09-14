"""
E1 static boundary tests: transaction ownership, SQL safety, and logging hygiene.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REPOSITORIES_DIR = REPO / "app" / "persistence" / "repositories"


def _trees(directory: Path):
    for path in sorted(directory.glob("*.py")):
        yield path.name, ast.parse(path.read_text(encoding="utf-8"))


def _imported_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_repositories_never_own_transactions():
    forbidden = {"commit", "rollback", "begin", "begin_nested", "close"}
    for name, tree in _trees(REPOSITORIES_DIR):
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden, f"{name}: .{node.attr}"


def test_repositories_use_no_textual_sql():
    for name, tree in _trees(REPOSITORIES_DIR):
        imported = _imported_names(tree)
        assert "sqlalchemy.text" not in imported, name
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"exec_driver_sql", "text"}, f"{name}: .{node.attr}"


def test_repositories_do_not_log_or_print():
    for name, tree in _trees(REPOSITORIES_DIR):
        assert not any(module.split(".")[0] == "logging" for module in _imported_names(tree)), name
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id != "print", name


def test_repositories_have_no_broad_exception_handlers():
    for name, tree in _trees(REPOSITORIES_DIR):
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                assert node.type is not None, f"{name}: bare except"
                types = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
                for handler in types:
                    label = handler.id if isinstance(handler, ast.Name) else getattr(handler, "attr", "")
                    assert label not in {"Exception", "BaseException"}, f"{name}: except {label}"
