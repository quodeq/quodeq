"""Shared results repository: clone, refresh, and path management.

The shared repo is a git remote holding an evaluations/ tree in the same
layout as the local evaluations dir. We keep a full clone (no --depth,
results repos are small; a shallow clone made git-log-based attribution
misattribute every project to whoever pushed last)
under ~/.quodeq/cache/shared/<url-hash>/repo (QUODEQ_CACHE_ROOT overrides
the base).

Git-mutation serialization matters: background refreshes and an
in-flight publish share one clone directory, so an unserialized fetch +
hard-reset racing a stage/commit/push can tear a commit or contend on
.git/index.lock. `clone_lock()` gives every mutator (refresh_shared_clone,
ensure_shared_clone, publish_project) one process-wide lock per clone path.
Readers (published_meta, sync_shared_index, the read-only /api/shared/*
route mirrors) are deliberately NOT serialized against this lock -- full
reader serialization is deferred. Torn reads are bounded instead by the
atomic meta writes (published.json via tmp+rename): a reader can see a
project that is one publish stale, never a half-written published.json.
"""
from __future__ import annotations

import logging
import os
import shutil
import stat
import threading
from collections.abc import Callable, Mapping
from pathlib import Path

# Re-exported so the api layer can validate a shared-repo URL without
# importing quodeq.data directly (the import-layer gate in
# tools/check_imports.py allows api -> services and services -> data, but
# not api -> data). services/evaluation_mixin.py imports the same function
# straight from quodeq.data.fs.repo_validation for the same reason.
from quodeq.data.fs.repo_validation import validate_remote_url  # noqa: F401
from quodeq.data.fs.git_progress import ProgressUpdate, parse_progress
from quodeq.data.fs.git_stream import run_git_streaming
from quodeq.data.fs.shared_repo_git import (  # noqa: F401 -- re-exported for existing callers
    DEFAULT_GIT_TIMEOUT_S,
    EVALUATIONS_DIRNAME,
    run_git,
    shared_cache_dir,
    shared_evaluations_root,
    shared_repo_path,
)
from quodeq.shared.constants import GIT_DIR_NAME
# Re-exported: format/bootstrap, index sync and publish attribution live in
# shared_repo_meta.py; services/shared_repo.py and wiring.py import them
# through this module.
from quodeq.data.fs.shared_repo_meta import (  # noqa: F401
    FORMAT_NAME,
    FORMAT_VERSION,
    MARKER_FILENAME,
    PUBLISHED_META_FILENAME,
    RepoFormat,
    bootstrap_repo_layout,
    check_repo_format,
    published_meta,
    read_state,
    shared_index_db_path,
    shared_score_cache_path,
    sync_shared_index,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[ProgressUpdate], None]


def _forward_progress(progress: ProgressCallback | None) -> Callable[[str], None]:
    """An on_line callback that parses git's progress lines into *progress*."""
    def on_line(line: str) -> None:
        if progress is None:
            return
        update = parse_progress(line)
        if update is not None:
            progress(update)
    return on_line


