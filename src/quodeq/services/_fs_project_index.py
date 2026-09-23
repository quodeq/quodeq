"""Lightweight project index + windowed hydration, for pagination.

Split out so a paginated request can slice the
project set *before* the expensive per-project hydration
(``build_project_entry``) runs, instead of after.

``build_project_index`` is a cheap whole-set pass -- id/path/location/parent
only, read from each candidate's ``repository_info.json`` -- no run-dir
scan, no summary/language-stat reads, no backfill write. It is what
parent/child auto-detection (``auto_detect_parents``, which only needs
``.path``/``.location``/``.id``/``.parent``) and pagination windowing run
against.

``build_project_entries`` then fully hydrates exactly the ids a caller
needs (typically one page), reusing the same threaded builder
``fs_projects.build_project_list`` uses for its own (unpaginated,
untouched) full-list callers.

One known trade-off vs. ``build_project_list``: a directory with run data
but no ``repository_info.json`` and not referenced as anyone's parent (a
corrupted/partial state, not a normal registration flow) is included by the
full/unpaginated listing (which scans every dir's runs) but not by this
index (which never scans runs). Unpaginated callers are unaffected -- they
still go through ``build_project_list`` directly.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.types import ProjectEntry
from quodeq.services._fs_metadata import extract_project_metadata
from quodeq.services.fs_project_helpers import (
    KnownProjectIds,
    ListingOptions,
    auto_detect_parents,
    backfill_onboarding_field,
    max_projects_listed,
    project_entry_identity,
)
from quodeq.services.fs_projects import (
    build_parent_child_sets,
    build_project_entries_threaded,
    collect_candidate_dirs,
)
from quodeq.services.wiring import repository_info_exists


def _build_lightweight_entry(entry_name: str, info: dict) -> ProjectEntry:
    """A sparse ``ProjectEntry`` carrying only what parent-detection needs."""
    meta = extract_project_metadata(info, entry_name)
    return ProjectEntry(**project_entry_identity(entry_name, meta))


def _collect_lightweight_entries(reports_root: Path, dir_names: list[str]) -> list[ProjectEntry]:
    parent_ids, subproject_ids, info_by_name = build_parent_child_sets(reports_root, dir_names)
    # info_by_name already holds every parseable record, so only the dirs it
    # lacks need the presence probe: a corrupt repository_info.json still
    # marks a registered project (see repository_info_exists) and is listed
    # with fallback metadata, as before.
    included = [
        n for n in dir_names
        if n in info_by_name or n in parent_ids or n in subproject_ids
        or repository_info_exists(reports_root / n)
    ]
    return [_build_lightweight_entry(name, info_by_name.get(name) or {}) for name in included]


def build_project_index(reports_root: Path) -> list[ProjectEntry]:
    """Cheap whole-set pass: id/path/location/parent only.

    ``build_project_entries`` does the expensive hydration afterwards, only
    for the ids a caller actually needs.
    """
    dir_names = collect_candidate_dirs(reports_root, max_projects_listed())
    entries = _collect_lightweight_entries(reports_root, dir_names)
    entries.sort(key=lambda p: p.name)
    return auto_detect_parents(entries)


def build_project_entries(
    reports_root: Path, ids: list[str], *, backfill: bool = True, inline_summaries: bool = False,
) -> list[ProjectEntry]:
    """Fully hydrate ``ProjectEntry`` objects for exactly *ids*.

    *ids* must already be vetted by ``build_project_index`` (registered, a
    parent, or a subproject) -- every id here is therefore known-included,
    so the zero-run stray-dir filter in ``build_project_entries_threaded``
    is bypassed by treating the whole window as pre-registered.
    """
    if backfill:
        for name in ids:
            backfill_onboarding_field(reports_root / name)
    return build_project_entries_threaded(
        reports_root, ids, KnownProjectIds(registered=set(ids)),
        ListingOptions(backfill=backfill, inline_summaries=inline_summaries),
    )
