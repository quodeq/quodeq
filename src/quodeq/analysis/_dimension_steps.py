"""Dimension step functions: prompt building, AI execution, evidence parsing."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.subprocess import AnalysisConfig, count_files_from_stream, run_analysis
from quodeq.analysis.stream.parser import extract_evidence_from_stream
from quodeq.analysis.stream.validation import get_mcp_status, is_stream_valid
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.analysis.prompts.builder import PromptContext, build_analysis_prompt
from quodeq.engine._runner_markers import make_heartbeat
from quodeq.shared.logging import log_warning


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
        ai_model=config.options.ai_model,
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
    if config.options.deadline_at is not None:
        ac_kwargs["deadline_at"] = config.options.deadline_at
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
