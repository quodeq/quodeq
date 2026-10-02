#!/usr/bin/env python3
"""Git-prompt-guard ratchet: every git subprocess closes stdin and passes an env.

A git subprocess that inherits a tty can block on a credential or passphrase
prompt until its timeout, then be misreported as a network failure (the
onboarding clone did exactly that). The fix at every site is
``env=git_env_floor(...)`` (data/git_cli.py, which sets GIT_TERMINAL_PROMPT=0)
plus ``stdin=subprocess.DEVNULL``. This gate flags a ``subprocess.run`` /
``Popen`` / ``check_output`` whose argv list starts with the literal ``"git"``
or the name ``GIT_BIN`` and lacks either keyword. It follows ``import subprocess
[as x]`` and ``from subprocess import run [as y]`` bindings, and argv given as
``args=``.

Known limitation: argv built in a variable is not followed. The one known site
the gate cannot see is src/quodeq/assistant/_worktree_git.py (``run_git_bytes``
takes an argv parameter; it runs local worktree commands only).

Existing sites are grandfathered in tools/git_prompt_guard_baseline.txt so the
gate runs green today while preventing new ones. Regenerate (only with
justification) via:
    python tools/check_git_prompt_guard.py --update-baseline
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import _ratchet
from _ratchet import read_text as _read_text

REPO_ROOT = Path(__file__).resolve().parent.parent
PY_ROOT = REPO_ROOT / "src" / "quodeq"
BASELINE_PATH = Path(__file__).resolve().parent / "git_prompt_guard_baseline.txt"

_SUBPROCESS_CALLS = frozenset({"run", "Popen", "check_output", "check_call", "call"})
_GIT_ARGV0 = "git"
_GIT_BIN_NAME = "GIT_BIN"


@dataclass(frozen=True, slots=True)
class Hit:
    path: Path
    line: int
    missing: str  # "stdin", "env" or "stdin,env"


def _subprocess_bindings(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Names bound to the subprocess module, and to its call functions."""
    modules: set[str] = set()
    funcs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(a.asname or a.name for a in node.names if a.name == "subprocess")
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            funcs.update(a.asname or a.name for a in node.names if a.name in _SUBPROCESS_CALLS)
    return modules, funcs


def _is_subprocess_call(node: ast.Call, modules: set[str], funcs: set[str]) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in funcs
    return (
        isinstance(func, ast.Attribute) and func.attr in _SUBPROCESS_CALLS
        and isinstance(func.value, ast.Name) and func.value.id in modules
    )


def _argv_node(node: ast.Call) -> ast.expr | None:
    if node.args:
        return node.args[0]
    return next((kw.value for kw in node.keywords if kw.arg == "args"), None)


def _argv_is_git(node: ast.Call) -> bool:
    argv = _argv_node(node)
    if not isinstance(argv, (ast.List, ast.Tuple)) or not argv.elts:
        return False
    first = argv.elts[0]
    if isinstance(first, ast.Constant):
        return first.value == _GIT_ARGV0
    return isinstance(first, ast.Name) and first.id == _GIT_BIN_NAME


def _missing_keywords(node: ast.Call) -> str:
    names = {kw.arg for kw in node.keywords}
    missing = [k for k in ("stdin", "env") if k not in names]
    return ",".join(missing)


def scan_file(path: Path) -> Iterator[Hit]:
    text = _read_text(path)
    if text is None:
        return
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    modules, funcs = _subprocess_bindings(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_subprocess_call(node, modules, funcs) and _argv_is_git(node):
            missing = _missing_keywords(node)
            if missing:
                yield Hit(path, node.lineno, missing)


def scan_tree(root: Path) -> list[Hit]:
    return [h for p in _ratchet.iter_python_files(root) for h in scan_file(p)]


def _key(hit: Hit, root: Path) -> str:
    return f"{hit.path.relative_to(root).as_posix()}:{hit.line}"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    hits = scan_tree(PY_ROOT)
    keys = sorted(_key(h, REPO_ROOT) for h in hits)
    if "--update-baseline" in args:
        header = "# git subprocesses lacking stdin=DEVNULL or env= (relpath:lineno)\n"
        n = _ratchet.write_baseline(BASELINE_PATH, header, keys)
        print(f"wrote {n} entries to {BASELINE_PATH}")
        return 0
    baseline = _ratchet.load_baseline(BASELINE_PATH)
    new = [k for k in keys if k not in baseline]
    stale = sorted(baseline - set(keys))
    for k in new:
        print(f"NEW git subprocess without prompt guard: {k}")
    for k in stale:
        print(f"stale baseline entry (fixed, remove it): {k}")
    if new or stale:
        return 1
    print(f"check_git_prompt_guard: OK ({len(keys)} grandfathered)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
