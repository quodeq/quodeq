#!/usr/bin/env python3
"""Parameter-count ratchet: flag functions with more than 5 parameters.

Standard M-MOD-4: functions have at most 5 parameters; more than that
means the caller should pass an options object (a frozen dataclass here).
Existing violations are grandfathered in tools/param_baseline.txt so the
gate runs green today while preventing NEW ones. Regenerate the baseline
(only with justification) via:
    python tools/check_params.py --update-baseline

Scans src/quodeq/**/*.py with `ast`, excluding vendored/generated dirs
(see tools/_ratchet.py:EXCLUDE_DIRS). Positional, keyword-only, *args and
**kwargs all count; `self`/`cls` on methods do not. Keys are
`relpath:qualname` (e.g. `src/quodeq/x.py:Foo.m`, `src/quodeq/y.py:outer.inner`),
not line-keyed, so edits above a grandfathered function do not churn the
baseline. JS parameter counts are enforced separately by
src/quodeq/ui/eslint.hygiene.config.js (`max-params`).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterator

import _ratchet

MAX_PARAMS = 5
REPO_ROOT = Path(__file__).resolve().parent.parent
PY_ROOT = REPO_ROOT / "src" / "quodeq"
BASELINE_PATH = Path(__file__).resolve().parent / "param_baseline.txt"

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
Violation = tuple[str, str, int]  # (relpath, qualname, count)

_IMPLICIT_FIRST = frozenset({"self", "cls"})


def _is_staticmethod(fn: FunctionNode) -> bool:
    return any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in fn.decorator_list)


def param_count(fn: FunctionNode, *, is_method: bool) -> int:
    """Number of parameters a caller has to supply or think about."""
    a = fn.args
    names = [p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)]
    if a.vararg is not None:
        names.append(a.vararg.arg)
    if a.kwarg is not None:
        names.append(a.kwarg.arg)
    if is_method and not _is_staticmethod(fn) and names and names[0] in _IMPLICIT_FIRST:
        names = names[1:]
    return len(names)


def iter_functions(tree: ast.Module) -> Iterator[tuple[str, FunctionNode, bool]]:
    """Yield (qualname, node, is_method) for every def/async def in tree.

    `is_method` is True only for functions whose enclosing scope is a class
    body (possibly through if/try blocks), not for functions nested inside
    a method.
    """
    def visit(node: ast.AST, prefix: str, in_class: bool) -> Iterator[tuple[str, FunctionNode, bool]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                yield from visit(child, f"{prefix}{child.name}.", True)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}{child.name}"
                yield qual, child, in_class
                yield from visit(child, f"{qual}.", False)
            else:
                yield from visit(child, prefix, in_class)

    yield from visit(tree, "", False)


def _scan() -> list[Violation]:
    """Return sorted (relpath, qualname, count) for every over-limit function."""
    found: list[Violation] = []
    for py in _ratchet.iter_python_files(PY_ROOT):
        text = _ratchet.read_text(py)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as e:
            print(f"warning: skipping {py}: {e}", file=sys.stderr)
            continue
        rel = py.relative_to(REPO_ROOT).as_posix()
        for qual, fn, is_method in iter_functions(tree):
            n = param_count(fn, is_method=is_method)
            if n > MAX_PARAMS:
                found.append((rel, qual, n))
    return sorted(found)


def violation_key(v: Violation) -> str:
    """Identity for a violation, independent of its current count."""
    relpath, qualname, _count = v
    return f"{relpath}:{qualname}"


def collect_violations() -> list[str]:
    """Return baseline keys for all current violations."""
    return sorted({violation_key(v) for v in _scan()})


def load_baseline(path: Path = BASELINE_PATH) -> set[str]:
    return _ratchet.load_baseline(path)


def write_baseline(path: Path = BASELINE_PATH) -> int:
    header = (
        "# Grandfathered parameter-count violations (functions with more than 5\n"
        "# parameters, self/cls excluded). Do NOT add entries without\n"
        "# justification -- the goal is to burn this list down, not grow it.\n"
        "# Regenerate intentionally: python tools/check_params.py --update-baseline\n"
    )
    return _ratchet.write_baseline(path, header, collect_violations())


def main(argv: list[str] | None = None) -> int:
    return _ratchet.run_cli(
        argv,
        script_name="check_params.py",
        baseline_path=BASELINE_PATH,
        scan=_scan,
        violation_key=violation_key,
        update_baseline=write_baseline,
        describe=lambda v: f"{v[0]}:{v[1]} has {v[2]} parameters (max {MAX_PARAMS})",
        noun="parameter-count",
    )


if __name__ == "__main__":
    sys.exit(main())
