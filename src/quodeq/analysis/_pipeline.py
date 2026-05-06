"""Pipeline coordination — dimension orchestration, merging, and public API."""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from quodeq.analysis._dim_estimates import compute_dim_estimates, write_dim_estimates
from quodeq.analysis._incremental_context import load_analysis_context as _load_ctx
from quodeq.analysis._loops import run_incremental_loop, run_per_dimension_loop
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis._dimension_ops import (
    _build_dimension_prompt,
    _log_dimension_result,
    _parse_dimension_evidence,
    _process_single_dimension,
    _run_dimension_analysis,
    _save_dimension_fingerprint,
)
from quodeq.analysis.errors import EvaluationError as EvaluationError  # re-export
from quodeq.analysis.subagents.runner import process_consolidated_dimensions
from quodeq.analysis.subprocess import _get_provider_type
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.merge import merge_evidence
from quodeq.engine._runner_markers import emit_marker
from quodeq.shared.logging import log_info, log_warning
from quodeq.shared.utils import get_ai_cmd


def load_analysis_context(config: RunConfig) -> tuple[list[str], _AnalysisContext]:
    """Load dimensions data and resolve which dimensions to analyze."""
    return _load_ctx(config)


def _run_dry_run(
    config: RunConfig,
    on_dimension_done: "Callable[[str, Evidence], None] | None" = None,
) -> dict[str, Evidence]:
    """Return empty Evidence per dimension without making any AI calls."""
    dimensions, ctx = load_analysis_context(config)
    emit_marker("setup", dimensions=dimensions)
    result: dict[str, Evidence] = {}
    date_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
    evidence_dir = config.work_dir or config.src
    for idx, dimension in enumerate(dimensions, 1):
        log_info(f"→ [{idx}/{ctx.total}] Dry-run: skipping AI call for {dimension}")
        emit_marker("analyzing", dimension=dimension)
        ev = Evidence(
            repository=str(config.src),
            language=config.language,
            date=date_str,
            source_file_count=config.source_file_count,
            files_read=0,
            coverage_pct=0.0,
        )
        _save_dimension_fingerprint(config, dimension, files=[], analyzed_files=set())
        jsonl_path = evidence_dir / f"{dimension}_evidence.jsonl"
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        if not jsonl_path.exists():
            jsonl_path.touch()
        emit_marker("scoring", dimension=dimension)
        result[dimension] = ev
        if on_dimension_done:
            on_dimension_done(dimension, ev)
    return result


def _persist_dim_estimates(config: RunConfig, dimensions: list[str]) -> None:
    """Compute and persist per-dim file estimates so the dashboard total
    is accurate before any dim starts. Best-effort: a failure here must
    not break the run — the UI will fall back to the project-wide ceiling.
    """
    if not config.work_dir:
        return  # dev mode (no run_dir) — nothing for the dashboard to read
    try:
        estimates = compute_dim_estimates(config, dimensions)
    except (OSError, ValueError, KeyError, RuntimeError):
        return
    write_dim_estimates(config.work_dir.parent, estimates)


def _run_dimensions(
    config: RunConfig,
    on_dimension_done: "Callable[[str, Evidence], None] | None" = None,
) -> dict[str, Evidence]:
    """Run AI analysis for each dimension and return per-dimension Evidence."""
    if config.options.dry_run:
        return _run_dry_run(config, on_dimension_done=on_dimension_done)

    dimensions, ctx = load_analysis_context(config)
    _persist_dim_estimates(config, dimensions)

    # Set the run-level deadline once, just before the dim loop starts.
    # Skipped for dry runs (already returned above), unlimited budget, or
    # when an outer caller (tests) has pre-set deadline_at.
    budget_s = config.options.time_limit
    if config.options.deadline_at is None and budget_s is not None and budget_s > 0:
        config.options.deadline_at = time.monotonic() + budget_s
        deadline_iso = (
            datetime.now(timezone.utc) + timedelta(seconds=budget_s)
        ).isoformat()
        emit_marker("analyzing_start", deadline_at=deadline_iso, budget_s=budget_s)

    # Diff mode always per-dimension — consolidated/incremental loops are
    # incompatible with evidence-only runs (no prior fingerprint, no
    # cross-dimension scoring). Explicit branch keeps intent clear even if
    # the consolidated fall-through later changes.
    if config.options.diff_from:
        emit_marker("setup", dimensions=dimensions)
        return run_per_dimension_loop(
            config, dimensions, ctx,
            process_fn=_process_single_dimension,
            on_dimension_done=on_dimension_done,
        )

    if config.options.incremental:
        # Default path. AnalysisOptions.incremental defaults to True so
        # any run that hasn't explicitly opted out (via --clean-scan or
        # --diff-from at the CLI/API layer) carries forward findings for
        # unchanged files via per-dimension fingerprint lookup.
        emit_marker("setup", dimensions=dimensions)
        return run_incremental_loop(
            config, dimensions, ctx,
            process_fn=_process_single_dimension,
            log_result_fn=_log_dimension_result,
            on_dimension_done=on_dimension_done,
        )

    # Clean-scan path: full re-analysis, no carry-forward. Reached only
    # when the user requested --clean-scan or --diff-from. Consolidated
    # mode is allowed here because there is no prior fingerprint to honour.
    emit_marker("setup", dimensions=dimensions)

    # Consolidated mode: evaluate all dimensions in one pass.
    # Disabled for API providers — per-dimension gives better coverage
    # since local models struggle with 8 dimensions in one prompt.
    _provider_type = _get_provider_type(get_ai_cmd())
    if (config.options.consolidated
            and len(dimensions) > 1
            and config.options.max_subagents > 1
            and _provider_type != "api"):
        try:
            result = process_consolidated_dimensions(config, dimensions, ctx)
            if result:
                dim_index = {d: i + 1 for i, d in enumerate(dimensions)}
                for dim, ev in result.items():
                    idx = dim_index.get(dim, 0)
                    _log_dimension_result(ev, dim, idx, len(dimensions))
                return result
            log_warning("Consolidated mode produced no results, falling back to per-dimension")
        except (OSError, KeyError, ValueError, RuntimeError) as exc:
            log_warning(f"Consolidated mode failed: {exc}, falling back to per-dimension")

    return run_per_dimension_loop(
        config, dimensions, ctx,
        process_fn=_process_single_dimension,
        on_dimension_done=on_dimension_done,
    )


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
