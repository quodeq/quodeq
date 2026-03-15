"""Filesystem-backed implementation of the ActionProvider interface."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable

from quodeq.shared.types import JsonObject, ProjectEntry, ProjectListResponse, ProjectMetadata, ViolationSummary

from quodeq.provider.base import ActionProvider
from quodeq.provider.jobs import JobManager
from quodeq.provider.evaluation_mixin import FsEvaluationMixin
from quodeq.provider.tooling_mixin import FsToolingMixin
from quodeq.provider.violations import aggregate_violations, resolve_dimension_eval
from quodeq.config.paths import default_paths
from quodeq.provider.accumulated import compute_accumulated
from quodeq.provider.dashboard import build_dashboard
from quodeq.adapters.fs.report_parser import (
    RunInfo,
    list_runs,
    read_run_data,
    safe_read_dir,
    summarize_dimensions,
)


def _read_repo_info(reports_root: Path, entry_name: str) -> JsonObject:
    """Read repository_info.json for a project, returning an empty dict on failure."""
    info_path = reports_root / entry_name / "repository_info.json"
    if not info_path.exists():
        return {}
    try:
        return json.loads(info_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _read_latest_run_summary(
    reports_root: Path, entry_name: str, run_id: str,
) -> tuple[str | None, str | None, int | None]:
    """Read latest grade, score, and file count from a run. Returns (grade, score, files)."""
    try:
        dims = read_run_data(reports_root, entry_name, run_id)
        summary = summarize_dimensions(dims)
        grade = summary.get("overallGrade")
        score = summary.get("numericAverage")
        files = next((d.get("sourceFileCount") for d in dims if d.get("sourceFileCount")), None)
        return grade, score, files
    except (OSError, json.JSONDecodeError, KeyError):
        return None, None, None


def _check_path_exists(path: str | None, location: str | None) -> bool | None:
    """Return whether a local path exists, or None if not applicable."""
    if location == "local" and path:
        return Path(path).exists()
    return None


def _extract_project_metadata(info: JsonObject, entry_name: str) -> ProjectMetadata:
    """Extract and normalize optional metadata fields from repository info."""
    return {
        "name": info.get("name") or entry_name,
        "parent": info.get("parent") or None,
        "displayName": info.get("displayName") or None,
        "discipline": info.get("discipline") or None,
        "path": info.get("path") or None,
        "location": info.get("location") or None,
    }


def _build_project_entry(reports_root: Path, entry_name: str, runs: list[RunInfo]) -> ProjectEntry:
    """Build a single project dict from its directory and run list."""
    info = _read_repo_info(reports_root, entry_name)
    meta = _extract_project_metadata(info, entry_name)
    latest_grade, latest_score, files_count = _read_latest_run_summary(
        reports_root, entry_name, runs[0].run_id,
    )
    return {
        "id": entry_name,
        **meta,
        "runsCount": len(runs),
        "latestRunId": runs[0].run_id,
        "latestDate": runs[0].date_iso,
        "pathExists": _check_path_exists(meta["path"], meta["location"]),
        "filesCount": files_count,
        "latestGrade": latest_grade,
        "latestScore": latest_score,
    }


def _find_best_parent(p_path: str, project_id: str, candidates: list[ProjectEntry]) -> str | None:
    """Find the candidate whose path is the longest prefix of *p_path*.

    Candidates must be pre-sorted by descending path length so the first
    matching candidate is always the longest (best) prefix — O(1) average case.
    """
    for candidate in candidates:
        if candidate["id"] == project_id:
            continue
        c_path = candidate["path"].rstrip("/")
        if p_path.startswith(c_path + "/"):
            return candidate["id"]
    return None


_DEFAULT_MAX_PROJECTS_LISTED = 200


def _max_projects_listed(override: int | None = None) -> int:
    """Return the max number of projects to list. *override* bypasses env."""
    if override is not None:
        return override
    return int(os.environ.get("QUODEQ_MAX_PROJECTS_LISTED", str(_DEFAULT_MAX_PROJECTS_LISTED)))


def _auto_detect_parents(projects: list[ProjectEntry]) -> None:
    """Set parent for local projects that share a path prefix with another project."""
    local_with_path = [p for p in projects if p.get("location") == "local" and p.get("path")]
    # Sort descending by path length so _find_best_parent returns on first match.
    local_with_path.sort(key=lambda p: len(p["path"]), reverse=True)
    for project in projects:
        if project.get("parent") is not None:
            continue
        if project.get("location") != "local" or not project.get("path"):
            continue
        best = _find_best_parent(project["path"].rstrip("/"), project["id"], local_with_path)
        if best:
            project["parent"] = best


def _read_discipline_from_eval(eval_path: Path) -> str | None:
    """Try to read a discipline string from a single evidence JSON file."""
    try:
        return json.loads(eval_path.read_text()).get("discipline") or None
    except (OSError, json.JSONDecodeError):
        return None


def _find_discipline_in_run(evidence_dir: Path) -> str | None:
    """Search a single run's evidence directory for a discipline string."""
    for ev in safe_read_dir(evidence_dir):
        if ev.name.endswith("_evidence.json"):
            found = _read_discipline_from_eval(Path(ev.path))
            if found:
                return found
    return None


