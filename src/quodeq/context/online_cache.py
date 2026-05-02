"""Persistent shallow-clone cache for online repositories.

Today every evaluation of an online repo re-clones into ``mkdtemp()`` and
deletes the temp dir on exit, paying the full clone cost every run. This
module replaces that with a deterministic cache under
``~/.quodeq/cache/online/<url_hash>/repo``: the first evaluation clones
shallow, every subsequent evaluation fetches and fast-forwards instead.

The cache is purely derivative. Wipe it and the next evaluation will
re-populate it; no user data lives here. The location is fixed
(``~/.quodeq/cache/online/``) and survives subprocess boundaries, so
both the GUI and the CLI converge on the same path.

A kill switch (``QUODEQ_DISABLE_ONLINE_CACHE=1``) bypasses the cache and
restores the old mkdtemp-based flow, in case a user hits a corrupt cache
entry or wants reproducible-from-scratch evaluations.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
from pathlib import Path

_logger = logging.getLogger(__name__)

_CACHE_ENV = "QUODEQ_CACHE_ROOT"  # override the cache root for tests / sandboxing
_DISABLE_ENV = "QUODEQ_DISABLE_ONLINE_CACHE"
_DEFAULT_CLONE_TIMEOUT_S = 300


def cache_root() -> Path:
    """Return the cache root, creating it if needed.

    Defaults to ``~/.quodeq/cache``; override with ``QUODEQ_CACHE_ROOT``
    so tests can point at a sandbox without touching the user's real cache.
    """
    raw = os.environ.get(_CACHE_ENV, "").strip()
    base = Path(raw) if raw else Path.home() / ".quodeq" / "cache"
    online = base / "online"
    online.mkdir(parents=True, exist_ok=True)
    return online


def cache_disabled() -> bool:
    """True when the user has flipped the kill switch."""
    return os.environ.get(_DISABLE_ENV, "").strip() in {"1", "true", "yes"}


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]


def cache_dir_for_url(url: str) -> Path:
    """Return the per-URL cache directory (``<root>/<url_hash>/``).

    The repo itself is cloned into the ``repo`` subdirectory; metadata
    (last-fetched timestamp, marker files) lives next to it. Truncating
    the hash to 16 hex chars keeps paths readable while still avoiding
    collisions on any plausible number of cached repos.
    """
    return cache_root() / _url_hash(url)


def repo_path_for_url(url: str) -> Path:
    """Return the working-copy path inside the cache for *url*."""
    return cache_dir_for_url(url) / "repo"


def is_inside_cache(path: str | Path) -> bool:
    """True when *path* lives under the cache root.

    Used by the eval-cleanup hook so an old ``rmtree(parent)`` doesn't
    nuke the cache when the working dir happens to live inside it.
    """
    try:
        resolved = Path(path).resolve()
        return resolved.is_relative_to(cache_root().resolve())
    except (OSError, RuntimeError):
        return False


def _git(args: list[str], *, cwd: Path | None = None,
         timeout: int = _DEFAULT_CLONE_TIMEOUT_S) -> bool:
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
    try:
        subprocess.run(
            ["git", *args], check=True, env=env, timeout=timeout,
            cwd=str(cwd) if cwd is not None else None,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        _logger.warning("git %s failed: %s", " ".join(args), exc)
        return False


def _refresh_existing(repo: Path) -> bool:
    """Fast-forward an existing cached clone to ``origin/HEAD``.

    Uses a shallow fetch + hard reset so cosmetic diffs from prior runs
    can't poison the next evaluation. If the fetch fails (network outage,
    upstream gone), the cached working copy is left as-is and the eval
    runs against stale code. That's strictly better than failing outright,
    and the user can always wipe the cache to retry from scratch.
    """
    if not _git(["fetch", "--depth", "1", "origin", "HEAD"], cwd=repo):
        return False
    return _git(["reset", "--hard", "FETCH_HEAD"], cwd=repo)


def ensure_clone(url: str) -> Path | None:
    """Return a cached working copy of *url*, cloning or refreshing as needed.

    First call shallow-clones into ``<cache>/<url_hash>/repo``. Subsequent
    calls fetch + reset that same directory. Returns ``None`` if the
    initial clone fails so the caller can fall back to the old mkdtemp
    path; established cache entries are returned even if refresh fails.
    """
    repo = repo_path_for_url(url)
    repo.parent.mkdir(parents=True, exist_ok=True)

    if (repo / ".git").exists():
        # Refresh failures don't invalidate the cache: stale code is
        # better than a hard failure when the network is flaky.
        _refresh_existing(repo)
        return repo

    # First-time clone — shallow, single-branch, default ref.
    if not _git(["clone", "--depth", "1", "--", url, str(repo)]):
        # Clean up a half-clone so the next ensure_clone retries cleanly.
        shutil.rmtree(repo, ignore_errors=True)
        return None
    return repo


def wipe_cache() -> int:
    """Remove every cached clone. Returns the number of entries wiped.

    The cache root itself is preserved (just emptied) so the next call
    to ``cache_root()`` doesn't have to recreate it.
    """
    root = cache_root()
    count = 0
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        shutil.rmtree(entry, ignore_errors=True)
        count += 1
    return count
