"""Publish a project into the shared results repo, plus the background
publish-job status tracker.

Split into two sibling modules plus this thin orchestrator:
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
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path

from quodeq.services._publish_git import (
    commit_staged_changes,
    push_with_rebase_fallback,
    prepare_clone,
)
from quodeq.services._publish_staging import (
    copy_run,
    list_completed_runs,
    merge_actions_log,
    stage_project,
)
from quodeq.services.wiring import (
    MARKER_FILENAME,
    bootstrap_repo_layout,
    clone_lock,
    ensure_shared_clone,
    run_git,
)
from quodeq.shared.validation import validate_path_segment

__all__ = [
    "GIT_ERROR_SNIPPET_MAX_CHARS", "PublishError", "PublishState", "PublishStatus",
    "get_publish_status", "publish_project", "start_publish",
    # Re-exported so callers and tests keep reaching them at this module's
    # path; ``ensure_shared_clone`` is also a patch target.
    "clone_lock", "copy_run", "ensure_shared_clone", "list_completed_runs",
    "merge_actions_log", "stage_project",
]

logger = logging.getLogger(__name__)


class PublishError(Exception):
    """User-facing publish failure."""


# git output is included verbatim in PublishError messages (add/commit/push);
# truncated to this many characters so a noisy git error can't blow up a
# status payload. Shared with _publish_git.py's commit/push failures.
GIT_ERROR_SNIPPET_MAX_CHARS = 300


@contextmanager
def _prepare_workspace(
    project_id: str, url: str, evaluations_root: Path, env: dict | None,
) -> Iterator[tuple[Path, Path]]:
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
    # process-wide clone lock, an RLock so the
    # ensure_shared_clone/refresh_shared_clone calls inside prepare_clone
    # (each of which acquires it again internally) reenter on this same
    # thread instead of deadlocking.
    with clone_lock(url, env):
        repo, fmt = prepare_clone(url, env)
        if fmt == "empty":
            try:
                bootstrap_repo_layout(repo)
            except (OSError, ValueError) as exc:
                raise PublishError(f"failed to stage project files, {exc}") from exc
        yield project_dir, repo


def _commit_and_push(repo: Path, project_id: str, count: int) -> None:
    add_paths = [MARKER_FILENAME, ".gitignore", f"evaluations/{project_id}"]
    if (repo / "evaluations" / ".gitkeep").exists():
        add_paths.append("evaluations/.gitkeep")
    ok, out = run_git(["add", "--", *add_paths], cwd=repo)
    if not ok:
        raise PublishError(f"git add failed, {out.strip()[:GIT_ERROR_SNIPPET_MAX_CHARS]}")

    commit_staged_changes(repo, project_id, count)
    push_with_rebase_fallback(repo)


def publish_project(
    project_id: str, url: str, *, evaluations_root: Path, env: dict | None = None
) -> int:
    """Stage a project's completed runs into the shared results repo and push them.

    Returns the number of runs staged. Raises ``PublishError`` for anything a
    user can act on (bad project id, missing project, git add/commit/push
    failure). The whole clone-stage-push sequence runs under one process-wide
    clone lock, so concurrent publishes serialise instead of racing on the
    working tree.
    """
    with _prepare_workspace(project_id, url, evaluations_root, env) as (project_dir, repo):
        try:
            count = stage_project(project_dir, repo / "evaluations" / project_id)
        except (OSError, ValueError) as exc:
            raise PublishError(f"failed to stage project files, {exc}") from exc

        _commit_and_push(repo, project_id, count)
        return count


class PublishState(StrEnum):
    """The states a background publish job passes through."""

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class PublishStatus:
    """Lock-guarded publish job status (states: idle/running/done/error).

    Instantiable so tests get isolated status; production shares the
    module-default instance below — a single global publish slot.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status: dict = {
            "state": PublishState.IDLE,
            "project": None,
            "runs": None,
            "error": None,
            "finished_at": None,
        }

    def copy(self) -> dict:
        """Return a snapshot of the status fields, safe to hand to a route."""
        with self._lock:
            return dict(self._status)

    def set(self, **fields) -> None:
        """Merge *fields* into the status. Keys are not validated."""
        with self._lock:
            self._status.update(fields)

    def claim(self, project_id: str) -> bool:
        """Atomically take the publish slot; False when a publish is running."""
        with self._lock:
            if self._status["state"] == PublishState.RUNNING:
                return False
            self._status.update(
                state=PublishState.RUNNING, project=project_id, runs=None, error=None,
                finished_at=None,
            )
            return True


_default_status = PublishStatus()


def get_publish_status(status: PublishStatus | None = None) -> dict:
    """Return a snapshot of the publish slot, defaulting to the module-wide one."""
    return (status or _default_status).copy()


def _run_publish(
    project_id: str, url: str, evaluations_root: Path, status: PublishStatus,
) -> None:
    try:
        count = publish_project(project_id, url, evaluations_root=evaluations_root)
        status.set(state=PublishState.DONE, runs=count, error=None, finished_at=time.time())
    except PublishError as exc:
        status.set(state=PublishState.ERROR, error=str(exc), finished_at=time.time())
    except Exception:  # never leave the job stuck in "running"
        logger.exception("unexpected publish failure")
        status.set(state=PublishState.ERROR, error="An unexpected error occurred while publishing.", finished_at=time.time())


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
    except Exception:
        status.set(state=PublishState.ERROR, error="Failed to start publish background job.", finished_at=time.time())
        logger.exception("failed to start publish thread")
        return "failed"
    return "started"
