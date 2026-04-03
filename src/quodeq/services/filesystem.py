"""Filesystem-backed implementation of the ActionProvider interface."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from quodeq.core.types import ProjectEntry, ViolationSummary, to_camel_dict
from quodeq.services import _fs_clone, _fs_projects, _fs_reports
from quodeq.services.base import ActionProvider
from quodeq.services.evaluation_mixin import FsEvaluationMixin
from quodeq.services.jobs import JobManager
from quodeq.services.tooling_mixin import FsToolingMixin

_PROJECT_CACHE_TTL_S = 5  # seconds before project list is re-read


class FilesystemActionProvider(FsEvaluationMixin, FsToolingMixin, ActionProvider):
    """Filesystem-backed action provider.

    This class uses cooperative multiple inheritance via **mixins** to compose
    orthogonal capabilities without code duplication:

    * ``FsEvaluationMixin`` -- evaluation lifecycle (start, status, cancel).
    * ``FsToolingMixin``    -- AI-client discovery and repo browsing.
    * ``ActionProvider``    -- abstract base defining the provider contract.

    The mixins are stateless mix-in classes (no ``__init__``, no instance
    state of their own) and do not form a diamond; they are combined here
    purely for composition.
    """

    def __init__(self, job_manager: JobManager | None = None, compiled_dir: Path | None = None) -> None:
        super().__init__()
        self._jobs = job_manager or JobManager()
        self._compiled_dir = compiled_dir
        self._model_fetchers: dict[str, Callable] = {
            "claude": self._get_claude_models,
        }
        self._project_cache: dict[str, Any] | None = None
        self._project_cache_time: float = 0

    # -- helpers --------------------------------------------------------

    @staticmethod
    def _build_project_list(reports_root: Path) -> list[ProjectEntry]:
        return _fs_projects.build_project_list(reports_root)

    def _is_cache_valid(self) -> bool:
        return self._project_cache is not None and (time.monotonic() - self._project_cache_time) < _PROJECT_CACHE_TTL_S

    # -- project CRUD (delegates to _fs_projects) -----------------------

    def list_projects(self, reports_dir: str) -> dict[str, Any]:
        if self._is_cache_valid():
            return self._project_cache  # type: ignore[return-value]
        projects = _fs_projects.build_project_list(Path(reports_dir))
        result = {"projects": [to_camel_dict(p) for p in projects]}
        self._project_cache = result
        self._project_cache_time = time.monotonic()
        return result

    def update_project_path(self, reports_dir: str, project: str, new_path: str) -> bool:
        return _fs_projects.update_project_path(reports_dir, project, new_path)

    def delete_project(self, reports_dir: str, project: str) -> bool:
        return _fs_projects.delete_project(reports_dir, project)

    def clone_to_local(self, reports_dir: str, project: str, destination: str) -> dict[str, Any] | None:
        return _fs_clone.clone_to_local(
            reports_dir, project, destination, get_project_info_fn=self.get_project_info,
        )

    def get_project_info(self, reports_dir: str, project: str) -> dict[str, Any] | None:
        return _fs_projects.get_project_info(reports_dir, project)

    # -- reports / dashboard (delegates to _fs_reports) -----------------

    def get_dashboard(self, reports_dir: str, project: str, run: str) -> dict[str, Any]:
        return _fs_reports.get_dashboard(reports_dir, project, run)

    def get_accumulated(self, reports_dir: str, project: str, as_of: str | None) -> dict[str, Any] | None:
        return _fs_reports.get_accumulated(reports_dir, project, as_of)

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
        return _fs_reports.get_dimension_eval(
            reports_dir, project, run_id, dimension, compiled_dir=self._compiled_dir,
        )

    def get_violations(self, reports_dir: str, project: str, run_id: str) -> ViolationSummary:
        return _fs_reports.get_violations(reports_dir, project, run_id)
