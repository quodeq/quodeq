"""Call classifiers for the blocking-timeout ratchet (tools/check_blocking_timeouts.py).

The CLI module owns the allowlist, the baseline and the file walk; this
module owns the per-call heuristics and exposes `scan_tree`, which
returns every hit in one parsed module with no allowlist applied.

The ratchet scans src/quodeq/**/*.py (vendored/generated dirs excluded)
with `ast` for three kinds of violation:
  - subprocess-run: a call to subprocess.run/check_output/check_call/call
    (attribute access on the literal name `subprocess`, or a bare name
    imported via `from subprocess import run` etc.) with no `timeout=`
    keyword. `subprocess.Popen(...)` construction is never flagged: it only
    starts a process, so `timeout=` is meaningless on the constructor.
  - subprocess-wait: `.wait()`/`.communicate()` on a receiver resolved,
    best-effort, as Popen-like (see below) with no `timeout=` keyword,
    unless the call is the sole positional argument to
    `asyncio.wait_for(..., <timeout>)` (that call bounds it instead).
  - http-no-timeout: httpx.get/post/put/delete/request/stream,
    httpx.Client(...)/AsyncClient(...) construction, urllib.request.urlopen
    (3rd positional argument also counts as a timeout), or openai.OpenAI(...)
    construction, each without a `timeout=` keyword (all also matched via a
    bare name imported from that module).

Receiver resolution for subprocess-wait is a same-function, spelling-based
heuristic, not real type inference (same spirit as
check_fault_tolerance.py's documented evasions): a name is Popen-like when,
within the same function, it is assigned from a call whose callee spells
`Popen`/`create_subprocess_exec`/`create_subprocess_shell` or contains
"spawn" (covers `session.spawn_fn(...)`, `spawn_action_api(...)`, or a local
`spawn` alias bound via `x or asyncio.create_subprocess_exec`), or when it
is a parameter (or a `self.<attr>` assigned from one) annotated as
`subprocess.Popen`. `threading.Event`/`Condition.wait()` never match: their
receivers are never bound either way.

Known evasions/limits, documented rather than closed (none happens by
accident):
  - a call through an injected parameter defaulting to the real callable
    (`runner=subprocess.run` in update/first_launch.py, `http_get=httpx.get`
    in update/source.py) is a bare Name at the call site, not a literal
    `subprocess.run(`/`httpx.get(` attribute expression, so it is invisible
    here.
  - `import subprocess as sp` / `import httpx as h` (module-level aliasing
    of the *module itself*, as opposed to a `from X import Y` name) is not
    resolved: only the literal names `subprocess`/`httpx`/`openai`/`urllib`
    are recognized.
  - a Popen-like receiver assigned in one method and waited on in another
    (e.g. `self._proc` set in `__init__`) is not resolved: the heuristic is
    scoped to a single function body.
  - the "callee name contains 'spawn'" half of the subprocess-wait receiver
    heuristic is an over-approximation, not just an under-approximation: a
    function named `spawn_something` that returns a non-process value would
    have its `.wait()`/`.communicate()` call flagged too. No such function
    exists in this tree today; if one is added and is a false positive,
    allowlist it rather than loosening the heuristic.
  - `f(**kwargs)` is NOT treated as compliant: a call built entirely from a
    spread with no literal `timeout=` is flagged like any other missing
    timeout, even though the spread might carry one. A verified compliant
    site goes in ALLOWLIST (see `llm_bridge/embeddings.py` above), not into
    a blanket exemption -- a blanket rule would also hide a genuinely
    missing timeout on any future `f(url, **opts)` call.
"""
from __future__ import annotations

import ast

KIND_SUBPROCESS_RUN = "subprocess-run"
KIND_SUBPROCESS_WAIT = "subprocess-wait"
KIND_HTTP_NO_TIMEOUT = "http-no-timeout"

_RUN_ATTRS = frozenset({"run", "check_output", "check_call", "call"})
_WAIT_ATTRS = frozenset({"wait", "communicate"})
_SPAWN_HINTS = frozenset({"popen", "create_subprocess_exec", "create_subprocess_shell"})
_HTTP_FUNCS = frozenset({"get", "post", "put", "delete", "request", "stream"})
_HTTPX_CTORS = frozenset({"Client", "AsyncClient"})
_OPENAI_CTORS = frozenset({"OpenAI"})
_URLOPEN_TIMEOUT_ARG_INDEX = 2  # urlopen(url, data=None, timeout=..., ...)


