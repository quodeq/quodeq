"""Runner — orchestrates the AI-driven exploration pipeline.

Per dimension: build prompt → run AI analysis → extract JSONL → parse Evidence.
Merge per-dimension Evidence into a single Evidence object.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quodeq.engine.analysis import AnalysisConfig, HeartbeatCallback, count_files_from_stream, run_analysis
from quodeq.engine.stream_parser import extract_evidence_from_stream
from quodeq.engine.stream_validation import get_mcp_status, is_stream_valid
from quodeq.engine.evidence import Evidence
from quodeq.engine._merge import merge_evidence
from quodeq.engine._runner_markers import CC_MARKER_KEY, cleanup_stream, emit_marker, make_heartbeat
from quodeq.engine.evidence_parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.engine.plugin_loader import load_plugin_full
from quodeq.engine.prompt_builder import PromptContext, build_analysis_prompt, load_template
from quodeq.shared.logging import log_info, log_success, log_warning
from quodeq.shared.validation import validate_path_segment


@dataclass
class AnalysisOptions:
    """Optional runtime settings for an evaluation run."""
    analysis_budget: str | None = None
    heartbeat_callback: HeartbeatCallback | None = None
    template_path: Path | None = None
    dimensions: list[str] | None = None
    max_turns: int | None = None
    max_duration: int | None = None
    n_subagents: int = 1
    subagent_model: str | None = None


@dataclass
class RunConfig:
    """Configuration for a single evaluation run (source path, plugin, options)."""
    src: Path
    plugin_id: str
    evaluators_dir: Path
    standards_dir: Path | None = None
    source_file_count: int = 0
    work_dir: Path | None = None
    options: AnalysisOptions = field(default_factory=AnalysisOptions)




@dataclass(frozen=True)
class _PluginContext:
    """Pre-loaded plugin data reused across dimensions."""
    dimensions_data: dict
    analysis_md: str
    date_str: str
    template: str
    plugin_name: str
    total: int


def _build_dimension_prompt(
    config: RunConfig, dim_id: str, ctx: _PluginContext,
) -> str:
    """Build the analysis prompt for a single dimension."""
    return build_analysis_prompt(
        ctx.template,
        PromptContext(
            plugin_id=config.plugin_id,
            repo_name=str(config.src),
            date_str=ctx.date_str,
            dimension=dim_id,
            source_file_count=config.source_file_count,
            dimensions_data=ctx.dimensions_data,
            analysis_md=ctx.analysis_md,
            standards_dir=config.standards_dir,
        ),
    )


def _run_dimension_analysis(
    config: RunConfig, dim_id: str, prompt: str,
    idx: int, ctx: _PluginContext,
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
    run_analysis(
        work_dir=config.src,
        prompt=prompt,
        stream_file=stream_file,
        config=AnalysisConfig(**ac_kwargs),
    )
    return stream_file, jsonl_file


def _parse_dimension_evidence(
    config: RunConfig, dim_id: str, stream_file: Path, jsonl_file: Path,
    ctx: _PluginContext,
) -> Evidence | None:
    """Extract and parse evidence from stream/JSONL files for a single dimension.

    Returns Evidence or None if the stream is invalid.
    """
    if not is_stream_valid(stream_file):
        return None

    # MCP server writes findings directly to jsonl_file during analysis.
    # Fall back to stream extraction if MCP produced nothing.
    mcp_produced = jsonl_file.exists() and jsonl_file.stat().st_size > 0
    mcp_status = get_mcp_status(stream_file)
    if mcp_status and mcp_status != "connected":
        log_warning(f"MCP findings server {mcp_status} — falling back to stream extraction")
    if mcp_produced:
        files_read = count_files_from_stream(stream_file)
    else:
        files_read = extract_evidence_from_stream(stream_file, jsonl_file)

    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    ev = parse_jsonl_to_evidence(
        jsonl_file,
        EvidenceContext(
            plugin_id=config.plugin_id,
            repository=str(config.src),
            date_str=ctx.date_str,
            source_file_count=config.source_file_count,
            files_read=files_read,
        ),
        compiled_dir=compiled_dir,
    )
    ev.plugin_name = ctx.plugin_name
    return ev


def _process_dimension_with_subagents(
    config: RunConfig, dim_id: str, idx: int, ctx: _PluginContext,
) -> Evidence | None:
    """Run dimension analysis using N parallel subagents (delegates to _subagent_runner)."""
    from quodeq.engine._subagent_runner import DimensionCallbacks, process_dimension_with_subagents
    return process_dimension_with_subagents(
        config, dim_id, idx, ctx,
        callbacks=DimensionCallbacks(
            build_prompt=_build_dimension_prompt,
            run_analysis=_run_dimension_analysis,
            parse_evidence=_parse_dimension_evidence,
        ),
    )


def _load_plugin_context(config: RunConfig) -> tuple[list[str], _PluginContext]:
    """Load plugin data and resolve which dimensions to analyze."""
    validate_path_segment(config.plugin_id)
    plugin_dir = config.evaluators_dir / config.plugin_id
    if not plugin_dir.exists():
        raise ValueError(f"Plugin directory not found: {plugin_dir}")

    full = load_plugin_full(plugin_dir)
    analysis_file = plugin_dir / "knowledge" / "analysis.md"
    all_dims_raw = [d.get("id") for d in full["dimensions"].get("applies", []) if d.get("id")]
    if config.options.dimensions:
        dimensions = [d for d in all_dims_raw if d in config.options.dimensions]
    else:
        dimensions = all_dims_raw

    ctx = _PluginContext(
        dimensions_data=full["dimensions"],
        analysis_md=analysis_file.read_text() if analysis_file.exists() else "",
        date_str=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        template=load_template(config.options.template_path),
        plugin_name=full["plugin"].get("name", config.plugin_id),
        total=len(dimensions),
    )
    return dimensions, ctx


class EvaluationError(RuntimeError):
    """Raised when an evaluation completes but produces no usable findings."""


def _log_dimension_result(ev: Evidence, dimension: str, idx: int, total: int) -> None:
    """Emit scoring marker and log summary for a completed dimension."""
    emit_marker("scoring", dimension=dimension)
    violations = sum(len(pe.violations) for pe in ev.principles.values())
    compliances = sum(len(pe.compliance) for pe in ev.principles.values())
    log_success(f"[{idx}/{total}] {dimension} — {ev.files_read} files, {violations}v/{compliances}c")


def _process_single_dimension(
    config: RunConfig, dimension: str, idx: int, ctx: _PluginContext,
) -> Evidence | None:
    """Analyze a single dimension: build prompt, run AI, parse evidence."""
    emit_marker("analyzing", dimension=dimension)
    log_info(f"→ [{idx}/{ctx.total}] Analyzing {dimension}")

    if config.options.n_subagents > 1:
        ev = _process_dimension_with_subagents(config, dimension, idx, ctx)
    else:
        prompt = _build_dimension_prompt(config, dimension, ctx)
        stream_file, jsonl_file = _run_dimension_analysis(config, dimension, prompt, idx, ctx)
        ev = _parse_dimension_evidence(config, dimension, stream_file, jsonl_file, ctx)

    if ev is None:
        log_warning(f"[{idx}/{ctx.total}] {dimension} — no valid evidence, skipping")
        return None

    _log_dimension_result(ev, dimension, idx, ctx.total)
    return ev


def _run_dimensions(config: RunConfig) -> dict[str, Evidence]:
    """Run AI analysis for each dimension and return per-dimension Evidence."""
    dimensions, ctx = _load_plugin_context(config)
    result: dict[str, Evidence] = {}
    emit_marker("setup", dimensions=dimensions)
    skipped_count = 0

    for idx, dimension in enumerate(dimensions, 1):
        try:
            ev = _process_single_dimension(config, dimension, idx, ctx)
        except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
            log_warning(f"[{idx}/{ctx.total}] {dimension} — failed: {exc}")
            skipped_count += 1
            continue
        if ev is None:
            skipped_count += 1
            continue
        result[dimension] = ev

    if result and config.source_file_count > 0:
        total_findings = sum(
            sum(len(pe.violations) + len(pe.compliance) for pe in ev.principles.values())
            for ev in result.values()
        )
        if total_findings == 0:
            raise EvaluationError(
                f"Evaluation produced 0 findings across {len(result)} dimensions "
                f"({skipped_count} skipped). This usually means the AI CLI could not "
                f"read files or report findings — check tool permissions and MCP configuration."
            )

    return result


def run(config: RunConfig) -> Evidence:
    """Orchestrate: load plugin → per-dimension AI analysis → merged Evidence."""
    return merge_evidence(
        list(_run_dimensions(config).values()),
        source_file_count=config.source_file_count,
        src=str(config.src),
        plugin_id=config.plugin_id,
    )


def run_per_dimension(config: RunConfig) -> dict[str, Evidence]:
    """Like run(), but returns a dict of {dimension_id: Evidence} without merging."""
    return _run_dimensions(config)
