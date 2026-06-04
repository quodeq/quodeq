"""TTL-bounded cache for the project list.

The project list is read from disk on every dashboard refresh; caching it
for a few seconds collapses bursts of identical requests without making
edits feel stale.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from quodeq.core.types import to_camel_dict
from quodeq.services import _fs_projects

_DEFAULT_TTL_S = 5


class ProjectsCache:
    """In-memory, time-bounded cache around ``_fs_projects.build_project_list``.

    Returns the cached payload when called within *ttl_s* of the last
    successful read; refreshes from disk otherwise.
    """

    def __init__(self, ttl_s: int = _DEFAULT_TTL_S) -> None:
        self._ttl_s = ttl_s
        self._payload: dict[str, Any] | None = None
        self._stamp: float = 0.0

    def list(self, reports_dir: str) -> dict[str, Any]:
        if self._is_fresh():
            return self._payload  # type: ignore[return-value]
        projects = _fs_projects.build_project_list(Path(reports_dir))
        self._payload = {"projects": [to_camel_dict(p) for p in projects]}
        self._stamp = time.monotonic()
        return self._payload

    def invalidate(self) -> None:
        """Drop the cached payload; next ``list`` call re-reads from disk."""
        self._payload = None
        self._stamp = 0.0

    def _is_fresh(self) -> bool:
        return self._payload is not None and (time.monotonic() - self._stamp) < self._ttl_s
