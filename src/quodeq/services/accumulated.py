"""Accumulated (cross-run) view logic for the filesystem action provider."""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass, field, replace
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
from quodeq.core.types import DimensionResult, to_camel_dict
from quodeq.core.scoring.internals import score_to_grade_label
from quodeq.services._cache import make_lru_dimension_fetcher


def create_accumulated_cache() -> tuple[OrderedDict[tuple, list[DimensionResult]], threading.Lock]:
    """Create the default accumulated-view LRU cache and its lock.

    Override this factory to plug in a shared backend (e.g. a Redis-backed
    OrderedDict wrapper) for multi-worker deployments.
    """
    return OrderedDict(), threading.Lock()


_DEFAULT_ACC_CACHE_MAX = 256


def _acc_dim_cache_max(override: int | None = None, env: dict[str, str] | None = None) -> int:
    """Return the accumulated-view cache size limit. *override* bypasses env for testing."""
    if override is not None:
        return override
    try:
        return int((env or os.environ).get("QUODEQ_ACC_CACHE_MAX", str(_DEFAULT_ACC_CACHE_MAX)))
    except (ValueError, TypeError):
        return _DEFAULT_ACC_CACHE_MAX


def _read_all_run_data(
    reports_root: Path, project: str, all_run_infos: list[RunInfo], runs: list[str],
    get_run_data: Callable[[str], list[DimensionResult]] | None = None,
) -> tuple[dict[str, DimensionResult], dict[str, DimensionResult], list[DimensionResult]]:
    """Build accumulated data structures in a single sequential pass.

    Returns:
        latest_by_dimension: most recent dimension data, keyed by dimension name.
        prev_occurrence: for each dimension, its data from the next-older run
            (used for trend computation — replaces the O(n^2) _find_previous_run).
        prev_run_latest: most recent dimension data from runs[1:] (for previous average).
    """
    run_lookup = {r.run_id: r for r in all_run_infos}
    latest_by_dimension: dict[str, DimensionResult] = {}
    prev_occurrence: dict[str, DimensionResult] = {}
    prev_run_latest_map: dict[str, DimensionResult] = {}
    _fetch = get_run_data or (lambda rid: read_run_data(reports_root, project, rid))

    for run_idx_i, run_id in enumerate(runs):
        dims = _fetch(run_id)
        run_info = run_lookup.get(run_id)
        is_first_run = (run_idx_i == 0)

        for dim in dims:
            dim_name = dim.dimension
            if not dim_name:
                continue
            if dim_name not in latest_by_dimension:
                latest_by_dimension[dim_name] = replace(
                    dim,
                    from_run_id=run_id,
                    from_date_iso=run_info.date_iso if run_info else None,
                    from_date_label=run_info.date_label if run_info else None,
                )
            elif dim_name not in prev_occurrence:
                prev_occurrence[dim_name] = replace(dim, run_id=run_id)

            if not is_first_run and dim_name not in prev_run_latest_map:
                prev_run_latest_map[dim_name] = dim

    return latest_by_dimension, prev_occurrence, list(prev_run_latest_map.values())


def _compute_accumulated_trends(
    all_dimensions: list[DimensionResult],
    prev_occurrence: dict[str, DimensionResult],
) -> list[DimensionResult]:
    """Compute trend data for each accumulated dimension using pre-built prev_occurrence."""
    result: list[DimensionResult] = []
    for dim in all_dimensions:
        dim_name = dim.dimension
        previous = prev_occurrence.get(dim_name) if dim_name else None
        trend = calculate_trend(
            dim.overall_score,
            previous.overall_score if previous else None,
        )
        result.append(
            replace(
                dim,
                trend=trend,
                previous_run_id=previous.run_id if previous else None,
                previous_score=previous.overall_score if previous else None,
            )
        )
    return result


def _aggregate_severity_counts(all_dimensions: list[DimensionResult]) -> dict[str, int]:
    """Sum violation/compliance counts and severity buckets across dimensions."""
    total_violations = 0
    total_compliance = 0
    critical = 0
    major = 0
    minor = 0
    for dim in all_dimensions:
        totals = dim.totals
        if totals:
            total_violations += totals.violation_count
            total_compliance += totals.compliance_count
            critical += totals.severity.critical
            major += totals.severity.major
            minor += totals.severity.minor
    return {
        "totalViolations": total_violations,
        "totalCompliance": total_compliance,
        "critical": critical,
        "major": major,
        "minor": minor,
    }


def numeric_average(dimensions: list[DimensionResult]) -> float | None:
    """Compute the average numeric score from a list of DimensionResult objects."""
    raw = [d.overall_score for d in dimensions if d.overall_score]
    numeric = [s for s in (parse_numeric_score(v) for v in raw) if s is not None]
    return round(sum(numeric) / len(numeric), 1) if numeric else None


def _compute_accumulated_scores(
    all_dimensions: list[DimensionResult], prev_run_latest: list[DimensionResult],
) -> tuple[float | None, float | None]:
    """Compute current and previous overall average scores."""
    avg_score = numeric_average(all_dimensions)
    prev_avg_score = numeric_average(prev_run_latest) if prev_run_latest else None
    return avg_score, prev_avg_score


@dataclass
class AccumulatedCacheConfig:
    """Optional cache parameters for compute_accumulated (overrides module-level cache)."""

    cache: OrderedDict[tuple, list[DimensionResult]] = field(default_factory=OrderedDict)
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
    cache, lock = create_accumulated_cache()
    return cache, lock, _acc_dim_cache_max()


@dataclass(frozen=True)
class _AccumulatedResult:
    """Pre-computed parts for the accumulated response."""
    all_dimensions: list[DimensionResult]
    dimensions_with_trend: list[DimensionResult]
    severity: dict[str, int]
    avg_score: float | None
    prev_avg_score: float | None


def _build_accumulated_response(
    project: str,
    result: _AccumulatedResult,
) -> dict[str, Any]:
    """Assemble the final accumulated response dict."""
    return {
        "project": project,
        "dimensions": [to_camel_dict(d) for d in result.dimensions_with_trend],
        "summary": {
            "overallGrade": (
                score_to_grade_label(result.avg_score) if result.avg_score is not None
                else most_frequent_grade([d.overall_grade for d in result.all_dimensions if d.overall_grade])
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
) -> dict[str, Any] | None:
    """Compute the accumulated (cross-run) view for *project*.

    Parameter count is intentional: each argument represents a distinct
    query axis with no natural grouping.  *cache_config* overrides the
    module-level LRU cache for testing without global state mutation.
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
