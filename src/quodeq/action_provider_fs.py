"""Filesystem-backed implementation of the ActionProvider interface."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from quodeq.action_provider import ActionProvider
from quodeq.action_provider_jobs import JobManager
from quodeq._fs_evaluation_mixin import FsEvaluationMixin
from quodeq._fs_tooling_mixin import FsToolingMixin
from quodeq._fs_violations import parse_violations_from_evidence, parse_violations_from_jsonl, parse_violations_from_stream
from quodeq.action_provider_fs_dashboard import build_dashboard, compute_accumulated
from quodeq.adapters.fs.report_parser import (
    RunInfo,
    list_runs,
    parse_eval_from_json,
    parse_eval_markdown,
    read_run_data,
    safe_read_dir,
    summarize_dimensions,
)


_MAX_VIOLATION_FILES = 20


def _build_project_entry(reports_root: Path, entry_name: str, runs: list[RunInfo]) -> dict[str, Any]:
    """Build a single project dict from its directory and run list."""
    info: dict[str, Any] = {}
    info_path = reports_root / entry_name / "repository_info.json"
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    parent = info.get("parent") or None
    discipline = info.get("discipline") or None
    path = info.get("path") or None
    location = info.get("location") or None
    display_name = info.get("displayName") or None
    project_name = info.get("name") or entry_name
    latest_grade = None
    latest_score = None
    files_count = None
    try:
        dims = read_run_data(reports_root, entry_name, runs[0].run_id)
        summary = summarize_dimensions(dims)
        latest_grade = summary.get("overallGrade")
        latest_score = summary.get("numericAverage")
        files_count = next((d.get("sourceFileCount") for d in dims if d.get("sourceFileCount")), None)
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    path_exists = Path(path).exists() if location == "local" and path else None
    return {
        "id": entry_name,
        "name": project_name,
        "runsCount": len(runs),
        "latestRunId": runs[0].run_id,
        "latestDate": runs[0].date_iso,
        "parent": parent,
        "displayName": display_name,
        "discipline": discipline,
        "path": path,
        "location": location,
        "pathExists": path_exists,
        "filesCount": files_count,
        "latestGrade": latest_grade,
        "latestScore": latest_score,
    }


def _auto_detect_parents(projects: list[dict[str, Any]]) -> None:
    """Set parent for local projects that share a path prefix with another project."""
    local_with_path = [p for p in projects if p.get("location") == "local" and p.get("path")]
    for project in projects:
        if project.get("parent") is not None:
            continue
        if project.get("location") != "local" or not project.get("path"):
            continue
        p_path = project["path"].rstrip("/")
        best_parent = None
        best_len = 0
        for candidate in local_with_path:
            if candidate["id"] == project["id"]:
                continue
            c_path = candidate["path"].rstrip("/")
            if p_path.startswith(c_path + "/") and len(c_path) > best_len:
                best_parent = candidate["id"]
                best_len = len(c_path)
        if best_parent:
            project["parent"] = best_parent


def _read_discipline_from_eval(eval_path: Path) -> str | None:
    """Try to read a discipline string from a single evidence JSON file."""
    try:
        return json.loads(eval_path.read_text()).get("discipline") or None
    except (OSError, json.JSONDecodeError):
        return None


def _infer_discipline(reports_root: Path, project: str) -> str | None:
    """Infer discipline from the most recent evidence file."""
    for run in sorted(safe_read_dir(reports_root / project), key=lambda e: e.name, reverse=True):
        if not run.is_dir():
            continue
        for ev in safe_read_dir(reports_root / project / run.name / "evidence"):
            if ev.name.endswith("_evidence.json"):
                found = _read_discipline_from_eval(Path(ev.path))
                if found:
                    return found
    return None


def _list_available_dimensions_for_discipline(discipline: str) -> list[str]:
    """Resolve available dimensions for a plugin via its dimensions.json."""
    try:
        from quodeq.config.paths import default_paths
        plugin_dir = default_paths().evaluators_dir / discipline
        dims_file = plugin_dir / "dimensions.json"
        if dims_file.exists():
            data = json.loads(dims_file.read_text())
            return [d["id"] for d in data.get("applies", [])]
        return []
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return []


def _resolve_dimension_eval(
    base: Path, project: str, run_id: str, dimension: str,
) -> dict[str, Any] | None:
    """Try successive file formats to load evaluation data for a dimension."""
    eval_path = base / "evaluation" / f"{dimension}.json"
    if eval_path.exists():
        return parse_eval_from_json(eval_path, project, run_id, dimension)

    markdown_path = base / "evaluation" / f"{dimension}_eval.md"
    if markdown_path.exists():
        try:
            content = markdown_path.read_text()
        except OSError:
            return None
        return parse_eval_markdown(content, project, run_id, dimension)

    evidence_path = base / "evidence" / f"{dimension}_evidence.json"
    if evidence_path.exists():
        return parse_violations_from_evidence(evidence_path, project, run_id, dimension)

    jsonl_path = base / "evidence" / f"{dimension}_evidence.jsonl"
    stream_path = base / "evidence" / f"{dimension}_live.stream"
    if jsonl_path.exists() and jsonl_path.stat().st_size > 0:
        return parse_violations_from_jsonl(jsonl_path, stream_path, project, run_id, dimension)

    if stream_path.exists():
        return parse_violations_from_stream(stream_path, project, run_id, dimension)

    return None


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
        self._jobs = job_manager or JobManager()
        self._model_fetchers: dict[str, Callable] = {
            "claude": self._get_claude_models,
        }

    def list_projects(self, reports_dir: str) -> dict[str, Any]:
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
        projects.sort(key=lambda item: item["name"])
        _auto_detect_parents(projects)
        return {"projects": projects}

    def update_project_path(self, reports_dir: str, project: str, new_path: str) -> bool:
        """Update the local filesystem path stored in a project's metadata."""
        info_path = Path(reports_dir) / project / "repository_info.json"
        if not info_path.exists():
            return False
        try:
            info = json.loads(info_path.read_text())
            info["path"] = new_path
            info["location"] = "local"
            info_path.write_text(json.dumps(info, indent=2))
            return True
        except (json.JSONDecodeError, OSError):
            return False

    def delete_project(self, reports_dir: str, project: str) -> bool:
        """Remove a project directory and all its report data."""
        import shutil
        project_path = Path(reports_dir) / project
        if not project_path.exists() or not project_path.is_dir():
            return False
        shutil.rmtree(project_path)
        return True

    def get_project_info(self, reports_dir: str, project: str) -> dict[str, Any] | None:
        """Return project metadata including discipline and available dimensions."""
        info_path = Path(reports_dir) / project / "repository_info.json"
        if not info_path.exists():
            return None
        try:
            info = json.loads(info_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        discipline = info.get("discipline") or _infer_discipline(Path(reports_dir), project)
        available_dimensions = _list_available_dimensions_for_discipline(discipline) if discipline else []
        return {**info, "discipline": discipline, "availableDimensions": available_dimensions}

    def get_dashboard(self, reports_dir: str, project: str, run: str) -> dict[str, Any]:
        """Return the dashboard payload for a specific project run."""
        return build_dashboard(reports_dir, project, run)

    def get_accumulated(self, reports_dir: str, project: str, as_of: str | None) -> dict[str, Any] | None:
        """Return accumulated dimension data across all runs up to as_of."""
        return compute_accumulated(reports_dir, project, as_of)

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
        """Return parsed evaluation data for a single dimension in a run."""
        base = Path(reports_dir) / project / run_id
        result = _resolve_dimension_eval(base, project, run_id, dimension)
        if result is not None:
            return result
        # Run exists but dimension hasn't started yet
        if base.is_dir():
            return {"waiting": True, "project": project, "runId": run_id, "dimension": dimension}
        return None

    def get_violations(self, reports_dir: str, project: str, run_id: str) -> dict[str, Any]:
        """Return aggregated violation counts and top files for a run."""
        dashboard = self.get_dashboard(reports_dir, project, run_id)
        summary = {
            "total": 0,
            "critical": 0,
            "major": 0,
            "minor": 0,
            "byFile": {},
        }
        for dim in dashboard.get("dimensions", []) or []:
            summary["total"] += dim.get("totals", {}).get("violationCount", 0)
            severity = dim.get("totals", {}).get("severity", {})
            summary["critical"] += severity.get("critical", 0)
            summary["major"] += severity.get("major", 0)
            summary["minor"] += severity.get("minor", 0)

            for violation in dim.get("violations", []) or []:
                file_path = violation.get("file")
                if not file_path:
                    continue
                entry = summary["byFile"].setdefault(
                    file_path, {"path": file_path, "count": 0, "critical": 0, "major": 0, "minor": 0}
                )
                entry["count"] += 1
                sev = violation.get("severity", "minor")
                if sev in entry:
                    entry[sev] += 1

        files = sorted(summary["byFile"].values(), key=lambda item: item["count"], reverse=True)[:_MAX_VIOLATION_FILES]
        summary["files"] = files
        summary.pop("byFile", None)
        return summary

    # browse_repo, get_ai_clients, get_client_models -> FsToolingMixin
    # start_evaluation, get_evaluation_status, cancel_evaluation -> FsEvaluationMixin
