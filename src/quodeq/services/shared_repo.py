"""Shared results repository: clone, refresh, and path management.

The shared repo is a git remote holding an evaluations/ tree in the same
layout as the local evaluations dir. We keep a shallow clone under
~/.quodeq/cache/shared/<url-hash>/repo (QUODEQ_CACHE_ROOT overrides the base).
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_ENV = "QUODEQ_CACHE_ROOT"
_DEFAULT_GIT_TIMEOUT_S = 300


def run_git(
    args: list[str], *, cwd: Path | None = None, timeout: int = _DEFAULT_GIT_TIMEOUT_S
) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
        return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def _cache_base(env: dict | None = None) -> Path:
    e = env if env is not None else os.environ
    base = e.get(_CACHE_ENV)
    root = Path(base) if base else Path.home() / ".quodeq" / "cache"
    return root / "shared"


def shared_cache_dir(url: str, env: dict | None = None) -> Path:
    digest = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]
    return _cache_base(env) / digest


def shared_repo_path(url: str, env: dict | None = None) -> Path:
    return shared_cache_dir(url, env) / "repo"


def shared_evaluations_root(url: str, env: dict | None = None) -> Path:
    return shared_repo_path(url, env) / "evaluations"


def ensure_shared_clone(url: str, env: dict | None = None) -> Path | None:
    repo = shared_repo_path(url, env)
    if (repo / ".git").exists():
        return repo
    repo.parent.mkdir(parents=True, exist_ok=True)
    ok, out = run_git(["clone", "--depth", "1", "--", url, str(repo)])
    if not ok:
        logger.warning("shared clone failed for %s: %s", url, out.strip()[:500])
        shutil.rmtree(repo, ignore_errors=True)
        return None
    return repo


def refresh_shared_clone(url: str, env: dict | None = None) -> bool:
    repo = shared_repo_path(url, env)
    if not (repo / ".git").exists():
        return ensure_shared_clone(url, env) is not None
    ok, _ = run_git(["fetch", "--depth", "1", "origin", "HEAD"], cwd=repo)
    if not ok:
        return False
    ok, _ = run_git(["reset", "--hard", "FETCH_HEAD"], cwd=repo)
    return ok


def last_synced_at(url: str, env: dict | None = None) -> float | None:
    repo = shared_repo_path(url, env)
    for name in ("FETCH_HEAD", "HEAD"):
        candidate = repo / ".git" / name
        try:
            return candidate.stat().st_mtime
        except OSError:
            continue
    return None
