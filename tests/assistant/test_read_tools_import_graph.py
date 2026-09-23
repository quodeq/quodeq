"""The read-tools modules import in one direction: facade -> scope/violations -> common.

Read from the source with ast (no import of the private modules), so the test
itself adds nothing to the private-import ratchet.
"""
from __future__ import annotations

import ast
from pathlib import Path

import quodeq.assistant.tools as tools_pkg

PKG = Path(tools_pkg.__file__).parent
PREFIX = "quodeq.assistant.tools"
MODULES = ("_read_tools", "_read_tools_scope", "_read_tools_violations", "_read_tools_common")


def _read_tools_imports(module: str) -> set[str]:
    tree = ast.parse((PKG / f"{module}.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if node.module == PREFIX:
            found.update(alias.name for alias in node.names)
        elif node.module.startswith(PREFIX + "."):
            found.add(node.module.removeprefix(PREFIX + "."))
    return found & set(MODULES)


def test_common_is_a_leaf():
    assert _read_tools_imports("_read_tools_common") == set()


def test_scope_imports_only_common():
    assert _read_tools_imports("_read_tools_scope") == {"_read_tools_common"}


def test_violations_imports_scope_and_common():
    assert _read_tools_imports("_read_tools_violations") == {"_read_tools_scope", "_read_tools_common"}


def test_facade_imports_its_parts_and_nothing_imports_the_facade():
    assert _read_tools_imports("_read_tools") == set(MODULES[1:])
    assert all("_read_tools" not in _read_tools_imports(part) for part in MODULES[1:])
