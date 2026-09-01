"""Parent-detection helpers for the filesystem action provider.

Split out of _fs_project_helpers.py (Task 13): auto-detecting a local
project's parent by longest-path-prefix match, plus the max-projects-listed
env-backed limit. Both are re-exported from _fs_project_helpers.py, which
_fs_projects.py imports them from.
"""
from __future__ import annotations

from dataclasses import replace

from quodeq.core.types import ProjectEntry
from quodeq.shared.utils import _env_int

_DEFAULT_MAX_PROJECTS_LISTED = 200


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
