"""Helper functions for the filesystem action provider."""
from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from quodeq.config.paths import default_paths
from quodeq.core.types import ProjectEntry
from quodeq.adapters.fs.report_parser import (
    RunInfo,
    read_run_data,
    safe_read_dir,
    summarize_dimensions,
)


def _read_repo_info(reports_root: Path, entry_name: str) -> dict[str, Any]:
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
) -> tuple[str | None, float | None, int | None]:
    """Read latest grade, score, and file count from a run. Returns (grade, score, files)."""
    try:
        dims = read_run_data(reports_root, entry_name, run_id)
        summary = summarize_dimensions(dims)
        grade = summary.overall_grade
        score = summary.numeric_average
        files = next((d.source_file_count for d in dims if d.source_file_count), None)
        return grade, score, files
    except (OSError, json.JSONDecodeError, KeyError):
        return None, None, None


def _check_path_exists(path: str | None, location: str | None) -> bool | None:
    """Return whether a local path exists, or None if not applicable."""
    if location == "local" and path:
        return Path(path).exists()
    return None


def _extract_project_metadata(info: dict[str, Any], entry_name: str) -> dict[str, Any]:
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
    """Build a frozen ProjectEntry from its directory and run list."""
    info = _read_repo_info(reports_root, entry_name)
    meta = _extract_project_metadata(info, entry_name)
    latest_grade, latest_score, files_count = _read_latest_run_summary(
        reports_root, entry_name, runs[0].run_id,
    )
    return ProjectEntry(
        id=entry_name,
        name=meta["name"],
        parent=meta["parent"],
        display_name=meta["displayName"],
        discipline=meta["discipline"],
        path=meta["path"],
        location=meta["location"],
        runs_count=len(runs),
        latest_run_id=runs[0].run_id,
        latest_date=runs[0].date_iso,
        path_exists=_check_path_exists(meta["path"], meta["location"]),
        files_count=files_count,
        latest_grade=latest_grade,
        latest_score=latest_score,
    )


def _find_best_parent(p_path: str, project_id: str, candidates: list[ProjectEntry]) -> str | None:
    """Find the candidate whose path is the longest prefix of *p_path*.

    Candidates must be pre-sorted by descending path length so the first
    matching candidate is always the longest (best) prefix -- O(1) average case.
    """
    for candidate in candidates:
        if candidate.id == project_id:
            continue
        c_path = candidate.path.rstrip("/")
        if p_path.startswith(c_path + "/"):
            return candidate.id
    return None


_DEFAULT_MAX_PROJECTS_LISTED = 200


def _max_projects_listed(override: int | None = None) -> int:
    """Return the max number of projects to list. *override* bypasses env."""
    if override is not None:
        return override
    raw = os.environ.get("QUODEQ_MAX_PROJECTS_LISTED")
    if raw is None:
        return _DEFAULT_MAX_PROJECTS_LISTED
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_MAX_PROJECTS_LISTED


def _auto_detect_parents(projects: list[ProjectEntry]) -> list[ProjectEntry]:
    """Return projects with parent set for local projects sharing a path prefix."""
    local_with_path = [p for p in projects if p.location == "local" and p.path]
    # Sort descending by path length so _find_best_parent returns on first match.
    local_with_path.sort(key=lambda p: len(p.path), reverse=True)
    parent_map: dict[str, str] = {}
    for project in projects:
        if project.parent is not None:
            continue
        if project.location != "local" or not project.path:
            continue
        best = _find_best_parent(project.path.rstrip("/"), project.id, local_with_path)
        if best:
            parent_map[project.id] = best
    if not parent_map:
        return projects
    return [replace(p, parent=parent_map[p.id]) if p.id in parent_map else p for p in projects]


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
