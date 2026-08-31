"""Result-cache filesystem store — the on-disk V2 content-addressed cache adapter.

Sub-modules:
  entry    -- CacheEntry: the persisted record for one cache key
  backend  -- CacheBackend protocol + CacheStats
  local    -- LocalFileBackend: sharded filesystem implementation

``quodeq.analysis.cache.{entry,backend,local}`` re-export this package's
public names as shims, so every pre-existing import path stays live. The
analysis-internal cache machinery (key derivation, dispatch, tiered/gc
policy) stays in ``quodeq.analysis.cache`` -- only the storage record and
its filesystem backend moved here.
"""
from __future__ import annotations
