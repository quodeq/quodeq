"""Caching fetcher and lookup utilities for previous-run queries."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from quodeq.core.types import DimensionResult
from quodeq.shared.validation import validate_path_segment

_CACHING_FETCHER_MAX = 100


def _make_caching_fetcher(
    reports_root: Path, project: str,
    data_cache: dict[str, list[DimensionResult]] | None = None,
) -> Callable[[str], list[DimensionResult]]:
    """Return a fetcher that caches run data reads (bounded to last 100 runs).

    *data_cache* is injectable for testing; defaults to a fresh dict.
    """
    # Import here to avoid circular import (runs imports _run_lookup).
    from quodeq.data.fs.report_parser.runs import read_run_data

    cache = data_cache if data_cache is not None else {}

    def _fetch(run_id: str) -> list[DimensionResult]:
        if run_id not in cache:
            if len(cache) >= _CACHING_FETCHER_MAX:
                oldest = next(iter(cache))
                del cache[oldest]
            cache[run_id] = read_run_data(reports_root, project, run_id)
        return cache[run_id]

    return _fetch


@dataclass(frozen=True)
class RunLookupCache:
    """Pre-computed data to avoid repeated I/O when looking up previous runs."""

    runs: "list[Any]"  # list[RunInfo] — string annotation to avoid circular import
    get_run_data: Callable[[str], list[DimensionResult]]


def _get_previous_run_for_dimension(
    reports_root: Path,
    project: str,
    current_run_id: str,
    dimension: str,
    *,
    cache: RunLookupCache | None = None,
) -> dict[str, Any] | None:
    """Return the most recent run data for *dimension* before *current_run_id*, or None.

    Callers processing multiple dimensions for the same project should pass
    a *cache* (built from a single ``list_runs`` call and a dict-backed
    callable) to share I/O across calls rather than repeating the directory
    scan and file reads for each dimension.
    """
    from quodeq.data.fs.report_parser.runs import list_runs

    validate_path_segment(project, current_run_id)
    project_path = reports_root / project
    if not project_path.exists():
        return None
    if cache is None:
        all_runs = list_runs(reports_root, project)
        cache = RunLookupCache(
            runs=all_runs,
            get_run_data=_make_caching_fetcher(reports_root, project),
        )
    all_runs = cache.runs
    current_idx = next((i for i, r in enumerate(all_runs) if r.run_id == current_run_id), -1)
    if current_idx < 0:
        return None

    for run_info in all_runs[current_idx + 1:]:
        dims = cache.get_run_data(run_info.run_id)
        dim = next((d for d in dims if d.dimension == dimension), None)
        if dim:
            return {"runId": run_info.run_id, "dimension": dim}
    return None
