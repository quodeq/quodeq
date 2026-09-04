"""TTL-bounded cache for the project list.

The project list is read from disk on every dashboard refresh; caching it
for a few seconds collapses bursts of identical requests without making
edits feel stale. The cache holds ``ProjectEntry`` entities — serialization
to the camelCase wire shape happens at the route.

Two independent tiers:
  * The full/unpaginated payload (``list()`` with no offset/limit) keeps its
    original single-flight, whole-list caching, unchanged, and used by every
    non-paginated caller (``active_evaluation``, the shared-repo route,
    direct provider callers).
  * A paginated request (offset and/or limit given) instead caches a cheap
    whole-set *index* (id/path/location/parent only) plus a lazily-built,
    per-project *hydrated* cache — only the ids in the requested window get
    the full, expensive ``build_project_entries`` treatment.
"""
from __future__ import annotations

import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from quodeq.core.types import ProjectEntry
from quodeq.services import _fs_project_index, _fs_projects

_DEFAULT_TTL_S = 5


class ProjectsCache:
    """In-memory, time-bounded cache around the project-list build path.

    Returns cached data when called within *ttl_s* of the last successful
    build; rebuilds from disk otherwise. See the module docstring for the
    two tiers (full payload vs. index + lazily-hydrated window).
    """

    def __init__(self, ttl_s: int = _DEFAULT_TTL_S) -> None:
        self._ttl_s = ttl_s
        self._payload: dict[str, Any] | None = None
        self._stamp: float = 0.0
        self._lock = threading.Lock()
        self._index: list[ProjectEntry] | None = None
        self._index_stamp: float = 0.0
        self._index_lock = threading.Lock()
        self._hydrated: dict[str, ProjectEntry] = {}
        self._hydrated_stamp: float = 0.0
        self._hydrate_lock = threading.Lock()

    def list(self, reports_dir: str, *, offset: int = 0, limit: int = 0) -> dict[str, Any]:
        if offset > 0 or limit > 0:
            return self._list_page(reports_dir, offset, limit)
        return self._list_all(reports_dir)

    def _list_all(self, reports_dir: str) -> dict[str, Any]:
        if self._is_fresh():
            return self._payload  # type: ignore[return-value]
        # Single-flight: requests racing a cold cache wait for the one build
        # in progress instead of each starting their own. The client retries
        # a slow startup request, and the build can take minutes right after
        # an upgrade invalidates the score caches — without this lock those
        # retries multiplied the whole recompute.
        with self._lock:
            if self._is_fresh():
                return self._payload  # type: ignore[return-value]
            projects = _fs_projects.build_project_list(Path(reports_dir))
            # Entities, not wire dicts: the route serializes per request (WS6).
            # The cached part is the expensive disk walk; camelCase mapping is
            # cheap and belongs at the boundary.
            self._payload = {"projects": projects}
            # While any summary is still pending (warm-up in flight), leave the
            # cache cold so the UI's poll sees each newly filled grade. The
            # build is a pure cache read now, so re-running it is cheap.
            if any(getattr(p, "summary_pending", False) for p in projects):
                self._stamp = 0.0
            else:
                self._stamp = time.monotonic()
            return self._payload

    def _list_page(self, reports_dir: str, offset: int, limit: int) -> dict[str, Any]:
        index = self._get_index(reports_dir)
        end = offset + limit if limit > 0 else None
        window = index[offset:end]
        return {"projects": self._hydrate(reports_dir, window)}

    def _get_index(self, reports_dir: str) -> list[ProjectEntry]:
        if self._index_fresh():
            return self._index  # type: ignore[return-value]
        with self._index_lock:
            if self._index_fresh():
                return self._index  # type: ignore[return-value]
            self._index = _fs_project_index.build_project_index(Path(reports_dir))
            self._index_stamp = time.monotonic()
            # A regenerated index may have dropped or renamed ids -- a stale
            # hydrated entry for a since-deleted project must not linger.
            # _hydrated is otherwise only ever touched under _hydrate_lock
            # (see _hydrate/_fill_hydrated/invalidate) -- take it here too so
            # a concurrent request's fill-then-read in _hydrate can never
            # observe (or clobber) a reset that landed mid-read.
            with self._hydrate_lock:
                self._hydrated = {}
            return self._index

    def _hydrate(self, reports_dir: str, window: list[ProjectEntry]) -> list[ProjectEntry]:
        with self._hydrate_lock:
            if not self._hydrated_fresh():
                self._hydrated = {}
            missing = [p.id for p in window if p.id not in self._hydrated]
            if missing:
                self._fill_hydrated(reports_dir, missing)
            # The read that builds the response must happen under the same
            # lock as the write above -- otherwise a concurrent invalidate()
            # or index refresh landing between "fill" and "read" can return a
            # truncated or empty page with no error signal (a real race under
            # Flask's default threaded=True).
            #
            # The index already ran _auto_detect_parents over the WHOLE
            # project set (a windowed re-run couldn't see out-of-window
            # sibling candidates for the path-prefix match), so its .parent
            # is authoritative. _build_project_entry, which built the cached
            # entry, only ever reads the raw, unenriched "parent" field off
            # repository_info.json -- propagate the index's value onto each
            # hydrated result rather than silently returning that raw one.
            return [
                replace(self._hydrated[p.id], parent=p.parent)
                for p in window if p.id in self._hydrated
            ]

    def _fill_hydrated(self, reports_dir: str, missing: list[str]) -> None:
        """Build and cache *missing* ids. Caller holds ``_hydrate_lock``."""
        built = _fs_project_index.build_project_entries(Path(reports_dir), missing)
        for entry in built:
            self._hydrated[entry.id] = entry
        # Same "stay cold while pending" rule as the full-payload tier: a
        # still-pending summary must not be cached past the warm-up filling it.
        if any(getattr(e, "summary_pending", False) for e in built):
            self._hydrated_stamp = 0.0
        else:
            self._hydrated_stamp = time.monotonic()

    def invalidate(self) -> None:
        """Drop all cached data; next ``list`` call re-reads from disk."""
        with self._lock:
            self._payload = None
            self._stamp = 0.0
        with self._index_lock:
            self._index = None
            self._index_stamp = 0.0
        with self._hydrate_lock:
            self._hydrated = {}
            self._hydrated_stamp = 0.0

    def _is_fresh(self) -> bool:
        return self._payload is not None and (time.monotonic() - self._stamp) < self._ttl_s

    def _index_fresh(self) -> bool:
        return self._index is not None and (time.monotonic() - self._index_stamp) < self._ttl_s

    def _hydrated_fresh(self) -> bool:
        return (time.monotonic() - self._hydrated_stamp) < self._ttl_s