def _has_timeout_kwarg(call: ast.Call) -> bool:
    """True if *call* passes `timeout=` explicitly. A `**kwargs` spread with
    no literal `timeout=` keyword does NOT count: it is flagged like any
    other missing timeout (a verified compliant site goes in ALLOWLIST, not
    a blanket exemption -- see the module docstring)."""
    return any(kw.arg == "timeout" for kw in call.keywords)


def _bare_names_from(tree: ast.Module, module: str, wanted: frozenset[str]) -> dict[str, str]:
    """Map a locally bound name -> real attribute name, for
    `from <module> import <name> [as alias]` where name is in *wanted*."""
    mapping: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != module or node.level:
            continue
        for alias in node.names:
            if alias.name in wanted:
                mapping[alias.asname or alias.name] = alias.name
    return mapping


def _module_attr(call: ast.Call, module_name: str, wanted: frozenset[str]) -> str | None:
    """The attribute name if *call* is `<module_name>.<attr>(...)`, else None."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in wanted \
            and isinstance(func.value, ast.Name) and func.value.id == module_name:
        return func.attr
    return None


def _bare_call(call: ast.Call, bare_names: dict[str, str]) -> str | None:
    """The real attribute name if *call* is a bare name from *bare_names*."""
    func = call.func
    if isinstance(func, ast.Name) and func.id in bare_names:
        return bare_names[func.id]
    return None


def _is_urlopen_call(call: ast.Call, bare_urlopen: dict[str, str]) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "urlopen" \
            and isinstance(func.value, ast.Attribute) and func.value.attr == "request" \
            and isinstance(func.value.value, ast.Name) and func.value.value.id == "urllib":
        return True
    return _bare_call(call, bare_urlopen) == "urlopen"


def _classify_call(
    call: ast.Call,
    bare_run: dict[str, str],
    bare_httpx: dict[str, str],
    bare_urlopen: dict[str, str],
    bare_openai: dict[str, str],
) -> str | None:
    """Return this call's violation kind, or None if it is fine or unrelated."""
    has_timeout = _has_timeout_kwarg(call)

    if _module_attr(call, "subprocess", _RUN_ATTRS) or _bare_call(call, bare_run):
        return None if has_timeout else KIND_SUBPROCESS_RUN

    if _is_urlopen_call(call, bare_urlopen):
        return None if (has_timeout or len(call.args) > _URLOPEN_TIMEOUT_ARG_INDEX) else KIND_HTTP_NO_TIMEOUT

    if _module_attr(call, "httpx", _HTTP_FUNCS | _HTTPX_CTORS) or _bare_call(call, bare_httpx):
        return None if has_timeout else KIND_HTTP_NO_TIMEOUT

    if _module_attr(call, "openai", _OPENAI_CTORS) or _bare_call(call, bare_openai):
        return None if has_timeout else KIND_HTTP_NO_TIMEOUT

    return None


def _receiver_key(expr: ast.expr) -> str | None:
    """Dotted identity for an assignment target/receiver (`proc`,
    `self._proc`, ...). Anything else (subscript, call, ...) has no stable
    identity and returns None."""
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        base = _receiver_key(expr.value)
        return f"{base}.{expr.attr}" if base else None
    return None


def _callee_spelling(expr: ast.expr) -> str | None:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return None


def _looks_like_spawn(expr: ast.expr) -> bool:
    """True if *expr* spells a process-spawning callable: `Popen`,
    `create_subprocess_exec`/`_shell`, or any name/attribute containing
    "spawn" (covers `session.spawn_fn(...)`, `spawn_action_api(...)`, a
    local `spawn` alias). Spelling-only: an indirection through an
    unrelated name defeats it."""
    name = _callee_spelling(expr)
    if name is None:
        return False
    lname = name.lower()
    return lname in _SPAWN_HINTS or "spawn" in lname


