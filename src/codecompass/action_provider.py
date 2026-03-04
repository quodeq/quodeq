from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ActionProvider(Protocol):
    """Interface for all action providers (filesystem, API, etc.)."""

    def list_projects(self, reports_dir: str) -> dict:
        """Return a dict with a 'projects' list for the given reports directory."""
        ...

    def get_project_info(self, reports_dir: str, project: str) -> dict:
        """Return project metadata including discipline and available dimensions."""
        ...

    def get_dashboard(self, reports_dir: str, project: str, run: str) -> dict:
        """Return the dashboard payload for a specific project run."""
        ...

    def get_accumulated(self, reports_dir: str, project: str, as_of: str | None) -> dict:
        """Return accumulated dimension data across all runs up to as_of."""
        ...

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str) -> dict:
        """Return parsed evaluation data for a single dimension in a run."""
        ...

    def get_run_plan(self, reports_dir: str, project: str, run_id: str) -> dict:
        """Return the remediation plan for a run."""
        ...

    def get_violations(self, reports_dir: str, project: str, run_id: str) -> dict:
        """Return aggregated violation summary for a run."""
        ...

    def start_evaluation(self, repo: str, discipline: str | None, dimensions: str, numerical: bool, reports_dir: str, ai_cmd: str | None = None, ai_model: str | None = None) -> dict:
        """Start an asynchronous evaluation job and return job metadata."""
        ...

    def get_evaluation_status(self, job_id: str) -> dict:
        """Return current status of an evaluation job."""
        ...

    def cancel_evaluation(self, job_id: str) -> bool:
        """Cancel a running evaluation job. Return True on success."""
        ...

    def browse_repo(self, path: str | None) -> dict:
        """List directories at the given path for repository browsing."""
        ...

    def get_ai_clients(self) -> dict:
        """Return available AI CLI clients."""
        ...

    def get_client_models(self, client_id: str) -> dict:
        """Return available models for an AI client."""
        ...
