"""Pipeline coordination — dimension orchestration, merging, and public API."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple
from datetime import datetime, timezone

from quodeq.analysis._dim_estimates import compute_dim_estimates, write_dim_estimates
from quodeq.analysis._dim_order import DimEstimates, _order_by_backlog
from quodeq.analysis._analysis_context import load_analysis_context as _load_ctx
from quodeq.analysis._loop_state import DimTransition, _run_dir_for, _safe_write_dim_state
from quodeq.analysis._loop_steps import default_loop_deps
from quodeq.analysis._pipeline_setup import (
    _set_run_deadline, _warn_if_local_api_oversubscribed,
)
from quodeq.analysis._loops import run_incremental_loop, run_per_dimension_loop
from quodeq.analysis.run_types import RunConfig, _AnalysisContext
from quodeq.analysis.cache.gc import ensure_cache_ready
from quodeq.analysis.cache.local import LocalFileBackend
from quodeq.analysis.dimension_runner import DimensionRunner, _log_dimension_result
from quodeq.analysis.errors import EvaluationError as EvaluationError  # re-export
from quodeq.analysis.subagents.runner import process_consolidated_dimensions
from quodeq.analysis.subprocess import _get_provider_type
from quodeq.core.evidence.model import Evidence
from quodeq.data.fs.dimensions_state_store import DimState
from quodeq.core.evidence.merge import merge_evidence
from quodeq.analysis.runner_markers import emit_marker
from quodeq.shared.constants import CC_PHASE_ANALYZING, CC_PHASE_SCORING, CC_PHASE_SETUP
from quodeq.shared.logging import log_info, log_warning
from quodeq.shared.log_sink import SHARED_LOG


def load_analysis_context(config: RunConfig) -> tuple[list[str], _AnalysisContext]:
    """Load dimensions data and resolve which dimensions to analyze."""
    return _load_ctx(config)


class _DryRunScope(NamedTuple):
    """The per-run values every dry-run dimension reuses."""
    run_dir: Path | None
    evidence_dir: Path
    date_str: str
    total: int


def _dry_run_dimension(
    config: RunConfig, scope: _DryRunScope, dimension: str, idx: int,
) -> Evidence:
    """Walk one dimension through the dry-run states and return empty Evidence.

    Dim states must move to DONE here just like the real loops: the lifecycle
    flips anything still pending at exit to INCOMPLETE and stamps the run
    exit_reason=incomplete_dimensions.
    """
    _safe_write_dim_state(
        scope.run_dir, dimension, DimTransition(DimState.RUNNING), log=SHARED_LOG)
    log_info(f"→ [{idx}/{scope.total}] Dry-run: skipping AI call for {dimension}")
    emit_marker(CC_PHASE_ANALYZING, dimension=dimension)
    ev = Evidence(
        repository=str(config.src),
        language=config.language,
        date=scope.date_str,
        source_file_count=config.source_file_count,
        files_read=0,
        coverage_pct=0.0,
    )
    # V2 cache writes happen per-file inside the dispatch path; dry-run
    # has nothing to dispatch, so no cache state is created here.
    jsonl_path = scope.evidence_dir / f"{dimension}_evidence.jsonl"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    if not jsonl_path.exists():
        jsonl_path.touch()
    emit_marker(CC_PHASE_SCORING, dimension=dimension)
    _safe_write_dim_state(
        scope.run_dir, dimension, DimTransition(DimState.DONE), log=SHARED_LOG)
    return ev


def _run_dry_run(
    config: RunConfig,
    on_dimension_done: "Callable[[str, Evidence], None] | None" = None,
) -> dict[str, Evidence]:
    """Return empty Evidence per dimension without making any AI calls."""
    dimensions, ctx = load_analysis_context(config)
    emit_marker(CC_PHASE_SETUP, dimensions=dimensions)
    scope = _DryRunScope(
        run_dir=_run_dir_for(config),
        evidence_dir=config.work_dir or config.src,
        date_str=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        total=ctx.total,
    )
    result: dict[str, Evidence] = {}
    for idx, dimension in enumerate(dimensions, 1):
        ev = _dry_run_dimension(config, scope, dimension, idx)
        result[dimension] = ev
        if on_dimension_done:
            on_dimension_done(dimension, ev)
    return result


def _persist_dim_estimates(config: RunConfig, dimensions: list[str]) -> DimEstimates | None:
    """Compute and persist per-dim file estimates so the dashboard total
    is accurate before any dim starts. Best-effort: a failure here must
    not break the run — the UI will fall back to the project-wide ceiling.

    Returns the estimates (None when there are none) so the caller can
    order dimensions by pending backlog without a second cache walk.
    """
    if not config.work_dir:
        return None  # dev mode (no run_dir) — nothing for the dashboard to read
    try:
        estimates = compute_dim_estimates(config, dimensions, log=SHARED_LOG)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        SHARED_LOG.debug(f"dim estimates skipped; the dashboard falls back to the project-wide ceiling: {exc}")
        return None
    write_dim_estimates(config.work_dir.parent, estimates)
    return estimates


def _prepare_run_context(
    config: RunConfig,
) -> tuple[list[str], _AnalysisContext, DimensionRunner, dict[str, int] | None]:
    """Load dimensions/context, warm the classify cache, and build the runner.

    Dimensions come back ordered by pending backlog with their per-dim
    counts, or in the configured order with ``None`` counts (``_dim_order``).

    Activates the per-run classify stash so ``_persist_dim_estimates`` below
    and the dim runner inside ``cache/dimension_runner.py`` share a single
    walk of the source files per dim. Without this, the same
    ``classify_files_via_cache`` call happens twice per dim (once for the
    dashboard's upfront totals, once for the actual hit/miss dispatch), each
    repeating thousands of source-file hashes and cache.get() lookups. Tests
    and dry-run paths leave it as None.

    One runner per run. Per-run construction (vs. a module-level singleton)
    makes test substitution and concurrency-safety obvious: each evaluation
    owns its own DimensionCallbacks instance.

    Cache is constructed here (composition root) rather than left for
    process_dimension_with_cache to default lazily, so every dimension in
    this run shares one LocalFileBackend. The cache maintenance (schema
    migration, content-index build, legacy GC) that used to ride along with
    the lazy default is called explicitly here instead -- it's still
    once-per-(root, schema)-per-process (see ensure_cache_ready's own memo),
    just triggered at runner construction instead of on the first
    cache-is-None dimension call.
    """
    dimensions, ctx = load_analysis_context(config)
    if config._classify_cache is None:
        config._classify_cache = {}
    estimates = _persist_dim_estimates(config, dimensions)
    dimensions, dim_counts = _order_by_backlog(dimensions, estimates, log=SHARED_LOG)

    cache = LocalFileBackend()
    ensure_cache_ready(cache.root)
    runner = DimensionRunner(cache=cache, log=SHARED_LOG)
    return dimensions, ctx, runner, dim_counts


def _consolidated_is_available(config: RunConfig, dimensions: list[str]) -> bool:
    """True when one all-dimensions pass is worth attempting.

    It needs more than one dimension to consolidate, more than one subagent
    to spread them over, and a non-api provider: local models lose coverage
    when asked for eight dimensions in a single prompt.
    """
    return (
        config.options.consolidated
        and len(dimensions) > 1
        and config.options.max_subagents > 1
        and _get_provider_type(config.ai_cmd) != "api"
    )


def _try_consolidated_mode(
    config: RunConfig,
    dimensions: list[str],
    ctx: _AnalysisContext,
) -> dict[str, Evidence] | None:
    """Attempt consolidated (all-dimensions-in-one-pass) mode; None to fall back.

    Disabled for API providers — per-dimension gives better coverage since
    local models struggle with 8 dimensions in one prompt.
    """
    if not _consolidated_is_available(config, dimensions):
        return None
    try:
        result = process_consolidated_dimensions(
            config, dimensions, ctx, log=SHARED_LOG,
        )
        if result:
            dim_index = {d: i + 1 for i, d in enumerate(dimensions)}
            for dim, ev in result.items():
                idx = dim_index.get(dim, 0)
                _log_dimension_result(ev, dim, idx, len(dimensions), log=SHARED_LOG)
            return result
        log_warning("Consolidated mode produced no results, falling back to per-dimension")
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        log_warning(f"Consolidated mode failed: {exc}, falling back to per-dimension")
    return None


def _dispatch_fixed_mode(
    config: RunConfig,
    dimensions: list[str],
    ctx: _AnalysisContext,
    runner: DimensionRunner,
    on_dimension_done: "Callable[[str, Evidence], None] | None",
    *,
    dim_counts: dict[str, int] | None = None,
) -> dict[str, Evidence] | None:
    """Diff-mode or incremental-mode dispatch; None falls through to clean-scan.

    Diff mode always per-dimension — consolidated/incremental loops are
    incompatible with evidence-only runs (no prior fingerprint, no
    cross-dimension scoring).
    """
    if config.options.diff_from:
        emit_marker(CC_PHASE_SETUP, dimensions=dimensions)
        return run_per_dimension_loop(
            config, dimensions, ctx,
            default_loop_deps(runner, on_dimension_done, SHARED_LOG),
        )
    if config.options.incremental:
        # Default path. AnalysisOptions.incremental defaults to True so
        # any run that hasn't explicitly opted out (via --clean-scan or
        # --diff-from at the CLI/API layer) carries forward findings for
        # unchanged files via per-dimension fingerprint lookup.
        emit_marker(CC_PHASE_SETUP, dimensions=dimensions)
        return run_incremental_loop(
            config, dimensions, ctx,
            default_loop_deps(runner, on_dimension_done, SHARED_LOG),
            dim_counts=dim_counts,
        )
    return None


def _run_clean_scan(
    config: RunConfig,
    dimensions: list[str],
    ctx: _AnalysisContext,
    runner: DimensionRunner,
    on_dimension_done: "Callable[[str, Evidence], None] | None",
) -> dict[str, Evidence]:
    """Full re-analysis with no carry-forward, consolidated where possible.

    Reached only for --clean-scan or --diff-from. Consolidated mode is
    allowed here because there is no prior fingerprint to honour.
    """
    emit_marker(CC_PHASE_SETUP, dimensions=dimensions)
    consolidated_result = _try_consolidated_mode(config, dimensions, ctx)
    if consolidated_result is not None:
        return consolidated_result
    return run_per_dimension_loop(
        config, dimensions, ctx,
        default_loop_deps(runner, on_dimension_done, SHARED_LOG),
    )


def _run_dimensions(
    config: RunConfig,
    on_dimension_done: "Callable[[str, Evidence], None] | None" = None,
) -> dict[str, Evidence]:
    """Run AI analysis for each dimension and return per-dimension Evidence."""
    if config.options.dry_run:
        return _run_dry_run(config, on_dimension_done=on_dimension_done)

    _warn_if_local_api_oversubscribed(config, log=SHARED_LOG)

    dimensions, ctx, runner, dim_counts = _prepare_run_context(config)
    _set_run_deadline(config)

    fixed_mode_result = _dispatch_fixed_mode(
        config, dimensions, ctx, runner, on_dimension_done, dim_counts=dim_counts,
    )
    if fixed_mode_result is not None:
        return fixed_mode_result

    return _run_clean_scan(config, dimensions, ctx, runner, on_dimension_done)


def run(config: RunConfig) -> Evidence:
    """Orchestrate: load dimensions -> per-dimension AI analysis -> merged Evidence."""
    return merge_evidence(
        list(_run_dimensions(config).values()),
        source_file_count=config.source_file_count,
        src=str(config.src),
        language=config.language,
    )


def run_per_dimension(
    config: RunConfig,
    on_dimension_done: "Callable[[str, Evidence], None] | None" = None,
) -> dict[str, Evidence]:
    """Like run(), but returns a dict of {dimension_id: Evidence} without merging."""
    return _run_dimensions(config, on_dimension_done=on_dimension_done)
