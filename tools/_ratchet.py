"""Shared baseline plumbing for the tools/check_*.py ratchets.

A ratchet scans the tree, keys each violation with a stable string, and
compares against a committed baseline that may only shrink. Each checker
owns its scan and its key; this module owns the parts that were otherwise
copy-pasted between them: reading files, reading and writing the baseline
file, and the `[--update-baseline]` command line.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Sequence, TypeVar

V = TypeVar("V")


def read_text(path: Path) -> str | None:
    """Return a file's text, or None (after a warning) if it can't be read."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"warning: skipping {path}: {e}", file=sys.stderr)
        return None


def load_baseline(path: Path) -> set[str]:
    """Return the set of grandfathered keys (empty if no baseline)."""
    if not path.exists():
        return set()
    return {
        stripped
        for line in path.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    }


def write_baseline(path: Path, header: str, keys: Sequence[str]) -> int:
    """Write `header` (comment lines) plus sorted keys; return the count."""
    body = "\n".join(sorted(keys))
    path.write_text(header + body + ("\n" if keys else ""), encoding="utf-8")
    return len(keys)


def run_cli(
    argv: Sequence[str] | None,
    *,
    script_name: str,
    baseline_path: Path,
    scan: Callable[[], list[V]],
    violation_key: Callable[[V], str],
    update_baseline: Callable[[], int],
    describe: Callable[[V], str],
    noun: str,
) -> int:
    """Standard `check_x.py [--update-baseline]` entry point.

    Returns 0 when there are no violations outside the baseline, 1 when new
    violations exist (each printed via `describe`), 2 on unknown arguments.
    """
    args = list(argv) if argv is not None else sys.argv[1:]
    unknown = [a for a in args if a != "--update-baseline"]
    if unknown:
        print(f"Unknown argument(s): {' '.join(unknown)}. Usage: {script_name} [--update-baseline]")
        return 2
    if "--update-baseline" in args:
        n = update_baseline()
        print(f"Wrote {n} violation(s) to {baseline_path}")
        return 0

    baseline = load_baseline(baseline_path)
    all_violations = scan()
    new = [v for v in all_violations if violation_key(v) not in baseline]
    grandfathered = len(all_violations) - len(new)
    if not new:
        print(f"OK: no new {noun} violations ({grandfathered} grandfathered).")
        return 0
    print(f"Found {len(new)} NEW {noun} violation(s) ({grandfathered} grandfathered):\n")
    for v in new:
        print(f"  {describe(v)}")
    return 1
