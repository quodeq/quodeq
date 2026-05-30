"""Project-building helpers for the filesystem action provider."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
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


def _backfill_onboarding_field(project_dir: Path) -> dict | None:
    """Add ``onboardingCompletedAt`` to ``repository_info.json`` if missing.

    Returns the (possibly modified) data dict, or ``None`` if the file is
    missing or unreadable. Persists the change back to disk when a backfill
    happens. Treats absence of the field as already-onboarded — backfills to
    the project's existing ``createdAt`` timestamp, falling back to "now".
    """
    info_path = project_dir / "repository_info.json"
    if not info_path.exists():
        return None
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if "onboardingCompletedAt" in data:
        return data
    data["onboardingCompletedAt"] = data.get("createdAt") or datetime.now(timezone.utc).isoformat()
    try:
        info_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass
    return data


def _build_project_entry(reports_root: Path, entry_name: str, runs: list[RunInfo]) -> ProjectEntry:
    """Build a frozen ProjectEntry from its directory and run list."""
    # Lazy backfill: ensure legacy project records have an
    # ``onboardingCompletedAt`` field so the wizard never auto-opens for
    # already-onboarded projects. Returns the (possibly updated) info dict
    # so we can pass the field through to the entry without re-reading.
    project_dir = reports_root / entry_name
    backfilled = _backfill_onboarding_field(project_dir)
    info = backfilled if backfilled is not None else _read_repo_info(reports_root, entry_name)
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
        scope_path=meta.get("scopePath"),
        runs_count=len(runs),
        latest_run_id=runs[0].run_id if runs else None,
        latest_date=runs[0].date_iso if runs else None,
        path_exists=_check_path_exists(meta["path"], meta["location"]),
        files_count=files_count,
        latest_grade=latest_grade,
        latest_score=latest_score,
        language_stats=_read_language_stats(reports_root, entry_name, runs),
        onboarding_completed_at=info.get("onboardingCompletedAt"),
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
