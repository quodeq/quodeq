"""Mixin providing evaluation lifecycle methods for the filesystem provider."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol

from quodeq.core.types import JobSnapshot
from quodeq.services.base import EvaluationOptions, DEFAULT_MAX_SUBAGENTS, DEFAULT_TIME_LIMIT
from quodeq.data.fs.project_resolver import ProjectIdentity, resolve_project_uuid
from quodeq.services._wiring import read_dispatched_cache_keys, remove_matching_files
from quodeq.services.project_registration import mark_onboarding_complete, register_project
from quodeq.services.score_run import score_completed_evidence
from quodeq.shared.provider_env import provider_env_exports
from quodeq.shared.utils import get_ai_cmd, get_ai_model, is_repo_url, project_name_from_repo

if TYPE_CHECKING:
    from quodeq.services.jobs import JobManager

_logger = logging.getLogger(__name__)

_LOCATION_ONLINE = "online"
_LOCATION_LOCAL = "local"

class EvaluationDispatcher(Protocol):
    """Abstraction for dispatching evaluation work.

    The default implementation spawns a local subprocess via ``JobManager``.
    Replace with a task-queue or remote-worker implementation for horizontal
    scaling (e.g. Celery, cloud functions).
    """

    def dispatch(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        ai_provider: str | None = None,
        ai_model: str | None = None,
        time_limit_s: int | None = None,
    ) -> JobSnapshot:
        """Submit an evaluation command and return the initial job state."""
        ...


class SubprocessDispatcher:
    """Default dispatcher that delegates to the in-process ``JobManager``."""

    def __init__(self, job_manager: JobManager) -> None:
        self._jobs = job_manager

    def dispatch(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        ai_provider: str | None = None,
        ai_model: str | None = None,
        time_limit_s: int | None = None,
    ) -> JobSnapshot:
        return self._jobs.start_job(
            cmd, cwd=cwd, env=env,
            ai_provider=ai_provider, ai_model=ai_model,
            time_limit_s=time_limit_s,
        )


def _build_evaluate_cmd(
    repo: str, options: EvaluationOptions, reports_dir: str,
) -> list[str]:
    """Build the CLI command list for a V2 evaluation subprocess."""
    reports_abs = str(Path(reports_dir).resolve())
    repo_path = Path(repo)
    repo_arg = repo if is_repo_url(repo) else str(repo_path.resolve())

    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--_evaluate", "evaluate", repo_arg]
    else:
        cmd = [sys.executable, "-m", "quodeq.cli", "evaluate", repo_arg]
    cmd += ["-o", reports_abs]
    if options.dimensions:
        if isinstance(options.dimensions, list):
            cmd += ["-d", ",".join(options.dimensions)]
        else:
            cmd += ["-d", str(options.dimensions)]
    if options.numerical:
        cmd += ["-m", "numerical"]
    if options.max_subagents != DEFAULT_MAX_SUBAGENTS:
        cmd += ["--n-subagents", str(options.max_subagents)]
    if options.clean_scan:
        cmd += ["--clean-scan"]
    if options.branch:
        cmd += ["--branch", options.branch]
    if options.scope_path:
        cmd += ["--scope", options.scope_path]
    return cmd


class FsEvaluationMixin:
    """Evaluation lifecycle collaborator: start, status, cancel, score.

    Can be used as a standalone object (pass ``jobs`` to ``__init__``) or as a
    mixin (set ``self._jobs`` on the host before calling any method).  The
    ``get_status_fn`` hook lets a composing host override the status lookup so
    that external-job IDs (``ext-`` prefix, resolved via SQLite) work correctly
    inside ``cancel_evaluation`` without re-introducing MRO coupling.
    """

    _jobs: JobManager
    _dispatcher: EvaluationDispatcher | None

    def __init__(
        self,
        jobs: JobManager | None = None,
        get_status_fn: Callable | None = None,
    ) -> None:
        if jobs is not None:
            self._jobs = jobs
        self._dispatcher = None
        self._get_status_fn = get_status_fn

    @property
    def dispatcher(self) -> EvaluationDispatcher:
        """Return the evaluation dispatcher, defaulting to subprocess-based."""
        d = getattr(self, "_dispatcher", None)
        if d is not None:
            return d
        return SubprocessDispatcher(self._jobs)

    @staticmethod
    def _build_eval_env(repo: str, options: EvaluationOptions, env: dict[str, str] | None = None) -> dict[str, str]:
        """Build the subprocess environment for an evaluation run."""
        base = env if env is not None else os.environ
        built_env = {**base, "PYTHONUNBUFFERED": "1"}
        built_env["AI_CMD"] = options.ai_cmd or get_ai_cmd()
        # Validated at the API boundary (_validate_ai_cmd_path); the scan
        # subprocess spawns it as argv[0] while AI_CMD keeps keying the
        # provider config (analysis._command._cmd_binary).
        if options.ai_cmd_path:
            built_env["AI_CMD_PATH"] = options.ai_cmd_path
        ai_model = options.ai_model or get_ai_model()
        subagent_model = options.subagent_model or ai_model
        # Ensure both env vars are set consistently — prevents model swapping
        # between verification (reads AI_MODEL) and analysis (reads SUBAGENT_MODEL)
        if ai_model:
            built_env["AI_MODEL"] = ai_model
        if subagent_model:
            built_env["SUBAGENT_MODEL"] = subagent_model
        if not options.verify_findings:
            built_env["QUODEQ_NO_VERIFY"] = "1"
        # Always propagate the limit, including 0 (unlimited). The CLI
        # subprocess uses positive values to set the run-level deadline
        # (lifecycle.set_deadline + analyzing_start marker) that the
        # dashboard's countdown depends on. An absent env var resolves to
        # None in the CLI and the pool substitutes its 600s default, so
        # skipping 0 turned "unlimited" into a 10-minute run.
        if options.time_limit is not None and options.time_limit >= 0:
            built_env["QUODEQ_TIME_LIMIT"] = str(options.time_limit)
        if options.per_dimension:
            built_env["QUODEQ_NO_CONSOLIDATE"] = "1"
        if options.context_size > 0:
            built_env["QUODEQ_CONTEXT_SIZE"] = str(options.context_size)
        # Export user-entered API credentials under the env names the scan
        # subprocess resolves them from (provider's api_key_env). Without
        # this, a key typed in Settings for e.g. OpenRouter never reached
        # the run and it failed with a missing-key error.
        built_env.update(provider_env_exports(
            options.ai_cmd, options.provider_api_key, options.provider_api_base,
        ))
        if options.ai_cmd == "omlx":
            if options.provider_api_key:
                built_env["OMLX_API_KEY"] = options.provider_api_key
            if options.provider_api_base:
                built_env["OMLX_BASE_URL"] = options.provider_api_base
        return built_env

    def start_evaluation(self, repo: str, reports_dir: str, options: EvaluationOptions) -> JobSnapshot:
        """Start an asynchronous evaluation subprocess for a repository."""
        if is_repo_url(repo):
            raise ValueError(
                "URL repos are not supported here. Register the project via "
                "POST /api/projects (which clones to disk) and pass the local path."
            )
        resolved = Path(repo).resolve()
        if not resolved.exists():
            raise FileNotFoundError(
                f"Repository not found: {repo}. "
                f"Check that the path exists and is accessible from this machine."
            )

        cmd = _build_evaluate_cmd(repo, options, reports_dir)
        project_uuid = register_project(repo, options.discipline, reports_dir, scope_path=options.scope_path)
        # Launching an evaluation is the terminal step of project setup, so
        # the 'Resume setup' badge must clear here. Without this stamp the
        # null written at registration persists forever (the lazy backfill
        # only fills in a *missing* field, never a null one).
        mark_onboarding_complete(Path(reports_dir) / project_uuid)
        # Keep JobManager aware of the current reports root so _tee_run_log
        # can resolve run.log paths for dashboard-spawned evaluations.
        # Guard with hasattr so custom/stub job managers remain compatible.
        if hasattr(self._jobs, "set_reports_root"):
            self._jobs.set_reports_root(Path(reports_dir))
        env = self._build_eval_env(repo, options)
        # For files, walk up to find git root; for dirs, use as-is
        if resolved.is_file():
            candidate = resolved.parent
            cwd = str(candidate)
            while candidate != candidate.parent:
                if (candidate / ".git").exists():
                    cwd = str(candidate)
                    break
                candidate = candidate.parent
        else:
            cwd = str(resolved)
        return self.dispatcher.dispatch(
            cmd, cwd=cwd, env=env,
            ai_provider=options.ai_cmd,
            ai_model=options.ai_model,
            time_limit_s=options.time_limit,
        )

    def get_evaluation_status(self, job_id: str, reports_dir: str | None = None) -> JobSnapshot | None:
        """Return the current status of an evaluation job.

        When a ``get_status_fn`` was injected at construction time, delegates
        to that function (allows a composing host to supply a richer lookup,
        e.g. via ``EvaluationsIndex``, without MRO coupling).  Otherwise falls
        back to ``JobManager.get_job`` which handles the ``ext-`` prefix via
        the filesystem.
        """
        fn = getattr(self, "_get_status_fn", None)
        if fn is not None:
            return fn(job_id, reports_dir=reports_dir)
        reports_root = Path(reports_dir) if reports_dir else None
        return self._jobs.get_job(job_id, reports_root=reports_root)

    def cancel_evaluation(
        self, job_id: str, reports_dir: str | None = None,
        *, discard_partial: bool = False,
    ) -> bool:
        """Cancel a running evaluation job; score completed dims unless discarding.

        Uses ``self.get_evaluation_status`` rather than a bare
        ``self._jobs.get_job`` so that external runs (``ext-`` prefix) also
        resolve correctly via the SQLite index (Plan B1 override on
        ``FilesystemActionProvider``). Before this, ``get_job`` returned
        ``None`` for ``ext-`` ids and the scoring block was dead for them.
        ``score_completed_evidence`` is idempotent (skips dimensions whose
        report file already exists), so double-firing with the route-level
        scoring in ``_evaluation_routes`` is a no-op.

        After ``cancel_job`` returns we wait briefly for the run lifecycle
        handler in the subprocess to write ``status.json`` to a terminal
        state. Without this wait, the API returns while observers reading
        ``status.json`` (UI dashboard query, SSE stream, etc.) still see
        the run as ``in_progress`` for a window of ~100ms-1s, producing
        the "two running rows" UX after a cancel-then-start.

        When ``discard_partial`` is True the run must end up as if it never
        happened: completed evidence is NOT scored, and the traces the run
        left in shared state (V2 cache entries, evidence scratch) are wiped.
        ``FilesystemActionProvider.cancel_evaluation`` then removes the run
        directory and its index row.
        """
        reports_root = Path(reports_dir) if reports_dir else None
        job = self.get_evaluation_status(job_id, reports_dir=reports_dir)
        ok = self._jobs.cancel_job(job_id, reports_root=reports_root)
        # A job cancelled before the report_path marker landed has no
        # output_project/output_run_id yet — there is no run dir to wait on,
        # score, or discard.
        if ok and reports_dir and job and job.output_project and job.output_run_id:
            run_dir = Path(reports_dir) / job.output_project / job.output_run_id
            _wait_for_terminal_status(run_dir)
            if discard_partial:
                _discard_run_state(reports_dir, {
                    "outputProject": job.output_project,
                    "outputRunId": job.output_run_id,
                })
            else:
                score_completed_evidence(reports_dir, {
                    "outputProject": job.output_project,
                    "outputRunId": job.output_run_id,
                })
        return ok

    def score_failed_evaluation(self, job_id: str, reports_dir: str) -> bool:
        """Score any completed dimensions from a failed evaluation."""
        job = self._jobs.get_job(job_id)
        if not job or job.get("status") not in ("failed", "cancelled"):
            return False
        score_completed_evidence(reports_dir, job)
        return True

    def list_evaluations(
        self,
        *,
        limit: int = 0,
        reports_dir: str | None = None,
        states: set[str] | None = None,
    ) -> list[JobSnapshot]:
        """Return evaluation jobs (running, done, failed, cancelled).

        When *limit* > 0 only the most recent *limit* jobs are returned.
        When *reports_dir* is provided, external in-progress runs are merged in.
        When *states* is provided, only jobs with status in the set are returned.
        """
        reports_root = Path(reports_dir) if reports_dir else None
        jobs = self._jobs.list_jobs(reports_root=reports_root)
        if states:
            jobs = [j for j in jobs if j.status in states]
        return jobs[:limit] if limit > 0 else jobs


_TERMINAL_RUN_STATES = frozenset({"done", "failed", "cancelled"})
_CANCEL_WAIT_TIMEOUT_S = 2.0
_CANCEL_WAIT_POLL_S = 0.05


def _wait_for_terminal_status(
    run_dir: Path,
    *,
    timeout_s: float = _CANCEL_WAIT_TIMEOUT_S,
    poll_interval_s: float = _CANCEL_WAIT_POLL_S,
) -> bool:
    """Block until ``run_dir/status.json`` reports a terminal state, or timeout.

    Returns True when a terminal state ({done, failed, cancelled}) is
    observed on disk; returns False on timeout. Best-effort: a False
    return does not abort the calling cancel flow — downstream polling
    or SSE will eventually catch up.

    Bridges the async gap between ``JobManager.cancel_job`` returning
    (in-memory state flipped, signal sent to subprocess) and the run
    lifecycle handler in the subprocess flushing ``status.json`` to
    terminal. Without this wait, observers reading from disk
    immediately after the API returns can still see the run as
    ``in_progress`` for ~100ms-1s, producing a window where a
    follow-up "Start" surfaces two ``running`` rows in the UI.
    """
    deadline = time.monotonic() + timeout_s
    status_path = run_dir / "status.json"
    while True:
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("state") in _TERMINAL_RUN_STATES:
                return True
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval_s)


def _open_cache():
    """Lazily construct the default cache backend (import kept local)."""
    from quodeq.analysis.cache import LocalFileBackend
    return LocalFileBackend()


def _discard_run_state(reports_dir: str, job: dict, *, cache: "_CacheEraser | None" = None) -> None:
    """Wipe every trace a discarded run left behind.

    Invoked when the user cancels with "Discard findings": the run must end
    up as if it never happened. For EVERY dim that dispatched work (has a
    ``<dim>_dispatch_keys.json`` sidecar) the V2 content-addressed cache
    entries it wrote are deleted, including dims that finished cleanly.
    Without that, the next incremental run counts the discarded run's files
    as "analyzed in previous runs" in the coverage header. The sidecar holds
    only this run's dispatched (cache-miss) keys, so entries written by
    earlier kept runs are not touched.

    All per-dim scratch (queue, fingerprint, evidence JSONL, dispatch-keys
    and replayed-keys sidecars) is removed so the status-GET scoring path
    cannot resurrect a report from leftover evidence. The caller removes the
    run directory itself.
    """
    project = job.get("outputProject")
    run_id = job.get("outputRunId")
    if not project or not run_id:
        return

    run_dir = Path(reports_dir) / project / run_id
    evidence_dir = run_dir / "evidence"
    if not evidence_dir.is_dir():
        return

    keys = read_dispatched_cache_keys(evidence_dir)
    if keys:
        cache = cache or _open_cache()
        for key in keys:
            try:
                cache.delete(key)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Could not delete cache entry %s: %s", key, exc)

    scratch_patterns = (
        "*_queue.json", "*_fingerprint.json",
        "*_evidence.jsonl", "*_dispatch_keys.json",
        # Entries listed here belong to EARLIER runs, so they are cleaned up
        # as scratch but deliberately not fed to the cache-deletion loop above.
        "*_replayed_unconsolidated_keys.json",
    )
    remove_matching_files(evidence_dir, scratch_patterns)


class _CacheEraser(Protocol):
    """The one cache-backend method ``_discard_run_state`` needs.

    A local structural type instead of importing
    ``analysis.cache.backend.CacheBackend``: services/ must not import
    analysis/ (see ARCHITECTURE.md layering). ``LocalFileBackend`` (returned
    by ``_open_cache``, and every other real cache backend) satisfies this
    shape without any inheritance. Defined after ``_discard_run_state``
    (referenced there only as a deferred string annotation, per
    ``from __future__ import annotations``) so it doesn't shift the
    baseline-pinned lazy import inside ``_open_cache`` above.
    """

    def delete(self, key: str) -> None: ...
