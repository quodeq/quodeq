"""Filesystem-backed implementation of the ActionProvider interface.

Composition (one collaborator per concern):

* ``ProjectsCache``       — TTL-bounded project list cache.
* ``EvaluationsIndex``    — JobManager + SQLite run index queries.
* ``PostRunHook``         — ephemeral cleanup + event-log projection.
* ``FsEvaluationMixin``   — evaluation lifecycle (start, status, cancel).
* ``FsToolingMixin``      — AI-client discovery and repo browsing.

The provider itself is a thin coordinator: it constructs the collaborators,
wires ``JobManager(on_job_complete=PostRunHook(...))``, and delegates each
``ActionProvider`` method to the collaborator that owns the concern.

``FsEvaluationMixin`` and ``FsToolingMixin`` are held as instance attributes
(not base classes) so all dependencies are explicit and each collaborator is
independently testable.  ``FsEvaluationMixin`` receives a ``get_status_fn``
that routes through ``EvaluationsIndex`` — this is what makes ``ext-`` job
IDs resolve correctly inside ``cancel_evaluation`` without MRO coupling.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.core.types import ProjectEntry, ViolationSummary
from quodeq.core.types.job import JobSnapshot
from quodeq.services import fs_reports, fs_projects
from quodeq.services._evaluations_index import EvaluationsIndex
from quodeq.services._post_run_hook import PostRunHook
from quodeq.services._projects_cache import ProjectsCache
from quodeq.services.base import ActionProvider, CreateProjectResult, EvaluationOptions, NewProjectSpec
from quodeq.services.evaluation_mixin import FsEvaluationMixin
from quodeq.services.jobs import JobManager
from quodeq.services.project_registration import register_project_with_rollback
from quodeq.services.tooling_mixin import FsToolingMixin
from quodeq.shared.log_sink import SHARED_LOG


def _resolve_reports_root(reports_root: Path | None) -> Path:
    """The run-reports root, defaulting to the configured evaluations dir."""
    if reports_root is not None:
        return reports_root
    from quodeq.shared.env import get_evaluations_dir
    return Path(get_evaluations_dir())


def _resolve_index_db_path(index_db_path: Path | None) -> Path:
    """The run-index database path, defaulting to the configured location."""
    if index_db_path is not None:
        return index_db_path
    from quodeq.shared.env import get_index_db_path
    return Path(get_index_db_path())


def _default_job_manager(reports_root: Path) -> JobManager:
    """A JobManager wired to the post-run hook.

    Only built when the caller injects none: an injected manager comes with
    its own on-complete wiring, and we do not mutate externally-owned state.
    """
    return JobManager(
        reports_root=reports_root,
        on_job_complete=PostRunHook(reports_root=reports_root),
        log=SHARED_LOG,
    )


def _default_tooling() -> FsToolingMixin:
    """The tooling collaborator, with the Claude model fetcher registered."""
    tooling = FsToolingMixin()
    tooling.configure_model_fetchers()
    return tooling


class FilesystemActionProvider(ActionProvider):
    """Filesystem-backed action provider — thin coordinator.

    Composes ``ProjectsCache``, ``EvaluationsIndex``, ``PostRunHook``,
    ``FsEvaluationMixin``, and ``FsToolingMixin`` behind the
    ``ActionProvider`` interface. Each collaborator is independently
    testable; this class only wires them.
    """

    def __init__(
        self,
        job_manager: JobManager | None = None,
        compiled_dir: Path | None = None,
        index_db_path: Path | None = None,
        reports_root: Path | None = None,
    ) -> None:
        self._reports_root = _resolve_reports_root(reports_root)
        self._compiled_dir = compiled_dir
        self._jobs = job_manager or _default_job_manager(self._reports_root)
        self._projects = ProjectsCache()
        self._evaluations = EvaluationsIndex(
            jobs=self._jobs,
            index_db_path=_resolve_index_db_path(index_db_path),
            reports_root=self._reports_root,
        )
        # Evaluation collaborator: receives a get_status_fn so cancel_evaluation
        # resolves ext- job IDs via EvaluationsIndex without MRO coupling.
        self._eval_handler = FsEvaluationMixin(
            jobs=self._jobs,
            get_status_fn=lambda job_id, reports_dir=None:
                self._evaluations.get_status(job_id, reports_dir=reports_dir),
        )
        self._tooling = _default_tooling()

    # -- evaluations (delegate to EvaluationsIndex) ---------------------

    def list_evaluations(
        self,
        limit: int = 0,
        reports_dir: Path | None = None,
        states: set[str] | None = None,
    ) -> list[JobSnapshot]:
        """Return runs from the SQLite index merged with JobManager's in-memory jobs."""
        return self._evaluations.list(limit=limit, reports_dir=reports_dir, states=states)

    def delete_evaluation(self, job_id: str, reports_dir: Path | None = None) -> bool:
        """Drop the run directory and its index row. Running jobs are refused."""
        return self._evaluations.delete(job_id, reports_dir=reports_dir)

    def get_evaluation_status(
        self, job_id: str, reports_dir: Path | None = None,
    ) -> JobSnapshot | None:
        """Return one run's snapshot. ``ext-`` ids resolve from the index after a scoped sync."""
        return self._evaluations.get_status(job_id, reports_dir=reports_dir)

    def start_evaluation(
        self, repo: str, reports_dir: str, options: EvaluationOptions,
    ) -> JobSnapshot:
        """Spawn the evaluation subprocess. *repo* must be a local path, not a URL."""
        return self._eval_handler.start_evaluation(repo, reports_dir, options)

    def score_failed_evaluation(self, job_id: str, reports_dir: str) -> bool:
        """Score the dimensions that finished before the run failed or was cancelled."""
        return self._eval_handler.score_failed_evaluation(job_id, reports_dir)

    def cancel_evaluation(
        self, job_id: str, reports_dir: str | None = None,
        *, discard_partial: bool = False,
    ) -> bool:
        """Cancel a running job; promote stale rows when SIGTERM has nothing to signal.

        ``FsEvaluationMixin.cancel_evaluation`` returns False when the underlying
        process is already gone (the route would turn that into 409 and the
        UI would stay stuck on "Evaluation in Progress"). When that happens
        and the snapshot is still ``running``, the index row is force-promoted
        to ``cancelled(stale_detected)`` so the UI flips out of "running".

        On a keep-findings cancel, findings on disk are not touched. With
        ``discard_partial`` the run must vanish entirely: after the cancel
        lands, the run directory, its index row, and the in-memory job entry
        are removed so no view (Overview fallback, History, status GET) can
        surface the discarded run again.
        """
        ok = self._eval_handler.cancel_evaluation(
            job_id, reports_dir=reports_dir, discard_partial=discard_partial,
        )
        if not ok:
            ok = self._evaluations.promote_stale_to_cancelled(job_id, reports_dir=reports_dir)
        if ok and discard_partial:
            reports_path = Path(reports_dir) if reports_dir else None
            if not self._evaluations.delete(job_id, reports_dir=reports_path):
                # A wedged process can be killed without ever flipping
                # status.json to terminal, so the index still reads
                # "running" and delete() refuses the row. The kill already
                # landed (ok is True): promote the stale row, then purge.
                self._evaluations.promote_stale_to_cancelled(job_id, reports_dir=reports_dir)
                self._evaluations.delete(job_id, reports_dir=reports_path)
        return ok

    def get_log_run_dir(self, job_id: str) -> Path | None:
        """Return the run directory behind *job_id*, or None if no run matches.

        Completed runs with no in-memory job entry cost a filesystem scan.
        """
        return self._evaluations.get_log_run_dir(job_id)

    def is_job_complete(self, job_id: str) -> bool:
        """Return True once *job_id* has reached done, failed, or cancelled."""
        return self._evaluations.is_complete(job_id)

    def rebuild_index(self, reports_root: Path | None = None) -> tuple[int, int]:
        """Walk *reports_root* and rebuild the SQLite run index from scratch."""
        return self._evaluations.rebuild(reports_root=reports_root)

    # -- projects (delegate to ProjectsCache + fs_projects) ------------

    def list_projects(self, reports_dir: str, *, offset: int = 0, limit: int = 0) -> dict[str, Any]:
        """Return the ``{"projects": [...]}`` payload, served from the TTL-bounded cache."""
        return self._projects.list(reports_dir, offset=offset, limit=limit)

    def invalidate_projects_cache(self) -> None:
        """Drop the cached payload and index so the next listing re-reads from disk."""
        self._projects.invalidate()

    def create_project(self, reports_dir: str, spec: NewProjectSpec) -> CreateProjectResult:
        """Clone if needed, scan, and register a project, rolling back every step on failure."""
        return register_project_with_rollback(reports_dir, spec, log=SHARED_LOG)

    def update_project_path(self, reports_dir: str, project: str, new_path: str) -> bool:
        """Repoint a registered project at *new_path*. Return True on success."""
        return fs_projects.update_project_path(reports_dir, project, new_path)

    def delete_project(self, reports_dir: str, project: str) -> bool:
        """Remove a project's registry entry and its report data. Return True on success."""
        return fs_projects.delete_project(reports_dir, project)

    def get_project_info(self, reports_dir: str, project: str) -> dict[str, Any] | None:
        """Return a project's metadata (discipline, dimensions), or None if unregistered."""
        return fs_projects.get_project_info(reports_dir, project)

    @staticmethod
    def _build_project_list(reports_root: Path) -> list[ProjectEntry]:
        return fs_projects.build_project_list(reports_root)

    # -- reports (delegate to fs_reports) ------------------------------

    def get_dashboard(self, reports_dir: str, project: str, run: str) -> dict[str, Any]:
        """Return the dashboard payload assembled from one run's on-disk artifacts."""
        return fs_reports.get_dashboard(reports_dir, project, run, log=SHARED_LOG)

    def get_accumulated(
        self, reports_dir: str, project: str, as_of: str | None,
    ) -> dict[str, Any] | None:
        """Return dimension data accumulated across every run up to *as_of*, or None."""
        return fs_reports.get_accumulated(reports_dir, project, as_of)

    def get_dimension_eval(
        self, reports_dir: str, project: str, run_id: str, dimension: str,
    ) -> dict[str, Any] | None:
        """Return one dimension's parsed evaluation, resolved against ``_compiled_dir``."""
        return fs_reports.get_dimension_eval(
            reports_dir, project, run_id, dimension, compiled_dir=self._compiled_dir,
        )

    def get_violations(self, reports_dir: str, project: str, run_id: str) -> ViolationSummary:
        """Return the violation counts aggregated across a run's dimensions."""
        return fs_reports.get_violations(reports_dir, project, run_id, log=SHARED_LOG)

    # -- tooling (delegate to FsToolingMixin) ---------------------------

    def browse_repo(self, path: str | None, include_files: bool = False) -> dict[str, Any]:
        """List directories (and files when *include_files*) under *path*, jailed to the home dir."""
        return self._tooling.browse_repo(path, include_files)

    def browse_mkdir(self, parent: str, name: str) -> dict[str, Any]:
        """Create folder *name* under *parent*.

        Validation failures come back as an ``{"error", "error_code"}`` payload
        for the route to map onto HTTP, not as an exception.
        """
        return self._tooling.browse_mkdir(parent, name)

    def get_ai_clients(self, env: dict[str, str] | None = None) -> dict[str, list[dict[str, str]]]:
        """Return the installed CLI clients and configured API providers. *env* overrides ``os.environ``."""
        return self._tooling.get_ai_clients(env)

    def get_client_models(self, client_id: str) -> dict[str, Any]:
        """Return the models offered by *client_id*; Claude resolves through its own fetcher."""
        return self._tooling.get_client_models(client_id)
