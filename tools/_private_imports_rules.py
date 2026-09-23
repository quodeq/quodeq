"""AST rules for tools/check_private_imports.py: rule A and rule B.

Rule A (private-name): `from quodeq.<pkg...>.<mod> import _x` (a name with a
single leading underscore; dunders are not private) is a violation unless
the importing file's directory is the package directory that owns `<mod>`
(same package = same directory; a package's own `__init__` counts as that
directory).

Rule B (private-module): `from quodeq.<pkg...>._mod import y`,
`from quodeq.<pkg...> import _mod`, and `import quodeq.<pkg...>._mod [as m]`
are a violation unless the importing file lives in the package that
directly contains `_mod`. A private package anywhere in the dotted path
(`quodeq.pkg._sub.mod`) counts the same way for `_sub`.

Relative imports (`from . import x`, `from ._mod import _x`) are same-package
by construction and are never violations under rules A/B. The src scan adds
rules 2-4 on top through `scan_tree(..., extra=...)`; see
tools/_private_imports_strict.py.

Distinguishing the two rules for `from quodeq.<pkg...> import _x` (no `.mod`
in the dotted path) needs a filesystem check: if `_x` is itself an existing
submodule/subpackage of `<pkg...>`, it is rule B (a private module hiding
behind a plain name); otherwise it is rule A (a private name, typically
re-exported by the package's `__init__`).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

import _ratchet


@dataclass(frozen=True, slots=True)
class Hit:
    """One private-import violation: where it is and how it is keyed."""

    path: Path
    line: int
    kind: str
    module: str
    name: str
    key: str
    source: str


@dataclass(frozen=True, slots=True)
class _Classification:
    """A triggered rule and the directory that would have made it exempt."""

    kind: str
    required_dir: Path


@dataclass(frozen=True, slots=True)
class FileCtx:
    """The per-file facts every violation in it shares."""

    path: Path
    rel: str
    importer_dir: Path
    source_lines: list[str]


# A per-file rule set run after rules A/B (see tools/_private_imports_strict.py).
ExtraRule = Callable[[ast.Module, FileCtx, Path], Iterable[Hit]]


def is_private(name: str) -> bool:
    """True for a single-leading-underscore name; dunders are not private."""
    return name.startswith("_") and not name.startswith("__")


def quodeq_segments(dotted: str) -> list[str] | None:
    """Dotted path components after `quodeq`, or None if not quodeq-rooted."""
    if dotted == "quodeq":
        return []
    if dotted.startswith("quodeq."):
        return dotted[len("quodeq."):].split(".")
    return None


def dir_for_segments(src_root: Path, segments: Sequence[str]) -> Path:
    """The directory a dotted path's segments would live under, if it were
    a package: `src_root/seg0/seg1/...`."""
    return src_root.joinpath(*segments) if segments else src_root


def resolve_module_dir(src_root: Path, segments: Sequence[str]) -> Path:
    """Directory that owns a `from`-imported module's dotted path: its own
    directory when it is a package (`__init__` counts as that directory),
    else the directory holding its leaf module file."""
    if not segments:
        return src_root
    pkg_dir = dir_for_segments(src_root, segments)
    if pkg_dir.is_dir():
        return pkg_dir
    return dir_for_segments(src_root, segments[:-1])


def submodule_exists(src_root: Path, segments: Sequence[str], name: str) -> bool:
    """True if `name` is an existing submodule/subpackage of the package at
    `segments` (tells `from quodeq.pkg import _mod` apart from a private
    name re-exported by `pkg`'s `__init__`)."""
    pkg_dir = dir_for_segments(src_root, segments)
    if not pkg_dir.is_dir():
        return False
    return (pkg_dir / f"{name}.py").exists() or (pkg_dir / name / "__init__.py").exists()


def _first_private_index(segments: Sequence[str]) -> int | None:
    """Index of the first private segment in a dotted path, or None."""
    for index, segment in enumerate(segments):
        if is_private(segment):
            return index
    return None


def _classify_from_import(
    src_root: Path, segments: Sequence[str], imported_name: str,
) -> _Classification | None:
    """Rule A/B outcome for one name imported by a `from` statement, or
    None if neither rule is triggered."""
    if is_private(imported_name):
        if submodule_exists(src_root, segments, imported_name):
            return _Classification("private-module", dir_for_segments(src_root, segments))
        return _Classification("private-name", resolve_module_dir(src_root, segments))
    index = _first_private_index(segments)
    if index is None:
        return None
    return _Classification("private-module", dir_for_segments(src_root, segments[:index]))


def _classify_plain_import(src_root: Path, segments: Sequence[str]) -> _Classification | None:
    """Rule B outcome for `import quodeq.<pkg...>[.mod]`, or None."""
    index = _first_private_index(segments)
    if index is None:
        return None
    return _Classification("private-module", dir_for_segments(src_root, segments[:index]))


def _source_line(ctx: FileCtx, lineno: int) -> str:
    return ctx.source_lines[lineno - 1].strip() if lineno <= len(ctx.source_lines) else ""


def make_hit(ctx: FileCtx, line: int, kind: str, module: str, name: str) -> Hit:
    """A Hit keyed `relpath:line:kind:module.name`, carrying its source line."""
    key = f"{ctx.rel}:{line}:{kind}:{module}.{name}"
    return Hit(path=ctx.path, line=line, kind=kind, module=module, name=name, key=key,
               source=_source_line(ctx, line))


def _from_import_hits(node: ast.ImportFrom, ctx: FileCtx, src_root: Path) -> Iterator[Hit]:
    if node.level or node.module is None:
        return  # relative import: same-package by construction, never a violation
    segments = quodeq_segments(node.module)
    if segments is None:
        return
    for alias in node.names:
        if alias.name == "*":
            continue
        cls = _classify_from_import(src_root, segments, alias.name)
        if cls is None or ctx.importer_dir == cls.required_dir:
            continue
        yield make_hit(ctx, node.lineno, cls.kind, node.module, alias.name)


def _plain_import_hits(node: ast.Import, ctx: FileCtx, src_root: Path) -> Iterator[Hit]:
    for alias in node.names:
        segments = quodeq_segments(alias.name)
        if segments is None:
            continue
        cls = _classify_plain_import(src_root, segments)
        if cls is None or ctx.importer_dir == cls.required_dir:
            continue
        name = alias.asname or segments[-1]
        yield make_hit(ctx, node.lineno, cls.kind, alias.name, name)


def _file_hits(
    path: Path, rel: str, src_root: Path, text: str, extra: ExtraRule | None,
) -> list[Hit]:
    """Return every rule A/B violation in one already-read source file."""
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []
    ctx = FileCtx(path=path, rel=rel, importer_dir=path.parent, source_lines=text.splitlines())
    found: list[Hit] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.extend(_from_import_hits(node, ctx, src_root))
        elif isinstance(node, ast.Import):
            found.extend(_plain_import_hits(node, ctx, src_root))
    if extra is not None:
        found.extend(extra(tree, ctx, src_root))
    return found


def scan_tree(
    root: Path, src_root: Path, repo_root: Path, extra: ExtraRule | None = None,
) -> list[Hit]:
    """Return every rule A/B violation under `root`.

    `src_root` is always the `src/quodeq` package tree (the anchor rule A/B
    directories are resolved against), even when `root` is `tests/`.
    `repo_root` is used only to compute the repo-relative key.
    """
    hits: list[Hit] = []
    for py in _ratchet.iter_python_files(root):
        text = _ratchet.read_text(py)
        if text is None:
            continue
        rel = py.relative_to(repo_root).as_posix()
        hits.extend(_file_hits(py, rel, src_root, text, extra))
    return sorted(hits, key=lambda h: h.key)
