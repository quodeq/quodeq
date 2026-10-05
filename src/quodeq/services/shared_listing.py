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

import threading
from pathlib import Path
from typing import Any, Callable

from quodeq.core.types import ProjectEntry
from quodeq.core.types.project_source import ProjectSource
from quodeq.services import fs_projects
from quodeq.services.score_cache import score_cache_path_override
from quodeq.services.shared_repo import last_synced_at, published_meta, shared_score_cache_path
from quodeq.services.warmup import WarmupEngine, warm_project


def _warm_under_clone_cache(url: str) -> Callable[[str, str], None]:
    """The engine's warm step for *url*'s clone: ``warm_project`` with the
    score cache scoped to the clone's own DB. The worker thread never inherits
    a route's contextvar override, so the step scopes its own; without it the
    warm-up would fill the LOCAL cache (a miss for the route, and shared rows
    mixed into local ones)."""
    def warm(reports_dir: str, project_id: str) -> None:
        with score_cache_path_override(shared_score_cache_path(url)):
            warm_project(reports_dir, project_id)
    return warm


class SharedWarmup:
    """The warm-up engine over the connected clone's projects.

    The shared listing has no boot-time enumeration: the listing itself
    queues every card it reports pending, and the worker fills the clone's
    score cache so the next listing answers from it. One engine per clone
    url: binding another url stops the previous worker and starts a fresh
    queue over the new clone, so a reconnect never warms the old clone's
    projects into the new cache.
    """

    def __init__(self) -> None:
        self._engine: WarmupEngine | None = None
        self._url: str | None = None
        self._lock = threading.Lock()

    def bind(self, eval_root: Path, url: str) -> None:
        """Make sure an engine over *eval_root* is running for *url*."""
        with self._lock:
            if self._engine is not None and self._url == url:
                return
            if self._engine is not None:
                self._engine.stop()
            self._engine = WarmupEngine(warm_fn=_warm_under_clone_cache(url), list_fn=lambda _root: [])
            self._url = url
            self._engine.start(str(eval_root))

    def enqueue_pending(self, entries: list) -> None:
        """Queue every entry still reported ``summary_pending`` (no-op before ``bind``)."""
        with self._lock:
            engine = self._engine
        if engine is not None:
            engine.enqueue_pending(entries)

    def snapshot(self) -> dict | None:
        """Warm-up progress for the listing payload, or None before ``bind``."""
        with self._lock:
            engine = self._engine
        return engine.snapshot() if engine is not None else None

    def reset_for_tests(self) -> None:
        """Stop the worker and forget the bound clone (test seam)."""
        with self._lock:
            engine, self._engine, self._url = self._engine, None, None
        if engine is not None:
            engine.stop()


shared_warmup = SharedWarmup()


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


def _hydrate(eval_root: Path, url: str) -> tuple[list[ProjectEntry], dict[str, dict]]:
    """The listing's expensive half: every project entry, plus publish attribution.

    backfill=False: the shared clone is a git worktree, not a local
    evaluations dir -- writing onboardingCompletedAt into
    repository_info.json here would dirty it, and a dirty worktree can make
    publish's `pull --rebase` refuse (confusing wedge) the next time someone
    publishes into this clone.

    A missing project-card summary is reported pending and queued on
    ``shared_warmup``, never computed inline here: on a fresh clone or after
    an upgrade that would mean every project's summary inside one request,
    which outlasted the UI's timeout and hid every card until the last one
    was scored. The cards land one by one as the worker fills the clone's
    score cache and the UI re-lists while any is pending.
    """
    projects = fs_projects.build_project_list(eval_root, backfill=False, inline_summaries=False)
    shared_warmup.bind(eval_root, url)
    shared_warmup.enqueue_pending(projects)
    return projects, published_meta(url)


def warm_shared_listing(eval_root: Path, url: str) -> int:
    """List the clone once so its cold cards are queued for the warm-up; returns the project count.

    The connect and refresh jobs call this before reporting DONE. The listing
    is a read (the summaries are only queued), so DONE arrives as soon as the
    clone is read and the cards fill in afterwards.

    The cache hit/miss check and the queued warm-ups go to the clone's own
    score cache, the DB the list route reads under ``with_shared_root``. A
    job thread does not inherit the route's contextvar override, so this
    scopes its own.
    """
    if not eval_root.is_dir():
        return 0
    with score_cache_path_override(shared_score_cache_path(url)):
        projects, _meta = _hydrate(eval_root, url)
    return len(projects)


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
    projects, meta = _hydrate(eval_root, url)
    listing = {"projects": [serialize(p) for p in projects]}
    for project in listing["projects"]:
        key = project.get("id") or project.get("name")
        _merge_published_meta(project, key, meta)
    listing["lastSynced"] = last_synced_at(url)
    if stale is not None:
        listing["stale"] = stale
    snapshot = shared_warmup.snapshot()
    if snapshot is not None:
        listing["warmup"] = snapshot
    return listing
