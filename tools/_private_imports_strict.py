"""Strict private-name rules for src/quodeq (rules 2-4 of the private-import gate).

Rule 2: a `_name` imported from another file is a violation, same directory
or not, relative import or not. Rule A in `_private_imports_rules.py`
already reports the cross-directory absolute case; this module adds the
same-directory absolute case and every relative one.

Rule 3: a `_name` listed in a module's `__all__` is a violation.

Rule 4: `mod._x` read through a module alias (`import quodeq.a.b as mod`,
`from quodeq.a import b`, `from . import b`) is a violation. So is a dotted
chain rooted at `quodeq` after a plain `import quodeq.a.b` (`quodeq.a.b._x`).
Instance attribute reads (`self._x`, `provider._x`) are not checked: too
many of them are a class reading its own state.

A private module (`_mod.py`) imported from inside its package stays legal
(rule 1, unchanged, enforced by rule B).

Applied to src/quodeq only; tests keep rules A/B and their ratchet.

Not checked: dynamic lookups (`getattr(mod, "_x")`) and `importlib`-based
access. Both read a name the AST never spells out.
"""
from __future__ import annotations

import ast
import functools
from pathlib import Path
from typing import Iterator

from _private_imports_rules import (
    FileCtx,
    Hit,
    dir_for_segments,
    is_private,
    make_hit,
    quodeq_segments,
    resolve_module_dir,
)


@functools.lru_cache(maxsize=None)
def _is_module_at(package_dir: Path, name: str) -> bool:
    """True if `name` is a module or package directly inside `package_dir`.

    Memoized: the same (package, name) pairs recur across ~1900 scanned files
    and the tree does not change during one gate run.
    """
    return (package_dir / f"{name}.py").exists() or (package_dir / name / "__init__.py").exists()


def _relative_base(ctx: FileCtx, node: ast.ImportFrom) -> Path:
    """The directory a relative `from` import resolves against."""
    base = ctx.importer_dir
    for _ in range(node.level - 1):
        base = base.parent
    return base.joinpath(*node.module.split(".")) if node.module else base


def _import_source(
    node: ast.ImportFrom, ctx: FileCtx, src_root: Path,
) -> tuple[Path, str, bool] | None:
    """(package dir the names come from, module label, is relative), or None
    for a non-quodeq absolute import."""
    if node.level:
        return _relative_base(ctx, node), "." * node.level + (node.module or ""), True
    segments = quodeq_segments(node.module or "")
    if segments is None:
        return None
    return dir_for_segments(src_root, segments), node.module or "", False


def _private_name_hits(node: ast.ImportFrom, ctx: FileCtx, src_root: Path) -> Iterator[Hit]:
    """Rule 2 cases rule A lets through: relative and same-directory imports."""
    source = _import_source(node, ctx, src_root)
    if source is None:
        return
    package_dir, module, relative = source
    if not relative:
        owner = resolve_module_dir(src_root, quodeq_segments(module) or [])
        if owner != ctx.importer_dir:
            return  # rule A already reports the cross-directory case
    for alias in node.names:
        if is_private(alias.name) and not _is_module_at(package_dir, alias.name):
            yield make_hit(ctx, node.lineno, "private-name", module, alias.name)


def _all_value_elts(node: ast.stmt) -> list[ast.expr] | None:
    """The list/tuple elements of an `__all__` statement (`=`, annotated
    `=`, or `+=`), or None if `node` is not one."""
    if isinstance(node, ast.Assign):
        targets, value = node.targets, node.value
    elif isinstance(node, ast.AnnAssign):
        targets, value = ([node.target] if node.target is not None else []), node.value
    elif isinstance(node, ast.AugAssign):
        targets, value = [node.target], node.value
    else:
        return None
    if value is None or not isinstance(value, (ast.List, ast.Tuple)):
        return None
    if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
        return None
    return list(value.elts)


def _export_hits(tree: ast.Module, ctx: FileCtx) -> Iterator[Hit]:
    """Rule 3: private names listed in `__all__` (`=`, annotated `=`, or `+=`)."""
    for node in tree.body:
        elts = _all_value_elts(node)
        if elts is None:
            continue
        for elt in elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str) and is_private(elt.value):
                yield make_hit(ctx, elt.lineno, "private-export", "__all__", elt.value)


def _module_aliases(tree: ast.Module, ctx: FileCtx, src_root: Path) -> dict[str, str]:
    """Local names bound to a quodeq module in this file -> the module label."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname and quodeq_segments(alias.name) is not None:
                    aliases[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom):
            source = _import_source(node, ctx, src_root)
            if source is None:
                continue
            package_dir, module, _ = source
            for alias in node.names:
                if _is_module_at(package_dir, alias.name):
                    sep = "" if module.endswith(".") else "."
                    aliases[alias.asname or alias.name] = f"{module}{sep}{alias.name}"
    return aliases


def _attr_hits(tree: ast.Module, ctx: FileCtx, src_root: Path) -> Iterator[Hit]:
    """Rule 4: `alias._x` where `alias` is bound to a quodeq module."""
    aliases = _module_aliases(tree, ctx, src_root)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and is_private(node.attr)
                and isinstance(node.value, ast.Name) and node.value.id in aliases):
            yield make_hit(ctx, node.lineno, "private-attr", aliases[node.value.id], node.attr)


def _has_plain_quodeq_import(tree: ast.Module) -> bool:
    """True if the file has an `import quodeq[.a.b]` with no `as` alias."""
    return any(
        isinstance(node, ast.Import)
        and any(alias.asname is None and quodeq_segments(alias.name) is not None for alias in node.names)
        for node in ast.walk(tree)
    )


def _flatten_attr_chain(node: ast.expr) -> list[str] | None:
    """`[quodeq, a, b, _x]` for `quodeq.a.b._x`, or None off a non-name root."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    parts.reverse()
    return parts


def _chain_hits(tree: ast.Module, ctx: FileCtx) -> Iterator[Hit]:
    """Rule 4 (dotted form): `quodeq.a.b._x` after a plain `import quodeq.a.b`."""
    if not _has_plain_quodeq_import(tree):
        return
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and is_private(node.attr)):
            continue
        chain = _flatten_attr_chain(node)
        if chain is None or len(chain) < 3 or chain[0] != "quodeq":
            continue
        yield make_hit(ctx, node.lineno, "private-attr", ".".join(chain[:-1]), chain[-1])


def strict_hits(tree: ast.Module, ctx: FileCtx, src_root: Path) -> Iterator[Hit]:
    """Every rule 2-4 violation in one parsed src file."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            yield from _private_name_hits(node, ctx, src_root)
    yield from _export_hits(tree, ctx)
    yield from _attr_hits(tree, ctx, src_root)
    yield from _chain_hits(tree, ctx)
