"""Compute per-dim file count estimates before any dim runs.

The dashboard uses these to render an accurate run total upfront, instead
of waiting for each dim to start and reveal its post-filter queue size
one at a time. The estimate matches what the queue will hold once the
dim actually runs, so the header total stays stable as dims transition
from pending → running.

Each estimate carries a short *reason* tag so the UI can flag inflated
counts that aren't really "this much code" but the cache being cold:

  - "full"        — non-incremental (clean-scan); estimate = full source list
  - "diff"        — diff filter active; estimate = filter intersection
  - "incremental" — incremental run; estimate = cache-miss count
  - "first-run"   — cold cache for this dim; everything is a miss

Each estimate also carries ``total`` (all source files for the dim) and
``cached`` (files already analyzed in previous runs) so the dashboard can
render total project coverage, not just this run's queue. Non-incremental
modes set ``total = count`` and ``cached = 0``.

The on-disk format, IO, and normalisation live in
``quodeq.shared.dim_estimates_io`` (re-exported below), since the reader is
also used by ``quodeq.services.scan_progress``, which may not import
analysis.
"""
from __future__ import annotations

from typing import Any

from quodeq.analysis._types import RunConfig
from quodeq.analysis.cache import LocalFileBackend, classify_files_via_cache
from quodeq.analysis.dispatch_policy import api_file_size_cap
from quodeq.analysis.subagents._source_files import _list_source_files
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.shared.dim_estimates_io import (
    DIM_ESTIMATES_FILENAME,
    read_dim_estimates,
    write_dim_estimates,
)

__all__ = [
    "DIM_ESTIMATES_FILENAME",
    "compute_dim_estimates",
    "read_dim_estimates",
    "write_dim_estimates",
]


def _log_excluded_once(log: LogSink, n_excluded: int, excluded_logged: bool) -> bool:
    """Log the file-size-cap exclusion count once per run; return the updated flag.

    The excluded set is dim-agnostic (size cap only), so it's logged once
    per run, not once per dimension.
    """
    if n_excluded and not excluded_logged:
        log.info(
            f"  {n_excluded} file(s) excluded from analysis: over the API "
            f"file-size cap ({api_file_size_cap()} bytes). Raise "
            f"QUODEQ_MAX_API_FILE_SIZE to include them."
        )
        return True
    return excluded_logged


def _estimate_incremental(
    config: RunConfig, dim_id: str, files: list[str],
    cache: LocalFileBackend, n_excluded: int,
) -> dict[str, Any]:
    """Estimate one dim's count/reason for an incremental (cache-aware) run."""
    classify = classify_files_via_cache(config, dim_id, files, cache)
    miss_count = len(classify.misses)
    if miss_count == len(files):
        # Every file is a miss → cache cold for this dim.
        reason = "first-run"
    else:
        reason = "incremental"
    return {
        "count": miss_count, "reason": reason,
        "total": len(files), "cached": len(files) - miss_count,
        "excluded": n_excluded,
    }


def _estimate_non_incremental(
    files: list[str], file_filter: Any, n_excluded: int,
) -> dict[str, Any]:
    """Estimate one dim's count/reason for a non-incremental (diff/full) run."""
    if file_filter is not None:
        count = sum(1 for f in files if f in file_filter)
        return {
            "count": count, "reason": "diff", "total": count, "cached": 0,
            "excluded": n_excluded,
        }
    return {
        "count": len(files), "reason": "full", "total": len(files), "cached": 0,
        "excluded": n_excluded,
    }


def compute_dim_estimates(
    config: RunConfig, dimensions: list[str], *, log: LogSink = NULL_LOG,
) -> dict[str, dict[str, Any]]:
    """Estimate per-dim file count + reason, before any dim runs.

    Returns ``{dim_id: {"count": int, "reason": str, "total": int, "cached": int}}``.
    ``count`` is the number of cache misses per dimension — exactly what V2
    will dispatch on this run. ``total`` and ``cached`` describe overall
    project coverage (see module docstring).
    """
    estimates: dict[str, dict[str, Any]] = {}
    file_filter = config.options.incremental_file_filter
    cache = LocalFileBackend()
    excluded_logged = False
    for dim_id in dimensions:
        files, _ext, excluded = _list_source_files(config, dim_id, ignore_file_filter=True)
        n_excluded = len(excluded)
        excluded_logged = _log_excluded_once(log, n_excluded, excluded_logged)
        if not files:
            estimates[dim_id] = {
                "count": 0, "reason": "empty", "total": 0, "cached": 0,
                "excluded": n_excluded,
            }
            continue
        if config.options.incremental:
            estimates[dim_id] = _estimate_incremental(config, dim_id, files, cache, n_excluded)
        else:
            estimates[dim_id] = _estimate_non_incremental(files, file_filter, n_excluded)
    return estimates
