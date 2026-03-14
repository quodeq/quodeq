"""Accumulated (cross-run) view logic for the filesystem action provider."""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

from quodeq.adapters.fs.report_parser import (
    RunInfo,
    calculate_trend,
    list_runs,
    most_frequent_grade,
    parse_numeric_score,
    read_run_data,
)
from quodeq.provider._cache import make_lru_dimension_fetcher

# Module-level LRU cache for accumulated-view disk reads (bounded, cross-request).
# Process-local cache; in multi-worker deployments, replace with a shared cache
# (Redis, memcached) via the dimension_fetcher callable.
_ACC_DIM_CACHE: OrderedDict[tuple, list[dict[str, Any]]] = OrderedDict()
_ACC_DIM_CACHE_MAX = 256
_ACC_DIM_LOCK = threading.Lock()


def _make_acc_dimension_fetcher(
    reports_root: Path, project: str,
) -> Callable[[str], list[dict[str, Any]]]:
    """Return a cached fetcher for run dimension data (LRU, bounded)."""
    return make_lru_dimension_fetcher(
        reports_root, project, _ACC_DIM_CACHE, _ACC_DIM_LOCK, _ACC_DIM_CACHE_MAX,
    )


def _read_all_run_data(
    reports_root: Path, project: str, all_run_infos: list[RunInfo], runs: list[str],
    get_run_data: Callable[[str], list[dict[str, Any]]] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Build accumulated data structures in a single sequential pass.

    Returns:
        latest_by_dimension: most recent dimension data, keyed by dimension name.
        prev_occurrence: for each dimension, its data from the next-older run
            (used for trend computation — replaces the O(n²) _find_previous_run).
        prev_run_latest: most recent dimension data from runs[1:] (for previous average).
    """
    run_lookup = {r.run_id: r for r in all_run_infos}
    latest_by_dimension: dict[str, dict[str, Any]] = {}
    prev_occurrence: dict[str, dict[str, Any]] = {}
    prev_run_latest_map: dict[str, dict[str, Any]] = {}
    _fetch = get_run_data or (lambda rid: read_run_data(reports_root, project, rid))

    for run_idx_i, run_id in enumerate(runs):
        dims = _fetch(run_id)
        run_info = run_lookup.get(run_id)
        is_first_run = (run_idx_i == 0)

        for dim in dims:
            dim_name = dim.get("dimension")
            if not dim_name:
                continue
            if dim_name not in latest_by_dimension:
                latest_by_dimension[dim_name] = {
                    **dim,
                    "fromRunId": run_id,
                    "fromDateISO": run_info.date_iso if run_info else None,
                    "fromDateLabel": run_info.date_label if run_info else None,
                }
            elif dim_name not in prev_occurrence:
                prev_occurrence[dim_name] = {"runId": run_id, "dimension": dim}

            if not is_first_run and dim_name not in prev_run_latest_map:
                prev_run_latest_map[dim_name] = dim

    return latest_by_dimension, prev_occurrence, list(prev_run_latest_map.values())


def _compute_accumulated_trends(
    all_dimensions: list[dict[str, Any]],
    prev_occurrence: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compute trend data for each accumulated dimension using pre-built prev_occurrence."""
    result = []
    for dim in all_dimensions:
        dim_name = dim.get("dimension")
        previous = prev_occurrence.get(dim_name) if dim_name else None
        trend = calculate_trend(
            dim.get("overallScore"),
            previous.get("dimension", {}).get("overallScore") if previous else None,
        )
        result.append(
            {
                **dim,
                "trend": trend,
                "previousRunId": previous.get("runId") if previous else None,
                "previousScore": previous.get("dimension", {}).get("overallScore") if previous else None,
            }
        )
    return result


def _aggregate_severity_counts(all_dimensions: list[dict[str, Any]]) -> dict[str, int]:
    """Sum violation/compliance counts and severity buckets across dimensions."""
    total_violations = 0
    total_compliance = 0
    critical = 0
    major = 0
    minor = 0
    for dim in all_dimensions:
        totals = dim.get("totals", {})
        severity = totals.get("severity", {}) if totals else {}
        total_violations += totals.get("violationCount", 0) if totals else 0
        total_compliance += totals.get("complianceCount", 0) if totals else 0
        critical += severity.get("critical", 0)
        major += severity.get("major", 0)
        minor += severity.get("minor", 0)
    return {
        "totalViolations": total_violations,
        "totalCompliance": total_compliance,
        "critical": critical,
        "major": major,
        "minor": minor,
    }


def numeric_average(dimensions: list[dict[str, Any]]) -> float | None:
    """Compute the average numeric score from a list of dimension dicts."""
    raw = [d.get("overallScore") for d in dimensions if d.get("overallScore")]
    numeric = [s for s in (parse_numeric_score(v) for v in raw) if s is not None]
    return round(sum(numeric) / len(numeric), 1) if numeric else None


def _compute_accumulated_scores(
    all_dimensions: list[dict[str, Any]], prev_run_latest: list[dict[str, Any]],
) -> tuple[float | None, float | None]:
    """Compute current and previous overall average scores."""
    avg_score = numeric_average(all_dimensions)
    prev_avg_score = numeric_average(prev_run_latest) if prev_run_latest else None
    return avg_score, prev_avg_score


def compute_accumulated(
    reports_dir: str,
    project: str,
    as_of: str | None,
    *,
    cache: OrderedDict[tuple, list[dict[str, Any]]] | None = None,
    cache_lock: threading.Lock | None = None,
    cache_max: int | None = None,
) -> dict[str, Any] | None:
    """Compute the accumulated (cross-run) view for *project*.

    Optional *cache*, *cache_lock*, and *cache_max* override the module-level
    LRU cache, making the function testable without global state mutation.
    """
    reports_root = Path(reports_dir)
    project_path = reports_root / project
    if not project_path.exists():
        return None

    all_run_infos = list_runs(reports_root, project)  # newest first
    if as_of:
        as_of_idx = next((idx for idx, r in enumerate(all_run_infos) if r.run_id == as_of), None)
        all_run_infos = all_run_infos[as_of_idx:] if as_of_idx is not None else []
    runs = [r.run_id for r in all_run_infos]
    if not runs:
        return None

    _cache = cache if cache is not None else _ACC_DIM_CACHE
    _lock = cache_lock if cache_lock is not None else _ACC_DIM_LOCK
    _max = cache_max if cache_max is not None else _ACC_DIM_CACHE_MAX
    get_run_data = make_lru_dimension_fetcher(reports_root, project, _cache, _lock, _max)
    latest_by_dimension, prev_occurrence, prev_run_latest = _read_all_run_data(
        reports_root, project, all_run_infos, runs, get_run_data
    )
    all_dimensions = list(latest_by_dimension.values())
    dimensions_with_trend = _compute_accumulated_trends(all_dimensions, prev_occurrence)
    severity = _aggregate_severity_counts(all_dimensions)
    avg_score, prev_avg_score = _compute_accumulated_scores(all_dimensions, prev_run_latest)

    return {
        "project": project,
        "dimensions": dimensions_with_trend,
        "summary": {
            "overallGrade": most_frequent_grade(
                [d.get("overallGrade") for d in all_dimensions if d.get("overallGrade")]
            ),
            "numericAverage": avg_score,
            "previousNumericAverage": prev_avg_score,
            "totalViolations": severity["totalViolations"],
            "totalCompliance": severity["totalCompliance"],
            "dimensionCount": len(dimensions_with_trend),
            "severity": {"critical": severity["critical"], "major": severity["major"], "minor": severity["minor"]},
        },
    }
