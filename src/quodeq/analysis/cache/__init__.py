"""Content-addressed cache for analysis results.

A successful (file, dimension) analysis is keyed by the SHA-256 of its real
per-unit inputs (file content, path, dimension, language) and stored as one
atomic, self-describing JSON entry. The next run computes the same key and
either serves the recorded result or dispatches the work and writes the new
entry.

The key is permissive (cost-first): volatile inputs (model, prompts,
standards, sampling) are NOT keyed — switching them reuses prior work. Each
entry records those in its ``provenance`` block, so reuse across a model /
prompts / standards boundary is surfaced, not silent; the user refreshes on
demand with ``--clean-scan``.

This is the canonical incremental layer. Half-computed work never gets a
key, so there is no partial state to recover from.
"""
from __future__ import annotations

from quodeq.analysis.cache.backend import CacheBackend, CacheStats
from quodeq.analysis.cache.dimension_helpers import (
    ClassifyResult,
    build_cache_key_for_file,
    classify_files_via_cache,
    format_provenance_drift,
    persist_dispatch_results,
)
from quodeq.analysis.cache.entry import CacheEntry
from quodeq.analysis.cache.gc import (
    collect_legacy_entries,
    maybe_collect_legacy_entries,
)
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
    "ClassifyResult",
    "DispatchResult",
    "Dispatcher",
    "LocalFileBackend",
    "TieredCache",
    "UnitResult",
    "WorkUnit",
    "analyze_unit",
    "build_cache_key_for_file",
    "classify_files_via_cache",
    "collect_legacy_entries",
    "compute_key",
    "default_cache_root",
    "format_provenance_drift",
    "maybe_collect_legacy_entries",
    "persist_dispatch_results",
]
