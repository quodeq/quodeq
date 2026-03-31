"""Runner — orchestrates the AI-driven exploration pipeline.

Per dimension: build prompt → run AI analysis → extract JSONL → parse Evidence.
Merge per-dimension Evidence into a single Evidence object.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.analysis._dimensions import (
    DimensionEntry as DimensionEntry,
    DimensionsConfig as DimensionsConfig,
    load_universal_dimensions as load_universal_dimensions,
)
from quodeq.analysis._types import (  # noqa: F401 — re-export
    AnalysisOptions as AnalysisOptions,
    RunConfig as RunConfig,
    _AnalysisContext as _AnalysisContext,
)
from quodeq.analysis.manifest import AnalysisTarget, SourceManifest
from quodeq.analysis.subprocess import AnalysisConfig, HeartbeatCallback, count_files_from_stream, run_analysis
from quodeq.analysis.stream.parser import extract_evidence_from_stream
from quodeq.analysis.stream.validation import get_mcp_status, is_stream_valid
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.merge import merge_evidence
from quodeq.engine._runner_markers import CC_MARKER_KEY, cleanup_stream, emit_marker, make_heartbeat
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.analysis.prompts.builder import PromptContext, build_analysis_prompt
from quodeq.analysis.subagents.runner import DimensionCallbacks, process_dimension_with_subagents
from quodeq.shared.logging import log_info, log_success, log_warning
from quodeq.shared.validation import validate_path_segment


def _build_dimension_prompt(
    config: RunConfig, dim_id: str, ctx: _AnalysisContext,
) -> str:
    """Build the analysis prompt for a single dimension."""
    return build_analysis_prompt(
        ctx.template,
        PromptContext(
            language=config.language,
            repo_name=str(config.src),
            date_str=ctx.date_str,
            dimension=dim_id,
            source_file_count=config.source_file_count,
            dimensions_data=ctx.dimensions_data,
            standards_dir=config.standards_dir,
            evaluators_dir=config.evaluators_dir,
            manifest=config.manifest,
            target=config.target,
            work_dir=config.work_dir or config.src,
        ),
    )


def _run_dimension_analysis(
    config: RunConfig, dim_id: str, prompt: str,
    idx: int, ctx: _AnalysisContext,
) -> tuple[Path, Path]:
    """Run the AI analysis subprocess for a single dimension.

    Returns (stream_file, jsonl_file).
    """
    evidence_dir = config.work_dir or config.src
    stream_file = evidence_dir / f"{dim_id}_live.stream"
    jsonl_file = evidence_dir / f"{dim_id}_evidence.jsonl"

    heartbeat = config.options.heartbeat_callback or make_heartbeat(dim_id, idx, ctx.total)

    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    ac_kwargs: dict[str, Any] = dict(
        jsonl_file=jsonl_file,
        analysis_budget=config.options.analysis_budget,
        heartbeat_callback=heartbeat,
        compiled_dir=compiled_dir,
        dimension=dim_id,
    )
    if config.options.max_turns is not None:
        ac_kwargs["max_turns"] = config.options.max_turns
    if config.options.max_duration is not None:
        ac_kwargs["max_duration"] = config.options.max_duration
    if config.options.pool_budget is not None:
        ac_kwargs["pool_budget"] = config.options.pool_budget
    run_analysis(
        work_dir=config.src,
        prompt=prompt,
        stream_file=stream_file,
        config=AnalysisConfig(**ac_kwargs),
    )
    return stream_file, jsonl_file


def _try_parse_stream_evidence(stream_file: Path, jsonl_file: Path) -> int:
    """Resolve files_read from MCP output or fall back to stream extraction.

    Returns the number of files read.
    """
    mcp_produced = jsonl_file.exists() and jsonl_file.stat().st_size > 0
    mcp_status = get_mcp_status(stream_file)
    if mcp_status and mcp_status != "connected":
        log_warning(f"MCP findings server {mcp_status} — falling back to stream extraction")
    if mcp_produced:
        return count_files_from_stream(stream_file)
    return extract_evidence_from_stream(stream_file, jsonl_file)


def _parse_dimension_evidence(
    config: RunConfig, dim_id: str, stream_file: Path, jsonl_file: Path,
    ctx: _AnalysisContext,
) -> Evidence | None:
    """Extract and parse evidence from stream/JSONL files for a single dimension.

    Returns Evidence or None if the stream is invalid.
    """
    if not is_stream_valid(stream_file):
        return None

    files_read = _try_parse_stream_evidence(stream_file, jsonl_file)

    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    return parse_jsonl_to_evidence(
        jsonl_file,
        EvidenceContext(
            language=config.language,
            repository=str(config.src),
            date_str=ctx.date_str,
            source_file_count=config.source_file_count,
            files_read=files_read,
            module=config.target.name if config.target else "",
        ),
        compiled_dir=compiled_dir,
        evaluators_dir=config.evaluators_dir,
    )


def load_analysis_context(config: RunConfig) -> tuple[list[str], _AnalysisContext]:
    """Load dimensions data and resolve which dimensions to analyze."""
    from quodeq.analysis._incremental import load_analysis_context as _load_ctx
    return _load_ctx(config)


class EvaluationError(RuntimeError):
    """Raised when an evaluation completes but produces no usable findings."""


def _save_dimension_fingerprint(
    config: RunConfig, dimension: str, files: list[str] | None = None,
    analyzed_files: set[str] | None = None,
) -> None:
    """Save a fingerprint after any successful dimension analysis."""
    from quodeq.analysis._incremental import save_dimension_fingerprint
    save_dimension_fingerprint(config, dimension, files, analyzed_files)


def _log_dimension_result(ev: Evidence, dimension: str, idx: int, total: int) -> None:
    """Emit scoring marker and log summary for a completed dimension."""
    emit_marker("scoring", dimension=dimension)
    violations = sum(len(pe.violations) for pe in ev.principles.values())
    compliances = sum(len(pe.compliance) for pe in ev.principles.values())
    log_success(f"[{idx}/{total}] {dimension} — {ev.files_read} files, {violations}v/{compliances}c")


def _process_single_dimension(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
    *, emit_log: bool = True,
) -> Evidence | None:
    """Analyze a single dimension: build prompt, run AI, parse evidence."""
    if emit_log:
        emit_marker("analyzing", dimension=dimension)
        log_info(f"→ [{idx}/{ctx.total}] Analyzing {dimension}")

    if config.options.max_subagents > 1:
        ev = process_dimension_with_subagents(
            config, dimension, idx, ctx,
            callbacks=DimensionCallbacks(
                build_prompt=_build_dimension_prompt,
                run_analysis=_run_dimension_analysis,
                parse_evidence=_parse_dimension_evidence,
            ),
        )
    else:
        prompt = _build_dimension_prompt(config, dimension, ctx)
        stream_file, jsonl_file = _run_dimension_analysis(config, dimension, prompt, idx, ctx)
        ev = _parse_dimension_evidence(config, dimension, stream_file, jsonl_file, ctx)

    if ev is None:
        log_warning(f"[{idx}/{ctx.total}] {dimension} — no valid evidence, skipping")
        return None

    _save_dimension_fingerprint(config, dimension)
    if emit_log:
        _log_dimension_result(ev, dimension, idx, ctx.total)
    return ev


def _run_dimension_incremental(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
) -> Evidence | None:
    """Incremental path: detect changes, carry forward, analyze only changed files."""
    from quodeq.analysis._incremental import run_dimension_incremental
    return run_dimension_incremental(config, dimension, idx, ctx)


def _run_dimensions(config: RunConfig) -> dict[str, Evidence]:
    """Run AI analysis for each dimension and return per-dimension Evidence."""
    from quodeq.analysis._incremental import (
        run_incremental_loop, run_per_dimension_loop,
    )

    dimensions, ctx = load_analysis_context(config)

    if config.options.incremental:
        emit_marker("setup", dimensions=dimensions)
        return run_incremental_loop(config, dimensions, ctx)

    emit_marker("setup", dimensions=dimensions)

    # Consolidated mode: evaluate all dimensions in one pass
    if (config.options.consolidated
            and len(dimensions) > 1
            and config.options.max_subagents > 1):
        from quodeq.analysis.subagents.runner import process_consolidated_dimensions
        try:
            result = process_consolidated_dimensions(config, dimensions, ctx)
            if result:
                for dim, ev in result.items():
                    idx = dimensions.index(dim) + 1 if dim in dimensions else 0
                    _log_dimension_result(ev, dim, idx, len(dimensions))
                return result
            log_warning("Consolidated mode produced no results, falling back to per-dimension")
        except (OSError, KeyError, ValueError, RuntimeError) as exc:
            log_warning(f"Consolidated mode failed: {exc}, falling back to per-dimension")

    return run_per_dimension_loop(config, dimensions, ctx)


def run(config: RunConfig) -> Evidence:
    """Orchestrate: load dimensions → per-dimension AI analysis → merged Evidence."""
    return merge_evidence(
        list(_run_dimensions(config).values()),
        source_file_count=config.source_file_count,
        src=str(config.src),
        language=config.language,
    )


def run_per_dimension(config: RunConfig) -> dict[str, Evidence]:
    """Like run(), but returns a dict of {dimension_id: Evidence} without merging."""
    return _run_dimensions(config)
