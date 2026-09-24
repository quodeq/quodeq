"""Dimension step functions: prompt building, AI execution, evidence parsing."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.analysis.run_types import RunConfig, AnalysisContext
from quodeq.analysis.subprocess import AnalysisConfig, count_files_from_stream, run_analysis
from quodeq.analysis.stream.parser import extract_evidence_from_stream
from quodeq.analysis.stream.validation import get_mcp_status, is_stream_valid
from quodeq.analysis.evidence_parser import parse_evidence_file
from quodeq.core.evidence.model import Evidence
from quodeq.analysis.prompts.builder import build_analysis_prompt, prompt_context
from quodeq.analysis.runner_markers import make_heartbeat
from quodeq.data.fs.run_files import evidence_file_size
from quodeq.shared.logging import log_warning


def build_dimension_prompt(
    config: RunConfig, dim_id: str, ctx: AnalysisContext,
) -> str:
    """Build the analysis prompt for a single dimension."""
    return build_analysis_prompt(ctx.template, prompt_context(config, ctx, dim_id))


def run_dimension_analysis(
    config: RunConfig, dim_id: str, prompt: str,
    idx: int, ctx: AnalysisContext,
) -> tuple[Path, Path]:
    """Run the AI analysis subprocess for a single dimension.

    Returns (stream_file, jsonl_file).
    """
    evidence_dir = config.work_dir or config.src
    stream_file = evidence_dir / f"{dim_id}_live.stream"
    jsonl_file = evidence_dir / f"{dim_id}_evidence.jsonl"

    heartbeat = config.options.heartbeat_callback or make_heartbeat(dim_id, idx, ctx.total)

    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    opts = config.options
    ac_kwargs: dict[str, Any] = dict(
        ai_cmd=config.ai_cmd,
        ai_cmd_path=config.options.ai_cmd_path,
        cache_root=config.options.cache_root,
        ai_model=config.options.ai_model,
        jsonl_file=jsonl_file,
        analysis_budget=config.options.analysis_budget,
        heartbeat_callback=heartbeat,
        compiled_dir=compiled_dir,
        dimension=dim_id,
        # The run's single-agent ceilings apply when no explicit cap was set.
        max_turns=opts.max_turns if opts.max_turns is not None else opts.default_max_turns,
        max_duration=opts.max_duration if opts.max_duration is not None else opts.default_max_duration,
    )
    # Left out rather than passed as None so AnalysisConfig's own defaults win
    # for every budget the run did not set.
    for name in ("time_limit", "deadline_at"):
        value = getattr(config.options, name)
        if value is not None:
            ac_kwargs[name] = value
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
    mcp_produced = evidence_file_size(jsonl_file) > 0
    mcp_status = get_mcp_status(stream_file)
    if mcp_status and mcp_status != "connected":
        log_warning(f"MCP findings server {mcp_status} — falling back to stream extraction")
    if mcp_produced:
        return count_files_from_stream(stream_file)
    return extract_evidence_from_stream(stream_file, jsonl_file)


def parse_dimension_evidence(
    config: RunConfig, _dim_id: str, stream_file: Path, jsonl_file: Path,
    ctx: AnalysisContext,
) -> Evidence | None:
    """Extract and parse evidence from stream/JSONL files for a single dimension.

    Returns Evidence or None if the stream is invalid.
    """
    if not is_stream_valid(stream_file):
        return None

    files_read = _try_parse_stream_evidence(stream_file, jsonl_file)
    return parse_evidence_file(config, ctx, jsonl_file, files_read)
