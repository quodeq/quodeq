from __future__ import annotations

import os
import sys
from pathlib import Path

from codecompass.utils import is_repo_url


class FsEvaluationMixin:
    """Mixin for evaluation start/status/cancel methods."""

    def start_evaluation(self, repo: str, discipline: str | None, dimensions: str, numerical: bool, reports_dir: str, ai_cmd: str | None = None, ai_model: str | None = None):
        repo_path = Path(repo)
        if not is_repo_url(repo) and not repo_path.exists():
            raise FileNotFoundError(f"Repository not found: {repo}")

        reports_abs = str(Path(reports_dir).resolve())
        cmd = [sys.executable, "-m", "codecompass.cli", "evaluate"]
        cmd += ["--evaluations", reports_abs]
        if dimensions:
            cmd += ["-d", dimensions]
        if numerical:
            cmd.append("-n")
        if discipline:
            cmd.append(discipline)
        if is_repo_url(repo):
            cmd.append(repo)
        else:
            cmd.append(str(repo_path.resolve()))

        from codecompass.evaluate.project_resolver import resolve_project_uuid
        repo_resolved = str(Path(repo).resolve()) if not is_repo_url(repo) else repo
        project_name = repo.split("/")[-1].replace(".git", "") if is_repo_url(repo) else Path(repo).name
        location = "online" if is_repo_url(repo) else "local"
        resolve_project_uuid(Path(reports_dir), project_name, repo_resolved, discipline, location=location)

        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        if ai_cmd:
            env["AI_CMD"] = ai_cmd
        if ai_model:
            env["AI_MODEL"] = ai_model

        cwd = str(Path.cwd()) if is_repo_url(repo) else str(repo_path.resolve())
        return self._jobs.start_job(cmd, cwd=cwd, env=env)

    def get_evaluation_status(self, job_id: str):
        return self._jobs.get_job(job_id)

    def cancel_evaluation(self, job_id: str) -> bool:
        return self._jobs.cancel_job(job_id)

    def list_evaluations(self) -> list[dict]:
        return self._jobs.list_jobs()
