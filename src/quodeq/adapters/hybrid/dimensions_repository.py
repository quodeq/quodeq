"""Hybrid repository that tries the web adapter first, falling back to filesystem."""

from __future__ import annotations

from typing import Any

from quodeq.adapters.hybrid._hybrid_call import hybrid_call
from quodeq.ports.dimensions import DimensionsRepository


class HybridDimensionsRepository:
    """Dimension repository that delegates to web then falls back to filesystem."""

    def __init__(self, web: DimensionsRepository, fs: DimensionsRepository) -> None:
        self._web = web
        self._fs = fs

    def list_dimensions(self) -> list[str]:
        """Return all dimension names, preferring the web source.

        Example::

            repo = HybridDimensionsRepository(web=web_repo, fs=fs_repo)
            names = repo.list_dimensions()
        """
        return hybrid_call(self._web.list_dimensions, self._fs.list_dimensions)

    def get_dimension(self, name: str) -> dict[str, Any]:
        """Fetch a single dimension definition, preferring the web source.

        Example::

            dim = repo.get_dimension("security")
        """
        return hybrid_call(self._web.get_dimension, self._fs.get_dimension, name)
