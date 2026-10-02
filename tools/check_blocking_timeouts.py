#!/usr/bin/env python3
"""Blocking-timeout ratchet: flag subprocess/HTTP calls with no explicit timeout.

tools/blocking_timeouts_baseline.txt is pinned empty: every violation this
gate can see has been fixed, so a new one fails CI immediately instead of
being grandfathered. Regenerate the baseline (only with justification) via:
    python tools/check_blocking_timeouts.py --update-baseline

The call classifiers (which calls count, how a Popen-like receiver is
resolved, the documented evasions) live in tools/_blocking_timeouts_rules.py;
this module applies ALLOWLIST on top and drives the ratchet.

ALLOWLIST covers two kinds of already-audited site, keyed `relpath:lineno:kind`
with each entry commented why:
  - 3 post-kill reaps: once a process has been sent SIGKILL, the wait is
    bounded by that signal, not by the wait call itself, so a second
    explicit timeout would be redundant. (SIGTERM does not qualify: the
    child can handle or ignore it, so a wait after terminate() needs its
    own timeout.)
  - 1 http-no-timeout site (`llm_bridge/embeddings.py`) where the timeout is
    set inside a `**kwargs` dict built by a helper (`_client_kwargs`), not as
    a literal keyword at the call site.
Any *new* violation must add a `timeout=` or a new, justified allowlist
entry -- it must not silently land in the baseline. An allowlist entry the
scanner cannot actually reach must not be kept "just in case": it earns its
place by suppressing a real, verified hit (see the test that reproduces each
site's exact relpath/line), never by resembling one.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import _ratchet
from _blocking_timeouts_rules import scan_tree
from _ratchet import read_text as _read_text

REPO_ROOT = Path(__file__).resolve().parent.parent
PY_ROOT = REPO_ROOT / "src" / "quodeq"
BASELINE_PATH = Path(__file__).resolve().parent / "blocking_timeouts_baseline.txt"


# Each entry suppresses one verified, already-audited site (see the module
# docstring). Post-kill reaps: the preceding kill() already bounds how long
# the wait can take, so a second timeout on the wait itself would be
# redundant.
ALLOWLIST: frozenset[str] = frozenset({
    # proc.wait() right after proc.kill(), inside stream_log_names' finally.
    "src/quodeq/data/git_cli.py:246:subprocess-wait",
    # await process.wait() right after process.kill() (asyncio subprocess).
    "src/quodeq/data/copilot_models.py:153:subprocess-wait",
    # process.wait() right after process.kill(), in _terminate_then_kill's
    # TimeoutExpired branch (the post-SIGTERM wait carries a timeout).
    "src/quodeq/dashboard/_api_spawn.py:86:subprocess-wait",
    # openai.OpenAI(**_client_kwargs(...)): timeout always set by
    # _client_kwargs() (defaults to BATCH_TIMEOUT when none is passed in).
    "src/quodeq/llm_bridge/embeddings.py:88:http-no-timeout",
})


def _relpath(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def violation_key(v: tuple[str, int, str]) -> str:
    """Identity for a violation: relpath:lineno:kind."""
    relpath, lineno, kind = v
    return f"{relpath}:{lineno}:{kind}"


def _scan_tree(tree: ast.AST, rel: str) -> list[tuple[str, int, str]]:
    """Return (relpath, lineno, kind) violations found in one parsed module."""
    return [v for v in scan_tree(tree, rel) if violation_key(v) not in ALLOWLIST]


def _scan_python() -> list[tuple[str, int, str]]:
    """Return (relpath, lineno, kind) violations for src/quodeq/**/*.py."""
    found: list[tuple[str, int, str]] = []
    for py in _ratchet.iter_python_files(PY_ROOT):
        text = _read_text(py)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as e:
            print(f"warning: skipping {py}: {e}", file=sys.stderr)
            continue
        found.extend(_scan_tree(tree, _relpath(py)))
    return found


def _scan() -> list[tuple[str, int, str]]:
    """Return all (relpath, lineno, kind) blocking-timeout violations, sorted."""
    return sorted(_scan_python())


def collect_violations() -> list[str]:
    """Return baseline keys for all current blocking-timeout violations."""
    return sorted({violation_key(v) for v in _scan()})


def load_baseline(path: Path = BASELINE_PATH) -> set[str]:
    """Return the set of grandfathered violation keys (empty if no baseline)."""
    return _ratchet.load_baseline(path)


def write_baseline(path: Path = BASELINE_PATH) -> int:
    """Write current violations to the baseline file; return the count."""
    header = (
        "# Grandfathered blocking-timeout violations (subprocess.run/wait or\n"
        "# an HTTP/SDK call with no explicit timeout=). Do NOT add entries\n"
        "# without justification -- the goal is to burn this list down, not\n"
        "# grow it.\n"
        "# Regenerate intentionally: python tools/check_blocking_timeouts.py --update-baseline\n"
        "# Entries are line-keyed (relpath:lineno:kind), so an unrelated line-count\n"
        "# change elsewhere in a file can shift existing entries. Prefer hand-editing\n"
        "# the baseline (update the shifted line number) over blind --update-baseline\n"
        "# regeneration, which can silently absorb a genuinely new violation\n"
        "# introduced in the same change.\n"
    )
    return _ratchet.write_baseline(path, header, collect_violations())


def main(argv: list[str] | None = None) -> int:
    return _ratchet.run_cli(argv, _ratchet.RatchetSpec(
        script_name="check_blocking_timeouts.py",
        noun="blocking-timeout",
        baseline_path=BASELINE_PATH,
        scan=_scan,
        violation_key=violation_key,
        update_baseline=write_baseline,
        describe=lambda v: f"{v[0]}:{v[1]}:{v[2]}",
    ))


if __name__ == "__main__":
    sys.exit(main())
