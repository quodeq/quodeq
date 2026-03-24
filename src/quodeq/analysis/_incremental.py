"""Incremental dimension analysis — extracted from runner.py for file-length limits."""
from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.analysis.fingerprint import build_fingerprint, load_fingerprint, save_fingerprint
from quodeq.analysis.incremental import classify_files, carry_forward_findings, identify_backfill_files
from quodeq.analysis.subagents.verify import _resolve_evidence_paths
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.shared.logging import log_debug, log_info, log_warning

if TYPE_CHECKING:
    from quodeq.analysis.runner import RunConfig, _AnalysisContext


def load_analysis_context(config: "RunConfig") -> tuple[list[str], "_AnalysisContext"]:
    """Load dimensions data and resolve which dimensions to analyze."""
    from datetime import datetime, timezone
    from quodeq.analysis.prompts.builder import load_template
    from quodeq.analysis.runner import _AnalysisContext

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


def save_dimension_fingerprint(
    config: RunConfig, dimension: str, files: list[str] | None = None,
    analyzed_files: set[str] | None = None,
) -> None:
    """Save a fingerprint after any successful dimension analysis."""
    try:
        evidence_dir = config.work_dir or config.src
        if files is None:
            from quodeq.analysis.subagents.runner import _list_source_files
            saved_filter = config.options.incremental_file_filter
            config.options.incremental_file_filter = None
            files, _ = _list_source_files(config, dimension)
            config.options.incremental_file_filter = saved_filter
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


def _find_previous_fingerprint(
    evidence_dir: Path, dimension: str,
) -> tuple[dict | None, Path | None]:
    """Find the fingerprint and evidence dir from the most recent previous run."""
    paths_info = _resolve_evidence_paths(evidence_dir)
    if not paths_info:
        log_warning(f"  [{dimension}] Cannot resolve evidence paths — falling back to full analysis")
        return None, None

    current_run_id, project_uuid, reports_base = paths_info
    from quodeq.data.fs.report_parser.runs import list_runs
    for run_info in list_runs(reports_base, project_uuid):
        if run_info.run_id == current_run_id:
            continue
        prev_evidence = reports_base / project_uuid / run_info.run_id / "evidence"
        fp = load_fingerprint(prev_evidence, dimension)
        if fp:
            return fp, prev_evidence
    return None, None


def _parse_evidence_from_jsonl(
    config: RunConfig, dimension: str, ctx: _AnalysisContext,
    jsonl_file: Path, files_read: int,
) -> Evidence | None:
    """Parse a JSONL file into Evidence."""
    if not jsonl_file.exists() or jsonl_file.stat().st_size == 0:
        return None
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    return parse_jsonl_to_evidence(
        jsonl_file,
        EvidenceContext(
            language=config.language, repository=str(config.src),
            date_str=ctx.date_str, source_file_count=config.source_file_count,
            files_read=files_read, module=config.target.name if config.target else "",
        ),
        compiled_dir=compiled_dir,
    )


def _run_phase1_analysis(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
    classification: object, evidence_dir: Path,
) -> Evidence | None:
    """Phase 1: analyze changed files or use cached findings only."""
    from quodeq.analysis.runner import _process_single_dimension

    if not classification.to_analyze:
        log_info(f"  [{dimension}] No changes detected — using cached findings only")
        jsonl_file = evidence_dir / f"{dimension}_evidence.jsonl"
        return _parse_evidence_from_jsonl(config, dimension, ctx, jsonl_file, len(classification.unchanged))

    log_info(f"  [{dimension}] Analyzing {len(classification.to_analyze)} changed files ({len(classification.unchanged)} cached)")
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
        ev = _parse_evidence_from_jsonl(
            config, dimension, ctx, output_jsonl,
            ev.files_read if ev else 0,
        )
    return ev


