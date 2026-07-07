"""Accumulated (cross-run) view logic for the filesystem action provider."""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from quodeq.core.scoring.internals import score_to_grade_label
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams, dimension_weighted_average
from quodeq.core.types import DimensionResult, to_camel_dict
from quodeq.services._cache import make_lru_dimension_fetcher
from quodeq.services.deleted import filter_deleted_from_dimensions
from quodeq.services.dim_resolution import is_eligible_for_default_view
from quodeq.services.dismissed import filter_dismissed_from_dimensions
from quodeq.services._fs_projects import find_children as _find_children
from quodeq.services.ports import RunInfo, calculate_trend, list_runs, most_frequent_grade, parse_numeric_score
from quodeq.shared.utils import _env_int

# Re-export so existing external imports keep working.
from quodeq.services._accumulated_data import _read_all_run_data  # noqa: F401

_DEFAULT_ACC_CACHE_MAX = 256


def numeric_average(
    dimensions: list[DimensionResult],
    params: ScoringParams = DEFAULT_PARAMS,
) -> float | None:
    """Compute the average numeric score from a list of DimensionResult objects."""
    pairs = [
        (d.dimension, score)
        for d, score in ((d, parse_numeric_score(d.overall_score)) for d in dimensions if d.overall_score)
        if score is not None
    ]
    return dimension_weighted_average(pairs, params)


def _compute_accumulated_trends(
    all_dimensions: list[DimensionResult],
    prev_occurrence: dict[str, DimensionResult],
) -> list[DimensionResult]:
    result: list[DimensionResult] = []
    for dim in all_dimensions:
        dim_name = dim.dimension
        previous = prev_occurrence.get(dim_name) if dim_name else None
        trend = calculate_trend(
            dim.overall_score,
            previous.overall_score if previous else None,
        )
        result.append(replace(
            dim,
            trend=trend,
            previous_run_id=previous.run_id if previous else None,
            previous_score=previous.overall_score if previous else None,
        ))
    return result


def _aggregate_severity_counts(all_dimensions: list[DimensionResult]) -> dict[str, int]:
    """Sum violation/compliance counts and severity buckets across dimensions."""
    total_violations = total_compliance = critical = major = minor = 0
    for dim in all_dimensions:
        totals = dim.totals
        if totals:
            total_violations += totals.violation_count
            total_compliance += totals.compliance_count
            critical += totals.severity.critical
            major += totals.severity.major
            minor += totals.severity.minor
    return {
        "totalViolations": total_violations, "totalCompliance": total_compliance,
        "critical": critical, "major": major, "minor": minor,
    }


def _compute_accumulated_scores(
    all_dimensions: list[DimensionResult], prev_run_latest: list[DimensionResult],
    params: ScoringParams = DEFAULT_PARAMS,
) -> tuple[float | None, float | None]:
    return (
        numeric_average(all_dimensions, params),
        (numeric_average(prev_run_latest, params) if prev_run_latest else None),
    )


@dataclass(frozen=True)
class _AccumulatedResult:
    all_dimensions: list[DimensionResult]
    dimensions_with_trend: list[DimensionResult]
    severity: dict[str, int]
    avg_score: float | None
    prev_avg_score: float | None


def _build_accumulated_response(
    project: str, result: _AccumulatedResult,
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, Any]:
    return {
        "project": project,
        "dimensions": [to_camel_dict(d) for d in result.dimensions_with_trend],
        "summary": {
            "overallGrade": (
                score_to_grade_label(result.avg_score, params=params) if result.avg_score is not None
                else most_frequent_grade([d.overall_grade for d in result.all_dimensions if d.overall_grade])
            ),
            "numericAverage": result.avg_score,
            "previousNumericAverage": result.prev_avg_score,
            "totalViolations": result.severity["totalViolations"],
            "totalCompliance": result.severity["totalCompliance"],
            "dimensionCount": len(result.dimensions_with_trend),
            "severity": {
                "critical": result.severity["critical"],
                "major": result.severity["major"],
                "minor": result.severity["minor"],
            },
        },
    }

def create_accumulated_cache() -> tuple[OrderedDict[tuple, list[DimensionResult]], threading.Lock]:
    """Create the default accumulated-view LRU cache and its lock."""
    return OrderedDict(), threading.Lock()


def _acc_dim_cache_max(override: int | None = None, env: dict[str, str] | None = None) -> int:
    """Return the accumulated-view cache size limit."""
    if override is not None:
        return override
    return _env_int("QUODEQ_ACC_CACHE_MAX", _DEFAULT_ACC_CACHE_MAX, env=env)


@dataclass
class AccumulatedCacheConfig:
    """Optional cache parameters for compute_accumulated."""
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


