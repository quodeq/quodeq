"""Local git repository statistics.

A read-only ``git`` subprocess call over an analyzed repo's history. Fails
open (returns None) on any git/subprocess trouble -- a missing repo, no git
binary, a non-zero exit, a timeout -- so a staleness signal can never crash
the caller that asks for it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_DEFAULT_TIMEOUT_S = 5


def count_commits_since(
    repo_root: Path, since_iso: str, *, timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> int | None:
    """Commits in *repo_root* since *since_iso*, or None when unknowable.

    None (never 0 as a stand-in) on any git trouble: a missing repo, no git
    binary, a non-zero exit, a timeout, or an unparseable count. Callers must
    not infer "no new commits" from a None result.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-list", "--count", f"--since={since_iso}", "HEAD"],
            capture_output=True, encoding="utf-8", timeout=timeout_s, check=False,
        )
        if proc.returncode != 0:
            return None
        return int(proc.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
