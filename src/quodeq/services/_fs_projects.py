"""Project CRUD helpers for the filesystem action provider."""

from __future__ import annotations

import contextvars
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quodeq.core.types import ProjectEntry
from quodeq.services._filesystem_helpers import _list_available_dimensions_for_discipline
from quodeq.services._fs_metadata import _has_fingerprints, _infer_discipline
from quodeq.services._fs_project_helpers import (
    _auto_detect_parents,
    _backfill_onboarding_field,
    _build_project_entry,
    _max_projects_listed,
)
from quodeq.services.ports import list_runs, safe_read_dir
from quodeq.shared.repo_handler import is_valid_repo_url
from quodeq.shared.utils import is_repo_url

_MAX_PROJECT_BUILD_WORKERS = 8


def _derive_last_fetched_at(repo_path: str | None) -> str | None:
    """Return ISO-8601 mtime of .git/FETCH_HEAD (or .git/HEAD as fallback), or None."""
    if not repo_path:
        return None
    p = Path(repo_path)
    fetch_head = p / ".git" / "FETCH_HEAD"
    head = p / ".git" / "HEAD"
    candidate = fetch_head if fetch_head.exists() else head if head.exists() else None
    if candidate is None:
        return None
    try:
        ts = candidate.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _is_evaluable(repo_path: str | None) -> bool:
    """Return True if the working copy directory exists on disk."""
    if not repo_path:
        return False
    return Path(repo_path).is_dir()


def find_children(reports_root: Path, parent_id: str) -> list[str]:
    """Return UUIDs of child projects whose parent matches *parent_id*."""
    children: list[str] = []
    for entry in reports_root.iterdir():
        if not entry.is_dir() or entry.name == parent_id:
            continue
        info_path = entry / "repository_info.json"
        if not info_path.exists():
            continue
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
            if info.get("parent") == parent_id:
                children.append(entry.name)
        except (json.JSONDecodeError, OSError):
            continue
    return children


def _build_parent_child_sets(reports_root: Path, dir_names: list[str]) -> tuple[set[str], set[str]]:
    """Single pass: return (parent_ids, subproject_ids) from repo info files."""
    parent_ids: set[str] = set()
    subproject_ids: set[str] = set()
    for name in dir_names:
        info_path = reports_root / name / "repository_info.json"
        if not info_path.exists():
            continue
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
            parent = info.get("parent")
            if parent:
                parent_ids.add(parent)
                subproject_ids.add(name)
        except (json.JSONDecodeError, OSError):
            continue
    return parent_ids, subproject_ids


def build_project_list(reports_root: Path, *, backfill: bool = True) -> list[ProjectEntry]:
    """Collect eligible project dirs and build entries in parallel.

    *backfill* controls the lazy ``onboardingCompletedAt`` backfill below (and
    the equivalent one inside ``_build_project_entry``): when False, records
    are read as-is and never rewritten. Local callers keep the default
    (True); the shared-repo route passes False so listing a clone's projects
    never dirties its git worktree (see routes_shared.py shared_projects).
    """
    max_listed = _max_projects_listed()
    dir_names: list[str] = []
    for entry in safe_read_dir(reports_root):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        dir_names.append(entry.name)
        if len(dir_names) >= max_listed:
            break

    # Lazy backfill: ensure legacy project records have an
    # ``onboardingCompletedAt`` field. Run before the parent/child sweep so
    # any subsequent reads see the updated file. Idempotent — no-op for
    # records that already have the field. Failures are silently ignored.
    if backfill:
        for name in dir_names:
            _backfill_onboarding_field(reports_root / name)

    parent_ids, subproject_ids = _build_parent_child_sets(reports_root, dir_names)

    def _build_one(name: str) -> ProjectEntry | None:
        runs = list_runs(reports_root, name)
        if not runs and name not in parent_ids and name not in subproject_ids:
            return None
        return _build_project_entry(reports_root, name, runs, backfill=backfill)

    # contextvars do NOT propagate into ThreadPoolExecutor worker threads --
    # each worker runs with its own default Context, so a caller-side
    # score_cache_path_override (e.g. from _with_shared_root) would be
    # invisible inside _build_one and per-project summaries would read/write
    # the LOCAL score cache DB instead of the scoped one. Copy the calling
    # context once per task -- a single Context object cannot be entered by
    # more than one thread concurrently -- so each worker sees the same
    # contextvar values (including the override, when active) as the caller.
    # When no override is active this is a no-op: copy_context().run just
    # calls _build_one with the same (empty) contextvar state.
    ctxs = [contextvars.copy_context() for _ in dir_names]
    with ThreadPoolExecutor(max_workers=min(_MAX_PROJECT_BUILD_WORKERS, len(dir_names) or 1)) as pool:
        results = pool.map(
            lambda pair: pair[0].run(_build_one, pair[1]), zip(ctxs, dir_names),
        )
    projects = [p for p in results if p is not None]
    projects.sort(key=lambda p: p.name)
    return _auto_detect_parents(projects)


def update_project_path(reports_dir: str, project: str, new_path: str) -> bool:
    """Update the path stored in a project's metadata."""
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
        # Reject path-traversal attempts in the raw input before resolving.
        if ".." in Path(new_path).parts:
            return False
        resolved = Path(new_path).resolve()
        if not resolved.is_absolute() or not resolved.is_dir():
            return False
        resolved_path = str(resolved)
        location = "local"

    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
        info["path"] = resolved_path
        info["location"] = location
        info_path.write_text(json.dumps(info, indent=2), encoding="utf-8")
        return True
    except (json.JSONDecodeError, OSError):
        return False


def delete_project(reports_dir: str, project: str) -> bool:
    """Remove a project directory and all its report data.

    If the project is a parent, cascade-deletes all children.
    """
    reports_root = Path(reports_dir).resolve()
    project_path = (reports_root / project).resolve()
    if not project_path.is_relative_to(reports_root):
        return False
    if not project_path.exists() or not project_path.is_dir():
        return False

    # Cascade: find and delete children first
    for child_id in find_children(reports_root, project):
        shutil.rmtree(reports_root / child_id, ignore_errors=True)

    try:
        shutil.rmtree(project_path)
    except OSError:
        return False
    return True


def get_project_info(reports_dir: str, project: str) -> dict[str, Any] | None:
    """Return project metadata including discipline and available dimensions."""
    info_path = (Path(reports_dir) / project / "repository_info.json").resolve()
    if not info_path.is_relative_to(Path(reports_dir).resolve()):
        return None
    if not info_path.exists():
        return None
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    discipline = info.get("discipline") or _infer_discipline(Path(reports_dir), project)
    available_dimensions = _list_available_dimensions_for_discipline() if discipline else []
    has_fingerprints = _has_fingerprints(Path(reports_dir), project)
    path_missing = (
        info.get("location") == "online"
        and not (info.get("path", "").startswith(("https://", "git@")))
    )
    repo_path = info.get("path")
    info["lastFetchedAt"] = _derive_last_fetched_at(repo_path)
    info["evaluable"] = _is_evaluable(repo_path)
    info.setdefault("ephemeral", False)
    return {
        **info,
        "discipline": discipline,
        "availableDimensions": available_dimensions,
        "hasFingerprints": has_fingerprints,
        "pathMissing": path_missing,
    }
