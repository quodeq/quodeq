"""Evaluation run lifecycle — directory setup, RunLifecycleContext wiring,
and cleanup.

Split from ``cli_evaluation.py`` to keep each module under 300 lines.
Re-exported from ``cli_evaluation.py`` so existing
``quodeq.cli_evaluation.<name>`` imports and patches keep working.

The names tests patch at ``quodeq.cli_evaluation.<name>``
(``resolve_project_uuid``, ``project_name_from_repo``, ``is_repo_url``,
``emit_marker``, ``cleanup_cloned_repo``, ``cleanup_worktree``,
``get_ai_model``, ``save_manifest``, ``build_run_config``,
``execute_pipeline``) reach this module as a :class:`LifecycleHooks`
bundle that ``cli_evaluation`` assembles at call time, so this module never
imports its own importer.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator

from quodeq.analysis.run_lifecycle import RunLifecycleContext
from quodeq.analysis.errors import (
    REASON_AGENT_FAILURE_STREAK, REASON_PROVIDER_FATAL, provider_exit_reason,
)
from quodeq.analysis.runner import EvaluationError, RunConfig
from quodeq.analysis.subprocess import AnalysisError
from quodeq.core.run.job_status import external_job_id
from quodeq.core.types.project_source import ProjectLocation
from quodeq._cli_env import resolve_time_limit
from quodeq._cli_resolution import ResolvedInputs
from quodeq.data.fs.project_resolver import ProjectIdentity
from quodeq.data.git_cli import git_head_sha, git_worktree_dirty
from quodeq.shared.constants import CC_PHASE_REPORT_PATH
from quodeq.shared.logging import log_error, log_info
from quodeq.shared.utils import get_ai_cmd, is_repo_url

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LifecycleHooks:
    """The ``cli_evaluation`` collaborators a lifecycle run calls back into."""

    resolve_project_uuid: Callable[..., str]
    project_name_from_repo: Callable[[str], str]
    is_repo_url: Callable[[str], bool]
    emit_marker: Callable[..., None]
    cleanup_cloned_repo: Callable[[str], None]
    cleanup_worktree: Callable[[Path, Path], None]
    get_ai_model: Callable[[], str | None]
    save_manifest: Callable[[object, Path], None]
    build_run_config: Callable[..., RunConfig]
    execute_pipeline: Callable[..., int]


# ---------------------------------------------------------------------------
# Run directory setup
# ---------------------------------------------------------------------------

def setup_run_dirs(args: argparse.Namespace, src: Path, hooks: LifecycleHooks) -> tuple[Path, Path, Path]:
    """Resolve project UUID and create evidence/evaluation directories."""
    reports_root = Path(args.output)
    reports_root.mkdir(parents=True, exist_ok=True)

    project_name = hooks.project_name_from_repo(args.repo)
    location = ProjectLocation.ONLINE if is_repo_url(args.repo) else ProjectLocation.LOCAL
    scope = getattr(args, "scope", None)

    # Detect the git 'origin' remote so two clones of the same repo in
    # different local paths share a single project identity.
    remote_url = None
    if location == ProjectLocation.LOCAL:
        from quodeq.data.git_cli import git_remote_url
        remote_url = git_remote_url(str(src))

    project_uuid = hooks.resolve_project_uuid(
        reports_root,
        ProjectIdentity(project_name, str(src), None, location, scope_path=scope, remote_url=remote_url),
    )

    run_id = str(uuid.uuid4())
    evidence_dir = reports_root / project_uuid / run_id / "evidence"
    evaluation_dir = reports_root / project_uuid / run_id / "evaluation"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    return reports_root, evidence_dir, evaluation_dir


# ---------------------------------------------------------------------------
# Deadline / provider-fatal exit_reason tagging
# ---------------------------------------------------------------------------

def record_deadline_if_hit(lifecycle: "RunLifecycleContext", config: "RunConfig") -> None:
    """Tag the lifecycle with exit_reason='deadline' if the run's
    --max-duration was reached before natural completion.

    A run that outlives its budget stops silently: the subagent pool simply
    declines to spawn more agents once ``deadline_at`` has passed, and the
    dimension loop then runs out of work. Nothing raises.
    Without this hook, a deadline-truncated run finalizes with
    ``exit_reason=null``, indistinguishable from a clean completion. The
    dashboard then can't render the "Partial" badge.
    """
    deadline_at = getattr(getattr(config, "options", None), "deadline_at", None)
    if not isinstance(deadline_at, (int, float)):
        return
    if time.monotonic() >= deadline_at:
        lifecycle.set_exit_reason("deadline")


def record_provider_fatal_if_cancelled(lifecycle: "RunLifecycleContext") -> None:
    """Tag a completed run that a dead provider cut short.

    ``raise_on_fatal_cancel`` lets the pipeline finish when files were
    already analysed before the provider died (partial data is worth
    keeping). Without this hook such a run finalizes with
    ``exit_reason=null``, indistinguishable from a clean completion, and
    the UI can't warn that the results are partial. Runs after the
    deadline hook so the provider failure, being the actual cause, wins.
    """
    from quodeq.shared import cancellation
    reason = cancellation.cancel_reason() or ""
    if reason.startswith(REASON_PROVIDER_FATAL):
        lifecycle.set_exit_reason(provider_exit_reason(reason))
    elif reason == REASON_AGENT_FAILURE_STREAK:
        lifecycle.set_exit_reason("failure_streak")


# ---------------------------------------------------------------------------
# Pipeline execution wrapper
# ---------------------------------------------------------------------------

@contextmanager
def _run_log_handler(run_dir: Path) -> Iterator[None]:
    """Route every ``quodeq`` log record into the run's run.log for the block."""
    from quodeq.shared.run_log import RunLogHandler, RunLogWriter

    writer = RunLogWriter(run_dir)
    handler = RunLogHandler(writer)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger_root = logging.getLogger("quodeq")
    logger_root.addHandler(handler)
    try:
        yield
    finally:
        logger_root.removeHandler(handler)
        writer.close()


