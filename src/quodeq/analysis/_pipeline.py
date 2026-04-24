"""Pipeline coordination — dimension orchestration, merging, and public API."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

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


def _run_dimensions(
    config: RunConfig,
    on_dimension_done: "Callable[[str, Evidence], None] | None" = None,
) -> dict[str, Evidence]:
    """Run AI analysis for each dimension and return per-dimension Evidence."""
    if config.options.dry_run:
        return _run_dry_run(config, on_dimension_done=on_dimension_done)

    dimensions, ctx = load_analysis_context(config)

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
        emit_marker("setup", dimensions=dimensions)
        return run_incremental_loop(
            config, dimensions, ctx,
            process_fn=_process_single_dimension,
            log_result_fn=_log_dimension_result,
            on_dimension_done=on_dimension_done,
        )

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
