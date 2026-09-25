"""The "stay cold while a summary is pending" rule, on both cache tiers.

The full-payload tier is pinned in test_projects_cache_entities.py; this file
pins the paginated (hydrated) tier, which shares one stamp rule with it.
"""
from __future__ import annotations

from unittest.mock import patch

from quodeq.core.types import ProjectEntry
from quodeq.services.filesystem import ProjectsCache

_INDEX_TARGET = "quodeq.services._projects_cache._fs_project_index.build_project_index"
_ENTRIES_TARGET = "quodeq.services._projects_cache._fs_project_index.build_project_entries"


def _page_twice(pending: bool) -> int:
    """Request the same page twice; return how many times hydration rebuilt it."""
    index = [ProjectEntry(id="p1", name="p1")]
    hydrated = [ProjectEntry(id="p1", name="p1", summary_pending=pending)]
    with patch(_INDEX_TARGET, return_value=index), patch(
        _ENTRIES_TARGET, return_value=hydrated,
    ) as build:
        cache = ProjectsCache()
        cache.list("/reports", offset=0, limit=10)
        cache.list("/reports", offset=0, limit=10)
    return build.call_count


def test_pending_hydrated_entries_keep_the_page_cold():
    assert _page_twice(pending=True) == 2


def test_settled_hydrated_entries_are_served_from_the_cache():
    assert _page_twice(pending=False) == 1
