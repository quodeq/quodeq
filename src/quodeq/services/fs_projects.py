"""Project CRUD helpers for the filesystem action provider."""

from __future__ import annotations

import contextvars
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from quodeq.core.types import ProjectEntry
from quodeq.core.types.project_source import ProjectLocation
from quodeq.core.utils.io import is_within
from quodeq.services._filesystem_helpers import list_available_dimensions_for_discipline
from quodeq.shared.log_sink import SHARED_LOG
from quodeq.services._fs_metadata import project_has_fingerprints, infer_discipline
from quodeq.services._fs_project_primitives import repo_attach_reason  # noqa: F401 — re-export
from quodeq.services._fs_working_copy import annotate_working_copy, online_path_missing
from quodeq.services.fs_project_helpers import (
    KnownProjectIds,
    ListingOptions,
    auto_detect_parents,
    backfill_onboarding_field,
    build_project_entry,
    max_projects_listed,
)
from quodeq.services._repo_index import RepoIdentity, rekey_repo_index_entry, remove_repo_index_entries
from quodeq.services.wiring import (
    find_children,
    is_valid_repo_url,
    list_runs,
    read_repository_info,
    remove_project_dir,
    repository_info_exists,
    safe_read_dir,
    write_repository_info,
)
from quodeq.shared.utils import is_repo_url, project_name_from_repo

_logger = logging.getLogger(__name__)

_MAX_PROJECT_BUILD_WORKERS = 8


def build_parent_child_sets(reports_root: Path, dir_names: list[str]) -> tuple[set[str], set[str], dict[str, dict]]:
    """Single pass: return (parent_ids, subproject_ids, info_by_name) from repo info files."""
    parent_ids: set[str] = set()
    subproject_ids: set[str] = set()
    info_by_name: dict[str, dict] = {}
    for name in dir_names:
        info = read_repository_info(reports_root / name)
        if info is None:
            continue
        info_by_name[name] = info
        parent = info.get("parent")
        if parent:
            parent_ids.add(parent)
            subproject_ids.add(name)
    return parent_ids, subproject_ids, info_by_name


def collect_candidate_dirs(reports_root: Path, max_listed: int) -> list[str]:
    """Return up to *max_listed* non-hidden directory names under reports_root."""
    dir_names: list[str] = []
    for entry in safe_read_dir(reports_root):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        dir_names.append(entry.name)
        if len(dir_names) >= max_listed:
            break
    return dir_names


def build_project_entries_threaded(
    reports_root: Path, dir_names: list[str], known: KnownProjectIds,
    options: ListingOptions, info_by_name: dict[str, dict] | None = None,
) -> list[ProjectEntry]:
    """Build a ProjectEntry per candidate dir in parallel, dropping stray dirs.

    A registered project (repository_info.json present) is listed even with
    zero runs — the onboarding wizard creates projects before any evaluation
    exists and the UI shows an empty state for them. Only dirs with neither
    runs nor a project record (stray non-project dirs) are dropped.
    """
    if info_by_name is None:
        info_by_name = {}

    def _build_one(name: str) -> ProjectEntry | None:
        try:
            runs = list_runs(reports_root, name)
            if not runs and name not in known.registered and name not in known.parents and name not in known.subprojects:
                return None
            return build_project_entry(
                reports_root, name, runs, options, pre_read_info=info_by_name.get(name),
            )
        except (OSError, ValueError, KeyError) as exc:  # JSONDecodeError is a ValueError
            _logger.warning("Skipping project dir %r: could not build entry: %s", name, exc)

    # contextvars do NOT propagate into ThreadPoolExecutor worker threads --
    # each worker runs with its own default Context, so a caller-side
    # score_cache_path_override (e.g. from with_shared_root) would be
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
    return [p for p in results if p is not None]


def _classify_known_ids(
    reports_root: Path, dir_names: list[str], *, backfill: bool,
) -> tuple[KnownProjectIds, dict[str, dict]]:
    """Read every candidate's repo record once: known-id sets plus the records by name.

    With *backfill* the lazy ``onboardingCompletedAt`` backfill runs on each
    record before the registered set is taken.
    """
    parent_ids, subproject_ids, info_by_name = build_parent_child_sets(reports_root, dir_names)
    if backfill:
        for name in dir_names:
            backfill_onboarding_field(reports_root / name, pre_read_data=info_by_name.get(name))
    # info_by_name already holds every parseable record; only the dirs it
    # lacks need the presence probe (a corrupt record still registers).
    registered_ids = {
        name for name in dir_names
        if name in info_by_name or repository_info_exists(reports_root / name)
    }
    return KnownProjectIds(registered_ids, parent_ids, subproject_ids), info_by_name


