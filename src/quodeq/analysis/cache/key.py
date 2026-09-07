"""Shim: cache key moved to ``data/cache_store``.

The key formula is needed by the data-layer schema migration, so it lives at
``quodeq.data.cache_store.key``. This module re-exports the public names so
every pre-existing ``quodeq.analysis.cache.key`` import path keeps working.
"""
from __future__ import annotations

from quodeq.data.cache_store.key import SCHEMA_VERSION, CacheKey, compute_key  # noqa: F401
