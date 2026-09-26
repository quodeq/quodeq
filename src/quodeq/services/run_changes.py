"""Which files moved between the commits two runs evaluated."""
from __future__ import annotations

from pathlib import Path

from quodeq.services.wiring import GIT_FLAG_C, git_stdout

SCOPE_CHANGED = "changed-files"
SCOPE_ALL = "all"
_DIFF = "diff"
_NAME_ONLY = "--name-only"


def changed_files(repo_root: Path | None, base_sha: str | None, head_sha: str | None) -> set[str] | None:
    """Paths (relative to *repo_root*) that differ between the two commits.

    None when the scope cannot be known: no local repo, a missing SHA, or
    git failing (an unknown commit, a shallow clone). Callers fall back to
    every file and say so."""
    if repo_root is None or not base_sha or not head_sha:
        return None
    out = git_stdout([GIT_FLAG_C, str(repo_root), _DIFF, _NAME_ONLY, base_sha, head_sha])
    if out is None:
        return None
    return {line.strip() for line in out.splitlines() if line.strip()}
