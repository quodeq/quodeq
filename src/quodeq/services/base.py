"""Protocol definitions for the action provider abstraction layer."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from quodeq.core.types import JobSnapshot, ViolationSummary
from quodeq.shared.constants import (  # noqa: F401 — re-export for backward compat
    DEFAULT_MAX_SUBAGENTS,
    DEFAULT_TIME_LIMIT,
)

_logger = logging.getLogger(__name__)


def resolve_clean_scan(payload: dict) -> bool:
    """Resolve the user's clean_scan intent from new and legacy fields.

    New: ``cleanScan: bool`` -- explicit opt-out, default False.
    Legacy: ``incremental: bool`` -- deprecated, with inverted semantics
    (old ``True`` meant "use cache" -> ``clean_scan=False``; old ``False``
    meant "ignore cache" -> ``clean_scan=True``). One-release back-compat.

    Sending both is rejected: we won't guess intent if a client transitions
    mid-deployment and ends up posting conflicting flags.
    """
    has_new = "cleanScan" in payload
    has_legacy = "incremental" in payload
    if has_new and has_legacy:
        raise ValueError(
            "`cleanScan` and `incremental` cannot be combined in a single payload. "
            "Use `cleanScan` only -- `incremental` is deprecated. "
            "Send `cleanScan: false` (use cached findings, default) or `cleanScan: true` "
            "(force full re-analysis)."
        )
    if has_legacy:
        _logger.warning(
            "Evaluation payload uses deprecated `incremental` field. "
            "Migrate to `cleanScan` (inverted semantics). "
            "Legacy field will be removed in the next release.",
        )
        return not bool(payload.get("incremental"))
    return bool(payload.get("cleanScan", False))


@dataclass
class EvaluationOptions:
    """Options controlling an evaluation run (discipline, dimensions, scoring mode)."""
    discipline: str | None = None
    dimensions: str = ""
    numerical: bool = False
    ai_cmd: str | None = None
    ai_cmd_path: str | None = None
    ai_model: str | None = None
    subagent_model: str | None = None
    verify_findings: bool = True
    max_subagents: int = DEFAULT_MAX_SUBAGENTS
    time_limit: int = DEFAULT_TIME_LIMIT
    clean_scan: bool = False
    per_dimension: bool = False
    branch: str | None = None
    scope_path: str | None = None
    context_size: int = 0
    provider_api_key: str = ""
    provider_api_base: str = ""


@dataclass(frozen=True)
class NewProjectSpec:
    """Request-boundary-validated inputs for registering a new project.

    The route builds this after its own request-boundary checks (repo-URL
    shape, cloneDest containment under home, local-path allowlist); the
    provider's ``create_project`` owns everything from here on (duplicate
    detection, clone + scan, rollback on failure).
    """
    repo: str
    discipline: str | None
    scope_path: str | None
    clone_dest: str | None
    ephemeral: bool


@dataclass(frozen=True)
class CreateProjectResult:
    """Outcome of ``ProjectActions.create_project``.

    ``status`` drives the route's HTTP translation:
    created | duplicate | invalid_repo | clone_failed | internal_error.
    """
    status: str
    project_id: str | None = None
    scan_data: dict | None = None
    existing_project_id: str | None = None
    message: str = ""
    clone_error_kind: str | None = None


class ProjectActions(Protocol):
    """Methods for project listing and metadata."""

    def list_projects(self, reports_dir: str) -> dict:
        """Return a dict with a 'projects' list for the given reports directory."""
        ...

    def create_project(self, reports_dir: str, spec: NewProjectSpec) -> CreateProjectResult:
        """Register (clone if needed + scan) a new project.

        Owns duplicate detection, the clone/scan attempt, rollback of any
        partial project directory on failure, and the scan.json readback
        (with a zero-run fallback). See NewProjectSpec/CreateProjectResult.
        """
        ...

    def get_project_info(self, reports_dir: str, project: str) -> dict:
        """Return project metadata including discipline and available dimensions."""
        ...

    def update_project_path(self, reports_dir: str, project: str, new_path: str) -> bool:
        """Update the local filesystem path for a project. Return True on success."""
        ...

    def delete_project(self, reports_dir: str, project: str) -> bool:
        """Remove a project and all its report data. Return True on success."""
        ...

    def invalidate_projects_cache(self) -> None:
        """Drop any cached project list so the next listing re-reads from disk.

        Default is a no-op; providers that cache ``list_projects`` results
        (see ``ProjectsCache``) override this so registration is visible in
        an immediately-following listing.
        """


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

    def browse_mkdir(self, parent: str, name: str) -> dict:
        """Create subdirectory *name* under *parent* (jailed to the home dir).

        Returns ``{"created": True, "path": ...}`` or an
        ``{"error", "error_code"}`` payload the route maps to HTTP."""
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
