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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path

from quodeq.services._publish_git import (
    commit_staged_changes,
    push_with_rebase_fallback,
    prepare_clone,
)
from quodeq.services._publish_standards import (
    record_shared_hashes,
    stage_scored_standards,
)
from quodeq.services._publish_staging import (
    StagedProject,
    copy_run,
    list_completed_runs,
    merge_actions_log,
    stage_project,
)
from quodeq.services.github_access import forget_url
from quodeq.services.job_status import JobSlotStatus
from quodeq.services._fs_metadata import local_repo_root
from quodeq.services.shared_activity import stage_activity
from quodeq.services.wiring import (
    RepoFormat,
    bootstrap_repo_layout,
    clone_lock,
    ensure_shared_clone,
    run_git,  # noqa: F401 -- _publish_git reads run_git from this namespace
    stage_publish_paths,
)
from quodeq.services.wiring_sync import (
    SHARED_STANDARDS_DIRNAME, find_repo_link, reset_clone_to_remote, restore_shared_standards, stage_standard_paths,
)
from quodeq.shared.fault_isolation import run_isolated
from quodeq.shared.log_sink import LoggerSink
from quodeq.shared.validation import validate_path_segment

__all__ = [
    "GIT_ERROR_SNIPPET_MAX_CHARS", "PublishError", "PublishState", "PublishStatus",
    "get_publish_status", "publish_project", "start_publish",
    # Re-exported so callers and tests keep reaching them at this module's
    # path; ``ensure_shared_clone`` is also a patch target.
    "StagedProject", "clone_lock", "copy_run", "ensure_shared_clone", "list_completed_runs",
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
        if fmt == RepoFormat.EMPTY:
            try:
                bootstrap_repo_layout(repo)
            except (OSError, ValueError) as exc:
                raise PublishError(f"failed to stage project files, {exc}") from exc
        yield project_dir, repo


def _refuse_links(repo: Path, project_id: str) -> None:
    """Refuse before any write when the repository holds a link where publish writes (it would write through it)."""
    link = find_repo_link(repo, (f"evaluations/{project_id}", SHARED_STANDARDS_DIRNAME))
    if link is not None:
        raise PublishError(f"The shared repository contains a link at {link}. "
                           "Remove it from the repository and publish again.")


def _commit_and_push(repo: Path, project_id: str, staged: StagedProject, env: dict | None = None,
                     standard_ids: list[str] | None = None) -> None:
    ok, out = stage_publish_paths(repo, staged.paths)
    if ok and standard_ids:
        ok, out = stage_standard_paths(repo, standard_ids)
    if not ok:
        raise PublishError(f"git add failed, {out.strip()[:GIT_ERROR_SNIPPET_MAX_CHARS]}")

    commit_staged_changes(repo, project_id, staged.runs)
    push_with_rebase_fallback(repo, env)


def publish_project(
    project_id: str, url: str, *, evaluations_root: Path, env: dict | None = None,
    on_skipped: Callable[[list[str]], None] | None = None, with_snippets: bool = False,
) -> int:
    """Stage a project's completed runs into the shared results repo and push them.

    The custom standards those runs scored ride in the same commit; ids whose
    shared copy is newer are left alone and handed to *on_skipped* after the
    push. Code snippets are published only *with_snippets* (the shared
    repository's opt-in). Returns the number of runs staged. Raises ``PublishError`` for anything a
    user can act on (bad project id, missing project, git add/commit/push
    failure). The whole clone-stage-push sequence runs under one process-wide
    clone lock, so concurrent publishes serialise instead of racing on the
    working tree.
    """
    with _prepare_workspace(project_id, url, evaluations_root, env) as (project_dir, repo):
        # A failed earlier attempt can leave standards/ files the comparison
        # below would read as already shared: start from HEAD.
        restored, out = restore_shared_standards(repo)
        if not restored:
            raise PublishError("failed to reset the shared standards folder, "
                               f"{out.strip()[:GIT_ERROR_SNIPPET_MAX_CHARS]}")
        _refuse_links(repo, project_id)
        try:
            staged = stage_project(project_dir, repo / "evaluations" / project_id, with_snippets=with_snippets)
            activity = stage_activity(project_dir, repo / "evaluations" / project_id,
                                      local_repo_root(evaluations_root, project_id), log=LoggerSink(logger))
            if activity is not None:
                staged.paths.append(activity)
            standards = stage_scored_standards(project_dir, repo, log=LoggerSink(logger))
        except (OSError, ValueError) as exc:
            raise PublishError(f"failed to stage project files, {exc}") from exc

        try:
            _commit_and_push(repo, project_id, staged, env, standards.published)
        except PublishError:
            # An unpushed commit must not read as shared (listing, installs).
            reset_clone_to_remote(url, env)
            raise
        record_shared_hashes(repo, standards, log=LoggerSink(logger))
    if on_skipped is not None:
        on_skipped(standards.skipped)
    return staged.runs


class PublishState(StrEnum):
    """The states a background publish job passes through."""

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class PublishStatus(JobSlotStatus):
    """Lock-guarded publish job status (states: idle/running/done/error).

    Instantiable so tests get isolated status; production shares the
    module-default instance below — a single global publish slot.
    """

    def __init__(self) -> None:
        super().__init__(
            {
                "state": PublishState.IDLE,
                "project": None,
                "runs": None,
                "error": None,
                "finished_at": None,
                "skipped_standards": [],
            },
            PublishState.RUNNING,
        )

    def claim(self, project_id: str) -> bool:
        """Atomically take the publish slot; False when a publish is running."""
        return self.claim_slot(project=project_id)


_default_status = PublishStatus()


def get_publish_status(status: PublishStatus | None = None) -> dict:
    """Return a snapshot of the publish slot, defaulting to the module-wide one."""
    return (status or _default_status).copy()


def _do_publish(
    project_id: str, url: str, evaluations_root: Path, status: PublishStatus,
    env: dict | None = None, with_snippets: bool = False,
) -> None:
    try:
        skipped: list[str] = []
        count = publish_project(project_id, url, evaluations_root=evaluations_root, env=env,
                                on_skipped=skipped.extend, with_snippets=with_snippets)
        status.set(state=PublishState.DONE, runs=count, error=None, finished_at=time.time(),
                   skipped_standards=skipped)
    except PublishError as exc:
        forget_url(url)  # a stale "reachable" cache entry must not outlive a failed push
        status.set(state=PublishState.ERROR, error=str(exc), finished_at=time.time())


def _run_publish(
    project_id: str, url: str, evaluations_root: Path, status: PublishStatus,
    env: dict | None = None, with_snippets: bool = False,
) -> None:
    run_isolated(
        lambda: _do_publish(project_id, url, evaluations_root, status, env, with_snippets),
        label="publish", log=logger,
        on_error=lambda _exc: status.set(
            state=PublishState.ERROR,
            error="An unexpected error occurred while publishing.",
            finished_at=time.time(),
        ),
    )


class PublishStartResult(StrEnum):
    """``start_publish``'s return value."""

    STARTED = "started"
    ALREADY_RUNNING = "already_running"  # another publish holds the slot
    FAILED = "failed"  # the worker thread could not be started; status dict carries the error


def start_publish(
    project_id: str, url: str, *,
    evaluations_root: Path,
    status: PublishStatus | None = None,
    env: dict | None = None,
    with_snippets: bool = False,
) -> str:
    """Kick off a background publish.

    Returns ``PublishStartResult.STARTED``, ``ALREADY_RUNNING`` (another
    publish holds the slot), or ``FAILED`` (the worker thread could not be
    started; the status dict carries the error). Callers must not collapse
    the last two: one is a 409-style conflict, the other a server-side failure.
    """
    status = status or _default_status
    if not status.claim(project_id):
        return PublishStartResult.ALREADY_RUNNING
    try:
        thread = threading.Thread(
            target=_run_publish, args=(project_id, url, evaluations_root, status, env, with_snippets),
            daemon=True,
        )
        thread.start()
    except RuntimeError:
        status.set(state=PublishState.ERROR, error="Failed to start publish background job.", finished_at=time.time())
        logger.exception("failed to start publish thread")
        return PublishStartResult.FAILED
    return PublishStartResult.STARTED