def _cleanup_run_artifacts(
    pid_file: Path, args: argparse.Namespace, inputs: ResolvedInputs, hooks: LifecycleHooks,
) -> None:
    """Run-exit cleanup: pid unlink, cloned-repo cleanup, worktree cleanup.

    Grouped into a single function — called exactly once, from
    ``_run_lifecycle_body``'s ``finally`` block — so this cleanup envelope
    always runs to completion together rather than being split across
    multiple functions that could partially execute.
    """
    try:
        pid_file.unlink(missing_ok=True)
    except OSError as exc:
        _logger.debug(
            "pid file cleanup failed; cancel-by-filesystem is unavailable for this run: %s", exc)
    if hooks.is_repo_url(args.repo):
        hooks.cleanup_cloned_repo(str(inputs.src))
    if inputs.worktree_dir and inputs.worktree_origin:
        hooks.cleanup_worktree(inputs.worktree_origin, inputs.worktree_dir)


def _apply_time_budget(args: argparse.Namespace, lifecycle: "RunLifecycleContext", config: RunConfig) -> None:
    """Resolve and persist the run-level time budget/deadline onto the lifecycle.

    Resolves from CLI args OR env vars — dashboard runs pass QUODEQ_TIME_LIMIT
    via env, not the CLI flag. Wires the pool auto-scale extension callback so
    a deadline widened mid-run lands in status.json too.
    """
    budget_s = resolve_time_limit(args)
    if budget_s is not None:
        lifecycle.set_time_limit(budget_s)
    if budget_s is not None and budget_s > 0:
        deadline_iso = (datetime.now(timezone.utc) + timedelta(seconds=budget_s)).isoformat()
        lifecycle.set_deadline(deadline_iso)
        config.options.on_deadline_extended = lifecycle.set_deadline


