"""The "rebuild once warm-up moves while a summary is pending" rule, on both tiers.

The settled full-payload case is pinned in test_projects_cache_entities.py.
"""
from __future__ import annotations

from unittest.mock import patch

from quodeq.core.types import ProjectEntry
from quodeq.services.filesystem import ProjectsCache

_INDEX_TARGET = "quodeq.services._projects_cache._fs_project_index.build_project_index"
_ENTRIES_TARGET = "quodeq.services._projects_cache._fs_project_index.build_project_entries"
_GENERATION_TARGET = "quodeq.services._projects_cache.warmup_engine.generation"


def _page_twice(pending: bool, *, warmed_between: bool = False) -> int:
    """Request the same page twice; return how many times hydration rebuilt it."""
    index = [ProjectEntry(id="p1", name="p1")]
    hydrated = [ProjectEntry(id="p1", name="p1", summary_pending=pending)]
    with patch(_INDEX_TARGET, return_value=index), patch(
        _ENTRIES_TARGET, return_value=hydrated,
    ) as build, patch(_GENERATION_TARGET, side_effect=_generations(warmed_between)):
        cache = ProjectsCache()
        cache.list("/reports", offset=0, limit=10)
        cache.list("/reports", offset=0, limit=10)
    return build.call_count


def _generations(warmed_between: bool):
    """Warm-up generation per call: it moves after the first build when *warmed_between*."""
    first = [0]
    rest = 1 if warmed_between else 0
    return lambda: first.pop() if first else rest


def test_pending_hydrated_entries_are_reused_until_warmup_moves():
    assert _page_twice(pending=True) == 1


def test_pending_hydrated_entries_rebuild_once_a_project_warms():
    assert _page_twice(pending=True, warmed_between=True) == 2


def test_settled_hydrated_entries_are_served_from_the_cache():
    assert _page_twice(pending=False) == 1


def _warms_after(calls: int):
    """A warm-up generation that reads 0 for *calls* reads, then 1."""
    seen = [0]

    def generation() -> int:
        seen[0] += 1
        return 0 if seen[0] <= calls else 1
    return generation


def test_pending_summaries_rebuild_once_warmup_finishes_a_project(tmp_path):
    """While any entry is summary-pending the list is rebuilt as soon as the
    warm-up engine finishes a project, so the UI's poll sees each filled grade."""
    pending = ProjectEntry(id="p1", name="proj", runs_count=2, latest_run_id="r2", summary_pending=True)
    with patch(
        "quodeq.services._projects_cache.fs_projects.build_project_list",
        return_value=[pending],
    ) as spy, patch(
        _GENERATION_TARGET, side_effect=_warms_after(2),
    ):
        cache = ProjectsCache()
        cache.list(str(tmp_path))
        cache.list(str(tmp_path))
        cache.list(str(tmp_path))
    assert spy.call_count == 2, "a pending list is reused until warm-up moves"
