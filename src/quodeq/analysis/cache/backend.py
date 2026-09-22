"""Shim: cache backend protocol moved to ``data/cache_store``.

The V2 result-cache record and its filesystem backend are a storage
adapter, not analysis logic; they now live at ``quodeq.data.cache_store``.
This module re-exports the public names so every pre-existing
``quodeq.analysis.cache.backend`` import path keeps working.
"""
from __future__ import annotations

from quodeq.data.cache_store.backend import CacheBackend, CacheStats  # noqa: F401
