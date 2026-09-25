#!/usr/bin/env python3
"""Loop-IO ratchet: flag file, database, lock and event-log calls made once
per loop iteration in the service, data and analysis layers.

Existing sites are grandfathered in tools/loop_io_baseline.txt so the gate
runs green today while blocking NEW ones. Regenerate (only with
justification) via:
    python tools/check_loop_io.py --update-baseline

Entries are line-keyed (relpath:lineno:callee), like the fault-tolerance and
import ratchets, so an edit above a grandfathered site shifts its entry.
Prefer hand-editing the line number over a blind --update-baseline, which
can absorb a genuinely new site introduced in the same change.

What counts as loop IO (lexical, `ast` only): a call inside the body of a
`for`/`async for`/`while`, or inside the per-item part of a comprehension
(element, conditions, and the iterables of the second and later `for`
clauses; the first iterable runs once), whose callee is one of:
  - `open(...)` and `X.open(...)`
  - `X.read_text/write_text/read_bytes/write_bytes(...)`
  - `connect(...)` and `X.connect(...)` (sqlite3.connect included)
  - any `open_*(...)` / `X.open_*(...)` helper (open_evaluation_db,
    open_index, open_text, ...)
  - `X.emit(...)`, `get_file_lock(...)` / `X.get_file_lock(...)`, and
    `commit(...)` / `X.commit(...)`

Two exemptions keep the gate on the pattern that costs something (the same
resource reopened per item) and off IO that is inherent per item:
  - per-item resource: a file/database call (every kind above except emit,
    get_file_lock and commit) whose resource expression (the receiver of a
    Path method, else the first positional argument) mentions the loop
    target or a name the loop body derives from it. `for p in d.glob("*.json"):
    p.read_text()` reads each file once; there is nothing to batch.
    emit, get_file_lock and commit are never exempt: one append, one lock
    or one DB commit per item is what emit_many, a hoisted lock and a
    batched commit exist to remove.
  - small literal: a loop over a tuple/list/set literal of at most
    _SMALL_LITERAL_MAX elements (`for src in (ours, theirs):`) walks a fixed
    handful of known resources, not data.

Known limits, documented rather than closed:
  - IO behind a helper call (`for r in runs: load(r)`) is not seen; the
    gate is lexical by design.
  - nested def/lambda/class bodies inside a loop are skipped (defining a
    function is not calling it).
  - a `while` loop has no target, so every IO call in its body is flagged,
    including one an inner `for`'s own per-item rule would exempt on its
    own: `while more(): for q in d.glob(...): q.read_text()` still flags
    `read_text`, the same as the two-loop `for`-in-`for` case above (the
    while's iteration can repeat the inner loop's work exactly like an
    outer for's can); a poll loop is a legitimate baseline entry.
  - taint tracking is flow-insensitive: a name assigned an IO handle
    anywhere in the function counts as that handle everywhere in it.
  - emit and commit are matched by name on any receiver: a logging
    handler's emit, a signal's emit, or git's commit trip the gate the
    same as the ones it targets.
"""
from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

import _ratchet

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = tuple(
    REPO_ROOT / "src" / "quodeq" / layer for layer in ("services", "data", "analysis")
)
BASELINE_PATH = Path(__file__).resolve().parent / "loop_io_baseline.txt"

# Path methods that read or write one whole file; the receiver is the file.
_PATH_METHODS = frozenset({"open", "read_text", "write_text", "read_bytes", "write_bytes"})
# Callees that open a file or database named by their first argument.
_OPENERS = frozenset({"open", "connect"})
_OPENER_PREFIX = "open_"
# One event-log append, one lock acquisition or one DB commit per item: never exempt.
_SHARED = frozenset({"emit", "get_file_lock", "commit"})
# A literal iterable this short is a fixed handful of resources, not data.
_SMALL_LITERAL_MAX = 3

_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)

Violation = tuple[str, int, str]


def _callee(call: ast.Call) -> str | None:
    """The IO callee name this call matches, or None for any other call."""
    func = call.func
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
        if name in _PATH_METHODS:
            return name
    else:
        return None
    if name in _SHARED or name in _OPENERS or name.startswith(_OPENER_PREFIX):
        return name
    return None


def _subject(call: ast.Call, callee: str) -> ast.expr | None:
    """The expression naming the resource: a Path method's receiver, else
    the first positional argument (None when there is none)."""
    func = call.func
    if isinstance(func, ast.Attribute) and callee in _PATH_METHODS:
        return func.value
    return call.args[0] if call.args else None


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _bindings(node: ast.AST) -> list[tuple[ast.AST, ast.AST]]:
    """The (target, value) pairs one node binds, for the per-item data flow."""
    if isinstance(node, ast.Assign):
        return [(target, node.value) for target in node.targets]
    if isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and node.value is not None:
        return [(node.target, node.value)]
    if isinstance(node, ast.withitem) and node.optional_vars is not None:
        return [(node.optional_vars, node.context_expr)]
    if isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
        return [(node.target, node.iter)]
    return []


def _per_item_names(targets: set[str], parts: list[ast.AST]) -> set[str]:
    """The loop targets plus every name *parts* derive from them, to a fixpoint."""
    names = set(targets)
    pairs = [pair for part in parts for node in ast.walk(part) for pair in _bindings(node)]
    grew = True
    while grew:
        grew = False
        for target, value in pairs:
            new = _names(target) - names
            if new and _names(value) & names:
                names |= new
                grew = True
    return names