def _compute_result(
    reports_root: Path, project: str, all_run_infos: list[RunInfo],
    cache_config: AccumulatedCacheConfig | None,
    params: ScoringParams = DEFAULT_PARAMS,
) -> _AccumulatedResult:
    """Load run data and compute trends, severity, and scores.

    Only ``complete`` runs feed the overview by default. ``in_progress``
    runs are excluded so partial mid-flight dims don't leak into the
    cards: during a running evaluation the overview shows the previous
    complete run's data unchanged, and when the run terminates with
    status ``complete`` its dims become the new latest pick. ``failed``
    runs are excluded outright (no trustworthy data).

    If no complete run exists but cancelled runs do (fresh project where
    every attempt was stopped early), fall back to those — better to
    show what real data we have than to render a blank dashboard. The
    fallback explicitly excludes ``in_progress`` so a brand-new project
    whose first run is still alive starts blank, matching the rule that
    in-progress dims never count toward the overview.

    The eligibility predicate is the shared
    ``dim_resolution.is_eligible_for_default_view`` rule, used by both
    this call site and ``dashboard._resolve_selected_run`` so the
    headline and cards always read from the same set of runs.
    """
    eligible_run_infos = [r for r in all_run_infos if is_eligible_for_default_view(r.status)]
    if not eligible_run_infos:
        # Fall back to terminal-but-not-complete runs (cancelled), still
        # excluding in_progress. ``_read_all_run_data``'s per-eval-file
        # trustworthiness check filters out stub evals from these.
        eligible_run_infos = [r for r in all_run_infos if r.status != "in_progress"]
    return _build_accumulated_for_runs(reports_root, project, eligible_run_infos, cache_config, params)


def _scope_to_configured(
    all_dims: list[DimensionResult], configured: set[str],
) -> list[DimensionResult]:
    """Drop dimensions not in *configured*, the project's current standard.

    Removes stale dimensions (e.g. ``clean-architecture``) that a project
    no longer evaluates but that linger in old runs / ``evaluation.db``
    drift. Fail-open: an empty *configured* set (unreadable dimensions.json
    / status.json) means "unknown", so nothing is dropped — never return an
    empty grade because a config file went missing.
    """
    if not configured:
        return all_dims
    return [d for d in all_dims if d.dimension in configured]


def _build_accumulated_for_runs(
    reports_root: Path, project: str, run_infos: list[RunInfo],
    cache_config: AccumulatedCacheConfig | None,
    params: ScoringParams = DEFAULT_PARAMS,
) -> _AccumulatedResult:
    """Read run data and assemble the accumulated result for *run_infos*."""
    runs = [r.run_id for r in run_infos]
    _cache, _lock, _max = _resolve_cache(cache_config)
    get_run_data = make_lru_dimension_fetcher(reports_root, project, _cache, _lock, _max)
    latest_by_dim, prev_occurrence, prev_run_latest = _read_all_run_data(
        reports_root, project, run_infos, runs, get_run_data,
    )
    project_dir = reports_root / project
    all_dims = filter_dismissed_from_dimensions(list(latest_by_dim.values()), project_dir)
    all_dims = filter_deleted_from_dimensions(all_dims, project_dir)
    dims_with_trend = _compute_accumulated_trends(all_dims, prev_occurrence)
    severity = _aggregate_severity_counts(all_dims)
    avg, prev_avg = _compute_accumulated_scores(all_dims, prev_run_latest, params)
    return _AccumulatedResult(all_dims, dims_with_trend, severity, avg, prev_avg)


def _compute_parent_accumulated(
    reports_root: Path,
    children: list[str],
    parent_id: str,
    cache_config: AccumulatedCacheConfig | None,
    extra_dims: list[DimensionResult] | None = None,
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, Any] | None:
    """Merge latest findings from all children (and optional own dims) and score.

    *extra_dims* are dimensions from the parent's own runs, included when the
    parent has both its own evaluation runs and scoped children.
    """
    all_dims: list[DimensionResult] = list(extra_dims) if extra_dims else []
    # Track which child each dimension came from
    dim_source: dict[str, str] = {}  # dimension_name -> child_project_id
    for child in children:
        child_runs = list_runs(reports_root, child, limit=50)
        if not child_runs:
            continue
        result = _compute_result(reports_root, child, child_runs, cache_config, params)
        for d in result.all_dimensions:
            dim_source[d.dimension] = child
        all_dims.extend(result.all_dimensions)
    if not all_dims:
        return None
    severity = _aggregate_severity_counts(all_dims)
    avg, _ = _compute_accumulated_scores(all_dims, [], params)
    merged_result = _AccumulatedResult(all_dims, all_dims, severity, avg, None)
    response = _build_accumulated_response(parent_id, merged_result, params)
    # Tag each dimension with its source child project for navigation
    for dim_dict in response.get("dimensions", []):
        dim_name = dim_dict.get("dimension", "")
        if dim_name in dim_source:
            dim_dict["fromProject"] = dim_source[dim_name]
    return response


def compute_accumulated(
    reports_dir: str, project: str, as_of: str | None,
    *, cache_config: AccumulatedCacheConfig | None = None,
    params: ScoringParams | None = None,
) -> dict[str, Any] | None:
    """Compute the accumulated (cross-run) view for *project*.

    When *params* is None, the saved grade-formula params are loaded.
    """
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()
    reports_root = Path(reports_dir)
    if not (reports_root / project).exists():
        return None
    all_run_infos = list_runs(reports_root, project)
    if as_of:
        idx = next((i for i, r in enumerate(all_run_infos) if r.run_id == as_of), None)
        all_run_infos = all_run_infos[idx:] if idx is not None else []
    children = _find_children(reports_root, project)

    # No runs and no children — nothing to show
    if not all_run_infos and not children:
        return None

    # Pure parent (no own runs) — aggregate children only
    if not all_run_infos and children:
        return _compute_parent_accumulated(reports_root, children, project, cache_config, params=params)

    # Has own runs — check if also has children to merge
    own_result = _compute_result(reports_root, project, all_run_infos, cache_config, params)
    if not children:
        return _build_accumulated_response(project, own_result, params)

    # Has both own runs AND children — merge everything
    return _compute_parent_accumulated(
        reports_root, children, project, cache_config,
        extra_dims=own_result.all_dimensions,
        params=params,
    )