@dataclass(frozen=True)
class RunLifecyclePaths:
    """The on-disk paths a lifecycle-tracked run needs."""

    evidence_dir: Path
    evaluation_dir: Path
    run_dir: Path
    run_id: str
    pid_file: Path


def _run_lifecycle_body(
    args: argparse.Namespace, inputs: ResolvedInputs, config: RunConfig,
    paths: RunLifecyclePaths, hooks: LifecycleHooks,
) -> int:
    """Run the lifecycle-tracked pipeline; always clean up run artifacts on exit."""
    dimensions_list: list[str] = list(config.options.dimensions or [])

    try:
        ai_provider = get_ai_cmd()
        ai_model = hooks.get_ai_model()
        context = RunLifecycleContext(
            run_dir=paths.run_dir,
            job_id=external_job_id(paths.run_id),
            dimensions=dimensions_list,
            ai_provider=ai_provider,
            ai_model=ai_model,
        )
        if not is_repo_url(args.repo):
            source = str(inputs.src)
            context.set_commit_sha(git_head_sha(source), dirty=git_worktree_dirty(source))
        with context as lifecycle:
            try:
                # "analyzing" gates dashboard per-dimension polling.
                lifecycle.set_phase("analyzing")
                _apply_time_budget(args, lifecycle, config)
                result = hooks.execute_pipeline(args, config, paths.evidence_dir, paths.evaluation_dir)
                record_deadline_if_hit(lifecycle, config)
                record_provider_fatal_if_cancelled(lifecycle)
                # run_full writes per-dimension reports as it goes, so scoring
                # is already done by the time it returns.
                lifecycle.set_phase("scoring")
                lifecycle.transition_to_finalizing()
                return result
            finally:
                # See _cleanup_run_artifacts's docstring for why this is one call.
                _cleanup_run_artifacts(paths.pid_file, args, inputs, hooks)
    except (AnalysisError, EvaluationError) as exc:
        # RunLifecycleContext.__exit__ has already written state=failed.
        log_error(str(exc))
        return 1


def _announce_run(
    inputs: ResolvedInputs, evidence_dir: Path, evaluation_dir: Path, hooks: LifecycleHooks,
) -> None:
    """Publish the report path to the log and the marker stream, and save the manifest."""
    log_info(f"Report path: {evaluation_dir}")
    run_dir = evaluation_dir.parent
    hooks.emit_marker(
        CC_PHASE_REPORT_PATH, project=run_dir.parent.name, runId=run_dir.name,
    )
    hooks.save_manifest(inputs.manifest, evidence_dir)


def _write_pid_file(run_dir: Path) -> Path:
    """Write the run's .pid so the dashboard can detect and cancel this external run.

    Best-effort: a failure only costs cancel-by-filesystem, not the run.
    """
    pid_file = run_dir / ".pid"
    try:
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
    except OSError as exc:
        _logger.debug(
            "pid file write failed; cancel-by-filesystem is unavailable for this run: %s", exc)
    return pid_file


def run_pipeline_with_cleanup(
    args: argparse.Namespace, inputs: ResolvedInputs, paths: tuple[Path, Path, Path], hooks: LifecycleHooks,
) -> int:
    """Set up directories, build config, run the pipeline, and clean up cloned repos."""
    _reports_root, evidence_dir, evaluation_dir = paths
    run_dir = evaluation_dir.parent
    _announce_run(inputs, evidence_dir, evaluation_dir, hooks)

    lifecycle_paths = RunLifecyclePaths(
        evidence_dir=evidence_dir,
        evaluation_dir=evaluation_dir,
        run_dir=run_dir,
        run_id=run_dir.name,
        pid_file=_write_pid_file(run_dir),
    )
    config = hooks.build_run_config(args, inputs=inputs, evidence_dir=evidence_dir, run_dir=run_dir)

    with _run_log_handler(run_dir):
        return _run_lifecycle_body(args, inputs, config, lifecycle_paths, hooks)
