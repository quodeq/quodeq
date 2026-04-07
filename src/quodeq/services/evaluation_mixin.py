"""Mixin providing evaluation lifecycle methods for the filesystem provider."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from quodeq.core.types import JobSnapshot
from quodeq.services.base import EvaluationOptions, _DEFAULT_MAX_SUBAGENTS, _DEFAULT_POOL_BUDGET
from quodeq.shared.project_resolver import ProjectIdentity, resolve_project_uuid
from quodeq.shared.repo_handler import is_valid_repo_url
from quodeq.shared.utils import get_ai_cmd, get_ai_model, is_repo_url, project_name_from_repo

if TYPE_CHECKING:
    from quodeq.services.jobs import JobManager

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
    ) -> JobSnapshot:
        return self._jobs.start_job(cmd, cwd=cwd, env=env)


def _build_evaluate_cmd(
    repo: str, options: EvaluationOptions, reports_dir: str,
) -> list[str]:
    """Build the CLI command list for a V2 evaluation subprocess."""
    reports_abs = str(Path(reports_dir).resolve())
    repo_path = Path(repo)
    repo_arg = repo if is_repo_url(repo) else str(repo_path.resolve())

    cmd = [sys.executable, "-m", "quodeq.cli", "evaluate", repo_arg]
    cmd += ["-o", reports_abs]
    if options.dimensions:
        if isinstance(options.dimensions, list):
            cmd += ["-d", ",".join(options.dimensions)]
        else:
            cmd += ["-d", str(options.dimensions)]
    if options.numerical:
        cmd += ["-m", "numerical"]
    if options.max_subagents != _DEFAULT_MAX_SUBAGENTS:
        cmd += ["--n-subagents", str(options.max_subagents)]
    if options.incremental:
        cmd += ["--incremental"]
    if options.branch:
        cmd += ["--branch", options.branch]
    if options.scope_path:
        cmd += ["--scope", options.scope_path]
    return cmd


def _register_project(repo: str, discipline: str | None, reports_dir: str) -> None:
    """Resolve and register the project UUID before evaluation starts."""
    repo_resolved = str(Path(repo).resolve()) if not is_repo_url(repo) else repo
    project_name = project_name_from_repo(repo)
    location = _LOCATION_ONLINE if is_repo_url(repo) else _LOCATION_LOCAL
    resolve_project_uuid(Path(reports_dir), ProjectIdentity(project_name, repo_resolved, discipline, location))


class FsEvaluationMixin:
    """Mixin for evaluation start/status/cancel methods.

    Requires the host class to provide a ``_jobs`` attribute (a ``JobManager``)
    and optionally a ``_dispatcher`` attribute (an ``EvaluationDispatcher``).
    When no dispatcher is set, a ``SubprocessDispatcher`` wrapping ``_jobs``
    is used automatically.
    """

    _jobs: JobManager
    _dispatcher: EvaluationDispatcher | None

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
        if options.pool_budget != _DEFAULT_POOL_BUDGET:
            built_env["QUODEQ_POOL_BUDGET"] = str(options.pool_budget)
        if options.per_dimension:
            built_env["QUODEQ_NO_CONSOLIDATE"] = "1"
        return built_env

    def start_evaluation(self, repo: str, reports_dir: str, options: EvaluationOptions) -> JobSnapshot:
        """Start an asynchronous evaluation subprocess for a repository."""
        if is_repo_url(repo):
            if not is_valid_repo_url(repo):
                raise ValueError(f"Invalid repository URL format: {repo}")
        else:
            resolved = Path(repo).resolve()
            if not resolved.exists():
                raise FileNotFoundError(f"Repository not found: {repo}")

        cmd = _build_evaluate_cmd(repo, options, reports_dir)
        _register_project(repo, options.discipline, reports_dir)
        env = self._build_eval_env(repo, options)
        if is_repo_url(repo):
            cwd = str(Path.cwd())
        else:
            resolved = Path(repo).resolve()
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
        return self.dispatcher.dispatch(cmd, cwd=cwd, env=env)

    def get_evaluation_status(self, job_id: str) -> JobSnapshot | None:
        """Return the current status of an evaluation job."""
        return self._jobs.get_job(job_id)

    def cancel_evaluation(self, job_id: str, reports_dir: str | None = None) -> bool:
        """Cancel a running evaluation job and score any completed dimensions."""
        # Get job info before cancellation
        job = self._jobs.get_job(job_id)
        ok = self._jobs.cancel_job(job_id)
        if ok and reports_dir and job:
            _score_completed_evidence(reports_dir, job)
        return ok

    def score_failed_evaluation(self, job_id: str, reports_dir: str) -> bool:
        """Score any completed dimensions from a failed evaluation."""
        job = self._jobs.get_job(job_id)
        if not job or job.get("status") not in ("failed", "cancelled"):
            return False
        _score_completed_evidence(reports_dir, job)
        return True

    def list_evaluations(self) -> list[JobSnapshot]:
        """Return all evaluation jobs (running, done, failed, cancelled)."""
        return self._jobs.list_jobs()


def _score_completed_evidence(reports_dir: str, job: dict) -> None:
    """Score any dimensions that have evidence but no evaluation report.

    Called after cancellation so completed dimensions are preserved in the
    dashboard even when the overall run was cancelled.
    """
    project = job.get("outputProject")
    run_id = job.get("outputRunId")
    if not project or not run_id:
        return

    import logging
    _log = logging.getLogger(__name__)

    evidence_dir = Path(reports_dir) / project / run_id / "evidence"
    evaluation_dir = Path(reports_dir) / project / run_id / "evaluation"
    if not evidence_dir.is_dir():
        return

    evaluation_dir.mkdir(parents=True, exist_ok=True)

    for jsonl_path in evidence_dir.glob("*_evidence.jsonl"):
        dim_id = jsonl_path.name.replace("_evidence.jsonl", "")
        eval_file = evaluation_dir / f"{dim_id}.json"
        if eval_file.exists():
            continue  # already scored
        if jsonl_path.stat().st_size == 0:
            continue  # no findings
        # Only score dimensions that passed verification (analysis queue exists)
        queue_file = evidence_dir / f"{dim_id}_queue.json"
        if not queue_file.exists():
            continue  # verification not completed for this dimension

        try:
            from quodeq.core.evidence.parser import parse_jsonl_to_evidence, EvidenceContext
            from quodeq.core.scoring.engine import score_evidence
            from quodeq.analysis.report import write_dimension_report

            evidence = parse_jsonl_to_evidence(jsonl_path, EvidenceContext(
                dimension=dim_id, src="", language="", source_file_count=0,
                compiled_dir=None, files_read=0,
            ))
            if evidence is None:
                continue
            scores = score_evidence(evidence, mode="numerical")
            write_dimension_report(evidence, scores, dim_id, evaluation_dir)
            _log.info("Scored cancelled dimension '%s' for run %s", dim_id, run_id[:8])
        except Exception as exc:
            _log.debug("Could not score cancelled dimension '%s': %s", dim_id, exc)