def build_project_list(
    reports_root: Path, *, backfill: bool = True, inline_summaries: bool = False,
) -> list[ProjectEntry]:
    """Collect eligible project dirs and build entries in parallel.

    *backfill* controls the lazy ``onboardingCompletedAt`` backfill below (and
    the equivalent one inside ``build_project_entry``): when False, records
    are read as-is and never rewritten. Local callers keep the default
    (True); the shared-repo route passes False so listing a clone's projects
    never dirties its git worktree (see routes_shared.py shared_projects).

    *inline_summaries* is forwarded to ``build_project_entry`` (as
    ``compute_on_miss``): the shared-repo route has no warm-up engine to fill
    a missing project-card summary, so it passes True to keep computing one
    inline on a miss. Local callers keep the default (False) -- a miss is
    reported pending and left for the warm-up engine.
    """
    dir_names = collect_candidate_dirs(reports_root, max_projects_listed())
    known, info_by_name = _classify_known_ids(reports_root, dir_names, backfill=backfill)
    projects = build_project_entries_threaded(
        reports_root, dir_names, known,
        ListingOptions(backfill=backfill, inline_summaries=inline_summaries), info_by_name,
    )
    projects.sort(key=lambda p: p.name)
    return auto_detect_parents(projects)


def _contained_project_dir(reports_root: Path, project: str) -> Path | None:
    """``reports_root / project`` resolved, or None when it escapes *reports_root*."""
    project_dir = (reports_root / project).resolve()
    return project_dir if is_within(project_dir, reports_root) else None


def update_project_path(reports_dir: str, project: str, new_path: str) -> bool:
    """Update the path stored in a project's metadata."""
    reports_root = Path(reports_dir).resolve()
    project_dir = _contained_project_dir(reports_root, project)
    if project_dir is None:
        return False
    if not repository_info_exists(project_dir):
        return False
    try:
        is_url = is_repo_url(new_path)
    except ValueError:
        return False

    if is_url:
        if not is_valid_repo_url(new_path):
            return False
        resolved_path = new_path
        location = ProjectLocation.ONLINE
    else:
        # Reject path-traversal attempts in the raw input before resolving.
        if ".." in Path(new_path).parts:
            return False
        resolved = Path(new_path).resolve()
        if not resolved.is_absolute() or not resolved.is_dir():
            return False
        resolved_path = str(resolved)
        location = ProjectLocation.LOCAL

    info = read_repository_info(project_dir)
    if info is None:
        return False
    info["path"] = resolved_path
    info["location"] = location
    if not write_repository_info(project_dir, info):
        return False
    # ``path`` is part of find_existing_project's index key, so the old key
    # would keep pointing here and make a fresh repo registered at the
    # now-freed path look like a duplicate. Key the new entry on the BARE
    # name derived from the path -- the identity find_existing_project
    # actually computes -- never on the record's own ``name``, which for a
    # scoped project is the compound "<name>/<scope>" and would install a key
    # no lookup can ever reach. URL and scoped hits are trusted unverified
    # once found, so a wrongly-keyed rekey is exactly as damaging as the
    # staleness it replaces.
    rekey_repo_index_entry(
        reports_root, project_dir.name,
        RepoIdentity(project_name_from_repo(resolved_path), resolved_path, info.get("scopePath")),
    )
    return True


def delete_project(reports_dir: str, project: str) -> bool:
    """Remove a project directory and all its report data.

    If the project is a parent, cascade-deletes all children.
    """
    reports_root = Path(reports_dir).resolve()
    project_path = _contained_project_dir(reports_root, project)
    if project_path is None:
        return False
    if not project_path.exists() or not project_path.is_dir():
        return False
    # Cascade: find and delete children first
    children_removed = True
    removed_ids: set[str] = set()
    for child_id in find_children(reports_root, project):
        child_path = reports_root / child_id
        if remove_project_dir(child_path):
            removed_ids.add(child_id)
        else:
            _logger.warning("Could not remove child project directory %s", child_path)
            children_removed = False

    # Keep find_existing_project's duplicate-check index in sync: a stale
    # entry pointing at a deleted uuid would let it wrongly report a
    # "duplicate" for a repo identity that's actually free again. Purge
    # whatever was actually removed regardless of the parent's own removal
    # outcome below -- a child gone from disk must not leave a dangling
    # index entry just because the parent dir removal then fails.
    if not remove_project_dir(project_path):
        remove_repo_index_entries(reports_root, removed_ids)
        return False

    removed_ids.add(project)
    remove_repo_index_entries(reports_root, removed_ids)
    return children_removed


def get_project_info(
    reports_dir: str, project: str,
    *,
    list_dimensions: Callable[..., tuple[str, ...]] = list_available_dimensions_for_discipline,
    has_fingerprints: Callable[[Path, str], bool] = project_has_fingerprints,
) -> dict[str, Any] | None:
    """Return project metadata including discipline and available dimensions.

    *list_dimensions* and *has_fingerprints* are injection seams for tests,
    defaulting to the production collaborators of the same name
    (``list_available_dimensions_for_discipline``, ``project_has_fingerprints``).
    """
    project_dir = _contained_project_dir(Path(reports_dir), project)
    if project_dir is None:
        return None
    info = read_repository_info(project_dir)
    if info is None:
        return None
    discipline = info.get("discipline") or infer_discipline(Path(reports_dir), project)
    available_dimensions = (
        list_dimensions(log=SHARED_LOG) if discipline else []
    )
    fingerprints_found = has_fingerprints(Path(reports_dir), project)
    path_missing = online_path_missing(info)
    annotate_working_copy(info)
    return {
        **info,
        "discipline": discipline,
        "availableDimensions": available_dimensions,
        "hasFingerprints": fingerprints_found,
        "pathMissing": path_missing,
    }
