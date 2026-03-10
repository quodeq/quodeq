"""Mixin providing evaluation lifecycle methods for the filesystem provider."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from quodeq.provider.base import EvaluationOptions
from quodeq.shared.utils import is_repo_url, project_name_from_repo

if TYPE_CHECKING:
    from quodeq.provider.jobs import JobManager


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
    from quodeq.shared.project_resolver import ProjectIdentity, resolve_project_uuid
    repo_resolved = str(Path(repo).resolve()) if not is_repo_url(repo) else repo
    project_name = project_name_from_repo(repo)
    location = "online" if is_repo_url(repo) else "local"
    resolve_project_uuid(Path(reports_dir), ProjectIdentity(project_name, repo_resolved, discipline, location))


class FsEvaluationMixin:
    """Mixin for evaluation start/status/cancel methods.

    Requires the host class to provide a ``_jobs`` attribute (a ``JobManager``).
    """

    _jobs: JobManager

    def start_evaluation(self, repo: str, reports_dir: str, options: EvaluationOptions) -> dict[str, Any]:
        """Start an asynchronous evaluation subprocess for a repository."""
        repo_path = Path(repo)
        if not is_repo_url(repo) and not repo_path.exists():
            raise FileNotFoundError(f"Repository not found: {repo}")

        cmd = _build_evaluate_cmd(repo, options, reports_dir)
        _register_project(repo, options.discipline, reports_dir)

        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        if options.ai_cmd:
            env["AI_CMD"] = options.ai_cmd
        if options.ai_model:
            env["AI_MODEL"] = options.ai_model

        cwd = str(Path.cwd()) if is_repo_url(repo) else str(repo_path.resolve())
        return self._jobs.start_job(cmd, cwd=cwd, env=env)

    def get_evaluation_status(self, job_id: str) -> dict[str, Any] | None:
        """Return the current status of an evaluation job."""
        return self._jobs.get_job(job_id)

    def cancel_evaluation(self, job_id: str) -> bool:
        """Cancel a running evaluation job."""
        return self._jobs.cancel_job(job_id)

    def list_evaluations(self) -> list[dict]:
        """Return all evaluation jobs (running, done, failed, cancelled)."""
        return self._jobs.list_jobs()
