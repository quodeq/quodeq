"""Shared-clone project listing: refresh-on-read, and publish attribution.

Split out of api/routes_shared_mirrors.py's ``_shared_projects`` handler,
which used to orchestrate the clone refresh, index sync, and per-project
metadata merge itself. The route now delegates here and only handles the
HTTP concerns (query-arg parsing, jsonify).

``list_shared_projects`` takes the wire serializer as a required *serialize*
parameter rather than importing one itself: wire serialization belongs at
the HTTP boundary (see tests/tools/test_serialization_boundary.py), so the
route supplies its own serializer instead of this module reaching for it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from quodeq.core.types.project_source import ProjectSource
from quodeq.services import fs_projects
from quodeq.services.shared_repo import last_synced_at, published_meta


def _merge_published_meta(info: dict, key: str, meta: dict) -> dict:
    """Merge *meta*'s entry for *key* into *info* in place, and stamp it
    as a shared-source project. Shared by both callers below so "how a
    project gets its publishedBy/publishedAt" cannot drift between them."""
    info.update(meta.get(key, {}))
    info["source"] = ProjectSource.SHARED
    return info


def enrich_shared_info(info: dict, key: str, url: str) -> dict:
    """Merge publishedBy/publishedAt attribution into *info* for project *key*.

    Fetches ``published_meta(url)`` once for this single project. Callers
    merging many projects (see ``list_shared_projects``) should fetch
    ``published_meta`` once and loop themselves instead of calling this per
    item -- it walks the whole shared clone (and can shell out to git), so
    calling it once per project would multiply that cost by project count.
    """
    return _merge_published_meta(info, key, published_meta(url))


def list_shared_projects(
    eval_root: Path, url: str,
    *, refresh: bool, refresh_clone: Callable[[str], tuple[bool, object]],
    sync_index: Callable[[str], object], serialize: Callable[[Any], dict],
) -> dict:
    """Build the ``/api/shared/projects`` listing payload.

    ``refresh``: the UI calls this on tab entry to force the clone up to
    date before listing, rather than showing whatever was last fetched. A
    failed refresh (host unreachable) is not fatal -- fall through and serve
    the existing (now-stale) clone contents, just flag it. The index is
    only re-synced after a successful refresh; there is nothing new to
    index when the fetch itself failed.

    ``serialize`` renders one project entry to its wire dict; see the
    module docstring for why it is injected rather than imported here.
    """
    stale = None
    if refresh:
        ok, _ = refresh_clone(url)
        if ok:
            sync_index(url)
            stale = False
        else:
            stale = True
    # backfill=False: the shared clone is a git worktree, not a local
    # evaluations dir -- writing onboardingCompletedAt into
    # repository_info.json here would dirty it, and a dirty worktree can
    # make publish's `pull --rebase` refuse (confusing wedge) the next
    # time someone publishes into this clone.
    # inline_summaries=True: this route has no warm-up engine to fill a
    # missing project-card summary later, so a cache miss must compute
    # it inline here instead of reporting it pending forever.
    projects = fs_projects.build_project_list(
        eval_root, backfill=False, inline_summaries=True,
    )
    listing = {"projects": [serialize(p) for p in projects]}
    meta = published_meta(url)
    for project in listing["projects"]:
        key = project.get("id") or project.get("name")
        _merge_published_meta(project, key, meta)
    listing["lastSynced"] = last_synced_at(url)
    if stale is not None:
        listing["stale"] = stale
    return listing
