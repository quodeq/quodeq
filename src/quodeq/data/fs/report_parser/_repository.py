"""Repository metadata construction."""

from __future__ import annotations

from pathlib import Path

from quodeq.shared.utils import is_repo_url

_GIT_SUFFIX = ".git"


def build_repository_info(repo: str, discipline: str | None) -> dict[str, str | None]:
    """Build a repository metadata dict from a local path or remote URL.

    Example::

        build_repository_info("https://github.com/org/repo.git", "python")
    """
    if is_repo_url(repo):
        name = repo.split("/")[-1].replace(_GIT_SUFFIX, "")
        return {
            "name": name,
            "discipline": discipline,
            "location": "online",
            "path": repo,
        }
    resolved = Path(repo).resolve()
    return {
        "name": resolved.name,
        "discipline": discipline,
        "location": "local",
        "path": resolved.name,
    }
