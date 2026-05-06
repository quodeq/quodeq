"""Protocol definitions for the action provider abstraction layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from quodeq.core.types import JobSnapshot, ViolationSummary
from quodeq.shared.constants import (  # noqa: F401 — re-export for backward compat
    _DEFAULT_MAX_SUBAGENTS,
    _DEFAULT_POOL_BUDGET,
    _DEFAULT_TIME_LIMIT,
)


@dataclass
class EvaluationOptions:
    """Options controlling an evaluation run (discipline, dimensions, scoring mode)."""
    discipline: str | None = None
    dimensions: str = ""
    numerical: bool = False
    ai_cmd: str | None = None
    ai_model: str | None = None
    subagent_model: str | None = None
    verify_findings: bool = True
    max_subagents: int = _DEFAULT_MAX_SUBAGENTS
    time_limit: int = _DEFAULT_TIME_LIMIT
    clean_scan: bool = False
    per_dimension: bool = False
    branch: str | None = None
    scope_path: str | None = None
    context_size: int = 0


class ProjectActions(Protocol):
    """Methods for project listing and metadata."""

    def list_projects(self, reports_dir: str) -> dict:
        """Return a dict with a 'projects' list for the given reports directory."""
        ...

    def get_project_info(self, reports_dir: str, project: str) -> dict:
        """Return project metadata including discipline and available dimensions."""
        ...

    def update_project_path(self, reports_dir: str, project: str, new_path: str) -> bool:
        """Update the local filesystem path for a project. Return True on success."""
        ...

    def clone_to_local(self, reports_dir: str, project: str, destination: str) -> dict | None:
        """Clone an online project's repo to a local directory. Return updated info or None."""
        ...

    def delete_project(self, reports_dir: str, project: str) -> bool:
        """Remove a project and all its report data. Return True on success."""
        ...


class ReportActions(Protocol):
    """Methods for reading evaluation reports and dashboards."""

    def get_dashboard(self, reports_dir: str, project: str, run: str) -> dict:
        """Return the dashboard payload for a specific project run."""
        ...

    def get_accumulated(self, reports_dir: str, project: str, as_of: str | None) -> dict:
        """Return accumulated dimension data across all runs up to as_of."""
        ...

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str) -> dict:
        """Return parsed evaluation data for a single dimension in a run."""
        ...

    def get_violations(self, reports_dir: str, project: str, run_id: str) -> ViolationSummary:
        """Return aggregated violation summary for a run."""
        ...


class EvaluationActions(Protocol):
    """Methods for running and managing evaluations."""

    def start_evaluation(self, repo: str, reports_dir: str, options: EvaluationOptions) -> JobSnapshot:
        """Start an asynchronous evaluation job and return job metadata."""
        ...

    def get_evaluation_status(self, job_id: str, reports_dir: str | None = None) -> JobSnapshot | None:
        """Return current status of an evaluation job."""
        ...

    def cancel_evaluation(
        self, job_id: str, reports_dir: str | None = None,
        *, discard_partial: bool = False,
    ) -> bool:
        """Cancel a running evaluation job. Return True on success.

        When ``discard_partial`` is True, any in-flight dim's
        ``<dim>_queue.json`` and ``<dim>_fingerprint.json`` are deleted so
        the next run cannot resume from this run's partial state. Dims that
        already produced ``evaluation/<dim>.json`` are preserved — only
        unfinished ones are wiped.
        """
        ...

    def list_evaluations(
        self,
        *,
        limit: int = 0,
        reports_dir: str | None = None,
        states: set[str] | None = None,
    ) -> list[JobSnapshot]:
        """Return evaluation jobs. If *states* is given, only jobs whose status
        is in the set are returned (e.g. {"running", "done"} to hide cancelled/failed)."""
        ...

    def delete_evaluation(self, job_id: str, reports_dir: str | None = None) -> bool:
        """Delete a finished evaluation's on-disk artifacts and index row.
        Refuses to delete a running job (returns False). Returns True on success."""
        ...


class ToolingActions(Protocol):
    """Methods for browsing repos and discovering AI clients."""

    def browse_repo(self, path: str | None) -> dict:
        """List directories at the given path for repository browsing."""
        ...

    def get_ai_clients(self) -> dict:
        """Return available AI CLI clients."""
        ...

    def get_client_models(self, client_id: str) -> dict:
        """Return available models for an AI client."""
        ...


@runtime_checkable
class ActionProvider(ProjectActions, ReportActions, EvaluationActions, ToolingActions, Protocol):
    """Composite interface for all action providers (filesystem, API, etc.)."""
    ...
