"""Per-run facts the dashboard shows next to the numbers: commit and coverage."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.services.wiring import iter_readable_eval_reports, read_status
from quodeq.shared.dim_estimates_io import read_dim_estimates

_KEY_COMMIT_SHA = "commit_sha"
_ESTIMATE_MISSES = "count"
_ESTIMATE_CACHED = "cached"
_ESTIMATE_EXCLUDED = "excluded"


def read_run_metadata(run_dir: Path) -> dict[str, Any]:
    """Commit SHA from status.json and per-dimension coverage from the reports
    and dim_estimates.json. Missing inputs yield None / empty, never an error."""
    status = read_status(run_dir) or {}
    estimates = read_dim_estimates(run_dir)
    coverage: dict[str, dict[str, Any]] = {}
    for dim_id, report in iter_readable_eval_reports(run_dir):
        if not isinstance(report, dict):
            continue
        estimate = estimates.get(dim_id) or {}
        coverage[dim_id] = {
            "sourceFileCount": report.get("sourceFileCount"),
            "filesRead": report.get("filesRead"),
            "coveragePct": report.get("coveragePct"),
            "cached": estimate.get(_ESTIMATE_CACHED),
            "misses": estimate.get(_ESTIMATE_MISSES),
            "excluded": estimate.get(_ESTIMATE_EXCLUDED),
        }
    return {"commitSha": status.get(_KEY_COMMIT_SHA), "coverage": coverage}