def _infer_discipline(reports_root: Path, project: str) -> str | None:
    """Infer discipline from the most recent evidence file."""
    for run in sorted(safe_read_dir(reports_root / project), key=lambda e: e.name, reverse=True):
        if not run.is_dir():
            continue
        found = _find_discipline_in_run(reports_root / project / run.name / "evidence")
        if found:
            return found
    return None


def _list_available_dimensions_for_discipline(
    discipline: str, evaluators_dir: Path | None = None,
) -> list[str]:
    """Resolve available dimensions for a plugin via its dimensions.json.

    *evaluators_dir* overrides the default path lookup, making the function
    testable without relying on the global config.
    """
    try:
        base = evaluators_dir if evaluators_dir is not None else default_paths().evaluators_dir
        plugin_dir = base / discipline
        dims_file = plugin_dir / "dimensions.json"
        if dims_file.exists():
            data = json.loads(dims_file.read_text())
            return [d["id"] for d in data.get("applies", [])]
        return []
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return []


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

    def __init__(self, job_manager: JobManager | None = None) -> None:
        super().__init__()
        self._jobs = job_manager or JobManager()
        self._model_fetchers: dict[str, Callable] = {
            "claude": self._get_claude_models,
        }

    def list_projects(self, reports_dir: str) -> ProjectListResponse:
        """Return all projects found under the reports directory."""
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
        projects.sort(key=lambda item: item["name"])
        _auto_detect_parents(projects)
        return {"projects": projects}

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

    def get_project_info(self, reports_dir: str, project: str) -> JsonObject | None:
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
        available_dimensions = _list_available_dimensions_for_discipline(discipline) if discipline else []
        return {**info, "discipline": discipline, "availableDimensions": available_dimensions}

    def get_dashboard(self, reports_dir: str, project: str, run: str) -> JsonObject:
        """Return the dashboard payload for a specific project run."""
        return build_dashboard(reports_dir, project, run)

    def get_accumulated(self, reports_dir: str, project: str, as_of: str | None) -> JsonObject | None:
        """Return accumulated dimension data across all runs up to as_of."""
        return compute_accumulated(reports_dir, project, as_of)

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str) -> JsonObject | None:
        """Return parsed evaluation data for a single dimension in a run."""
        from quodeq.config.paths import default_paths
        base = (Path(reports_dir) / project / run_id).resolve()
        if not base.is_relative_to(Path(reports_dir).resolve()):
            return None
        compiled_dir = default_paths().standards_dir / "compiled"
        result = resolve_dimension_eval(base, project, run_id, dimension, compiled_dir=compiled_dir if compiled_dir.exists() else None)
        if result is not None:
            return result
        # Run exists but dimension hasn't started yet
        if base.is_dir():
            return {"waiting": True, "project": project, "runId": run_id, "dimension": dimension}
        return None

    def get_violations(self, reports_dir: str, project: str, run_id: str) -> ViolationSummary:
        """Return aggregated violation counts and top files for a run."""
        dashboard = self.get_dashboard(reports_dir, project, run_id)
        return aggregate_violations(dashboard)
