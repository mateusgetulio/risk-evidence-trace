from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src" / "decision"

ALLOWED_STDLIB = {
    "__future__",
    "collections",
    "dataclasses",
    "datetime",
    "enum",
    "hashlib",
    "json",
    "typing",
}


def imported_roots(source: str) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                roots.add("decision")
            elif node.module:
                roots.add(node.module.split(".")[0])
    return roots


def violations(source: str) -> set[str]:
    return imported_roots(source) - ALLOWED_STDLIB - {"decision"}


FORBIDDEN_CALLS = {"open", "__import__", "exec", "eval", "compile", "print", "input"}


def forbidden_calls(source: str) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in FORBIDDEN_CALLS
    }


def test_decision_package_imports_only_pure_modules() -> None:
    files = sorted(SOURCE_DIR.rglob("*.py"))
    assert files
    for path in files:
        assert violations(path.read_text()) == set(), path.name
        assert forbidden_calls(path.read_text()) == set(), path.name


def test_checker_flags_io_builtins() -> None:
    for bad in ("open('x')", "__import__('os')", "print(1)", "eval('1')"):
        assert forbidden_calls(bad) != set()


def test_checker_flags_framework_and_io_imports() -> None:
    for bad in ("fastapi", "sqlalchemy", "os", "socket", "requests", "pathlib", "logging"):
        assert violations(f"import {bad}") == {bad}
        assert violations(f"from {bad}.sub import x") == {bad}


def test_forbidden_frameworks_are_not_loaded_by_the_engine() -> None:
    code = (
        "import sys, decision;"
        "bad = {'fastapi', 'sqlalchemy', 'strawberry'} & set(sys.modules);"
        "sys.exit(1 if bad else 0)"
    )
    env = {**os.environ, "PYTHONPATH": str(SOURCE_DIR.parent)}
    result = subprocess.run([sys.executable, "-c", code], env=env, check=False)
    assert result.returncode == 0
