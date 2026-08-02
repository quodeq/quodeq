"""Find uses of watched symbols, resolved through the file's own imports.

``os.environ`` reaches a module under several names: a plain attribute access,
an aliased ``import os as o``, a bare ``environ`` from ``from os import
environ``, a renamed ``ge`` from ``getenv as ge``. A text search finds the
spelling you happened to think of; binding each reference back to its canonical
dotted name finds all of them, and that needs the import statements.

The rule that keeps it precise: a reference only counts when the file actually
imported the thing it refers to. A local variable named ``os`` is not the
standard library.
"""
from __future__ import annotations

import ast
import logging
from collections.abc import Iterable
from pathlib import Path

from quodeq.core.checks.model import SymbolUse
from quodeq.data.fs.import_graph import relative_python_files

_logger = logging.getLogger(__name__)


def _alias_map(tree: ast.AST) -> dict[str, str]:
    """``{local name: canonical dotted name}`` for everything the file imports.

    ``import os.path`` binds the name ``os``, not ``os.path`` -- so an unaliased
    dotted import maps its top package to itself, matching what Python does.
    Relative imports are skipped: watched symbols are library names, never
    first-party ones.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
                else:
                    top = alias.name.split(".", 1)[0]
                    aliases[top] = top
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            for alias in node.names:
                if alias.name == "*":
                    continue
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _dotted(node: ast.AST) -> str | None:
    """The dotted name of a pure ``Name``/``Attribute`` chain, else None."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _watched(dotted: str, aliases: dict[str, str], names: frozenset[str]) -> str | None:
    """The watched symbol *dotted* refers to, after alias resolution."""
    head, _, rest = dotted.partition(".")
    base = aliases.get(head)
    if base is None:
        return None  # never imported here, so not the symbol we are watching
    resolved = f"{base}.{rest}" if rest else base
    parts = resolved.split(".")
    # Longest prefix wins: os.environ.get is a use of os.environ.
    for depth in range(len(parts), 0, -1):
        candidate = ".".join(parts[:depth])
        if candidate in names:
            return candidate
    return None


def _uses_in_file(root: Path, rel: str, names: frozenset[str]) -> list[SymbolUse]:
    try:
        tree = ast.parse((root / rel).read_text(encoding="utf-8"), filename=rel)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as exc:
        _logger.debug("symbol uses: skipping %s (%s)", rel, exc)
        return []

    aliases = _alias_map(tree)
    if not aliases:
        return []
    seen: set[tuple[int, str]] = set()
    found: list[SymbolUse] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Name, ast.Attribute)):
            continue
        dotted = _dotted(node)
        if dotted is None:
            continue
        symbol = _watched(dotted, aliases, names)
        # ast.walk visits os.environ.get, os.environ and os in turn; the
        # dedupe below is what stops one expression counting three times.
        if symbol is None or (node.lineno, symbol) in seen:
            continue
        seen.add((node.lineno, symbol))
        found.append(SymbolUse(file=rel, line=node.lineno, symbol=symbol))
    return found


def build_symbol_uses(
    root: Path, files: Iterable[Path], names: frozenset[str],
) -> tuple[SymbolUse, ...]:
    """Every use of a *names* symbol in *files*, as canonical dotted names."""
    if not names:
        return ()
    root = Path(root).resolve()
    found: list[SymbolUse] = []
    for rel in relative_python_files(root, files):
        found.extend(_uses_in_file(root, rel, names))
    found.sort(key=lambda u: (u.file, u.line, u.symbol))
    return tuple(found)
