"""Mixin providing evaluation lifecycle methods for the filesystem provider.

Split to stay under the file-size cap: the dispatch abstraction and CLI
command building live in ``_evaluation_dispatch.py``, env-var building in
``_evaluation_env.py``, and the cancel-wait/discard machinery in
``_run_discard.py``. All are re-exported here — tests import
``SubprocessDispatcher``/``build_evaluate_cmd`` and patch
``wait_for_terminal_status``/``discard_run_state`` at this module's path.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from quodeq.core.run.job_status import JobStatus
from quodeq.core.types import JobSnapshot
from quodeq.services._job_model import JobLaunchOptions
from quodeq.services.base import EvaluationOptions, NewProjectSpec
from quodeq.services.project_registration import mark_onboarding_complete, register_project
from quodeq.services.score_run import score_completed_evidence
from quodeq.shared.utils import get_ai_cmd, get_ai_model, is_repo_url

from quodeq.services._evaluation_dispatch import EvaluationDispatcher, SubprocessDispatcher, build_evaluate_cmd  # re-export
from quodeq.services._evaluation_env import build_eval_env
from quodeq.services._run_discard import (  # noqa: F401 — re-export
    CacheEraser,
    discard_run_state,
    open_cache,
    wait_for_terminal_status,
)

if TYPE_CHECKING:
    from quodeq.services.jobs import JobManager


def _run_ref(job: JobSnapshot) -> dict[str, str | None]:
    """The ``{"outputProject", "outputRunId"}`` payload the run-state helpers take."""
    return {"outputProject": job.output_project, "outputRunId": job.output_run_id}


class FsEvaluationMixin:
    """Evaluation lifecycle collaborator: start, status, cancel, score.

    Held as an attribute, not inherited: ``FilesystemActionProvider``
    constructs one with its ``jobs`` and delegates to it, so the name's
    "Mixin" suffix is historical. Setting ``self._jobs`` on a host before
    calling any method still works. The ``get_status_fn`` hook lets the
    composing host override the status lookup so that external-job IDs
    (``ext-`` prefix, resolved via SQLite) work correctly inside
    ``cancel_evaluation`` without re-introducing MRO coupling.
    """

    _jobs: "JobManager"
    _dispatcher: EvaluationDispatcher | None

    def __init__(
        self,
        jobs: "JobManager | None" = None,
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
    def _build_eval_env(options: EvaluationOptions, env: dict[str, str] | None = None) -> dict[str, str]:
        """Build the subprocess environment for an evaluation run."""
        return build_eval_env(
            options, env,
            ai_cmd=options.ai_cmd or get_ai_cmd(),
            ai_model=options.ai_model or get_ai_model(),
        )

    @staticmethod
    def _resolve_repo_target(repo: str) -> Path:
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
        return resolved

    @staticmethod
    def _register_target_project(
        repo: str, reports_dir: str, options: EvaluationOptions,
    ) -> None:
        project_uuid = register_project(
            reports_dir, NewProjectSpec(repo, options.discipline, scope_path=options.scope_path),
        )
        # Launching an evaluation is the terminal step of project setup, so
        # the 'Resume setup' badge must clear here. Without this stamp the
        # null written at registration persists forever (the lazy backfill
        # only fills in a *missing* field, never a null one).
        mark_onboarding_complete(Path(reports_dir) / project_uuid)

    @staticmethod
    def _git_root_cwd(resolved: Path) -> str:
        # For files, walk up to find git root; for dirs, use as-is
        if not resolved.is_file():
            return str(resolved)
        candidate = resolved.parent
        cwd = str(candidate)
        while candidate != candidate.parent:
            if (candidate / ".git").exists():
                cwd = str(candidate)
                break
            candidate = candidate.parent
        return cwd

    def _launch_evaluation_job(
        self, cmd: list[str], reports_dir: str, options: EvaluationOptions, resolved: Path,
    ) -> JobSnapshot:
        # Keep JobManager aware of the current reports root so _tee_run_log
        # can resolve run.log paths for dashboard-spawned evaluations.
        # Guard with hasattr so custom/stub job managers remain compatible.
        if hasattr(self._jobs, "set_reports_root"):
            self._jobs.set_reports_root(Path(reports_dir))
        env = self._build_eval_env(options)
        return self.dispatcher.dispatch(cmd, JobLaunchOptions(
            cwd=self._git_root_cwd(resolved), env=env,
            ai_provider=options.ai_cmd,
            ai_model=options.ai_model,
            time_limit_s=options.time_limit,
        ))

    def start_evaluation(self, repo: str, reports_dir: str, options: EvaluationOptions) -> JobSnapshot:
        """Start an asynchronous evaluation subprocess for a repository."""
        resolved = self._resolve_repo_target(repo)
        cmd = build_evaluate_cmd(repo, options, reports_dir)
        self._register_target_project(repo, reports_dir, options)
        return self._launch_evaluation_job(cmd, reports_dir, options, resolved)

    def get_evaluation_status(self, job_id: str, reports_dir: str | None = None) -> JobSnapshot | None:
        """Return the current status of an evaluation job.

        When a ``get_status_fn`` was injected at construction time, delegates
        to that function (allows a composing host to supply a richer lookup,
        e.g. via ``EvaluationsIndex``, without MRO coupling).  Otherwise falls
        back to ``JobManager.get_job``, which only knows in-memory jobs and
        returns None for an ``ext-`` id.
        """
        fn = getattr(self, "_get_status_fn", None)
        if fn is not None:
            return fn(job_id, reports_dir=reports_dir)
        return self._jobs.get_job(job_id)

    def in_memory_job(self, job_id: str) -> JobSnapshot | None:
        """The in-memory JobManager view of *job_id*, or None.

        Unlike ``get_evaluation_status`` this never consults the run index,
        so an ``ext-`` id or an unknown id returns None. The log-stream routes
        use it for the freshest status of an internal run.
        """
        return self._jobs.get_job(job_id)

    def cancel_evaluation(
        self, job_id: str, reports_dir: str | None = None,
        *, discard_partial: bool = False,
    ) -> bool:
        """Cancel a running evaluation job; score completed dims unless discarding.

        Uses ``self.get_evaluation_status`` rather than a bare
        ``self._jobs.get_job`` so that external runs (``ext-`` prefix) also
        resolve correctly via the SQLite index (``FilesystemActionProvider``
        overrides the status lookup). Before this, ``get_job`` returned
        ``None`` for ``ext-`` ids and the scoring block was dead for them.
        ``score_completed_evidence`` is idempotent (skips dimensions whose
        report file already exists), so double-firing with the route-level
        scoring in ``_evaluation_routes`` is a no-op.

        After ``cancel_job`` returns we wait briefly for the run lifecycle
        handler in the subprocess to write ``status.json`` to a terminal
        state. Without this wait, the API returns while observers reading
        ``status.json`` (UI dashboard query, SSE stream, etc.) still see
        the run as ``running`` for a window of ~100ms-1s, producing
        the "two running rows" UX after a cancel-then-start.

        When ``discard_partial`` is True the run must end up as if it never
        happened: completed evidence is NOT scored, and the traces the run
        left in shared state (V2 cache entries, evidence scratch) are wiped.
        ``FilesystemActionProvider.cancel_evaluation`` then removes the run
        directory and its index row.
        """
        reports_root = Path(reports_dir) if reports_dir else None
        job = self.get_evaluation_status(job_id, reports_dir=reports_dir)
        # A job cancelled before the report_path marker landed has no
        # output_project/output_run_id yet — there is no run dir to wait on,
        # score, discard, or hand to cancel_job as its ext- lookup hint.
        run_dir: Path | None = None
        if reports_dir and job and job.output_project and job.output_run_id:
            run_dir = Path(reports_dir) / job.output_project / job.output_run_id
        ok = self._jobs.cancel_job(job_id, reports_root=reports_root, run_dir=run_dir)
        if ok and run_dir is not None:
            wait_for_terminal_status(run_dir)
            if discard_partial:
                discard_run_state(reports_dir, _run_ref(job))
            else:
                score_completed_evidence(reports_dir, _run_ref(job))
        return ok

    def score_failed_evaluation(self, job_id: str, reports_dir: str) -> bool:
        """Score any completed dimensions from a failed evaluation."""
        job = self._jobs.get_job(job_id)
        if not job or job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
            return False
        if job.output_project and job.output_run_id:
            score_completed_evidence(reports_dir, _run_ref(job))
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
