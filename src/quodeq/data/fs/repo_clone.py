"""Repository cloning and cleanup — manages clone directories.

Online repos are cached under ``~/.quodeq/cache/online/<url_hash>/repo``
via :mod:`quodeq.context.online_cache`, so subsequent evaluations against
the same URL reuse the working copy (fetch + reset) instead of re-cloning
into a fresh temp dir. Set ``QUODEQ_DISABLE_ONLINE_CACHE=1`` to fall back
to the legacy mkdtemp flow (one fresh clone per evaluation).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from quodeq.context.online_cache import (
    cache_disabled,
    ensure_clone,
    is_inside_cache,
)
from quodeq.data.fs.repo_validation import validate_remote_url as _validate_remote_url

_logger = logging.getLogger(__name__)

_DEFAULT_CLONE_TIMEOUT_S = 300


def _get_clone_timeout(env: dict[str, str] | None = None) -> int:
    """Return the git clone timeout, reading the env var lazily."""
    try:
        return int((env or os.environ).get("QUODEQ_GIT_CLONE_TIMEOUT", str(_DEFAULT_CLONE_TIMEOUT_S)))
    except ValueError:
        return _DEFAULT_CLONE_TIMEOUT_S


def _legacy_tempdir_clone(repo_input: str) -> str:
    """Fall-back path: fresh ``mkdtemp`` + ``git clone`` every call.

    Used when the online cache is disabled or when the cache helper
    couldn't produce a working copy (e.g. the cache directory is read-only).
    """
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


def prepare_repository(repo_input: str) -> str:
    """Return a local working copy of *repo_input*, cloning if necessary.

    Routes through :func:`quodeq.context.online_cache.ensure_clone` so the
    second-and-onward evaluations of the same URL reuse a shallow cached
    clone (fetched + reset to ``origin/HEAD``). The legacy mkdtemp clone
    path is kept as a fallback and behind ``QUODEQ_DISABLE_ONLINE_CACHE``.

    Raises ValueError if the URL does not match the expected git
    repository format.
    """
    _validate_remote_url(repo_input)
    if cache_disabled():
        return _legacy_tempdir_clone(repo_input)
    cached = ensure_clone(repo_input)
    if cached is not None:
        return str(cached.resolve())
    # Cache-miss + clone failure: try the old path so a corrupt cache
    # entry doesn't take an entire evaluation offline.
    return _legacy_tempdir_clone(repo_input)


def cleanup_cloned_repo(repo_path: str) -> None:
    """Remove the temporary clone directory for *repo_path*.

    No-op when *repo_path* lives inside the persistent online cache:
    that dir survives between evaluations on purpose. Only the legacy
    mkdtemp clones get torn down here.
    """
    if is_inside_cache(repo_path):
        return
    parent = str(Path(repo_path).resolve().parent)
    try:
        shutil.rmtree(parent, ignore_errors=True)
    except OSError as exc:
        _logger.warning("Failed to clean up temp repo dir %s: %s", parent, exc)