def _run_backfill_phase(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
    files: list[str], prev_analyzed: set[str], phase1_files: set[str],
    evidence_dir: Path, phase_start: float,
) -> set[str]:
    """Phase 3: backfill previously-unevaluated files with remaining budget.

    Returns the set of backfill files actually taken.
    """
    from quodeq.analysis.runner import _process_single_dimension

    backfill_candidates = identify_backfill_files(files, list(prev_analyzed), phase1_files)
    output_jsonl = evidence_dir / f"{dimension}_evidence.jsonl"
    backfill_taken: set[str] = set()

    if not backfill_candidates:
        return backfill_taken

    elapsed = time.monotonic() - phase_start
    total_budget = config.options.pool_budget or 600
    remaining_budget = max(0, total_budget - int(elapsed))

    if remaining_budget < 60:
        log_info(f"  [{dimension}] Backfill: {len(backfill_candidates)} unevaluated files, but no budget remaining")
        return backfill_taken

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
    from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl
    if output_jsonl.exists():
        deduplicate_jsonl(output_jsonl)

    return backfill_taken


def _finalize_incremental(
    config: RunConfig, dimension: str, ctx: _AnalysisContext,
    files: list[str], all_analyzed: set[str], evidence_dir: Path,
    files_read: int,
) -> Evidence | None:
    """Re-parse JSONL, save fingerprint, and log coverage."""
    all_analyzed &= set(files)
    output_jsonl = evidence_dir / f"{dimension}_evidence.jsonl"
    ev = _parse_evidence_from_jsonl(config, dimension, ctx, output_jsonl, files_read)
    new_fp = build_fingerprint(config.src, files, dimension, config.standards_dir, analyzed_files=all_analyzed or None)
    save_fingerprint(new_fp, evidence_dir)
    coverage_pct = len(all_analyzed) * 100 // len(files) if files else 100
    log_info(f"  [{dimension}] Coverage: {len(all_analyzed)}/{len(files)} files ({coverage_pct}%)")
    return ev


def _maybe_carry_forward(
    prev_fp: dict | None, prev_evidence_dir: Path | None,
    classification: object, dimension: str, evidence_dir: Path,
) -> None:
    """Carry forward findings for unchanged files if conditions are met."""
    if not (prev_fp and prev_evidence_dir and not classification.full_reanalysis and classification.unchanged):
        return
    prev_jsonl = prev_evidence_dir / f"{dimension}_evidence.jsonl"
    output_jsonl = evidence_dir / f"{dimension}_evidence.jsonl"
    carried = carry_forward_findings(prev_jsonl, output_jsonl, classification.unchanged)
    log_info(f"  [{dimension}] Carried forward {carried} findings for {len(classification.unchanged)} unchanged files")


def run_dimension_incremental(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
) -> Evidence | None:
    """Incremental path: detect changes, carry forward, analyze only changed files."""
    phase_start = time.monotonic()
    evidence_dir = config.work_dir or config.src

    prev_fp, prev_evidence_dir = _find_previous_fingerprint(evidence_dir, dimension)

    # Get full source files list (for classification)
    from quodeq.analysis.subagents.runner import _list_source_files
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

    _maybe_carry_forward(prev_fp, prev_evidence_dir, classification, dimension, evidence_dir)

    # Phase 1: analyze changed files
    ev = _run_phase1_analysis(config, dimension, idx, ctx, classification, evidence_dir)

    # Phase 3: backfill
    prev_analyzed = set(prev_fp.get("analyzed_files", [])) if prev_fp else set()
    phase1_files = set(classification.to_analyze) if classification.to_analyze else set()
    backfill_taken = _run_backfill_phase(
        config, dimension, idx, ctx, files, prev_analyzed, phase1_files,
        evidence_dir, phase_start,
    )

    # Re-parse after all phases and save fingerprint
    all_analyzed = prev_analyzed | phase1_files | backfill_taken
    return _finalize_incremental(
        config, dimension, ctx, files, all_analyzed, evidence_dir,
        len(phase1_files) + len(backfill_taken) + len(classification.unchanged),
    )



# Re-export loop orchestrators from _loops.py for backward compatibility
from quodeq.analysis._loops import (  # noqa: F401
    check_zero_findings,
    run_incremental_loop,
    run_per_dimension_loop,
)
