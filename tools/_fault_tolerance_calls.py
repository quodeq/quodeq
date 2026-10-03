"""Call-site rules for the fault-tolerance ratchet (tools/check_fault_tolerance.py).

The CLI module owns the handler rules, the baseline and the file walk; this
module owns the rules keyed at a call and exposes `scan_calls`, which
returns every hit in one parsed module as (relpath, lineno, kind).

Kinds:
  - int-overflow: a call of the bare name `int` inside the body of a `try`
    whose handlers, taken together, catch both `ValueError` and
    `TypeError` but not `OverflowError`. A `TypeError` handler declares the
    input may be a non-str object, and a float object can be infinite:
    `int(float("inf"))` raises `OverflowError`, which escapes such a
    handler. A str-only parse (a `ValueError` handler alone) cannot raise
    `OverflowError`, so it is not flagged. `OverflowError` counts as caught
    when a handler names it, `ArithmeticError`, `Exception` or
    `BaseException`, or is a bare `except:`; those broad forms catch
    everything, so they never flag. Only the innermost `try` whose body
    holds the call is consulted; a call in a handler, `else` or `finally`
    block is guarded by the next enclosing `try`. A nested function or
    lambda starts a fresh scope: its body does not run inside the
    enclosing `try`. A handler that re-raises still counts as catching.
    Keyed at the call's line.
  - mkstemp-before-try: an assignment (`=` or annotated) whose value is a
    call to `tempfile.mkstemp` or bare `mkstemp`, where the next statement
    in the same body is a `try` with a handler naming `OSError`, `IOError`,
    `Exception` or `BaseException` (directly or in a tuple), or a bare
    `except:`. That handler was written for the temp-file write, and the
    creation raises the same class outside it. Move the `mkstemp` call to
    the first statement of the `try`. Keyed at the `mkstemp` line.

Known evasions, documented rather than closed:
  - `builtins.int(...)` (an attribute call) is not matched
  - `int` rebound to another name (`to_int = int` then `to_int(v)`)
  - an exception type reached through a name alias (`E = OverflowError`)
  - `int()` in a decorator or a default-argument expression of a function
    defined inside a flagged `try` runs in the enclosing try but is not
    flagged (the guard resets at the function node)
  - `mkstemp-before-try` needs the `try` to be the very next statement, so a
    statement in between (e.g. `config/ai_provider.py`, which re-raises) is
    not flagged
  - alias spellings (`from tempfile import mkstemp as mk`,
    `import tempfile as tf`) are not matched
"""
from __future__ import annotations

import ast

_INT_OVERFLOW = "int-overflow"
_CATCH_ALL = {"Exception", "BaseException"}
_OVERFLOW_CATCHERS = {"OverflowError", "ArithmeticError"} | _CATCH_ALL
_NON_STR_PARSE = {"ValueError", "TypeError"}
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_TRY_NODES = (ast.Try, ast.TryStar)
_BARE_EXCEPT = "BaseException"
_MKSTEMP_BEFORE_TRY = "mkstemp-before-try"
_MKSTEMP = "mkstemp"
_OSERROR_CATCHERS = {"OSError", "IOError"} | _CATCH_ALL


def _type_names(type_node: ast.expr | None) -> set[str]:
    """Names an except clause catches, by spelling (bare except -> BaseException)."""
    if type_node is None:
        return {_BARE_EXCEPT}
    if isinstance(type_node, ast.Tuple):
        return {name for elt in type_node.elts for name in _type_names(elt)}
    if isinstance(type_node, ast.Name):
        return {type_node.id}
    if isinstance(type_node, ast.Attribute):
        return {type_node.attr}
    return set()


def _misses_overflow(try_node: ast.AST) -> bool:
    """True when the try's handlers catch ValueError and TypeError but not OverflowError."""
    names = {name for h in try_node.handlers for name in _type_names(h.type)}
    return _NON_STR_PARSE <= names and not names & _OVERFLOW_CATCHERS


def _is_int_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "int"


def _visit(node: ast.AST, guard: ast.AST | None, rel: str, found: list[tuple[str, int, str]]) -> None:
    """Walk *node*; *guard* is the innermost try whose body encloses it."""
    if _is_int_call(node) and guard is not None and _misses_overflow(guard):
        found.append((rel, node.lineno, _INT_OVERFLOW))
    for field, value in ast.iter_fields(node):
        children = value if isinstance(value, list) else [value]
        for child in children:
            if not isinstance(child, ast.AST):
                continue
            if isinstance(child, _SCOPES):
                inner = None
            elif isinstance(node, _TRY_NODES) and field == "body":
                inner = node
            else:
                inner = guard
            _visit(child, inner, rel, found)


def _is_mkstemp_assign(stmt: ast.AST) -> bool:
    """True for `x = mkstemp(...)`/`x: T = tempfile.mkstemp(...)`."""
    if not isinstance(stmt, (ast.Assign, ast.AnnAssign)) or not isinstance(stmt.value, ast.Call):
        return False
    func = stmt.value.func
    if isinstance(func, ast.Name):
        return func.id == _MKSTEMP
    return (isinstance(func, ast.Attribute) and func.attr == _MKSTEMP
            and isinstance(func.value, ast.Name) and func.value.id == "tempfile")


def _catches_oserror(stmt: ast.AST) -> bool:
    """True when *stmt* is a try with a handler that catches OSError."""
    if not isinstance(stmt, _TRY_NODES):
        return False
    return any(_type_names(h.type) & _OSERROR_CATCHERS for h in stmt.handlers)


def _scan_mkstemp(tree: ast.AST, rel: str, found: list[tuple[str, int, str]]) -> None:
    """Flag each mkstemp assignment directly followed by an OSError-catching try."""
    for node in ast.walk(tree):
        for _field, stmts in ast.iter_fields(node):
            if not isinstance(stmts, list):
                continue
            for stmt, nxt in zip(stmts, stmts[1:]):
                if _is_mkstemp_assign(stmt) and _catches_oserror(nxt):
                    found.append((rel, stmt.lineno, _MKSTEMP_BEFORE_TRY))


def scan_calls(tree: ast.AST, rel: str) -> list[tuple[str, int, str]]:
    """Return (relpath, lineno, kind) call-site violations in one parsed module."""
    found: list[tuple[str, int, str]] = []
    _visit(tree, None, rel, found)
    _scan_mkstemp(tree, rel, found)
    return found
