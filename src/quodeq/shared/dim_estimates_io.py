"""On-disk IO + normalisation for the per-dim estimates sidecar.

``dim_estimates.json`` sits next to ``status.json`` in a run directory and
records, per dimension, how many files this run will process and how that
compares to the dimension's full project coverage. It is written once by the
analysis pipeline before any dim runs (see
``quodeq.analysis._dim_estimates.compute_dim_estimates``) and read by the
dashboard's progress reporting in ``quodeq.services.scan_progress``. Because
both the writer (analysis) and the reader (services) need this format, and
services must not import analysis, the IO lives here in the cross-cutting
shared package.

Each value is normalised to::

    {"count": int, "reason": str, "total": int, "cached": int}

- ``count``  — cache misses this run will dispatch for the dim.
- ``reason`` — short tag explaining the estimate (see
  ``compute_dim_estimates`` for the tag vocabulary).
- ``total``  — all source files for the dim (overall project size).
- ``cached`` — files already analyzed in previous runs.

Legacy fallbacks for older/partial payloads:

- Missing ``total`` falls back to ``count``.
- Missing ``cached`` falls back to ``0``.
- A bare int value (pre-dates the reason tag) becomes
  ``{"count": v, "reason": "", "total": v, "cached": 0}``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DIM_ESTIMATES_FILENAME = "dim_estimates.json"


def write_dim_estimates(
    run_dir: Path, estimates: dict[str, dict[str, Any]],
) -> None:
    """Persist per-dim estimates next to status.json. Best-effort."""
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(estimates, indent=2)
        (run_dir / DIM_ESTIMATES_FILENAME).write_text(payload, encoding="utf-8")
    except OSError:
        pass


def read_dim_estimates(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Return per-dim estimates from disk, or {} if missing/corrupt.

    Each value is normalised to
    ``{"count": int, "reason": str, "total": int, "cached": int}``.
    """
    path = run_dir / DIM_ESTIMATES_FILENAME
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in data.items():
        # Current format: {"count": int, "reason": str, "total": int, "cached": int}.
        if isinstance(v, dict) and isinstance(v.get("count"), int):
            count = v["count"]
            out[k] = {
                "count": count,
                "reason": str(v.get("reason", "")),
                "total": v["total"] if isinstance(v.get("total"), int) else count,
                "cached": v["cached"] if isinstance(v.get("cached"), int) else 0,
            }
        # Legacy format: a bare int. Older runs predate the reason tag.
        elif isinstance(v, int):
            out[k] = {"count": v, "reason": "", "total": v, "cached": 0}
    return out
