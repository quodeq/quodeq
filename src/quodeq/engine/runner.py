"""Runner — orchestrates the AI-driven exploration pipeline.

Pipeline per dimension:
    1. Build prompt (prompt_builder)
    2. Run AI analysis (analysis.py — spawn AI CLI)
    3. Extract JSONL from stream
    4. Parse into Evidence (evidence_parser)
Merge per-dimension Evidence into a single Evidence object.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, TypedDict

from quodeq.engine.analysis import AnalysisConfig, HeartbeatCallback, count_files_from_stream, run_analysis
from quodeq.engine.stream_parser import extract_evidence_from_stream
from quodeq.engine.stream_validation import get_mcp_status, is_stream_valid
from quodeq.engine.evidence import Evidence, PrincipleEvidence
from quodeq.engine.evidence_parser import EvidenceContext, parse_jsonl_to_evidence

from quodeq.engine.plugin_loader import load_plugin_full
from quodeq.engine.prompt_builder import PromptContext, build_analysis_prompt, load_template
from quodeq.shared.logging import log_info, log_success, log_warning


@dataclass
class AnalysisOptions:
    """Optional runtime settings for an evaluation run."""
    analysis_budget: str | None = None
    heartbeat_callback: HeartbeatCallback | None = None
    template_path: Path | None = None
    dimensions: list[str] | None = None
    max_turns: int | None = None
    max_duration: int | None = None


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


CC_MARKER_KEY = "_cc"  # shared constant for structured job-tracking markers


class _MarkerFields(TypedDict, total=False):
    """Fields that may appear in a structured JSON marker."""
    dimension: str
    dimensions: list[str]


def _emit_marker(phase: str, **kwargs: _MarkerFields) -> None:
    """Emit a structured JSON marker for job tracking.

    Only emitted when stdout is captured by the job manager (not a TTY).
    """
    if sys.stdout.isatty():
        return
    print(json.dumps({CC_MARKER_KEY: phase, **kwargs}), flush=True)


def _make_heartbeat(dim_name: str, idx: int, total: int, src_count: int) -> Callable[[int, dict], None]:
    """Return a heartbeat callback that prints progress to stdout."""
    def _cb(elapsed: int, progress: dict) -> None:
        secs = elapsed % 60
        mins = elapsed // 60
        files = progress.get("files_read", 0)
        evidence = progress.get("evidence", 0)
        pct_str = f" ({min(round(files / src_count * 100), 100)}%)" if src_count > 0 else ""
        log_info(f"  [{idx}/{total}] {dim_name} | {mins}m{secs:02d}s | {files} files{pct_str} | {evidence} findings")
    return _cb


def cleanup_stream(stream_file: Path) -> None:
    """Remove stream and stderr files after successful evidence extraction."""
    stream_file.unlink(missing_ok=True)
    err_file = Path(str(stream_file) + ".err")
    err_file.unlink(missing_ok=True)


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

    heartbeat = config.options.heartbeat_callback or _make_heartbeat(dim_id, idx, ctx.total, config.source_file_count)

    ac_kwargs: dict = dict(
        jsonl_file=jsonl_file,
        analysis_budget=config.options.analysis_budget,
        heartbeat_callback=heartbeat,
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

    ev = parse_jsonl_to_evidence(
        jsonl_file,
        EvidenceContext(
            plugin_id=config.plugin_id,
            repository=str(config.src),
            date_str=ctx.date_str,
            source_file_count=config.source_file_count,
            files_read=files_read,
        ),
        standards_dir=config.standards_dir,
    )
    ev.plugin_name = ctx.plugin_name
    return ev


def _load_plugin_context(config: RunConfig) -> tuple[list[str], _PluginContext]:
    """Load plugin data and resolve which dimensions to analyze."""
    plugin_dir = config.evaluators_dir / config.plugin_id
    if not plugin_dir.exists():
        raise ValueError(f"Plugin directory not found: {plugin_dir}")

    full = load_plugin_full(plugin_dir)
    analysis_file = plugin_dir / "knowledge" / "analysis.md"
    all_dims_raw = [d["id"] for d in full["dimensions"].get("applies", [])]
    dimensions = [d for d in all_dims_raw if d in config.options.dimensions] if config.options.dimensions else all_dims_raw

    ctx = _PluginContext(
        dimensions_data=full["dimensions"],
        analysis_md=analysis_file.read_text() if analysis_file.exists() else "",
        date_str=datetime.now().isoformat(timespec="seconds"),
        template=load_template(config.options.template_path),
        plugin_name=full["plugin"].get("name", config.plugin_id),
        total=len(dimensions),
    )
    return dimensions, ctx


class EvaluationError(RuntimeError):
    """Raised when an evaluation completes but produces no usable findings."""


def _run_dimensions(config: RunConfig) -> dict[str, Evidence]:
    """Run AI analysis for each dimension and return per-dimension Evidence."""
    dimensions, ctx = _load_plugin_context(config)
    result: dict[str, Evidence] = {}
    _emit_marker("setup", dimensions=dimensions)
    skipped_count = 0

    for idx, dimension in enumerate(dimensions, 1):
        _emit_marker("analyzing", dimension=dimension)
        log_info(f"→ [{idx}/{ctx.total}] Analyzing {dimension}")

        prompt = _build_dimension_prompt(config, dimension, ctx)
        stream_file, jsonl_file = _run_dimension_analysis(config, dimension, prompt, idx, ctx)

        ev = _parse_dimension_evidence(config, dimension, stream_file, jsonl_file, ctx)
        if ev is None:
            log_warning(f"[{idx}/{ctx.total}] {dimension} — no valid stream, skipping")
            skipped_count += 1
            continue

        _emit_marker("scoring", dimension=dimension)
        violations = sum(len(pe.violations) for pe in ev.principles.values())
        compliances = sum(len(pe.compliance) for pe in ev.principles.values())
        log_success(f"[{idx}/{ctx.total}] {dimension} — {ev.files_read} files, {violations}v/{compliances}c")
        result[dimension] = ev

    # Guard: an evaluation that ran on a real project but produced zero findings
    # across all dimensions is almost certainly broken (e.g. tools blocked,
    # permissions misconfigured). Only trigger when there were source files to
    # analyze and at least one dimension had a valid stream (result is non-empty).
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
    return _merge_evidence(list(_run_dimensions(config).values()), config)


def run_per_dimension(config: RunConfig) -> dict[str, Evidence]:
    """Like run(), but returns a dict of {dimension_id: Evidence} without merging."""
    return _run_dimensions(config)


def _merge_evidence(evidence_list: list[Evidence], config: RunConfig) -> Evidence:
    """Merge per-dimension Evidence objects into a single Evidence."""
    merged_principles: dict[str, PrincipleEvidence] = {}
    total_files_read = 0
    total_dismissed = 0

    for ev in evidence_list:
        total_files_read = max(total_files_read, ev.files_read)
        total_dismissed += ev.dismissed_count
        for pid, pe in ev.principles.items():
            if pid in merged_principles:
                existing = merged_principles[pid]
                existing.violations.extend(pe.violations)
                existing.compliance.extend(pe.compliance)
                existing.compute_metrics()
            else:
                merged_principles[pid] = pe

    coverage_pct = (
        round(total_files_read / config.source_file_count * 100, 1)
        if config.source_file_count > 0
        else 0.0
    )

    merged = Evidence(
        repository=str(config.src),
        plugin_id=config.plugin_id,
        date=evidence_list[0].date if evidence_list else "",
        source_file_count=config.source_file_count,
        files_read=total_files_read,
        coverage_pct=coverage_pct,
        principles=merged_principles,
        dismissed_count=total_dismissed,
    )
    if evidence_list:
        merged.plugin_name = evidence_list[0].plugin_name
    return merged
