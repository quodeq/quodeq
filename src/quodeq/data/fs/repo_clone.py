"""Repository cloning and cleanup — manages temporary clone directories."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from quodeq.data.fs.repo_validation import (
    _PRIVATE_HOST_RE,
    _REPO_URL_RE,
    _resolves_to_private,
)

_logger = logging.getLogger(__name__)

_DEFAULT_CLONE_TIMEOUT_S = 300


def _get_clone_timeout(env: dict[str, str] | None = None) -> int:
    """Return the git clone timeout, reading the env var lazily."""
    try:
        return int((env or os.environ).get("QUODEQ_GIT_CLONE_TIMEOUT", str(_DEFAULT_CLONE_TIMEOUT_S)))
    except ValueError:
        return _DEFAULT_CLONE_TIMEOUT_S


def prepare_repository(repo_input: str) -> str:
    """Clone a remote repository to a temporary directory and return its path.

    Raises ValueError if the URL does not match the expected git repository format.
    """
    if not _REPO_URL_RE.match(repo_input):
        raise ValueError(f"Invalid repository URL format: {repo_input}. Expected: https://github.com/user/repo or git@github.com:user/repo.git")
    if _PRIVATE_HOST_RE.match(repo_input):
        raise ValueError("Repository URLs pointing to private/internal addresses are not allowed")
    # Post-resolution check: guard against DNS rebinding where a public hostname
    # resolves to a private IP at clone time.
    if repo_input.startswith("http"):
        import urllib.parse
        hostname = urllib.parse.urlparse(repo_input).hostname or ""
        if hostname and _resolves_to_private(hostname):
            raise ValueError("Repository URL resolves to a private/internal address")
    repo_name = repo_input.split("/")[-1].replace(".git", "")
    tmp_dir = tempfile.mkdtemp()
    dest = Path(tmp_dir) / repo_name
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
    try:
        _logger.info("Cloning %s (timeout: %ds)...", repo_input, _get_clone_timeout())
        subprocess.run(
            ["git", "clone", "--progress", repo_input, str(dest)],
            check=True, env=env, timeout=_get_clone_timeout(),
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return str(dest.resolve())


def cleanup_cloned_repo(repo_path: str) -> None:
    """Remove the temporary clone directory for *repo_path*.

    Call this after the evaluation completes to free disk space promptly
    instead of accumulating temp directories until process exit.
    """
    parent = str(Path(repo_path).resolve().parent)
    try:
        shutil.rmtree(parent, ignore_errors=True)
    except OSError as exc:
        _logger.warning("Failed to clean up temp repo dir %s: %s", parent, exc)
