#!/usr/bin/env python3
"""API error-response gate: every error response carries a machine-readable code.

No baseline: the ceiling is zero from day one. There is nothing to
grandfather, so a single violation fails the gate immediately.

Scans src/quodeq/api/**/*.py (excluding api/pages/, which renders HTML, not
JSON error bodies) with `ast` for two kinds of violation:
  - uncoded-error: an error body with an "error" key and no "code" key,
    either as the first argument of a `jsonify(...)` call or as the dict
    literal of a `return <dict>, <status>` tuple whose status is 400 or
    more. AST-based on the literal's keys, not its string content, so a
    formatted message inside the value does not fool it. A dict literal
    whose "error" value is the constant `None` is exempt: that is a
    reserved slot in a success payload (see routes_shared_config's status
    body), not an error response.
  - abort:         an `abort(<status>, ...)` call whose first argument is
    an int literal, an `HTTPStatus.<NAME>` or an `http.HTTPStatus.<NAME>`
    attribute, of 400 or more. Route modules should raise a small exception
    caught by an `@app.errorhandler`, or return `error_response(...)`
    directly instead (see routes_findings.py's `_ProjectNotFoundError`): a
    bare `abort()` gives Flask's default HTML/JSON body, which has no
    `code` field. A status held in a variable cannot be resolved
    statically and is not reported.

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
# Lowest status that makes a response an error response.
_MIN_ERROR_STATUS = 400
# A Flask response tuple is (body, status).
_RESPONSE_TUPLE_LEN = 2


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


def _is_reserved_error_slot(node: ast.Dict) -> bool:
    """True when the dict literal's "error" value is the constant None.

    An always-present ``"error": None`` field in a SUCCESS payload (the
    shared status body binds to it without existence checks) is a reserved
    slot, not an error response, so it needs no code beside it.
    """
    for key, value in zip(node.keys, node.values):
        if isinstance(key, ast.Constant) and key.value == "error":
            return isinstance(value, ast.Constant) and value.value is None
    return False


def _is_uncoded_error_dict(node: ast.expr) -> bool:
    """True for a dict literal that is an error body carrying no code."""
    keys = _dict_literal_keys(node)
    if keys is None:
        return False
    if "error" not in keys or "code" in keys:
        return False
    return not _is_reserved_error_slot(node)


def _is_uncoded_jsonify(node: ast.expr) -> bool:
    if not _is_call_named(node, "jsonify") or not node.args:
        return False
    return _is_uncoded_error_dict(node.args[0])


def _status_value(node: ast.expr) -> int | None:
    """The integer status *node* denotes, or None if it isn't a literal
    status (an int constant, an `HTTPStatus.<NAME>` or an
    `http.HTTPStatus.<NAME>` attribute)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Attribute):
        owner = node.value
        on_httpstatus = (
            (isinstance(owner, ast.Name) and owner.id == "HTTPStatus")
            or (isinstance(owner, ast.Attribute) and owner.attr == "HTTPStatus")
        )
        if on_httpstatus:
            member = getattr(HTTPStatus, node.attr, None)
            if isinstance(member, HTTPStatus):
                return int(member)
    return None


def _is_error_abort(node: ast.expr) -> bool:
    if not _is_call_named(node, "abort") or not node.args:
        return False
    status = _status_value(node.args[0])
    return status is not None and status >= _MIN_ERROR_STATUS


def _is_uncoded_error_return(node: ast.Return) -> bool:
    """True for `return <dict literal>, <status 400+>`: the same error
    response as the jsonify form, one Flask convenience later."""
    if not isinstance(node.value, ast.Tuple) or len(node.value.elts) != _RESPONSE_TUPLE_LEN:
        return False
    status = _status_value(node.value.elts[1])
    if status is None or status < _MIN_ERROR_STATUS:
        return False
    return _is_uncoded_error_dict(node.value.elts[0])


def _scan_tree(tree: ast.AST, rel: str) -> list[tuple[str, int, str]]:
    """Return (relpath, lineno, kind) violations found in one parsed module."""
    found: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Return):
            if _is_uncoded_error_return(node):
                found.append((rel, node.lineno, "uncoded-error"))
            continue
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
