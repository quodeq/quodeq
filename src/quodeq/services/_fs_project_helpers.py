"""Project-building helpers for the filesystem action provider."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from quodeq.core.types import ProjectEntry
from quodeq.services._fs_metadata import (
    _check_path_exists,
    _extract_project_metadata,
    _read_accumulated_summary,
    _read_language_stats,
    _read_repo_info,
)
from quodeq.services.ports import RunInfo
from quodeq.shared.utils import _env_int


def _build_project_entry(reports_root: Path, entry_name: str, runs: list[RunInfo]) -> ProjectEntry:
    """Build a frozen ProjectEntry from its directory and run list."""
    info = _read_repo_info(reports_root, entry_name)
    meta = _extract_project_metadata(info, entry_name)
    latest_grade, latest_score, files_count = _read_accumulated_summary(
        reports_root, entry_name, runs,
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
        latest_run_id=runs[0].run_id if runs else None,
        latest_date=runs[0].date_iso if runs else None,
        path_exists=_check_path_exists(meta["path"], meta["location"]),
        files_count=files_count,
        latest_grade=latest_grade,
        latest_score=latest_score,
        language_stats=_read_language_stats(reports_root, entry_name, runs),
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


def _max_projects_listed(override: int | None = None, env: dict[str, str] | None = None) -> int:
    """Return the max number of projects to list. *override* bypasses env."""
    if override is not None:
        return override
    return _env_int("QUODEQ_MAX_PROJECTS_LISTED", _DEFAULT_MAX_PROJECTS_LISTED, env=env)


def _auto_detect_parents(projects: list[ProjectEntry]) -> list[ProjectEntry]:
    """Return projects with parent set for local projects sharing a path prefix."""
    local_with_path = [p for p in projects if p.location == "local" and p.path]
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
