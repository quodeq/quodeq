#!/usr/bin/env python3
"""API error-response gate: every error response carries a machine-readable code.

No baseline: the ceiling is zero from day one. There is nothing to
grandfather, so a single violation fails the gate immediately.

Scans src/quodeq/api/**/*.py (excluding api/pages/, which renders HTML, not
JSON error bodies) with `ast` for two kinds of violation:
  - uncoded-error: a `jsonify(...)` call whose first argument is a dict
    literal with an "error" key and no "code" key. AST-based on the
    literal's keys, not its string content, so a formatted message inside
    the value does not fool it.
  - abort:         an `abort(<status>, ...)` call whose first argument is
    an int literal, or an `HTTPStatus.<NAME>` attribute, of 400 or more.
    Route modules should raise a small exception caught by an
    `@app.errorhandler`, or return `error_response(...)` directly instead
    (see routes_findings.py's `_ProjectNotFoundError`): a bare `abort()`
    gives Flask's default HTML/JSON body, which has no `code` field.

Run directly:
    python tools/check_error_codes.py [--list]
"""
from __future__ import annotations

import ast
import sys
from http import HTTPStatus
from pathlib import Path
from typing import Iterator

import _ratchet
from _ratchet import read_text as _read_text

REPO_ROOT = Path(__file__).resolve().parent.parent
PY_ROOT = REPO_ROOT / "src" / "quodeq" / "api"
_EXCLUDED_DIR_NAMES = {"pages"}


def _relpath(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _iter_api_files() -> Iterator[Path]:
    """Yield src/quodeq/api/**/*.py, skipping the pages/ subtree."""
    for py in _ratchet.iter_python_files(PY_ROOT):
        if _EXCLUDED_DIR_NAMES.isdisjoint(py.relative_to(PY_ROOT).parts):
            yield py


def _is_call_named(node: ast.expr, name: str) -> bool:
    """True for a call to a bare `name(...)` or a qualified `X.name(...)`."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == name
    if isinstance(func, ast.Attribute):
        return func.attr == name
    return False


def _dict_literal_keys(node: ast.expr) -> set[str] | None:
    """String keys of a dict literal, or None if *node* isn't one.

    A `**spread` entry (key is None) or a non-string-literal key is simply
    not added to the set: it neither satisfies nor defeats the "error"/
    "code" check.
    """
    if not isinstance(node, ast.Dict):
        return None
    keys: set[str] = set()
    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.add(key.value)
    return keys


def _is_uncoded_jsonify(node: ast.expr) -> bool:
    if not _is_call_named(node, "jsonify") or not node.args:
        return False
    keys = _dict_literal_keys(node.args[0])
    if keys is None:
        return False
    return "error" in keys and "code" not in keys


def _status_value(node: ast.expr) -> int | None:
    """The integer status *node* denotes, or None if it isn't a literal
    status (an int constant, or an `HTTPStatus.<NAME>` attribute)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "HTTPStatus":
        member = getattr(HTTPStatus, node.attr, None)
        if isinstance(member, HTTPStatus):
            return int(member)
    return None


def _is_error_abort(node: ast.expr) -> bool:
    if not _is_call_named(node, "abort") or not node.args:
        return False
    status = _status_value(node.args[0])
    return status is not None and status >= 400


def _scan_tree(tree: ast.AST, rel: str) -> list[tuple[str, int, str]]:
    """Return (relpath, lineno, kind) violations found in one parsed module."""
    found: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _is_uncoded_jsonify(node):
            found.append((rel, node.lineno, "uncoded-error"))
        elif _is_error_abort(node):
            found.append((rel, node.lineno, "abort"))
    return found


def _scan() -> list[tuple[str, int, str]]:
    """Return all (relpath, lineno, kind) violations, sorted."""
    found: list[tuple[str, int, str]] = []
    for py in _iter_api_files():
        text = _read_text(py)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as e:
            print(f"warning: skipping {py}: {e}", file=sys.stderr)
            continue
        found.extend(_scan_tree(tree, _relpath(py)))
    return sorted(found)


def violation_key(v: tuple[str, int, str]) -> str:
    """Identity for a violation: relpath:lineno:kind."""
    relpath, lineno, kind = v
    return f"{relpath}:{lineno}:{kind}"


def collect_violations() -> list[str]:
    """Return `relpath:lineno:kind` for every current violation."""
    return sorted({violation_key(v) for v in _scan()})


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    unknown = [a for a in args if a != "--list"]
    if unknown:
        print(f"Unknown argument(s): {' '.join(unknown)}. Usage: check_error_codes.py [--list]")
        return 2
    violations = collect_violations()
    if not violations:
        print("OK: no API error responses without a machine-readable code.")
        return 0
    print(f"Found {len(violations)} API error response(s) missing a machine-readable code:\n")
    for v in violations:
        print(f"  {v}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
