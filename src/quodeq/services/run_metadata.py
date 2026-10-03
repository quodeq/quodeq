"""Per-run facts the dashboard shows next to the numbers: commit and cache statistics.

Coverage (files read, source count, percentage) already travels on each
dimension entry of the dashboard payload, so this reads only the two small
files the reports do not cover: status.json and dim_estimates.json.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.services.wiring import read_status
from quodeq.shared.dim_estimates_io import read_dim_estimates

_KEY_COMMIT_SHA = "commit_sha"
_ESTIMATE_MISSES = "count"
_ESTIMATE_CACHED = "cached"
_ESTIMATE_EXCLUDED = "excluded"


def read_run_metadata(run_dir: Path) -> dict[str, Any]:
    """Commit SHA from status.json and per-dimension cache hits / misses /
    provider-excluded counts from dim_estimates.json. Missing inputs yield
    None / empty, never an error."""
    status = read_status(run_dir) or {}
    cache_stats = {
        dim: {
            "cached": estimate.get(_ESTIMATE_CACHED),
            "misses": estimate.get(_ESTIMATE_MISSES),
            "excluded": estimate.get(_ESTIMATE_EXCLUDED),
        }
        for dim, estimate in read_dim_estimates(run_dir).items()
    }
    return {"commitSha": status.get(_KEY_COMMIT_SHA), "cacheStats": cache_stats}
