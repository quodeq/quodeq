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

from quodeq.engine.analysis import count_files_from_stream, run_analysis
from quodeq.engine.stream_parser import extract_evidence_from_stream
from quodeq.engine.stream_validation import get_mcp_status, is_stream_valid
from quodeq.engine.evidence import Evidence, PrincipleEvidence
from quodeq.engine.evidence_parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.engine.plugin_detector import count_source_files, detect_plugin  # noqa: F401
from quodeq.engine.plugin_loader import load_plugin_full
from quodeq.engine.prompt_builder import PromptContext, build_analysis_prompt, load_template


@dataclass
class AnalysisOptions:
    """Optional runtime settings for an evaluation run."""
    analysis_budget: str | None = None
    heartbeat_callback: object | None = None
    template_path: Path | None = None
    dimensions: list[str] | None = None


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
        print(f"  [{idx}/{total}] {dim_name} | {mins}m{secs:02d}s | {files} files{pct_str} | {evidence} findings", flush=True)
    return _cb


def _cleanup_stream(stream_file: Path) -> None:
    """Remove stream and stderr files after successful evidence extraction."""
    stream_file.unlink(missing_ok=True)
    err_file = Path(str(stream_file) + ".err")
    err_file.unlink(missing_ok=True)


def _build_dimension_prompt(
    config: RunConfig, dim_id: str, dimensions_data: dict,
    analysis_md: str, date_str: str, template: str,
) -> str:
    """Build the analysis prompt for a single dimension."""
    return build_analysis_prompt(
        template,
        PromptContext(
            plugin_id=config.plugin_id,
            repo_name=str(config.src),
            date_str=date_str,
            dimension=dim_id,
            source_file_count=config.source_file_count,
            dimensions_data=dimensions_data,
            analysis_md=analysis_md,
            standards_dir=config.standards_dir,
        ),
    )


def _run_dimension_analysis(
    config: RunConfig, dim_id: str, prompt: str, evidence_dir: Path,
    idx: int, total: int,
) -> tuple[Path, Path]:
    """Run the AI analysis subprocess for a single dimension.

    Returns (stream_file, jsonl_file).
    """
    stream_file = evidence_dir / f"{dim_id}_live.stream"
    jsonl_file = evidence_dir / f"{dim_id}_evidence.jsonl"

    heartbeat = config.options.heartbeat_callback or _make_heartbeat(dim_id, idx, total, config.source_file_count)

    run_analysis(
        work_dir=config.src,
        prompt=prompt,
        stream_file=stream_file,
        jsonl_file=jsonl_file,
        analysis_budget=config.options.analysis_budget,
        heartbeat_callback=heartbeat,
    )
    return stream_file, jsonl_file


def _parse_dimension_evidence(
    config: RunConfig, dim_id: str, stream_file: Path, jsonl_file: Path,
    date_str: str, plugin_name: str,
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
        print(f"  MCP findings server {mcp_status} — falling back to stream extraction", flush=True)
    if mcp_produced:
        files_read = count_files_from_stream(stream_file)
    else:
        files_read = extract_evidence_from_stream(stream_file, jsonl_file)

    ev = parse_jsonl_to_evidence(
        jsonl_file,
        EvidenceContext(
            plugin_id=config.plugin_id,
            repository=str(config.src),
            date_str=date_str,
            source_file_count=config.source_file_count,
            files_read=files_read,
        ),
        standards_dir=config.standards_dir,
    )
    ev.plugin_name = plugin_name
    return ev


def _run_dimensions(config: RunConfig) -> dict[str, Evidence]:
    """Run AI analysis for each dimension and return per-dimension Evidence."""
    plugin_dir = config.evaluators_dir / config.plugin_id
    if not plugin_dir.exists():
        raise ValueError(f"Plugin directory not found: {plugin_dir}")

    full = load_plugin_full(plugin_dir)
    template = load_template(config.options.template_path)
    date_str = datetime.now().isoformat(timespec="seconds")

    analysis_file = plugin_dir / "knowledge" / "analysis.md"
    analysis_md = analysis_file.read_text() if analysis_file.exists() else ""

    all_dims = [d["id"] for d in full["dimensions"].get("applies", [])]
    if config.options.dimensions:
        dimensions = [d for d in all_dims if d in config.options.dimensions]
    else:
        dimensions = all_dims
    work_dir = config.work_dir or config.src

    result: dict[str, Evidence] = {}
    total = len(dimensions)
    plugin_name = full["plugin"].get("name", config.plugin_id)
    _emit_marker("setup", dimensions=dimensions)

    for idx, dimension in enumerate(dimensions, 1):
        _emit_marker("analyzing", dimension=dimension)
        print(f"→ [{idx}/{total}] Analyzing {dimension}", flush=True)

        prompt = _build_dimension_prompt(config, dimension, full["dimensions"], analysis_md, date_str, template)
        stream_file, jsonl_file = _run_dimension_analysis(config, dimension, prompt, work_dir, idx, total)

        ev = _parse_dimension_evidence(config, dimension, stream_file, jsonl_file, date_str, plugin_name)
        if ev is None:
            print(f"  [{idx}/{total}] {dimension} — no valid stream, skipping", flush=True)
            continue

        _emit_marker("scoring", dimension=dimension)
        violations = sum(len(pe.violations) for pe in ev.principles.values())
        compliances = sum(len(pe.compliance) for pe in ev.principles.values())
        print(f"✓ [{idx}/{total}] {dimension} — {ev.files_read} files, {violations}v/{compliances}c", flush=True)
        result[dimension] = ev

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


def run_full(config: RunConfig, output_dir: Path, mode: str = "numerical") -> dict:
    """Full pipeline: run per-dimension → score each → write per-dimension reports.

    Returns dict of {dimension: overall_score_str}.
    """
    from quodeq.engine.scoring import score_evidence
    from quodeq.engine.report import write_dimension_report

    work_dir = config.work_dir or config.src
    per_dim_evidence = run_per_dimension(config)
    results: dict[str, str] = {}

    for dimension, evidence in per_dim_evidence.items():
        scores = score_evidence(evidence, mode=mode)
        write_dimension_report(evidence, scores, dimension, output_dir)
        # Clean up stream now that the eval JSON exists
        _cleanup_stream(work_dir / f"{dimension}_live.stream")
        overall = scores.get("overall", {})
        if mode == "numerical":
            val = overall.get("weighted_score")
            results[dimension] = f"{val}/10" if val is not None else "N/A"
        else:
            results[dimension] = overall.get("weighted_grade", "N/A")

    return results
