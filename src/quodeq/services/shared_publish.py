"""Publish a project into the shared results repo, plus the background
publish-job status tracker.

Split (Task 12) into two sibling modules plus this thin orchestrator:
  - _publish_staging.py: pure file-copy/merge staging (list_completed_runs,
    copy_run, merge_actions_log, stage_project).
  - _publish_git.py: the git-side steps (clone prep, staged-diff commit,
    push, rebase-fallback retry).

`run_git`, `ensure_shared_clone`, and the staging/git helper functions stay
imported here (some unused directly) so tests can keep patching
"quodeq.services.shared_publish.<name>" -- _publish_git.py looks up
`run_git` and `PublishError` on this module at call time rather than
binding its own copies.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from quodeq.services._publish_git import (
    _commit_staged_changes,
    _push_with_rebase_fallback,
    _prepare_clone,
)
from quodeq.services._publish_staging import stage_project
from quodeq.services._publish_staging import (  # noqa: F401 — re-export
    copy_run,
    list_completed_runs,
    merge_actions_log,
)
from quodeq.services._wiring import (
    MARKER_FILENAME,
    bootstrap_repo_layout,
    clone_lock,
    run_git,
)
from quodeq.services._wiring import ensure_shared_clone  # noqa: F401 — re-export/patch target
from quodeq.shared.validation import validate_path_segment

logger = logging.getLogger(__name__)


class PublishError(Exception):
    """User-facing publish failure."""


def publish_project(
    project_id: str, url: str, *, evaluations_root: Path, env: dict | None = None
) -> int:
    # The route validates too, but this is the last stop before project_id
    # becomes a filesystem path and a git pathspec, so guard it here as well.
    try:
        validate_path_segment(project_id)
    except ValueError as exc:
        raise PublishError(str(exc)) from exc
    project_dir = evaluations_root / project_id
    if not project_dir.is_dir():
        raise PublishError(f"project {project_id} not found in local evaluations")

    # Everything from here through the final push/rebase runs under one
    # process-wide clone lock (audit finding C2), an RLock so the
    # ensure_shared_clone/refresh_shared_clone calls inside _prepare_clone
    # (each of which acquires it again internally) reenter on this same
    # thread instead of deadlocking.
    with clone_lock(url, env):
        repo, fmt = _prepare_clone(url, env)
        try:
            if fmt == "empty":
                bootstrap_repo_layout(repo)
            count = stage_project(project_dir, repo / "evaluations" / project_id)
        except (OSError, ValueError) as exc:
            raise PublishError(f"failed to stage project files, {exc}") from exc

        add_paths = [MARKER_FILENAME, ".gitignore", f"evaluations/{project_id}"]
        if (repo / "evaluations" / ".gitkeep").exists():
            add_paths.append("evaluations/.gitkeep")
        ok, out = run_git(["add", "--", *add_paths], cwd=repo)
        if not ok:
            raise PublishError(f"git add failed, {out.strip()[:300]}")

        _commit_staged_changes(repo, project_id, count)
        _push_with_rebase_fallback(repo)
        return count


class PublishStatus:
    """Lock-guarded publish job status (states: idle/running/done/error).

    Instantiable so tests get isolated status; production shares the
    module-default instance below — a single global publish slot.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status: dict = {
            "state": "idle",
            "project": None,
            "runs": None,
            "error": None,
            "finished_at": None,
        }

    def copy(self) -> dict:
        with self._lock:
            return dict(self._status)

    def set(self, **fields) -> None:
        with self._lock:
            self._status.update(fields)

    def claim(self, project_id: str) -> bool:
        """Atomically take the publish slot; False when a publish is running."""
        with self._lock:
            if self._status["state"] == "running":
                return False
            self._status.update(
                state="running", project=project_id, runs=None, error=None,
                finished_at=None,
            )
            return True


_default_status = PublishStatus()


def get_publish_status(status: PublishStatus | None = None) -> dict:
    return (status or _default_status).copy()


def _run_publish(
    project_id: str, url: str, evaluations_root: Path, status: PublishStatus,
) -> None:
    try:
        count = publish_project(project_id, url, evaluations_root=evaluations_root)
        status.set(state="done", runs=count, error=None, finished_at=time.time())
    except PublishError as exc:
        status.set(state="error", error=str(exc), finished_at=time.time())
    except Exception as exc:  # never leave the job stuck in "running"
        logger.exception("unexpected publish failure")
        status.set(state="error", error=str(exc), finished_at=time.time())


def start_publish(
    project_id: str, url: str, *,
    evaluations_root: Path,
    status: PublishStatus | None = None,
) -> str:
    """Kick off a background publish.

    Returns "started", "already_running" (another publish holds the slot),
    or "failed" (the worker thread could not be started; the status dict
    carries the error). Callers must not collapse the last two: one is a
    409-style conflict, the other a server-side failure.
    """
    status = status or _default_status
    if not status.claim(project_id):
        return "already_running"
    try:
        thread = threading.Thread(
            target=_run_publish, args=(project_id, url, evaluations_root, status),
            daemon=True,
        )
        thread.start()
    except Exception as exc:
        status.set(state="error", error=str(exc), finished_at=time.time())
        logger.exception("failed to start publish thread")
        return "failed"
    return "started"
