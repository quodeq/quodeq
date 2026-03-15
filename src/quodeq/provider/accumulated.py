"""Accumulated (cross-run) view logic for the filesystem action provider."""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from quodeq.shared.types import DimensionData

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
# For multi-worker deployments, override the cache via compute_accumulated(cache_config=...)
# or supply a shared backend (e.g. Redis OrderedDict wrapper) through AccumulatedCacheConfig.
_ACC_DIM_CACHE: OrderedDict[tuple, list[DimensionData]] = OrderedDict()
_ACC_DIM_LOCK = threading.Lock()


_DEFAULT_ACC_CACHE_MAX = 256


def _acc_dim_cache_max(override: int | None = None) -> int:
    """Return the accumulated-view cache size limit. *override* bypasses env for testing."""
    if override is not None:
        return override
    return int(os.environ.get("QUODEQ_ACC_CACHE_MAX", str(_DEFAULT_ACC_CACHE_MAX)))


def _make_acc_dimension_fetcher(
    reports_root: Path, project: str,
) -> Callable[[str], list[DimensionData]]:
    """Return a cached fetcher for run dimension data (LRU, bounded)."""
    return make_lru_dimension_fetcher(
        reports_root, project, _ACC_DIM_CACHE, _ACC_DIM_LOCK, _acc_dim_cache_max(),
    )


def _read_all_run_data(
    reports_root: Path, project: str, all_run_infos: list[RunInfo], runs: list[str],
    get_run_data: Callable[[str], list[DimensionData]] | None = None,
) -> tuple[dict[str, DimensionData], dict[str, DimensionData], list[DimensionData]]:
    """Build accumulated data structures in a single sequential pass.

    Returns:
        latest_by_dimension: most recent dimension data, keyed by dimension name.
        prev_occurrence: for each dimension, its data from the next-older run
            (used for trend computation — replaces the O(n²) _find_previous_run).
        prev_run_latest: most recent dimension data from runs[1:] (for previous average).
    """
    run_lookup = {r.run_id: r for r in all_run_infos}
    latest_by_dimension: dict[str, DimensionData] = {}
    prev_occurrence: dict[str, DimensionData] = {}
    prev_run_latest_map: dict[str, DimensionData] = {}
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
    all_dimensions: list[DimensionData],
    prev_occurrence: dict[str, DimensionData],
) -> list[DimensionData]:
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


def _aggregate_severity_counts(all_dimensions: list[DimensionData]) -> dict[str, int]:
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


def numeric_average(dimensions: list[DimensionData]) -> float | None:
    """Compute the average numeric score from a list of dimension dicts."""
    raw = [d.get("overallScore") for d in dimensions if d.get("overallScore")]
    numeric = [s for s in (parse_numeric_score(v) for v in raw) if s is not None]
    return round(sum(numeric) / len(numeric), 1) if numeric else None


def _compute_accumulated_scores(
    all_dimensions: list[DimensionData], prev_run_latest: list[DimensionData],
) -> tuple[float | None, float | None]:
    """Compute current and previous overall average scores."""
    avg_score = numeric_average(all_dimensions)
    prev_avg_score = numeric_average(prev_run_latest) if prev_run_latest else None
    return avg_score, prev_avg_score


@dataclass
class AccumulatedCacheConfig:
    """Optional cache parameters for compute_accumulated (overrides module-level cache)."""

    cache: OrderedDict[tuple, list[DimensionData]] = field(default_factory=OrderedDict)
    cache_lock: threading.Lock = field(default_factory=threading.Lock)
    cache_max: int | None = None


def _resolve_cache(
    cache_config: AccumulatedCacheConfig | None,
) -> tuple[OrderedDict, threading.Lock, int]:
    """Resolve cache, lock, and max-size from *cache_config* or module defaults."""
    if cache_config is not None:
        return (
            cache_config.cache,
            cache_config.cache_lock,
            cache_config.cache_max if cache_config.cache_max is not None else _acc_dim_cache_max(),
        )
    return _ACC_DIM_CACHE, _ACC_DIM_LOCK, _acc_dim_cache_max()


@dataclass(frozen=True)
class _AccumulatedResult:
    """Pre-computed parts for the accumulated response."""
    all_dimensions: list[DimensionData]
    dimensions_with_trend: list[DimensionData]
    severity: dict[str, int]
    avg_score: float | None
    prev_avg_score: float | None


def _build_accumulated_response(
    project: str,
    result: _AccumulatedResult,
) -> dict[str, object]:
    """Assemble the final accumulated response dict."""
    return {
        "project": project,
        "dimensions": result.dimensions_with_trend,
        "summary": {
            "overallGrade": most_frequent_grade(
                [d.get("overallGrade") for d in result.all_dimensions if d.get("overallGrade")]
            ),
            "numericAverage": result.avg_score,
            "previousNumericAverage": result.prev_avg_score,
            "totalViolations": result.severity["totalViolations"],
            "totalCompliance": result.severity["totalCompliance"],
            "dimensionCount": len(result.dimensions_with_trend),
            "severity": {"critical": result.severity["critical"], "major": result.severity["major"], "minor": result.severity["minor"]},
        },
    }


def _compute_result(
    reports_root: Path, project: str, all_run_infos: list[RunInfo],
    cache_config: AccumulatedCacheConfig | None,
) -> _AccumulatedResult:
    """Load run data and compute trends, severity, and scores."""
    runs = [r.run_id for r in all_run_infos]
    _cache, _lock, _max = _resolve_cache(cache_config)
    get_run_data = make_lru_dimension_fetcher(reports_root, project, _cache, _lock, _max)
    latest_by_dimension, prev_occurrence, prev_run_latest = _read_all_run_data(
        reports_root, project, all_run_infos, runs, get_run_data
    )
    all_dimensions = list(latest_by_dimension.values())
    dimensions_with_trend = _compute_accumulated_trends(all_dimensions, prev_occurrence)
    severity = _aggregate_severity_counts(all_dimensions)
    avg_score, prev_avg_score = _compute_accumulated_scores(all_dimensions, prev_run_latest)
    return _AccumulatedResult(all_dimensions, dimensions_with_trend, severity, avg_score, prev_avg_score)


def compute_accumulated(
    reports_dir: str,
    project: str,
    as_of: str | None,
    *,
    cache_config: AccumulatedCacheConfig | None = None,
) -> dict[str, object] | None:
    """Compute the accumulated (cross-run) view for *project*.

    Optional *cache_config* overrides the module-level LRU cache, making
    the function testable without global state mutation.
    """
    reports_root = Path(reports_dir)
    project_path = reports_root / project
    if not project_path.exists():
        return None

    all_run_infos = list_runs(reports_root, project)  # newest first
    if as_of:
        as_of_idx = next((idx for idx, r in enumerate(all_run_infos) if r.run_id == as_of), None)
        all_run_infos = all_run_infos[as_of_idx:] if as_of_idx is not None else []
    if not all_run_infos:
        return None

    result = _compute_result(reports_root, project, all_run_infos, cache_config)
    return _build_accumulated_response(project, result)
