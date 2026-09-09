"""Guard against exception text flowing into API response bodies.

CodeQL's ``py/stack-trace-exposure`` fires on any
``except X as exc: ... jsonify(...str(exc)...)`` shape: the caught
exception's text ends up in an HTTP response. This walks every route module
under ``src/quodeq/api`` and asserts no handler lets the bound exception (or
its ``repr()``, an f-string interpolation of it, or its ``.args``) reach a
``jsonify()`` / ``error_response()`` call -- directly, or through a variable
assigned from one of those forms earlier in the same handler body.

Zero baseline: this must stay empty. A validator that needs to surface a
message writes a non-raising `<name>_error()` checker (see
``shared/validation.py``, ``core/utils/io.py``, ``shared/url_validation.py``)
and the route returns the checker's string or a fixed constant, never the
exception object itself.
"""
from __future__ import annotations

import ast
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[2] / "src" / "quodeq" / "api"
_REPO_ROOT = _API_ROOT.parents[2]
_SINK_NAMES = {"jsonify", "error_response"}


def _is_sink_call(node: ast.AST) -> bool:
    """True if *node* calls ``jsonify()``, ``error_response()``, or
    ``<anything>.error_response()``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id in _SINK_NAMES:
        return True
    return isinstance(func, ast.Attribute) and func.attr == "error_response"


def _is_flagged_expr(node: ast.AST, name: str) -> bool:
    """True if *node* echoes the bound exception *name*: ``str(name)``,
    ``repr(name)``, an f-string ``{name}`` interpolation, or ``name.args``."""
    if isinstance(node, ast.Call):
        func = node.func
        if (
            isinstance(func, ast.Name)
            and func.id in ("str", "repr")
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == name
        ):
            return True
    if isinstance(node, ast.FormattedValue):
        if isinstance(node.value, ast.Name) and node.value.id == name:
            return True
    if isinstance(node, ast.Attribute):
        if node.attr == "args" and isinstance(node.value, ast.Name) and node.value.id == name:
            return True
    return False


def _assigned_flagged_names(handler: ast.ExceptHandler, name: str) -> set[str]:
    """Variables directly assigned a flagged expression earlier in the same
    handler body, e.g. ``msg = str(exc)`` later used as ``jsonify({"error": msg})``."""
    names: set[str] = set()
    for stmt in handler.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and _is_flagged_expr(stmt.value, name)
        ):
            names.add(stmt.targets[0].id)
    return names


def _handler_hits(handler: ast.ExceptHandler) -> list[int]:
    """Line numbers where the exception (or a variable holding its echoed
    text) reaches a jsonify()/error_response() call within *handler*."""
    name = handler.name
    if name is None:
        return []
    flagged_vars = _assigned_flagged_names(handler, name)
    hits: list[int] = []
    for stmt in handler.body:
        for node in ast.walk(stmt):
            if not _is_sink_call(node):
                continue
            for sub in ast.walk(node):
                if sub is node:
                    continue
                if _is_flagged_expr(sub, name):
                    hits.append(getattr(sub, "lineno", node.lineno))
                elif isinstance(sub, ast.Name) and sub.id in flagged_vars:
                    hits.append(getattr(sub, "lineno", node.lineno))
    return hits


def _find_hits() -> list[str]:
    hits: list[str] = []
    for path in sorted(_API_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(_REPO_ROOT)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                for lineno in _handler_hits(node):
                    hits.append(f"{rel}:{lineno}")
    return sorted(set(hits))


def test_no_exception_text_in_api_responses() -> None:
    hits = _find_hits()
    assert hits == [], (
        "exception text reaches an HTTP response body at:\n"
        + "\n".join(hits)
        + "\nreturn a checker's message or a constant; never str(exc) in a response body"
    )
