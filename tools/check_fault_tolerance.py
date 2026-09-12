#!/usr/bin/env python3
"""Fault-tolerance ratchet: flag bare/empty/overly-broad exception handlers.

Existing violations are grandfathered via tools/fault_tolerance_baseline.txt
so the gate runs green in CI today while preventing NEW violations.
Regenerate the baseline (only with justification) via:
    python tools/check_fault_tolerance.py --update-baseline

Entries are line-keyed (relpath:lineno:kind), so an unrelated line-count
change elsewhere in a file can shift existing entries. Prefer hand-editing
the baseline (update the shifted line number) over blind --update-baseline
regeneration, which can silently absorb a genuinely new violation
introduced in the same change.

Scans src/quodeq/**/*.py (vendored/generated dirs excluded; tests/ and
JS/TS are out of scope for this ratchet, see the cycle 1 design doc) with
`ast` for four kinds of violation:
  - bare-except:  `except:` with no type at all
  - empty-except: the handler's entire body is `pass`, an ellipsis
    (`...`), or a docstring-only body
  - broad-except: catches Exception/BaseException (directly, via a
    qualified attribute, or inside a tuple of types) without re-raising
  - suppress:     `with contextlib.suppress(...):` (or `with suppress(...):`,
    or any `X.suppress(...)`) -- semantically an except-and-pass, just
    spelled as a context manager instead of a try/except, so it is caught
    the same way `broad-except`/`empty-except` are: grandfathered by line,
    not narrowed by the suppressed types (that is a judgment call, not a
    mechanical one)
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import _ratchet
from _ratchet import read_text as _read_text

REPO_ROOT = Path(__file__).resolve().parent.parent
PY_ROOT = REPO_ROOT / "src" / "quodeq"
BASELINE_PATH = Path(__file__).resolve().parent / "fault_tolerance_baseline.txt"

_BROAD_NAMES = {"Exception", "BaseException"}


def _is_broad_type(type_node: ast.expr) -> bool:
    """True if *type_node* is, or contains, Exception/BaseException."""
    if isinstance(type_node, ast.Tuple):
        return any(_is_broad_type(elt) for elt in type_node.elts)
    if isinstance(type_node, ast.Name):
        return type_node.id in _BROAD_NAMES
    if isinstance(type_node, ast.Attribute):
        return type_node.attr in _BROAD_NAMES
    return False


def _is_empty_body(body: list[ast.stmt]) -> bool:
    return all(
        isinstance(s, ast.Pass)
        or (
            isinstance(s, ast.Expr)
            and isinstance(s.value, ast.Constant)
            and (s.value.value is Ellipsis or isinstance(s.value.value, str))
        )
        for s in body
    )


def _reraises(body: list[ast.stmt]) -> bool:
    return any(isinstance(stmt, ast.Raise) for stmt in body)


def _is_suppress_call(node: ast.expr) -> bool:
    """True for `suppress(...)` or `contextlib.suppress(...)` (or any
    `X.suppress(...)`, since a module can be imported under an alias)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "suppress"
    if isinstance(func, ast.Attribute):
        return func.attr == "suppress"
    return False


def _with_has_suppress(node: ast.With | ast.AsyncWith) -> bool:
    return any(_is_suppress_call(item.context_expr) for item in node.items)


def _handler_kind(handler: ast.ExceptHandler) -> str | None:
    """Return the violation kind for one except-handler, or None if it's fine."""
    if handler.type is None:
        return "bare-except"
    if _is_empty_body(handler.body):
        return "empty-except"
    if _is_broad_type(handler.type) and not _reraises(handler.body):
        return "broad-except"
    return None


def _relpath(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _scan_python() -> list[tuple[str, int, str]]:
    """Return (relpath, lineno, kind) violations for src/quodeq/**/*.py."""
    found: list[tuple[str, int, str]] = []
    for py in _ratchet.iter_python_files(PY_ROOT):
        text = _read_text(py)
        if text is None:
            continue
        rel = _relpath(py)
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as e:
            print(f"warning: skipping {py}: {e}", file=sys.stderr)
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                kind = _handler_kind(node)
                if kind is not None:
                    found.append((rel, node.lineno, kind))
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                if _with_has_suppress(node):
                    found.append((rel, node.lineno, "suppress"))
    return found


def _scan() -> list[tuple[str, int, str]]:
    """Return all (relpath, lineno, kind) fault-tolerance violations, sorted."""
    return sorted(_scan_python())


def violation_key(v: tuple[str, int, str]) -> str:
    """Identity for a violation: relpath:lineno:kind."""
    relpath, lineno, kind = v
    return f"{relpath}:{lineno}:{kind}"


def collect_violations() -> list[str]:
    """Return baseline keys for all current fault-tolerance violations."""
    return sorted({violation_key(v) for v in _scan()})


def load_baseline(path: Path = BASELINE_PATH) -> set[str]:
    """Return the set of grandfathered violation keys (empty if no baseline)."""
    return _ratchet.load_baseline(path)


def write_baseline(path: Path = BASELINE_PATH) -> int:
    """Write current violations to the baseline file; return the count."""
    header = (
        "# Grandfathered fault-tolerance violations (bare/empty/overly-broad\n"
        "# except handlers, plus contextlib.suppress()). Do NOT add entries\n"
        "# without justification -- the goal is to burn this list down, not\n"
        "# grow it.\n"
        "# Regenerate intentionally: python tools/check_fault_tolerance.py --update-baseline\n"
        "# Entries are line-keyed (relpath:lineno:kind), so an unrelated line-count\n"
        "# change elsewhere in a file can shift existing entries. Prefer hand-editing\n"
        "# the baseline (update the shifted line number) over blind --update-baseline\n"
        "# regeneration, which can silently absorb a genuinely new violation\n"
        "# introduced in the same change.\n"
    )
    return _ratchet.write_baseline(path, header, collect_violations())


def main(argv: list[str] | None = None) -> int:
    return _ratchet.run_cli(
        argv,
        script_name="check_fault_tolerance.py",
        baseline_path=BASELINE_PATH,
        scan=_scan,
        violation_key=violation_key,
        update_baseline=write_baseline,
        describe=lambda v: f"{v[0]}:{v[1]}:{v[2]}",
        noun="fault-tolerance",
    )


if __name__ == "__main__":
    sys.exit(main())
