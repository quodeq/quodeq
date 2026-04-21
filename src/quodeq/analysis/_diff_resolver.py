"""Resolve the set of files changed between HEAD and a base git ref.

Used by PR diff mode to scope analysis to just the PR's changes. The base
ref is the PR's target branch (e.g., ``origin/develop``). Uses
``git merge-base`` so that changes on the base branch since the PR was
opened are not falsely attributed to the PR.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_GIT_TIMEOUT_S = 15


class DiffResolveError(RuntimeError):
    """Raised when ``git diff`` against the base ref cannot be computed."""


def _git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DiffResolveError(f"git {' '.join(args)} failed: {exc}") from exc
    if result.returncode != 0:
        raise DiffResolveError(
            f"git {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


def resolve_diff_files(src: Path, ref: str) -> list[str]:
    """Return files changed between ``HEAD`` and ``merge-base(ref, HEAD)``.

    Deleted files (in diff but absent from ``HEAD``) are dropped — PR mode
    only analyzes files that still exist on the PR branch.
    """
    base_sha = _git(["merge-base", ref, "HEAD"], src).strip()
    if not base_sha:
        raise DiffResolveError(f"empty merge-base output for ref {ref!r}")
    raw = _git(["diff", "--name-only", f"{base_sha}..HEAD"], src)
    candidates = [line.strip() for line in raw.splitlines() if line.strip()]
    return [f for f in candidates if (src / f).is_file()]
