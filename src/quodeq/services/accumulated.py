"""Accumulated (cross-run) view logic for the filesystem action provider.

Split: the walk-cache globals and per-call LRU cache config moved
to ``_accumulated_cache.py``; trend/severity/score aggregation (including the
wire-serialization call that builds the response payload) moved to
``_accumulated_aggregate.py``. Both are re-exported here — the walk-cache
globals are shared mutable state, so this module imports the OBJECTS (not
copies) to keep identity intact for tests that reach in directly
(``clear_accumulated_process_cache``).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types import DimensionResult
from quodeq.core.utils.io import resolve_child_dir
from quodeq.services.deleted import filter_deleted_from_dimensions
from quodeq.services.scoring_view import select_default_view_runs
from quodeq.services.dismissed import filter_dismissed_from_dimensions
from quodeq.services.wiring import (
    RunInfo,
    find_children as _find_children,
    list_runs,
)

# Re-export so existing external imports keep working.
from quodeq.services._accumulated_data import read_all_run_data
from quodeq.services._accumulated_data import make_slim_run_fetcher

from quodeq.services._accumulated_cache import (  # noqa: F401 — re-export
    AccumulatedCacheConfig,
    WALK_CACHE,
    WALK_CACHE_LOCK,
    acc_dim_cache_max,
    resolve_cache,
    walk_cache_max,
    clear_accumulated_process_cache,
    create_accumulated_cache,
)
from quodeq.services.cache import DimensionCacheContext, make_lru_dimension_fetcher
from quodeq.services._accumulated_aggregate import (  # noqa: F401 — re-export
    AccumulatedResult,
    aggregate_severity_counts,
    build_accumulated_response,
    compute_accumulated_scores,
    compute_accumulated_trends,
    numeric_average,
)


def _compute_result(
    reports_root: Path, project: str, all_run_infos: list[RunInfo],
    cache_config: AccumulatedCacheConfig | None,
    params: ScoringParams = DEFAULT_PARAMS,
    *, log: LogSink = NULL_LOG,
) -> AccumulatedResult:
    """Load run data and compute trends, severity, and scores.

    Only ``done`` runs feed the overview by default. ``running``
    runs are excluded so partial mid-flight dims don't leak into the
    cards: during a running evaluation the overview shows the previous
    done run's data unchanged, and when the run terminates with
    status ``done`` its dims become the new latest pick. ``failed``
    runs are excluded outright (no trustworthy data).

    If no done run exists but cancelled runs do (fresh project where
    every attempt was stopped early), fall back to those — better to
    show what real data we have than to render a blank dashboard. The
    fallback excludes ``running`` (a brand-new project whose first
    run is still alive starts blank) and ``failed`` (the run errored;
    its partial scoring must not masquerade as the project grade).

    The run-set selection is the shared
    ``scoring_view.select_default_view_runs`` rule, also used by the
    repositories screen's project-card summary so the card grade always
    matches the Overview behind the click.
    """
    eligible_run_infos = select_default_view_runs(all_run_infos)
    return _build_accumulated_for_runs(
        reports_root, project, eligible_run_infos, cache_config, params, log=log,
    )


def _load_run_dimensions(
    reports_root: Path, project: str, run_infos: list[RunInfo],
    cache_config: AccumulatedCacheConfig | None,
    *, log: LogSink = NULL_LOG,
) -> tuple[dict[str, DimensionResult], dict[str, DimensionResult], list[DimensionResult]]:
    _cache, _lock, _max = resolve_cache(cache_config)
    ctx = DimensionCacheContext(cache=_cache, lock=_lock, max_size=_max)
    get_run_data = make_lru_dimension_fetcher(reports_root, project, ctx)
    # A caller-supplied cache_config asks for per-call isolation, so it backs the
    # walk too; otherwise the walk runs off the shared process cache.
    if cache_config is not None:
        walk_cache, walk_lock, walk_max = _cache, _lock, _max
    else:
        walk_cache, walk_lock, walk_max = WALK_CACHE, WALK_CACHE_LOCK, walk_cache_max()
    get_run_slim = make_slim_run_fetcher(
        reports_root, project, walk_cache, walk_lock, walk_max, log=log,
    )
    return read_all_run_data(
        reports_root, project, run_infos, get_run_data, get_run_slim=get_run_slim,
    )


def _suppress_run_dimensions(
    latest_by_dim: dict[str, DimensionResult], project_dir: Path,
) -> list[DimensionResult]:
    all_dims = filter_dismissed_from_dimensions(list(latest_by_dim.values()), project_dir)
    return filter_deleted_from_dimensions(all_dims, project_dir)


def _build_accumulated_for_runs(
    reports_root: Path, project: str, run_infos: list[RunInfo],
    cache_config: AccumulatedCacheConfig | None,
    params: ScoringParams = DEFAULT_PARAMS,
    *, log: LogSink = NULL_LOG,
) -> AccumulatedResult:
    """Read run data and assemble the accumulated result for *run_infos*."""
    latest_by_dim, prev_occurrence, prev_run_latest = _load_run_dimensions(
        reports_root, project, run_infos, cache_config, log=log,
    )
    all_dims = _suppress_run_dimensions(latest_by_dim, reports_root / project)
    dims_with_trend = compute_accumulated_trends(all_dims, prev_occurrence)
    severity = aggregate_severity_counts(all_dims)
    avg, prev_avg = compute_accumulated_scores(all_dims, prev_run_latest, params)
    return AccumulatedResult(all_dims, dims_with_trend, severity, avg, prev_avg)


_MAX_CHILD_RUNS_CONSIDERED = 50  # per-child run cap when merging into a parent's accumulated view


@dataclass(frozen=True, slots=True)
class _ParentScope:
    """A parent project's id, its scoped child projects, and its own dimensions.

    ``extra_dims`` are dimensions from the parent's own runs, present when the
    parent has both its own evaluation runs and scoped children.
    """
    parent_id: str
    children: list[str]
    extra_dims: list[DimensionResult] | None = None


def _compute_parent_accumulated(
    reports_root: Path,
    scope: _ParentScope,
    cache_config: AccumulatedCacheConfig | None,
    params: ScoringParams = DEFAULT_PARAMS,
    *, log: LogSink = NULL_LOG,
) -> dict[str, Any] | None:
    """Merge latest findings from all children (and optional own dims) and score."""
    all_dims: list[DimensionResult] = list(scope.extra_dims) if scope.extra_dims else []
    # Track which child each dimension came from
    dim_source: dict[str, str] = {}  # dimension_name -> child_project_id
    for child in scope.children:
        child_runs = list_runs(reports_root, child, limit=_MAX_CHILD_RUNS_CONSIDERED)
        if not child_runs:
            continue
        result = _compute_result(reports_root, child, child_runs, cache_config, params, log=log)
        for d in result.all_dimensions:
            dim_source[d.dimension] = child
        all_dims.extend(result.all_dimensions)
    if not all_dims:
        return None
    severity = aggregate_severity_counts(all_dims)
    avg, _ = compute_accumulated_scores(all_dims, [], params)
    merged_result = AccumulatedResult(all_dims, all_dims, severity, avg, None)
    response = build_accumulated_response(scope.parent_id, merged_result, params)
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
    log: LogSink = NULL_LOG,
) -> dict[str, Any] | None:
    """Compute the accumulated (cross-run) view for *project*.

    When *params* is None, the saved grade-formula params are loaded.
    """
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()
    reports_root = Path(reports_dir)
    # *project* comes from the request path. Resolve it against the directory
    # listing instead of joining it onto reports_root, so a traversal or
    # absolute segment cannot probe for paths outside the reports tree.
    if resolve_child_dir(reports_root, project) is None:
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
        return _compute_parent_accumulated(
            reports_root, _ParentScope(project, children), cache_config, params, log=log,
        )

    # Has own runs — check if also has children to merge
    own_result = _compute_result(
        reports_root, project, all_run_infos, cache_config, params, log=log,
    )
    if not children:
        return build_accumulated_response(project, own_result, params)

    # Has both own runs AND children — merge everything
    return _compute_parent_accumulated(
        reports_root, _ParentScope(project, children, own_result.all_dimensions),
        cache_config, params, log=log,
    )
