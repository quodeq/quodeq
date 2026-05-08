"""Content-addressed cache for analysis results.

A successful (file, dimension) analysis is keyed by the SHA-256 of its
inputs (file content, standards, prompts, model, ...) and stored as one
atomic JSON entry. The next run computes the same key and either serves
the recorded result or dispatches the work and writes the new entry.

This replaces the implicit-state model of fingerprint+JSONL+queue with
an explicit cache lookup. Half-computed work never gets a key, so there
is no partial state to recover from.

The module is loaded eagerly but the cache itself is only consulted when
``QUODEQ_CACHE_V2`` is set; see ``flags`` for the wiring guard.
"""
from __future__ import annotations

from quodeq.analysis.cache.backend import CacheBackend, CacheStats
from quodeq.analysis.cache.entry import CacheEntry
from quodeq.analysis.cache.flags import is_cache_v2_enabled, is_result_cache_disabled
from quodeq.analysis.cache.key import CacheKey, compute_key
from quodeq.analysis.cache.local import LocalFileBackend, default_cache_root
from quodeq.analysis.cache.runner import (
    Dispatcher,
    DispatchResult,
    UnitResult,
    WorkUnit,
    analyze_unit,
)
from quodeq.analysis.cache.tiered import TieredCache

__all__ = [
    "CacheBackend",
    "CacheEntry",
    "CacheKey",
    "CacheStats",
    "DispatchResult",
    "Dispatcher",
    "LocalFileBackend",
    "TieredCache",
    "UnitResult",
    "WorkUnit",
    "analyze_unit",
    "compute_key",
    "default_cache_root",
    "is_cache_v2_enabled",
    "is_result_cache_disabled",
]
