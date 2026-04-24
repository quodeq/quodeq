"""Repository URL helpers."""
from __future__ import annotations

import subprocess
from pathlib import Path


def is_repo_url(repo_input: str) -> bool:
    """Return True if the input looks like a remote repository URL.

    Raises ValueError for cleartext ``http://`` URLs to enforce encrypted
    transport for credential safety.
    """
    if repo_input.startswith("http://"):
        raise ValueError(
            "Cleartext HTTP repository URLs are rejected to protect credentials. "
            "Use https:// or git@ instead."
        )
    return repo_input.startswith(("https://", "git@"))


def project_name_from_repo(repo: str) -> str:
    """Extract a human-readable project name from a repo path or URL."""
    if is_repo_url(repo):
        return repo.split("/")[-1].replace(".git", "")
    return Path(repo).resolve().name


def git_remote_url(repo_path: str) -> str | None:
    """Return the normalized canonical URL of the git 'origin' remote, if any.

    Reads the origin remote URL via ``git config`` from *repo_path*.
    Returns ``None`` if:
    - path is not a git repo
    - no 'origin' remote configured
    - git is not installed
    - remote URL is malformed / empty

    Normalization maps these equivalent forms to a single canonical form:
      - ``git@github.com:owner/repo.git`` -> ``github.com/owner/repo``
      - ``https://github.com/owner/repo.git`` -> ``github.com/owner/repo``
      - ``https://github.com/owner/repo`` -> ``github.com/owner/repo``
      - ``ssh://git@github.com/owner/repo.git`` -> ``github.com/owner/repo``

    Trailing ``.git`` is stripped. Leading ``https://`` / ``ssh://`` / ``git@``
    is stripped. The colon in ``git@host:path`` form is converted to ``/``.
    Non-standard ports (e.g. ``host:22/path``) are not supported.
    """
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    url = result.stdout.strip()
    if not url:
        return None

    # Strip known scheme prefixes
    if url.startswith("https://"):
        url = url[len("https://"):]
    elif url.startswith("ssh://"):
        url = url[len("ssh://"):]
    if url.startswith("git@"):
        url = url[len("git@"):]

    # Convert git@host:path form to host/path.
    # First colon splits host from path when path isn't numeric (port).
    if ":" in url:
        head, _sep, tail = url.partition(":")
        if tail and not tail[:1].isdigit():
            url = f"{head}/{tail}"

    if url.endswith(".git"):
        url = url[:-4]
    url = url.rstrip("/")
    return url or None