def _mentions_spawn(value: ast.expr) -> bool:
    """True if *value* (not itself called yet) spells a spawn-like
    callable, possibly behind `or`/a conditional expression -- covers
    `spawn = process_factory or asyncio.create_subprocess_exec`."""
    if isinstance(value, ast.BoolOp):
        return any(_mentions_spawn(v) for v in value.values)
    if isinstance(value, ast.IfExp):
        return _mentions_spawn(value.body) or _mentions_spawn(value.orelse)
    if isinstance(value, (ast.Name, ast.Attribute)):
        return _looks_like_spawn(value)
    return False


def _popen_annotated_params(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Parameter names (and any `self.<attr>` assigned from one verbatim in
    the function body) whose annotation spells `Popen`."""
    names: set[str] = set()
    args = func.args
    for a in (*args.posonlyargs, *args.args, *args.kwonlyargs):
        if a.annotation is None:
            continue
        if any(
            (isinstance(n, ast.Name) and n.id == "Popen")
            or (isinstance(n, ast.Attribute) and n.attr == "Popen")
            for n in ast.walk(a.annotation)
        ):
            names.add(a.arg)
    if not names:
        return names
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.value, ast.Name) and node.value.id in names:
            key = _receiver_key(node.targets[0])
            if key:
                names.add(key)
    return names


def _popen_receiver_keys(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Names, within *func*, bound to a Popen-like process handle. See the
    module docstring for the (best-effort, spelling-based) resolution
    rules."""
    assigns = [n for n in ast.walk(func) if isinstance(n, ast.Assign) and len(n.targets) == 1]
    aliases: set[str] = set()
    for a in assigns:
        if isinstance(a.value, (ast.Call, ast.Await)):
            continue
        if _mentions_spawn(a.value):
            key = _receiver_key(a.targets[0])
            if key:
                aliases.add(key)
    popen: set[str] = set()
    for a in assigns:
        value = a.value.value if isinstance(a.value, ast.Await) else a.value
        if not isinstance(value, ast.Call):
            continue
        if _looks_like_spawn(value.func) or _callee_spelling(value.func) in aliases:
            key = _receiver_key(a.targets[0])
            if key:
                popen.add(key)
    return popen | _popen_annotated_params(func)


def _is_wrapped_in_wait_for(node: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    """True if *node* is the first positional argument to `asyncio.wait_for(
    ..., <timeout>)` (or a bare `wait_for(...)`): that call bounds it."""
    parent = parents.get(node)
    if not isinstance(parent, ast.Call):
        return False
    name = _callee_spelling(parent.func)
    return name == "wait_for" and bool(parent.args) and parent.args[0] is node


def _wait_violations(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[int]:
    """Line numbers of unguarded `.wait()`/`.communicate()` calls in *func*."""
    popen_names = _popen_receiver_keys(func)
    if not popen_names:
        return []
    parents = {child: node for node in ast.walk(func) for child in ast.iter_child_nodes(node)}
    lines: list[int] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        call_func = node.func
        if not isinstance(call_func, ast.Attribute) or call_func.attr not in _WAIT_ATTRS:
            continue
        key = _receiver_key(call_func.value)
        if key is None or key not in popen_names:
            continue
        if _has_timeout_kwarg(node) or node.args:
            continue
        if _is_wrapped_in_wait_for(node, parents):
            continue
        lines.append(node.lineno)
    return lines


def scan_tree(tree: ast.AST, rel: str) -> list[tuple[str, int, str]]:
    """Return every (relpath, lineno, kind) hit in one parsed module, unfiltered."""
    bare_run = _bare_names_from(tree, "subprocess", _RUN_ATTRS)
    bare_httpx = _bare_names_from(tree, "httpx", _HTTP_FUNCS | _HTTPX_CTORS)
    bare_urlopen = _bare_names_from(tree, "urllib.request", frozenset({"urlopen"}))
    bare_openai = _bare_names_from(tree, "openai", _OPENAI_CTORS)

    found: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            kind = _classify_call(node, bare_run, bare_httpx, bare_urlopen, bare_openai)
            if kind is not None:
                found.append((rel, node.lineno, kind))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.extend((rel, lineno, KIND_SUBPROCESS_WAIT) for lineno in _wait_violations(node))
    return sorted(set(found))
