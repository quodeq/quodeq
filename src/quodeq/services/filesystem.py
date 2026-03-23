"""Filesystem-backed implementation of the ActionProvider interface."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable

_PROJECT_CACHE_TTL_S = 5  # seconds before project list is re-read

from quodeq.services.base import ActionProvider
from quodeq.services.jobs import JobManager
from quodeq.services.evaluation_mixin import FsEvaluationMixin
from quodeq.services.tooling_mixin import FsToolingMixin
from quodeq.services.violations import aggregate_violations, resolve_dimension_eval
from quodeq.config.paths import default_paths
from quodeq.core.types import ProjectEntry, ViolationResponse, ViolationSummary, to_camel_dict
from quodeq.services.accumulated import compute_accumulated
from quodeq.services.dashboard import build_dashboard
from quodeq.adapters.fs.report_parser import (
    list_runs,
    safe_read_dir,
)
from quodeq.services._filesystem_helpers import (
    _auto_detect_parents,
    _build_project_entry,
    _has_fingerprints,
    _infer_discipline,
    _list_available_dimensions_for_discipline,
    _max_projects_listed,
)


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

    def list_projects(self, reports_dir: str) -> dict[str, Any]:
        """Return all projects found under the reports directory (TTL-cached)."""
        now = time.monotonic()
        if self._project_cache is not None and (now - self._project_cache_time) < _PROJECT_CACHE_TTL_S:
            return self._project_cache
        reports_root = Path(reports_dir)
        projects = []
        for entry in safe_read_dir(reports_root):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            runs = list_runs(reports_root, entry.name)
            if not runs:
                continue
            projects.append(_build_project_entry(reports_root, entry.name, runs))
            if len(projects) >= _max_projects_listed():
                break
        projects.sort(key=lambda p: p.name)
        projects = _auto_detect_parents(projects)
        result = {"projects": [to_camel_dict(p) for p in projects]}
        self._project_cache = result
        self._project_cache_time = now
        return result

    def update_project_path(self, reports_dir: str, project: str, new_path: str) -> bool:
        """Update the local filesystem path stored in a project's metadata."""
        resolved_path = Path(new_path).resolve()
        if not resolved_path.is_absolute() or not resolved_path.is_dir():
            return False
        reports_root = Path(reports_dir).resolve()
        info_path = (reports_root / project).resolve()
        if not info_path.is_relative_to(reports_root):
            return False
        info_path = info_path / "repository_info.json"
        if not info_path.exists():
            return False
        try:
            info = json.loads(info_path.read_text())
            info["path"] = str(resolved_path)
            info["location"] = "local"
            info_path.write_text(json.dumps(info, indent=2))
            return True
        except (json.JSONDecodeError, OSError):
            return False

    def delete_project(self, reports_dir: str, project: str) -> bool:
        """Remove a project directory and all its report data."""
        reports_root = Path(reports_dir).resolve()
        project_path = (reports_root / project).resolve()
        if not project_path.is_relative_to(reports_root):
            return False
        if not project_path.exists() or not project_path.is_dir():
            return False
        try:
            shutil.rmtree(project_path)
        except OSError:
            return False
        return True

    def get_project_info(self, reports_dir: str, project: str) -> dict[str, Any] | None:
        """Return project metadata including discipline and available dimensions."""
        info_path = (Path(reports_dir) / project / "repository_info.json").resolve()
        if not info_path.is_relative_to(Path(reports_dir).resolve()):
            return None
        if not info_path.exists():
            return None
        try:
            info = json.loads(info_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        discipline = info.get("discipline") or _infer_discipline(Path(reports_dir), project)
        available_dimensions = _list_available_dimensions_for_discipline() if discipline else []
        has_fingerprints = _has_fingerprints(Path(reports_dir), project)
        return {**info, "discipline": discipline, "availableDimensions": available_dimensions, "hasFingerprints": has_fingerprints}

    def get_dashboard(self, reports_dir: str, project: str, run: str) -> dict[str, Any]:
        """Return the dashboard payload for a specific project run."""
        return build_dashboard(reports_dir, project, run)

    def get_accumulated(self, reports_dir: str, project: str, as_of: str | None) -> dict[str, Any] | None:
        """Return accumulated dimension data across all runs up to as_of."""
        return compute_accumulated(reports_dir, project, as_of)

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
        """Return parsed evaluation data for a single dimension in a run."""
        base = (Path(reports_dir) / project / run_id).resolve()
        if not base.is_relative_to(Path(reports_dir).resolve()):
            return None
        compiled_dir = self._compiled_dir or default_paths().standards_dir / "compiled"
        result = resolve_dimension_eval(base, project, run_id, dimension, compiled_dir=compiled_dir if compiled_dir.exists() else None)
        if result is not None:
            return to_camel_dict(result) if isinstance(result, ViolationResponse) else result
        # Run exists but dimension hasn't started yet
        if base.is_dir():
            return {"waiting": True, "project": project, "runId": run_id, "dimension": dimension}
        return None

    def get_violations(self, reports_dir: str, project: str, run_id: str) -> ViolationSummary:
        """Return aggregated violation counts and top files for a run."""
        dashboard = self.get_dashboard(reports_dir, project, run_id)
        return aggregate_violations(dashboard)
