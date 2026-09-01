#!/usr/bin/env python3
"""Size ratchet: flag files over 300 lines and functions over 50 lines.

Existing violations are grandfathered via tools/size_baseline.txt so the
gate runs green in CI today while preventing NEW violations. Regenerate the
baseline (only with justification) via:
    python tools/check_sizes.py --update-baseline

Scans src/quodeq/**/*.py with `ast` for both file- and function-level
violations (a "function" here means any FunctionDef/AsyncFunctionDef,
including methods). Scans src/quodeq/ui/src/**/*.{js,jsx} for file-level
violations only -- JS function length is enforced separately by
src/quodeq/ui/eslint.size.config.js, which can see arrow functions and
other JS-only function shapes that `ast` does not.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

MAX_FILE_LINES = 300
MAX_FUNCTION_LINES = 50

REPO_ROOT = Path(__file__).resolve().parent.parent
PY_ROOT = REPO_ROOT / "src" / "quodeq"
JS_ROOT = REPO_ROOT / "src" / "quodeq" / "ui" / "src"
BASELINE_PATH = Path(__file__).resolve().parent / "size_baseline.txt"

# Directories under JS_ROOT that hold generated or vendored output rather
# than hand-written source.
JS_EXCLUDE_DIRS = {"node_modules", "dist", "generated"}


def _read_text(path: Path) -> str | None:
    """Return a file's text, or None (after a warning) if it can't be read."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"warning: skipping {path}: {e}", file=sys.stderr)
        return None


def _line_count(text: str) -> int:
    """Return the number of lines in a text file's contents."""
    return len(text.splitlines()) if text else 0


def _function_violations(tree: ast.Module) -> list[tuple[int, int]]:
    """Return (lineno, size) for every over-limit function/method in tree."""
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.end_lineno is None:
            continue
        size = node.end_lineno - node.lineno + 1
        if size > MAX_FUNCTION_LINES:
            violations.append((node.lineno, size))
    return violations


def _relpath(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _scan_python() -> list[tuple[str, int, str, int]]:
    """Return (relpath, lineno, kind, size) violations for src/quodeq/**/*.py."""
    found: list[tuple[str, int, str, int]] = []
    for py in sorted(PY_ROOT.rglob("*.py")):
        text = _read_text(py)
        if text is None:
            continue
        rel = _relpath(py)
        size = _line_count(text)
        if size > MAX_FILE_LINES:
            found.append((rel, 1, "file", size))
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as e:
            print(f"warning: skipping {py}: {e}", file=sys.stderr)
            continue
        for lineno, fn_size in _function_violations(tree):
            found.append((rel, lineno, "function", fn_size))
    return found


def _is_js_excluded(path: Path) -> bool:
    return any(part in JS_EXCLUDE_DIRS for part in path.relative_to(JS_ROOT).parts)


def _scan_js() -> list[tuple[str, int, str, int]]:
    """Return (relpath, 1, "file", size) violations for src/quodeq/ui/src/**/*.{js,jsx}."""
    found: list[tuple[str, int, str, int]] = []
    if not JS_ROOT.exists():
        return found
    for ext in ("*.js", "*.jsx"):
        for js in sorted(JS_ROOT.rglob(ext)):
            if _is_js_excluded(js):
                continue
            text = _read_text(js)
            if text is None:
                continue
            size = _line_count(text)
            if size > MAX_FILE_LINES:
                found.append((_relpath(js), 1, "file", size))
    return found


def _scan() -> list[tuple[str, int, str, int]]:
    """Return all (relpath, lineno, kind, size) size violations, sorted."""
    return sorted(_scan_python() + _scan_js())


def violation_key(v: tuple[str, int, str, int]) -> str:
    """Identity for a violation, independent of its current size.

    Deliberately omits size: a function that shrinks but stays over the cap
    must keep the same key, so it is not mistaken for a stale (fixed) entry.
    """
    relpath, lineno, kind, _size = v
    return f"{relpath}:{lineno}:{kind}"


def collect_violations() -> list[str]:
    """Return baseline keys (`relpath:lineno:kind`, no size) for all current
    size violations."""
    return sorted({violation_key(v) for v in _scan()})


def load_baseline(path: Path = BASELINE_PATH) -> set[str]:
    """Return the set of grandfathered violation keys (empty if no baseline)."""
    if not path.exists():
        return set()
    return {
        stripped
        for line in path.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    }


def write_baseline(path: Path = BASELINE_PATH) -> int:
    """Write current violations to the baseline file; return the count."""
    keys = collect_violations()
    header = (
        "# Grandfathered size violations (files > 300 lines, functions > 50\n"
        "# lines). Do NOT add entries without justification -- the goal is\n"
        "# to burn this list down, not grow it.\n"
        "# Regenerate intentionally: python tools/check_sizes.py --update-baseline\n"
    )
    path.write_text(header + "\n".join(keys) + ("\n" if keys else ""), encoding="utf-8")
    return len(keys)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    unknown = [a for a in args if a != "--update-baseline"]
    if unknown:
        print(f"Unknown argument(s): {' '.join(unknown)}. Usage: check_sizes.py [--update-baseline]")
        return 2
    if "--update-baseline" in args:
        n = write_baseline()
        print(f"Wrote {n} violation(s) to {BASELINE_PATH}")
        return 0

    baseline = load_baseline()
    all_violations = _scan()
    new = [v for v in all_violations if violation_key(v) not in baseline]
    grandfathered = len(all_violations) - len(new)

    if not new:
        print(f"OK: no new size violations ({grandfathered} grandfathered).")
        return 0
    print(f"Found {len(new)} NEW size violation(s) ({grandfathered} grandfathered):\n")
    for relpath, lineno, kind, size in new:
        print(f"  {relpath}:{lineno}:{kind}:{size}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
