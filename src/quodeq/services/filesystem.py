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
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from quodeq.core.types import ProjectEntry, ViolationSummary
from quodeq.core.types.job import JobSnapshot
from quodeq.services import _fs_projects, _fs_reports
from quodeq.services._evaluations_index import EvaluationsIndex
from quodeq.services._post_run_hook import PostRunHook
from quodeq.services._projects_cache import ProjectsCache
from quodeq.services.base import ActionProvider
from quodeq.services.evaluation_mixin import FsEvaluationMixin
from quodeq.services.jobs import JobManager
from quodeq.services.tooling_mixin import FsToolingMixin


class FilesystemActionProvider(FsEvaluationMixin, FsToolingMixin, ActionProvider):
    """Filesystem-backed action provider — thin coordinator.

    Composes ``ProjectsCache``, ``EvaluationsIndex``, and ``PostRunHook``
    behind the ``ActionProvider`` interface. Each collaborator is
    independently testable; this class only wires them.
    """

    def __init__(
        self,
        job_manager: JobManager | None = None,
        compiled_dir: Path | None = None,
        index_db_path: Path | None = None,
        reports_root: Path | None = None,
    ) -> None:
        super().__init__()
        self._reports_root = reports_root
        self._compiled_dir = compiled_dir

        # When a JobManager is injected (tests, alternative wiring), the caller
        # owns the on-complete wiring — we don't mutate externally-owned state.
        if job_manager is not None:
            self._jobs = job_manager
        else:
            self._jobs = JobManager(
                reports_root=reports_root,
                on_job_complete=PostRunHook(reports_root=reports_root),
            )

        self._projects = ProjectsCache()
        self._evaluations = EvaluationsIndex(
            jobs=self._jobs,
            index_db_path=index_db_path,
            reports_root=reports_root,
        )
        self._model_fetchers: dict[str, Callable] = {
            "claude": self._get_claude_models,
        }

    # -- evaluations (delegate to EvaluationsIndex) ---------------------

    def list_evaluations(
        self,
        limit: int = 0,
        reports_dir: Path | None = None,
        states: set[str] | None = None,
    ) -> list[JobSnapshot]:
        return self._evaluations.list(limit=limit, reports_dir=reports_dir, states=states)

    def delete_evaluation(self, job_id: str, reports_dir: Path | None = None) -> bool:
        return self._evaluations.delete(job_id, reports_dir=reports_dir)

    def get_evaluation_status(
        self, job_id: str, reports_dir: Path | None = None,
    ) -> JobSnapshot | None:
        return self._evaluations.get_status(job_id, reports_dir=reports_dir)

    def cancel_evaluation(
        self, job_id: str, reports_dir: str | None = None,
        *, discard_partial: bool = False,
    ) -> bool:
        """Cancel a running job; promote stale rows when SIGTERM has nothing to signal.

        The mixin's ``cancel_evaluation`` returns False when the underlying
        process is already gone (the route would turn that into 409 and the
        UI would stay stuck on "Evaluation in Progress"). When that happens
        and the snapshot is still ``running``, the index row is force-promoted
        to ``cancelled(stale_detected)`` so the UI flips out of "running".
        Findings on disk are not touched.
        """
        ok = super().cancel_evaluation(
            job_id, reports_dir=reports_dir, discard_partial=discard_partial,
        )
        if ok:
            return True
        return self._evaluations.promote_stale_to_cancelled(job_id, reports_dir=reports_dir)

    def get_log_run_dir(self, job_id: str) -> Path | None:
        return self._evaluations.get_log_run_dir(job_id)

    def is_job_complete(self, job_id: str) -> bool:
        return self._evaluations.is_complete(job_id)

    def rebuild_index(self, reports_root: Path | None = None) -> tuple[int, int]:
        """Walk *reports_root* and rebuild the SQLite run index from scratch."""
        return self._evaluations.rebuild(reports_root=reports_root)

    # -- projects (delegate to ProjectsCache + _fs_projects) ------------

    def list_projects(self, reports_dir: str) -> dict[str, Any]:
        return self._projects.list(reports_dir)

    def update_project_path(self, reports_dir: str, project: str, new_path: str) -> bool:
        return _fs_projects.update_project_path(reports_dir, project, new_path)

    def delete_project(self, reports_dir: str, project: str) -> bool:
        return _fs_projects.delete_project(reports_dir, project)

    def get_project_info(self, reports_dir: str, project: str) -> dict[str, Any] | None:
        return _fs_projects.get_project_info(reports_dir, project)

    @staticmethod
    def _build_project_list(reports_root: Path) -> list[ProjectEntry]:
        return _fs_projects.build_project_list(reports_root)

    # -- reports (delegate to _fs_reports) ------------------------------

    def get_dashboard(self, reports_dir: str, project: str, run: str) -> dict[str, Any]:
        return _fs_reports.get_dashboard(reports_dir, project, run)

    def get_accumulated(
        self, reports_dir: str, project: str, as_of: str | None,
    ) -> dict[str, Any] | None:
        return _fs_reports.get_accumulated(reports_dir, project, as_of)

    def get_dimension_eval(
        self, reports_dir: str, project: str, run_id: str, dimension: str,
    ) -> dict[str, Any] | None:
        return _fs_reports.get_dimension_eval(
            reports_dir, project, run_id, dimension, compiled_dir=self._compiled_dir,
        )

    def get_violations(self, reports_dir: str, project: str, run_id: str) -> ViolationSummary:
        return _fs_reports.get_violations(reports_dir, project, run_id)
