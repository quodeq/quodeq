"""Filesystem-backed implementation of the ActionProvider interface."""

from __future__ import annotations

import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
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
from quodeq.services.ports import (
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

    @staticmethod
    def _build_project_list(reports_root: Path) -> list[ProjectEntry]:
        """Collect eligible project dirs and build entries in parallel."""
        max_listed = _max_projects_listed()
        dir_names: list[str] = []
        for entry in safe_read_dir(reports_root):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            dir_names.append(entry.name)
            if len(dir_names) >= max_listed:
                break

        def _build_one(name: str) -> ProjectEntry | None:
            runs = list_runs(reports_root, name)
            if not runs:
                return None
            return _build_project_entry(reports_root, name, runs)

        with ThreadPoolExecutor(max_workers=min(8, len(dir_names) or 1)) as pool:
            results = pool.map(_build_one, dir_names)
        projects = [p for p in results if p is not None]
        projects.sort(key=lambda p: p.name)
        return _auto_detect_parents(projects)

    def _is_cache_valid(self) -> bool:
        return self._project_cache is not None and (time.monotonic() - self._project_cache_time) < _PROJECT_CACHE_TTL_S

    def list_projects(self, reports_dir: str) -> dict[str, Any]:
        """Return all projects found under the reports directory (TTL-cached)."""
        if self._is_cache_valid():
            return self._project_cache
        projects = self._build_project_list(Path(reports_dir))
        result = {"projects": [to_camel_dict(p) for p in projects]}
        self._project_cache = result
        self._project_cache_time = time.monotonic()
        return result

    def update_project_path(self, reports_dir: str, project: str, new_path: str) -> bool:
        """Update the path stored in a project's metadata.

        Accepts both local directory paths and remote repository URLs.
        """
        from quodeq.shared.utils import is_repo_url
        from quodeq.shared.repo_handler import is_valid_repo_url

        reports_root = Path(reports_dir).resolve()
        info_path = (reports_root / project).resolve()
        if not info_path.is_relative_to(reports_root):
            return False
        info_path = info_path / "repository_info.json"
        if not info_path.exists():
            return False

        try:
            is_url = is_repo_url(new_path)
        except ValueError:
            return False

        if is_url:
            if not is_valid_repo_url(new_path):
                return False
            resolved_path = new_path
            location = "online"
        else:
            resolved = Path(new_path).resolve()
            if not resolved.is_absolute() or not resolved.is_dir():
                return False
            resolved_path = str(resolved)
            location = "local"

        try:
            info = json.loads(info_path.read_text())
            info["path"] = resolved_path
            info["location"] = location
            info_path.write_text(json.dumps(info, indent=2))
            return True
        except (json.JSONDecodeError, OSError):
            return False

    def clone_to_local(self, reports_dir: str, project: str, destination: str) -> dict[str, Any] | None:
        """Clone an online project's repo to a local path and update its metadata."""
        import subprocess as _subprocess

        from quodeq.shared.repo_handler import is_valid_repo_url

        reports_root = Path(reports_dir).resolve()
        info_path = (reports_root / project / "repository_info.json").resolve()
        if not info_path.is_relative_to(reports_root) or not info_path.exists():
            return None
        try:
            info = json.loads(info_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        url = info.get("path", "")
        if info.get("location") != "online" or not is_valid_repo_url(url):
            return None

        dest_dir = Path(destination).resolve()
        if not dest_dir.is_dir():
            return None

        project_name = info.get("name", url.split("/")[-1].replace(".git", ""))
        clone_dest = dest_dir / project_name

        env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
        try:
            _subprocess.run(
                ["git", "clone", "--progress", url, str(clone_dest)],
                check=True,
                env=env,
                timeout=300,
            )
        except (_subprocess.CalledProcessError, _subprocess.TimeoutExpired, OSError):
            return None

        resolved_clone = str(clone_dest.resolve())
        info["path"] = resolved_clone
        info["location"] = "local"
        try:
            info_path.write_text(json.dumps(info, indent=2))
        except OSError:
            return None

        return self.get_project_info(reports_dir, project)

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
        # Detect stale path: online project with a local path instead of a URL
        path_missing = (
            info.get("location") == "online"
            and not (info.get("path", "").startswith(("https://", "git@")))
        )
        return {
            **info,
            "discipline": discipline,
            "availableDimensions": available_dimensions,
            "hasFingerprints": has_fingerprints,
            "pathMissing": path_missing,
        }

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
        from quodeq.services.violations import _ResolveOptions
        result = resolve_dimension_eval(base, project, run_id, dimension, options=_ResolveOptions(compiled_dir=compiled_dir if compiled_dir.exists() else None))
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
