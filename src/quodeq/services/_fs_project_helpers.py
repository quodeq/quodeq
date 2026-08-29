"""Project-building helpers for the filesystem action provider."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from quodeq.core.types import ProjectEntry
from quodeq.services.ports import (
    read_repository_info,
    repository_info_exists,
    write_repository_info,
)
from quodeq.services._fs_metadata import (
    _check_path_exists,
    _extract_project_metadata,
    _read_accumulated_summary,
    _read_language_stats,
    _read_repo_info,
)
from quodeq.data.fs.report_parser.runs import RunInfo
from quodeq.shared.utils import _env_int


def _backfill_onboarding_field(
    project_dir: Path, *, heal_completed_at: str | None = None,
) -> dict | None:
    """Normalize ``onboardingCompletedAt`` in ``repository_info.json``.

    Returns the (possibly modified) data dict, or ``None`` if the file is
    missing or unreadable. Persists the change back to disk when a backfill
    happens. Treats absence of the field as already-onboarded — backfills to
    the project's existing ``createdAt`` timestamp, falling back to "now".

    *heal_completed_at*: when set and the field is present but null, stamp it
    with this value. Callers pass a timestamp only for projects that have
    evaluation runs — running an evaluation IS completing setup, so a null
    left behind by a pre-stamp wizard must not show 'Resume setup' forever.
    """
    data = read_repository_info(project_dir)
    if data is None:
        return None
    if "onboardingCompletedAt" in data:
        if data["onboardingCompletedAt"] is None and heal_completed_at:
            data["onboardingCompletedAt"] = heal_completed_at
            write_repository_info(project_dir, data)
        return data
    data["onboardingCompletedAt"] = data.get("createdAt") or datetime.now(timezone.utc).isoformat()
    write_repository_info(project_dir, data)
    return data


def _build_project_entry(
    reports_root: Path, entry_name: str, runs: list[RunInfo], *,
    backfill: bool = True, inline_summaries: bool = False,
) -> ProjectEntry:
    """Build a frozen ProjectEntry from its directory and run list.

    *backfill* mirrors ``build_project_list``'s parameter of the same name:
    when False, the record is read read-only and never rewritten (used by
    the shared-repo route so listing a clone never dirties its worktree).

    *inline_summaries* mirrors ``build_project_list``'s parameter of the same
    name, forwarded to ``_read_accumulated_summary`` as ``compute_on_miss``:
    the shared-repo route has no warm-up engine, so it keeps computing a
    missing summary inline instead of reporting it pending.
    """
    # Lazy backfill: ensure legacy project records have an
    # ``onboardingCompletedAt`` field so the wizard never auto-opens for
    # already-onboarded projects. Returns the (possibly updated) info dict
    # so we can pass the field through to the entry without re-reading.
    # Projects with runs also heal a null field to the first run's date:
    # an evaluation happened, so setup is complete (records that predate the
    # start_evaluation stamp would otherwise show 'Resume setup' forever).
    project_dir = reports_root / entry_name
    heal_at = (runs[-1].date_iso or datetime.now(timezone.utc).isoformat()) if runs else None
    backfilled = _backfill_onboarding_field(project_dir, heal_completed_at=heal_at) if backfill else None
    info = backfilled if backfilled is not None else _read_repo_info(reports_root, entry_name)
    meta = _extract_project_metadata(info, entry_name)
    latest_grade, latest_score, files_count, summary_pending = _read_accumulated_summary(
        reports_root, entry_name, runs, compute_on_miss=inline_summaries,
    )
    # runs is sorted newest-first (list_runs); status is already read there
    # (cancelled/failed/in_progress detection), so no extra per-run read is
    # needed here. "Done" == the "complete" bucket list_runs assigns to
    # anything that isn't a live/cancelled/failed run -- this is what the
    # update-vs-in-sync comparison needs: the newest run a republish would
    # actually move forward, skipping a newer run that failed or was
    # cancelled after the last successful one.
    latest_done_run_id = next((run.run_id for run in runs if run.status == "complete"), None)
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
        latest_done_run_id=latest_done_run_id,
        latest_date=runs[0].date_iso if runs else None,
        path_exists=_check_path_exists(meta["path"], meta["location"]),
        files_count=files_count,
        latest_grade=latest_grade,
        latest_score=latest_score,
        language_stats=_read_language_stats(reports_root, entry_name, runs),
        onboarding_completed_at=info.get("onboardingCompletedAt"),
        origin_url=info.get("originUrl"),
        summary_pending=summary_pending,
    )


def find_existing_project(reports_root: str, repo: str, scope_path: str | None) -> str | None:
    """Return an existing project UUID matching the given repo identity, or None.

    Walks the reports directory looking for a project whose repository
    record matches the resolved repo path/url, project name and (optional)
    scope_path. Pure read-only check — never mutates state. Used by the
    create-project route as its duplicate pre-flight.
    """
    from quodeq.shared.utils import is_repo_url, project_name_from_repo  # noqa: PLC0415

    try:
        is_url = is_repo_url(repo)
    except ValueError:
        return None
    repo_resolved = repo if is_url else str(Path(repo).resolve())
    expected_name = project_name_from_repo(repo)
    reports_path = Path(reports_root)
    if not reports_path.is_dir():
        return None
    for child in reports_path.iterdir():
        if not child.is_dir():
            continue
        data = read_repository_info(child)
        if data is None:
            continue
        if data.get("name") != expected_name:
            continue
        if data.get("path") != repo_resolved:
            continue
        if (data.get("scopePath") or None) != (scope_path or None):
            continue
        return child.name
    return None


def project_record_exists(project_dir: Path) -> bool:
    """True when the project's repository record exists on disk.

    Presence only — an unreadable record still counts (see
    :func:`read_project_record` for the content read). Gives the API layer
    a service-level entry so routes keep zero filesystem code.
    """
    return repository_info_exists(project_dir)


def read_project_record(project_dir: Path) -> dict | None:
    """The project's repository record; None when absent or unreadable."""
    return read_repository_info(project_dir)


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
