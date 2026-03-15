"""Mixin providing evaluation lifecycle methods for the filesystem provider."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from quodeq.core.types import JobSnapshot
from quodeq.services.base import EvaluationOptions
from quodeq.shared.project_resolver import ProjectIdentity, resolve_project_uuid
from quodeq.shared.repo_handler import is_valid_repo_url
from quodeq.shared.utils import get_ai_cmd, get_ai_model, is_repo_url, project_name_from_repo

if TYPE_CHECKING:
    from quodeq.services.jobs import JobManager


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
    return cmd


def _register_project(repo: str, discipline: str | None, reports_dir: str) -> None:
    """Resolve and register the project UUID before evaluation starts."""
    repo_resolved = str(Path(repo).resolve()) if not is_repo_url(repo) else repo
    project_name = project_name_from_repo(repo)
    location = "online" if is_repo_url(repo) else "local"
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
    def _build_eval_env(repo: str, options: EvaluationOptions) -> dict[str, str]:
        """Build the subprocess environment for an evaluation run."""
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        env["AI_CMD"] = options.ai_cmd or get_ai_cmd()
        ai_model = options.ai_model or get_ai_model()
        if ai_model:
            env["AI_MODEL"] = ai_model
        if options.subagent_model:
            env["SUBAGENT_MODEL"] = options.subagent_model
        return env

    def start_evaluation(self, repo: str, reports_dir: str, options: EvaluationOptions) -> JobSnapshot:
        """Start an asynchronous evaluation subprocess for a repository."""
        if is_repo_url(repo):
            if not is_valid_repo_url(repo):
                raise ValueError(f"Invalid repository URL format: {repo}")
        else:
            repo_path = Path(repo)
            if not repo_path.resolve().is_dir():
                raise FileNotFoundError(f"Repository not found: {repo}")

        cmd = _build_evaluate_cmd(repo, options, reports_dir)
        _register_project(repo, options.discipline, reports_dir)
        env = self._build_eval_env(repo, options)
        cwd = str(Path.cwd()) if is_repo_url(repo) else str(Path(repo).resolve())
        return self.dispatcher.dispatch(cmd, cwd=cwd, env=env)

    def get_evaluation_status(self, job_id: str) -> JobSnapshot | None:
        """Return the current status of an evaluation job."""
        return self._jobs.get_job(job_id)

    def cancel_evaluation(self, job_id: str) -> bool:
        """Cancel a running evaluation job."""
        return self._jobs.cancel_job(job_id)

    def list_evaluations(self) -> list[JobSnapshot]:
        """Return all evaluation jobs (running, done, failed, cancelled)."""
        return self._jobs.list_jobs()
