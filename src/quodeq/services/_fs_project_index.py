"""Lightweight project index + windowed hydration, for pagination.

Split out (Task 5, quality-cycle2) so a paginated request can slice the
project set *before* the expensive per-project hydration
(``_build_project_entry``) runs, instead of after.

``build_project_index`` is a cheap whole-set pass -- id/path/location/parent
only, read from each candidate's ``repository_info.json`` -- no run-dir
scan, no summary/language-stat reads, no backfill write. It is what
parent/child auto-detection (``_auto_detect_parents``, which only needs
``.path``/``.location``/``.id``/``.parent``) and pagination windowing run
against.

``build_project_entries`` then fully hydrates exactly the ids a caller
needs (typically one page), reusing the same threaded builder
``_fs_projects.build_project_list`` uses for its own (unpaginated,
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
from quodeq.services._fs_metadata import _extract_project_metadata
from quodeq.services._fs_project_helpers import (
    _auto_detect_parents,
    _backfill_onboarding_field,
    _max_projects_listed,
)
from quodeq.services._fs_projects import (
    _build_parent_child_sets,
    _build_project_entries_threaded,
    _collect_candidate_dirs,
)
from quodeq.services._wiring import read_repository_info, repository_info_exists


def _build_lightweight_entry(entry_name: str, info: dict) -> ProjectEntry:
    """A sparse ``ProjectEntry`` carrying only what parent-detection needs."""
    meta = _extract_project_metadata(info, entry_name)
    return ProjectEntry(
        id=entry_name, name=meta["name"], parent=meta["parent"],
        display_name=meta["displayName"], discipline=meta["discipline"],
        path=meta["path"], location=meta["location"], scope_path=meta.get("scopePath"),
    )


def _collect_lightweight_entries(reports_root: Path, dir_names: list[str]) -> list[ProjectEntry]:
    parent_ids, subproject_ids = _build_parent_child_sets(reports_root, dir_names)
    registered_ids = {n for n in dir_names if repository_info_exists(reports_root / n)}
    included = [n for n in dir_names if n in registered_ids or n in parent_ids or n in subproject_ids]
    return [
        _build_lightweight_entry(name, read_repository_info(reports_root / name) or {})
        for name in included
    ]


def build_project_index(reports_root: Path) -> list[ProjectEntry]:
    """Cheap whole-set pass: id/path/location/parent only.

    ``build_project_entries`` does the expensive hydration afterwards, only
    for the ids a caller actually needs.
    """
    dir_names = _collect_candidate_dirs(reports_root, _max_projects_listed())
    entries = _collect_lightweight_entries(reports_root, dir_names)
    entries.sort(key=lambda p: p.name)
    return _auto_detect_parents(entries)


def build_project_entries(
    reports_root: Path, ids: list[str], *, backfill: bool = True, inline_summaries: bool = False,
) -> list[ProjectEntry]:
    """Fully hydrate ``ProjectEntry`` objects for exactly *ids*.

    *ids* must already be vetted by ``build_project_index`` (registered, a
    parent, or a subproject) -- every id here is therefore known-included,
    so the zero-run stray-dir filter in ``_build_project_entries_threaded``
    is bypassed by treating the whole window as pre-registered.
    """
    if backfill:
        for name in ids:
            _backfill_onboarding_field(reports_root / name)
    return _build_project_entries_threaded(
        reports_root, ids, set(ids), set(), set(),
        backfill=backfill, inline_summaries=inline_summaries,
    )