def _is_small_literal(node: ast.expr) -> bool:
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return False
    if any(isinstance(elt, ast.Starred) for elt in node.elts):
        return False
    return len(node.elts) <= _SMALL_LITERAL_MAX


def _comprehension_parts(node: ast.expr) -> tuple[list[ast.AST], set[str]] | None:
    gens = node.generators
    if len(gens) == 1 and _is_small_literal(gens[0].iter):
        return None
    parts: list[ast.AST] = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
    for index, gen in enumerate(gens):
        parts.extend(gen.ifs)
        if index:
            parts.append(gen.iter)
    return parts, set().union(*(_names(gen.target) for gen in gens))


def _loop_parts(node: ast.AST) -> tuple[list[ast.AST], set[str]] | None:
    """(the code run once per iteration, the loop target names), or None
    when *node* is not a loop or loops over a small literal."""
    if isinstance(node, (ast.For, ast.AsyncFor)):
        if _is_small_literal(node.iter):
            return None
        return list(node.body), _names(node.target)
    if isinstance(node, ast.While):
        return list(node.body), set()
    if isinstance(node, _COMPREHENSIONS):
        return _comprehension_parts(node)
    return None


def _calls_in(parts: list[ast.AST]) -> Iterator[ast.Call]:
    """Every call in *parts*, not descending into nested defs, lambdas or classes."""
    stack = list(parts)
    while stack:
        node = stack.pop()
        if isinstance(node, _NESTED_SCOPES):
            continue
        if isinstance(node, ast.Call):
            yield node
        stack.extend(ast.iter_child_nodes(node))


def _is_per_item(call: ast.Call, callee: str, per_item: set[str]) -> bool:
    if callee in _SHARED:
        return False
    subject = _subject(call, callee)
    if subject is not None and bool(_names(subject) & per_item):
        return True
    # `open` is ambiguous: `path_obj.open()` takes the resource as its
    # receiver, but `gzip.open(p)` / `tarfile.open(p)` / `io.open(p)` /
    # `os.open(p)` take it as their module call's first argument, with the
    # receiver naming the module instead. Check the argument too.
    if callee == "open" and call.args:
        return bool(_names(call.args[0]) & per_item)
    return False


def scan_tree(tree: ast.AST, rel: str) -> set[Violation]:
    """Return the (relpath, lineno, callee) loop-IO sites in one parsed module."""
    found: set[Violation] = set()
    for node in ast.walk(tree):
        loop = _loop_parts(node)
        if loop is None:
            continue
        parts, targets = loop
        per_item = _per_item_names(targets, parts)
        for call in _calls_in(parts):
            callee = _callee(call)
            if callee is not None and not _is_per_item(call, callee, per_item):
                found.add((rel, call.lineno, callee))
    return found


def _scan_file(py: Path) -> set[Violation]:
    text = _ratchet.read_text(py)
    if text is None:
        return set()
    try:
        tree = ast.parse(text, filename=str(py))
    except SyntaxError as e:
        print(f"warning: skipping {py}: {e}", file=sys.stderr)
        return set()
    return scan_tree(tree, py.relative_to(REPO_ROOT).as_posix())


def _scan() -> list[Violation]:
    """Return every loop-IO site under SCAN_ROOTS, sorted."""
    found: set[Violation] = set()
    for root in SCAN_ROOTS:
        for py in _ratchet.iter_python_files(root):
            found |= _scan_file(py)
    return sorted(found)


def violation_key(v: Violation) -> str:
    """Identity for a site: relpath:lineno:callee."""
    relpath, lineno, callee = v
    return f"{relpath}:{lineno}:{callee}"


def collect_violations() -> list[str]:
    """Return baseline keys for every current loop-IO site."""
    return sorted({violation_key(v) for v in _scan()})


def load_baseline(path: Path = BASELINE_PATH) -> set[str]:
    """Return the grandfathered keys (empty if no baseline)."""
    return _ratchet.load_baseline(path)


def write_baseline(path: Path = BASELINE_PATH) -> int:
    """Write the current sites to the baseline file; return the count."""
    header = (
        "# Grandfathered loop-IO sites: a file, database, lock or event-log call\n"
        "# made once per loop iteration (see tools/check_loop_io.py for the rule\n"
        "# and its exemptions). Burn this list down; do not grow it without a\n"
        "# justification in the PR.\n"
        "# Regenerate intentionally: python tools/check_loop_io.py --update-baseline\n"
        "# Entries are line-keyed (relpath:lineno:callee): when an edit shifts a\n"
        "# site, hand-edit its line number instead of regenerating blind.\n"
    )
    return _ratchet.write_baseline(path, header, collect_violations())


def main(argv: list[str] | None = None) -> int:
    return _ratchet.run_cli(argv, _ratchet.RatchetSpec(
        script_name="check_loop_io.py",
        noun="loop-IO",
        baseline_path=BASELINE_PATH,
        scan=_scan,
        violation_key=violation_key,
        update_baseline=write_baseline,
        describe=violation_key,
    ))


if __name__ == "__main__":
    sys.exit(main())
