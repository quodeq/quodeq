"""Result-cache filesystem store — the on-disk V2 content-addressed cache adapter.

Sub-modules:
  key      -- CacheKey + compute_key + SCHEMA_VERSION: the key formula
  entry    -- CacheEntry: the persisted record for one cache key
  backend  -- CacheBackend protocol + CacheStats
  local    -- LocalFileBackend: sharded filesystem implementation
  index    -- ContentIndex: sqlite sidecar mapping content hashes to keys
  migrate  -- one-time schema migration, index build and legacy GC

``quodeq.analysis.cache.{key,entry,backend,local,gc}`` re-export this
package's public names as shims, so every pre-existing import path stays
live. The analysis-internal cache machinery (per-run key building, classify,
adoption, dispatch, tiered policy) stays in ``quodeq.analysis.cache``.
"""
from __future__ import annotations