def _clear_readonly_and_retry(func, path, exc):  # noqa: ARG001
    """rmtree onexc callback for git trees. Git marks object files read-only,
    and on Windows deleting a read-only file raises PermissionError (POSIX
    deletion only checks the parent dir). Clear the bit and retry once; if
    that also fails, log instead of raising so cleanup stays best-effort."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError as retry_exc:
        logger.warning("failed to remove %s: %s", path, retry_exc)


def remove_clone_dir(path: Path | str) -> None:
    """Best-effort recursive delete that tolerates git's read-only files.

    Missing paths are a no-op. Never raises: a half-removed or
    permission-denied dir must not turn cleanup into a 500.
    """
    if not os.path.lexists(path):
        return
    shutil.rmtree(path, onexc=_clear_readonly_and_retry)


_CLONE_LOCKS: dict[str, threading.RLock] = {}
_CLONE_LOCKS_GUARD = threading.Lock()


def clone_lock(url: str, env: Mapping[str, str] | None = None) -> threading.RLock:
    """Process-wide reentrant lock serializing git mutations on one clone.

    Keyed by the clone's resolved path (shared_repo_path), so any two
    callers that resolve to the same cache directory share one lock
    regardless of how they spelled the url. RLock, not Lock: publish_project
    holds this lock across its own internal refresh_shared_clone call, and
    refresh_shared_clone / ensure_shared_clone each acquire it again inside
    their own bodies -- a plain Lock would deadlock a thread against itself.
    See the module docstring for what this does and does not serialize.
    """
    key = str(shared_repo_path(url, env))
    with _CLONE_LOCKS_GUARD:
        return _CLONE_LOCKS.setdefault(key, threading.RLock())


def ensure_shared_clone(
    url: str, env: Mapping[str, str] | None = None, *, progress: ProgressCallback | None = None,
) -> Path | None:
    """Return the clone path for *url*, cloning it once if it is not there yet.

    None when the clone failed; the half-written directory is removed so the
    next call starts clean. Keeps the 300s default, unlike
    ``refresh_shared_clone`` -- a first clone can legitimately take minutes.
    Streams git's --progress lines into *progress* (see
    git_progress.parse_progress) so a UI can show the download.
    """
    with clone_lock(url, env):
        repo = shared_repo_path(url, env)
        if (repo / GIT_DIR_NAME).exists():
            return repo
        repo.parent.mkdir(parents=True, exist_ok=True)
        ok, out = run_git_streaming(
            ["clone", "--progress", "--", url, str(repo)],
            timeout=DEFAULT_GIT_TIMEOUT_S, env=env, on_line=_forward_progress(progress),
        )
        if not ok:
            logger.warning("shared clone failed for %s: %s", url, out.strip()[:500])
            remove_clone_dir(repo)
            return None
        return repo


_DEFAULT_REFRESH_TIMEOUT_S = 30


def _refresh_missing_clone(
    url: str, env: Mapping[str, str] | None, progress: ProgressCallback | None = None,
) -> tuple[bool, str]:
    if ensure_shared_clone(url, env, progress=progress) is not None:
        return True, ""
    reason = f"could not clone the repository, check that git can access {url}"
    logger.warning("refresh_shared_clone: %s", reason)
    return False, reason


def _fetch_and_reset_clone(
    url: str, repo: Path, timeout: int, env: Mapping[str, str] | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[bool, str]:
    # Unshallowing only applies to NEW clones: ensure_shared_clone stopped
    # passing --depth 1 in a prior fix, but a shared-clone cache directory
    # created back when it still did stays shallow forever otherwise --
    # ensure_shared_clone early-returns because `.git` already exists, and a
    # plain `fetch origin HEAD` does not unshallow a repo on its own. If
    # `.git/shallow` is present, try `git fetch --unshallow origin` first; a
    # failure there (network hiccup, odd remote) is not fatal -- fall through
    # to the plain fetch below, and a later refresh call retries the unshallow.
    if (repo / GIT_DIR_NAME / "shallow").exists():
        ok, out = run_git(["fetch", "--unshallow", "origin"], cwd=repo, timeout=timeout, env=env)
        if not ok:
            logger.debug("refresh_shared_clone: unshallow failed for %s: %s", url, out.strip()[:200])
    ok, out = run_git_streaming(
        ["fetch", "--progress", "origin", "HEAD"], cwd=repo, timeout=timeout, env=env,
        on_line=_forward_progress(progress),
    )
    if not ok:
        reason = out.strip()[:200]
        logger.warning("refresh_shared_clone: fetch failed for %s: %s", url, reason)
        return False, reason
    ok, out = run_git(["reset", "--hard", "FETCH_HEAD"], cwd=repo, timeout=timeout, env=env)
    if not ok:
        reason = out.strip()[:200]
        logger.warning("refresh_shared_clone: reset failed for %s: %s", url, reason)
        return False, reason
    return True, ""


def refresh_shared_clone(
    url: str, env: Mapping[str, str] | None = None, *, timeout: int = _DEFAULT_REFRESH_TIMEOUT_S,
    progress: ProgressCallback | None = None,
) -> tuple[bool, str]:
    """Fetch + hard-reset the clone to the remote's HEAD.

    Returns ``(ok, reason)``: *reason* is ``""`` on success, else the
    failing git command's stderr/stdout tail (<=200 chars) -- callers (the
    refresh route, the ?refresh=1 listing branch) surface this so a failed
    refresh reads as "could not resolve host" or "authentication failed"
    instead of a bare "Request failed: 502" that can't distinguish DNS vs
    auth vs a deleted origin. Every failure is ALSO
    logged via logger.warning, so a background/best-effort caller that
    discards *reason* (e.g. publish_project's internal refresh) still gets
    a diagnosable server-side trail.

    Called in-request (GET /api/shared/projects?refresh=1, POST
    /api/shared/refresh), so it must not inherit run_git's 300s default --
    a black-holed connection would otherwise hang the request for up to 5
    minutes. *timeout* bounds both the fetch (the network call) and the
    reset (local but kept consistent); a black-holed connection now turns
    into a stale=true response in ~*timeout* seconds instead. Does not
    affect ensure_shared_clone's own (still 300s) clone timeout -- an
    initial clone can legitimately take much longer than a refresh.

    Runs entirely under clone_lock: without it, this
    fetch + hard-reset can interleave with an in-flight publish_project's
    stage/commit/push on the same clone directory, tearing a commit or
    contending on .git/index.lock.
    """
    with clone_lock(url, env):
        repo = shared_repo_path(url, env)
        if not (repo / GIT_DIR_NAME).exists():
            return _refresh_missing_clone(url, env, progress)
        return _fetch_and_reset_clone(url, repo, timeout, env, progress)


def last_synced_at(url: str, env: Mapping[str, str] | None = None) -> float | None:
    """Unix mtime of the clone's last fetch, or None when it was never cloned.

    Falls back to HEAD when FETCH_HEAD is absent (cloned, never refreshed).
    """
    repo = shared_repo_path(url, env)
    for name in ("FETCH_HEAD", "HEAD"):
        candidate = repo / GIT_DIR_NAME / name
        try:
            return candidate.stat().st_mtime
        except OSError:
            continue
    return None


_GITIGNORE_FILENAME = ".gitignore"
_GITKEEP_FILENAME = ".gitkeep"


def stage_publish_paths(repo: Path, project_id: str) -> tuple[bool, str]:
    """``git add`` everything a publish of *project_id* may have written:
    the format marker, the ignore file, the project's evaluations tree and
    the evaluations/.gitkeep placeholder when the layout has one. Returns
    ``run_git``'s ``(ok, output)``.
    """
    add_paths = [MARKER_FILENAME, _GITIGNORE_FILENAME, f"{EVALUATIONS_DIRNAME}/{project_id}"]
    if (repo / EVALUATIONS_DIRNAME / _GITKEEP_FILENAME).exists():
        add_paths.append(f"{EVALUATIONS_DIRNAME}/{_GITKEEP_FILENAME}")
    return run_git(["add", "--", *add_paths], cwd=repo)
