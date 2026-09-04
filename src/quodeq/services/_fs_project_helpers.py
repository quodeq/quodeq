"""Project-building helpers for the filesystem action provider.

Split (Task 13): parent-detection and the max-projects-listed limit moved to
_fs_project_parents.py, re-exported here for _fs_projects.py's import.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from quodeq.core.types import ProjectEntry
from quodeq.services._wiring import (
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
from quodeq.services._fs_project_parents import (  # noqa: F401 — re-export
    _auto_detect_parents,
    _find_best_parent,
    _max_projects_listed,
)
from quodeq.data.fs.report_parser.runs import RunInfo
from quodeq.services._repo_index import _load_repo_index, _repo_index_key, _save_repo_index

_logger = logging.getLogger(__name__)


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


def _derive_latest_done_run_id(runs: list[RunInfo]) -> str | None:
    """The newest run a republish would actually move forward.

    runs is sorted newest-first (list_runs); status is already read there
    (cancelled/failed/in_progress detection), so no extra per-run read is
    needed here. "Done" == the "complete" bucket list_runs assigns to
    anything that isn't a live/cancelled/failed run -- this is what the
    update-vs-in-sync comparison needs, skipping a newer run that failed or
    was cancelled after the last successful one.
    """
    return next((run.run_id for run in runs if run.status == "complete"), None)


def _backfill_and_read_meta(
    reports_root: Path, entry_name: str, runs: list[RunInfo], *, backfill: bool,
) -> tuple[dict, dict]:
    """Lazy-backfill the project record, then extract its display metadata.

    Ensures legacy project records have an ``onboardingCompletedAt`` field so
    the wizard never auto-opens for already-onboarded projects. Returns the
    (possibly updated) info dict so callers can pass the field through to the
    entry without re-reading. Projects with runs also heal a null field to
    the first run's date: an evaluation happened, so setup is complete
    (records that predate the start_evaluation stamp would otherwise show
    'Resume setup' forever).

    *backfill* mirrors ``build_project_list``'s parameter of the same name:
    when False, the record is read read-only and never rewritten (used by
    the shared-repo route so listing a clone never dirties its worktree).
    """
    project_dir = reports_root / entry_name
    heal_at = (runs[-1].date_iso or datetime.now(timezone.utc).isoformat()) if runs else None
    backfilled = _backfill_onboarding_field(project_dir, heal_completed_at=heal_at) if backfill else None
    info = backfilled if backfilled is not None else _read_repo_info(reports_root, entry_name)
    return info, _extract_project_metadata(info, entry_name)


def _build_project_entry(
    reports_root: Path, entry_name: str, runs: list[RunInfo], *,
    backfill: bool = True, inline_summaries: bool = False,
) -> ProjectEntry:
    """Build a frozen ProjectEntry from its directory and run list.

    *inline_summaries* mirrors ``build_project_list``'s parameter of the same
    name, forwarded to ``_read_accumulated_summary`` as ``compute_on_miss``:
    the shared-repo route has no warm-up engine, so it keeps computing a
    missing summary inline instead of reporting it pending. See
    ``_backfill_and_read_meta`` for the *backfill* rationale.
    """
    info, meta = _backfill_and_read_meta(reports_root, entry_name, runs, backfill=backfill)
    latest_grade, latest_score, files_count, summary_pending = _read_accumulated_summary(
        reports_root, entry_name, runs, compute_on_miss=inline_summaries,
    )
    latest_done_run_id = _derive_latest_done_run_id(runs)
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


def _repo_identity_matches(
    project_dir: Path, expected_name: str, repo_resolved: str, scope_path: str | None,
) -> bool:
    """True when this project's record still carries that repo identity.

    The (name, path, scopePath) triple is exactly the repo-identity index
    key, so this is the authoritative check the index only caches.
    """
    data = read_repository_info(project_dir)
    return (
        data is not None
        and data.get("name") == expected_name
        and data.get("path") == repo_resolved
        and (data.get("scopePath") or None) == (scope_path or None)
    )


def find_existing_project(reports_root: str, repo: str, scope_path: str | None) -> str | None:
    """Return an existing project UUID matching the given repo identity, or None.

    Index-first: ``.repo_index.json`` maps (name, path, scopePath) to uuid
    for an O(1) lookup instead of reading every project's
    repository_info.json. Both directions of staleness resolve to the walk,
    never to a wrong answer: a miss falls through to it (and a hit there
    self-heals the index for next time), and a hit is verified against the
    candidate's own record before it is trusted, so an entry left behind by
    a path change, a corrupt index file, or a concurrent create/delete gets
    dropped and the walk decides.

    From the caller's perspective this is still a read-only check (both index
    writes are cache repair). Used by the create-project route as its
    duplicate pre-flight.
    """
    from quodeq.shared.utils import is_repo_url, project_name_from_repo  # noqa: PLC0415

    try:
        is_url = is_repo_url(repo)
    except ValueError as exc:
        _logger.warning("Rejecting malformed repo identifier %r in duplicate check: %s", repo, exc)
        return None
    repo_resolved = repo if is_url else str(Path(repo).resolve())
    expected_name = project_name_from_repo(repo)
    reports_path = Path(reports_root)
    if not reports_path.is_dir():
        return None

    key = _repo_index_key(expected_name, repo_resolved, scope_path)
    index = _load_repo_index(reports_path)
    candidate = index.get(key)
    if candidate is not None:
        if _repo_identity_matches(
            reports_path / candidate, expected_name, repo_resolved, scope_path,
        ):
            return candidate
        index.pop(key, None)
        _save_repo_index(reports_path, index)

    for child in reports_path.iterdir():
        if not child.is_dir():
            continue
        if not _repo_identity_matches(child, expected_name, repo_resolved, scope_path):
            continue
        index[key] = child.name
        _save_repo_index(reports_path, index)
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
