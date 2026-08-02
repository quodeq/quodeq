"""Build an :class:`ImportGraph` from a project's source files.

The checkers in ``core/checks`` are pure functions over the graph; this is the
one place that touches the disk for them.

Parsing goes through ``ast`` rather than a regex. A regex that misses an
import fails silently in the worst direction: the checker then reports the
dependency as absent. A file that will not parse contributes no edges at all,
which is visibly incomplete rather than quietly wrong.

Python only for now. Source in other languages simply yields no edges, so a
mixed repo is judged on its Python and stays quiet about the rest.
"""
from __future__ import annotations

import ast
import logging
from collections.abc import Iterable
from pathlib import Path

from quodeq.core.checks.model import ImportEdge, ImportGraph

_logger = logging.getLogger(__name__)
_PY_SUFFIXES = (".py", ".pyi")


def _relative_python_files(root: Path, files: Iterable[Path]) -> list[str]:
    """Repo-relative posix paths of the readable Python files inside *root*.

    Paths outside *root* are dropped: a caller-supplied file list is not a
    licence to read anywhere on the disk.
    """
    out: list[str] = []
    for raw in files:
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        if path.suffix not in _PY_SUFFIXES:
            continue
        try:
            rel = path.resolve().relative_to(root)
        except (ValueError, OSError):
            continue
        if path.is_file():
            out.append(rel.as_posix())
    return sorted(set(out))


def _package_roots(root: Path, rel_files: Iterable[str]) -> tuple[set[str], set[str]]:
    """Return (first-party package names, package-root dirs relative to *root*).

    A package is the topmost directory in a file's ancestry that still has an
    ``__init__.py``; its parent is the directory imports resolve against. That
    makes ``src/`` layouts work without naming ``src`` as a package.
    """
    names: set[str] = set()
    roots: set[str] = set()
    for rel in rel_files:
        parts = Path(rel).parts[:-1]
        topmost: int | None = None
        for depth in range(len(parts), 0, -1):
            if (root.joinpath(*parts[:depth]) / "__init__.py").is_file():
                topmost = depth
            else:
                break
        if topmost is None:
            continue
        names.add(parts[topmost - 1])
        roots.add("/".join(parts[: topmost - 1]))
    return names, roots


def _module_exists(root: Path, package_roots: set[str], module: str) -> bool:
    """True when *module* names a first-party file or package on disk."""
    tail = module.replace(".", "/")
    for prefix in package_roots:
        base = root / prefix if prefix else root
        if (base / f"{tail}.py").is_file() or (base / tail / "__init__.py").is_file():
            return True
    return False


def _own_package(rel: str, package_roots: set[str]) -> str | None:
    """The dotted package *containing* the file at *rel*.

    This is what a single leading dot resolves against: for ``a/b/c.py`` it is
    ``a.b``, and for ``a/b/__init__.py`` it is ``a.b`` as well, since that file
    *is* the package.
    """
    path = Path(rel)
    segments = list(path.parts)
    segments[-1] = path.stem
    is_init = segments[-1] == "__init__"
    if is_init:
        segments.pop()
    for prefix in sorted(package_roots, key=len, reverse=True):
        depth = len(Path(prefix).parts) if prefix else 0
        if prefix and "/".join(segments[:depth]) != prefix:
            continue
        remainder = segments[depth:]
        if not remainder:
            continue
        own = remainder if is_init else remainder[:-1]
        return ".".join(own) if own else None
    return None


def _from_import_base(node: ast.ImportFrom, own_package: str | None) -> str | None:
    """Absolute module a ``from ... import`` refers to, resolving relative levels.

    An unresolvable relative import (no known package for the file, or more
    dots than it has parents) yields None: an edge pointing at the wrong module
    is worse than a missing one.
    """
    if not node.level:
        return node.module or None
    if own_package is None:
        return None
    segments = own_package.split(".")
    if node.level > 1:
        segments = segments[: -(node.level - 1)]
    if not segments:
        return None
    base = ".".join(segments)
    return f"{base}.{node.module}" if node.module else base


def _edges_for_file(
    root: Path, rel: str, package_roots: set[str],
) -> list[ImportEdge]:
    """Parse one file into import edges (empty on any read/parse failure)."""
    try:
        tree = ast.parse((root / rel).read_text(encoding="utf-8"), filename=rel)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as exc:
        _logger.debug("import graph: skipping %s (%s)", rel, exc)
        return []

    own = _own_package(rel, package_roots)
    seen: set[tuple[str, int]] = set()
    edges: list[ImportEdge] = []

    def add(module: str | None, line: int) -> None:
        if not module or (module, line) in seen:
            return
        seen.add((module, line))
        edges.append(ImportEdge(file=rel, line=line, module=module))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            base = _from_import_base(node, own)
            if not base:
                continue
            # ``from app.utils import text`` names a module when app/utils/text
            # exists, and an attribute of app.utils when it doesn't. Prefer the
            # module: that is the edge the graph can actually be traversed on.
            for alias in node.names:
                candidate = f"{base}.{alias.name}"
                if alias.name != "*" and _module_exists(root, package_roots, candidate):
                    add(candidate, node.lineno)
                else:
                    add(base, node.lineno)
    return edges


def build_import_graph(root: Path, files: Iterable[Path]) -> ImportGraph:
    """Parse *files* under *root* into an :class:`ImportGraph`.

    *files* is supplied by the caller (the analysis pipeline already knows the
    project's source files and its ignore rules) so this module never walks the
    tree or re-implements ignore handling.
    """
    root = Path(root).resolve()
    rel_files = _relative_python_files(root, files)
    if not rel_files:
        return ImportGraph()
    first_party, package_roots = _package_roots(root, rel_files)
    edges: list[ImportEdge] = []
    for rel in rel_files:
        edges.extend(_edges_for_file(root, rel, package_roots))
    return ImportGraph(edges=tuple(edges), first_party=frozenset(first_party))
