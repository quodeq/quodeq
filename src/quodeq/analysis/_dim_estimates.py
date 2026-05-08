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
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quodeq.analysis._types import RunConfig
from quodeq.analysis.cache import LocalFileBackend, classify_files_via_cache
from quodeq.analysis.subagents._source_files import _list_source_files

DIM_ESTIMATES_FILENAME = "dim_estimates.json"


def compute_dim_estimates(
    config: RunConfig, dimensions: list[str],
) -> dict[str, dict[str, Any]]:
    """Estimate per-dim file count + reason, before any dim runs.

    Returns ``{dim_id: {"count": int, "reason": str}}``. The estimate is
    the number of cache misses per dimension — exactly what V2 will
    dispatch on this run.
    """
    estimates: dict[str, dict[str, Any]] = {}
    file_filter = config.options.incremental_file_filter
    cache = LocalFileBackend()
    for dim_id in dimensions:
        files, _ext = _list_source_files(config, dim_id, ignore_file_filter=True)
        if not files:
            estimates[dim_id] = {"count": 0, "reason": "empty"}
            continue
        if config.options.incremental:
            classify = classify_files_via_cache(config, dim_id, files, cache)
            miss_count = len(classify.misses)
            if miss_count == len(files):
                # Every file is a miss → cache cold for this dim.
                reason = "first-run"
            else:
                reason = "incremental"
            estimates[dim_id] = {"count": miss_count, "reason": reason}
        elif file_filter is not None:
            count = sum(1 for f in files if f in file_filter)
            estimates[dim_id] = {"count": count, "reason": "diff"}
        else:
            estimates[dim_id] = {"count": len(files), "reason": "full"}
    return estimates


def write_dim_estimates(
    run_dir: Path, estimates: dict[str, dict[str, Any]],
) -> None:
    """Persist per-dim estimates next to status.json. Best-effort."""
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / DIM_ESTIMATES_FILENAME).write_text(
            json.dumps(estimates, indent=2), encoding="utf-8",
        )
    except OSError:
        pass


def read_dim_estimates(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Return per-dim estimates from disk, or {} if missing/corrupt.

    Each value is normalised to ``{"count": int, "reason": str}``.
    """
    path = run_dir / DIM_ESTIMATES_FILENAME
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in data.items():
        # Current format: {"count": int, "reason": str}.
        if isinstance(v, dict) and isinstance(v.get("count"), int):
            out[k] = {"count": v["count"], "reason": str(v.get("reason", ""))}
        # Legacy format: a bare int. Older runs predate the reason tag.
        elif isinstance(v, int):
            out[k] = {"count": v, "reason": ""}
    return out
