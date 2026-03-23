"""Runner — orchestrates the AI-driven exploration pipeline.

Per dimension: build prompt → run AI analysis → extract JSONL → parse Evidence.
Merge per-dimension Evidence into a single Evidence object.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quodeq.analysis._dimensions import (
    DimensionEntry as DimensionEntry,
    DimensionsConfig as DimensionsConfig,
    load_universal_dimensions as load_universal_dimensions,
)
from quodeq.analysis.manifest import AnalysisTarget, SourceManifest
from quodeq.analysis.subprocess import AnalysisConfig, HeartbeatCallback, count_files_from_stream, run_analysis
from quodeq.analysis.stream.parser import extract_evidence_from_stream
from quodeq.analysis.stream.validation import get_mcp_status, is_stream_valid
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.merge import merge_evidence
from quodeq.engine._runner_markers import CC_MARKER_KEY, cleanup_stream, emit_marker, make_heartbeat
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.analysis.prompts.builder import PromptContext, build_analysis_prompt, load_template
from quodeq.analysis.subagents.runner import DimensionCallbacks, process_dimension_with_subagents
from quodeq.shared.logging import log_debug, log_info, log_success, log_warning
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
    max_subagents: int = 1
    subagent_model: str | None = None
    verify_findings: bool = False
    consolidated: bool = True
    pool_budget: int | None = None
    incremental: bool = False
    incremental_file_filter: set[str] | None = None


@dataclass
class RunConfig:
    """Configuration for a single evaluation run."""
    src: Path
    language: str
    standards_dir: Path | None = None
    work_dir: Path | None = None
    options: AnalysisOptions = field(default_factory=AnalysisOptions)
    manifest: SourceManifest | None = None
    dimensions_data: DimensionsConfig | None = None
    target: AnalysisTarget | None = None

    @property
    def source_file_count(self) -> int:
        """Derive source file count from the target or manifest."""
        if self.target:
            return self.target.total_files
        return self.manifest.total_files if self.manifest else 0


@dataclass(frozen=True)
class _AnalysisContext:
    """Pre-loaded data reused across dimensions."""
    dimensions_data: DimensionsConfig
    date_str: str
    template: str
    subagent_template: str
    total: int


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


def _parse_dimension_evidence(
    config: RunConfig, dim_id: str, stream_file: Path, jsonl_file: Path,
    ctx: _AnalysisContext,
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
            language=config.language,
            repository=str(config.src),
            date_str=ctx.date_str,
            source_file_count=config.source_file_count,
            files_read=files_read,
            module=config.target.name if config.target else "",
        ),
        compiled_dir=compiled_dir,
    )
    return ev


def _process_dimension_with_subagents(
    config: RunConfig, dim_id: str, idx: int, ctx: _AnalysisContext,
) -> Evidence | None:
    """Run dimension analysis using N parallel subagents (delegates to _subagent_runner)."""
    return process_dimension_with_subagents(
        config, dim_id, idx, ctx,
        callbacks=DimensionCallbacks(
            build_prompt=_build_dimension_prompt,
            run_analysis=_run_dimension_analysis,
            parse_evidence=_parse_dimension_evidence,
        ),
    )


def load_analysis_context(config: RunConfig) -> tuple[list[str], _AnalysisContext]:
    """Load dimensions data and resolve which dimensions to analyze."""
    dims_data = config.dimensions_data
    if dims_data is None:
        raise ValueError("RunConfig.dimensions_data is required")

    all_dims_raw = [d.get("id") for d in dims_data.get("applies", []) if d.get("id")]
    if config.options.dimensions:
        all_dims_set = set(all_dims_raw)
        unknown = [d for d in config.options.dimensions if d not in all_dims_set]
        if unknown:
            log_warning(f"Unknown dimensions ignored: {', '.join(unknown)}. "
                        f"Available: {', '.join(all_dims_raw)}")
        dimensions = [d for d in all_dims_raw if d in config.options.dimensions]
        if not dimensions:
            raise ValueError(
                f"No valid dimensions selected. "
                f"Requested: {', '.join(config.options.dimensions)}. "
                f"Available: {', '.join(all_dims_raw)}"
            )
    else:
        dimensions = all_dims_raw

    ctx = _AnalysisContext(
        dimensions_data=dims_data,
        date_str=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        template=load_template(config.options.template_path),
        subagent_template=load_template(template_name="subagent.md"),
        total=len(dimensions),
    )
    return dimensions, ctx


class EvaluationError(RuntimeError):
    """Raised when an evaluation completes but produces no usable findings."""


def _save_dimension_fingerprint(
    config: RunConfig, dimension: str, files: list[str] | None = None,
    analyzed_files: set[str] | None = None,
) -> None:
    """Save a fingerprint after any successful dimension analysis."""
    try:
        from quodeq.analysis.fingerprint import build_fingerprint, save_fingerprint
        evidence_dir = config.work_dir or config.src
        if files is None:
            from quodeq.analysis.subagents.runner import _list_source_files
            saved_filter = config.options.incremental_file_filter
            config.options.incremental_file_filter = None
            files, _ = _list_source_files(config, dimension)
            config.options.incremental_file_filter = saved_filter
        # Try to read analyzed files from the queue if not provided
        if analyzed_files is None:
            queue_path = evidence_dir / f"{dimension}_queue.json"
            if queue_path.exists():
                from quodeq.analysis.subagents.file_queue import FileQueue
                try:
                    queue = FileQueue(queue_path)
                    analyzed_files = set(queue.all_taken_files())
                except Exception:
                    pass
        fp = build_fingerprint(config.src, files, dimension, config.standards_dir, analyzed_files=analyzed_files)
        save_fingerprint(fp, evidence_dir)
    except Exception as exc:
        log_debug(f"  [{dimension}] Fingerprint save failed: {exc}")


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
        ev = _process_dimension_with_subagents(config, dimension, idx, ctx)
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
    from quodeq.analysis.fingerprint import build_fingerprint, save_fingerprint, load_fingerprint
    from quodeq.analysis.incremental import classify_files, carry_forward_findings
    from quodeq.analysis.subagents.verify import _resolve_evidence_paths

    phase_start = time.monotonic()
    evidence_dir = config.work_dir or config.src

    # Find previous fingerprint
    paths_info = _resolve_evidence_paths(evidence_dir)
    prev_fp = None
    prev_evidence_dir = None
    if not paths_info:
        log_warning(f"  [{dimension}] Cannot resolve evidence paths — falling back to full analysis")
    if paths_info:
        current_run_id, project_uuid, reports_base = paths_info
        from quodeq.data.fs.report_parser.runs import list_runs
        for run_info in list_runs(reports_base, project_uuid):
            if run_info.run_id == current_run_id:
                continue
            prev_evidence = reports_base / project_uuid / run_info.run_id / "evidence"
            fp = load_fingerprint(prev_evidence, dimension)
            if fp:
                prev_fp = fp
                prev_evidence_dir = prev_evidence
                break

    # Get full source files list (for classification)
    from quodeq.analysis.subagents.runner import _list_source_files
    # Temporarily disable file filter to get ALL files for classification
    saved_filter = config.options.incremental_file_filter
    config.options.incremental_file_filter = None
    files, extensions = _list_source_files(config, dimension)
    config.options.incremental_file_filter = saved_filter
    if not files:
        return None

    # Classify files
    classification = classify_files(
        src=config.src, files=files,
        prev_fingerprint=prev_fp,
        standards_dir=config.standards_dir,
        dimension=dimension,
        language=config.language,
    )

    # Carry forward unchanged findings
    if prev_fp and prev_evidence_dir and not classification.full_reanalysis and classification.unchanged:
        prev_jsonl = prev_evidence_dir / f"{dimension}_evidence.jsonl"
        output_jsonl = evidence_dir / f"{dimension}_evidence.jsonl"
        carried = carry_forward_findings(prev_jsonl, output_jsonl, classification.unchanged)
        log_info(f"  [{dimension}] Carried forward {carried} findings for {len(classification.unchanged)} unchanged files")

    if not classification.to_analyze:
        log_info(f"  [{dimension}] No changes detected — using cached findings only")
        # Parse the carried-forward JSONL as evidence
        jsonl_file = evidence_dir / f"{dimension}_evidence.jsonl"
        if jsonl_file.exists() and jsonl_file.stat().st_size > 0:
            compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
            ev = parse_jsonl_to_evidence(
                jsonl_file,
                EvidenceContext(
                    language=config.language, repository=str(config.src),
                    date_str=ctx.date_str, source_file_count=config.source_file_count,
                    files_read=len(classification.unchanged), module=config.target.name if config.target else "",
                ),
                compiled_dir=compiled_dir,
            )
        else:
            ev = None
    else:
        log_info(f"  [{dimension}] Analyzing {len(classification.to_analyze)} changed files ({len(classification.unchanged)} cached)")
        # Set file filter so _list_source_files returns only changed+dependent files
        config.options.incremental_file_filter = set(classification.to_analyze)
        try:
            ev = _process_single_dimension(config, dimension, idx, ctx, emit_log=False)
        finally:
            config.options.incremental_file_filter = None

        # Dedup: carried-forward + new findings may overlap
        from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl
        output_jsonl = evidence_dir / f"{dimension}_evidence.jsonl"
        if output_jsonl.exists():
            deduplicate_jsonl(output_jsonl)
            # Re-parse after dedup to get accurate Evidence
            compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
            ev = parse_jsonl_to_evidence(
                output_jsonl,
                EvidenceContext(
                    language=config.language, repository=str(config.src),
                    date_str=ctx.date_str, source_file_count=config.source_file_count,
                    files_read=ev.files_read if ev else 0,
                    module=config.target.name if config.target else "",
                ),
                compiled_dir=compiled_dir,
            )

    # --- Phase 3: Backfill — analyze previously-unevaluated files with remaining budget ---
    from quodeq.analysis.incremental import identify_backfill_files

    prev_analyzed = set(prev_fp.get("analyzed_files", [])) if prev_fp else set()
    phase1_files = set(classification.to_analyze) if classification.to_analyze else set()
    backfill_candidates = identify_backfill_files(files, list(prev_analyzed), phase1_files)

    output_jsonl = evidence_dir / f"{dimension}_evidence.jsonl"
    backfill_taken: set[str] = set()
    if backfill_candidates:
        elapsed = time.monotonic() - phase_start
        total_budget = config.options.pool_budget or 600
        remaining_budget = max(0, total_budget - int(elapsed))

        if remaining_budget >= 60:  # at least 1 minute remaining
            log_info(
                f"  [{dimension}] Backfill: {len(backfill_candidates)} unevaluated files, "
                f"{remaining_budget}s budget remaining"
            )
            config.options.incremental_file_filter = set(backfill_candidates)
            saved_budget = config.options.pool_budget
            config.options.pool_budget = remaining_budget
            try:
                _process_single_dimension(config, dimension, idx, ctx, emit_log=False)
            finally:
                config.options.incremental_file_filter = None
                config.options.pool_budget = saved_budget

            # Read which backfill files were actually taken from queue
            backfill_queue = evidence_dir / f"{dimension}_queue.json"
            if backfill_queue.exists():
                from quodeq.analysis.subagents.file_queue import FileQueue
                try:
                    backfill_taken = set(FileQueue(backfill_queue).all_taken_files())
                except Exception:
                    pass

            # Dedup carried + phase1 + backfill findings
            from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl as _dedup_jsonl
            if output_jsonl.exists():
                _dedup_jsonl(output_jsonl)
        else:
            log_info(f"  [{dimension}] Backfill: {len(backfill_candidates)} unevaluated files, but no budget remaining")

    # Re-parse after all phases to get accurate Evidence
    if output_jsonl.exists() and output_jsonl.stat().st_size > 0:
        compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
        ev = parse_jsonl_to_evidence(
            output_jsonl,
            EvidenceContext(
                language=config.language, repository=str(config.src),
                date_str=ctx.date_str, source_file_count=config.source_file_count,
                files_read=len(phase1_files) + len(backfill_taken) + len(classification.unchanged),
                module=config.target.name if config.target else "",
            ),
            compiled_dir=compiled_dir,
        )

    # Save new fingerprint (include backfill files in analyzed set)
    all_analyzed = phase1_files | backfill_taken
    new_fp = build_fingerprint(config.src, files, dimension, config.standards_dir, analyzed_files=all_analyzed or None)
    save_fingerprint(new_fp, evidence_dir)

    return ev


def _run_dimensions(config: RunConfig) -> dict[str, Evidence]:
    """Run AI analysis for each dimension and return per-dimension Evidence."""
    dimensions, ctx = load_analysis_context(config)

    # Incremental mode: per-dimension incremental analysis
    if config.options.incremental:
        emit_marker("setup", dimensions=dimensions)
        result: dict[str, Evidence] = {}
        for idx, dimension in enumerate(dimensions, 1):
            emit_marker("analyzing", dimension=dimension)
            log_info(f"→ [{idx}/{ctx.total}] Analyzing {dimension} (incremental)")
            try:
                ev = _run_dimension_incremental(config, dimension, idx, ctx)
            except (OSError, KeyError, ValueError, RuntimeError) as exc:
                log_warning(f"[{idx}/{ctx.total}] {dimension} — incremental failed: {exc}, falling back to full")
                config.options.incremental_file_filter = None
                ev = _process_single_dimension(config, dimension, idx, ctx)
            if ev:
                _log_dimension_result(ev, dimension, idx, ctx.total)
                result[dimension] = ev
        # Check for zero findings (same as existing logic)
        if result and config.source_file_count > 0:
            total_findings = sum(
                sum(len(pe.violations) + len(pe.compliance) for pe in ev.principles.values())
                for ev in result.values()
            )
            if total_findings == 0:
                raise EvaluationError(
                    f"Evaluation produced 0 findings across {len(result)} dimensions. "
                    f"This usually means the AI CLI could not read files or report findings "
                    f"— check tool permissions and MCP configuration."
                )
        return result

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

    # Per-dimension loop (fallback or single-dimension)
    result: dict[str, Evidence] = {}
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
