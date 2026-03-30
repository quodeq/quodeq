"""Incremental dimension analysis — extracted from runner.py for file-length limits."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.analysis._backfill import (
    BackfillContext, extract_files_from_jsonl, run_backfill_phase,
)
from quodeq.analysis.fingerprint import build_fingerprint, find_previous_fingerprint, save_fingerprint
from quodeq.analysis.incremental import classify_files, carry_forward_findings
from quodeq.analysis.subagents.runner import _list_source_files
from copy import copy
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.shared.logging import log_debug, log_info, log_warning

if TYPE_CHECKING:
    from quodeq.analysis.runner import RunConfig, _AnalysisContext

# Re-export for backward compatibility
_extract_files_from_jsonl = extract_files_from_jsonl


@dataclass
class IncrementalCoverage:
    """Groups coverage-related data for incremental finalization."""
    files: list[str]
    all_analyzed: set[str]
    files_read: int


def load_analysis_context(config: "RunConfig") -> tuple[list[str], "_AnalysisContext"]:
    """Load dimensions data and resolve which dimensions to analyze."""
    from datetime import datetime, timezone
    from quodeq.analysis.prompts.builder import load_template
    from quodeq.analysis.runner import _AnalysisContext

    dims_data = config.dimensions_data
    if dims_data is None:
        raise ValueError("RunConfig.dimensions_data is required")

    all_dims_raw = [d.get("id") for d in dims_data.get("applies", []) if d.get("id")]

    # Include custom evaluators from evaluators directory (only when dimensions are explicitly requested)
    if config.options.dimensions:
        _evaluators_dir = getattr(config, 'evaluators_dir', None)
        if _evaluators_dir is None:
            from quodeq.config.paths import default_paths
            _evaluators_dir = default_paths().evaluators_dir
    else:
        _evaluators_dir = None
    if _evaluators_dir and _evaluators_dir.is_dir():
        import json as _json
        for _p in _evaluators_dir.glob("*.json"):
            try:
                _eid = _json.loads(_p.read_text()).get("id")
                if _eid and _eid not in all_dims_raw:
                    all_dims_raw.append(_eid)
            except (OSError, ValueError, KeyError):
                pass

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
            files, _ = _list_source_files(config, dimension, ignore_file_filter=True)
        if analyzed_files is None:
            queue_files: set[str] = set()
            queue_path = evidence_dir / f"{dimension}_queue.json"
            if queue_path.exists():
                from quodeq.analysis.subagents.file_queue import FileQueue
                try:
                    queue_files = set(FileQueue(queue_path).all_taken_files())
                except (OSError, ValueError, KeyError) as exc:
                    log_debug(f"  [{dimension}] Could not read file queue: {exc}")
            jsonl_files = extract_files_from_jsonl(evidence_dir / f"{dimension}_evidence.jsonl")
            analyzed_files = queue_files | jsonl_files
        fp = build_fingerprint(config.src, files, dimension, config.standards_dir, analyzed_files=analyzed_files)
        save_fingerprint(fp, evidence_dir)
    except (OSError, ValueError, TypeError) as exc:
        log_debug(f"  [{dimension}] Fingerprint save failed: {exc}")



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
        evaluators_dir=config.evaluators_dir,
    )


def _run_phase1_analysis(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
    classification: object,
) -> Evidence | None:
    """Phase 1: analyze changed files or use cached findings only."""
    from quodeq.analysis.runner import _process_single_dimension

    evidence_dir = config.work_dir or config.src
    if not classification.to_analyze:
        log_info(f"  [{dimension}] No changes detected — using cached findings only")
        jsonl_file = evidence_dir / f"{dimension}_evidence.jsonl"
        return _parse_evidence_from_jsonl(config, dimension, ctx, jsonl_file, len(classification.unchanged))

    log_info(f"  [{dimension}] Analyzing {len(classification.to_analyze)} changed files ({len(classification.unchanged)} cached)")
    original_options = config.options
    config.options = copy(original_options)
    config.options.incremental_file_filter = set(classification.to_analyze)
    try:
        ev = _process_single_dimension(config, dimension, idx, ctx, emit_log=False)
    finally:
        config.options = original_options

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


def _finalize_incremental(
    config: RunConfig, dimension: str, ctx: _AnalysisContext,
    coverage: IncrementalCoverage,
) -> Evidence | None:
    """Re-parse JSONL, save fingerprint, and log coverage."""
    evidence_dir = config.work_dir or config.src
    all_analyzed = coverage.all_analyzed & set(coverage.files)
    output_jsonl = evidence_dir / f"{dimension}_evidence.jsonl"
    ev = _parse_evidence_from_jsonl(config, dimension, ctx, output_jsonl, coverage.files_read)
    new_fp = build_fingerprint(config.src, coverage.files, dimension, config.standards_dir, analyzed_files=all_analyzed or None)
    save_fingerprint(new_fp, evidence_dir)
    coverage_pct = len(all_analyzed) * 100 // len(coverage.files) if coverage.files else 100
    log_info(f"  [{dimension}] Coverage: {len(all_analyzed)}/{len(coverage.files)} files ({coverage_pct}%)")
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


def _list_all_source_files(config: RunConfig, dimension: str) -> list[str]:
    """List all source files, ignoring any active incremental filter."""
    files, _extensions = _list_source_files(config, dimension, ignore_file_filter=True)
    return files


def run_dimension_incremental(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
) -> Evidence | None:
    """Incremental path: detect changes, carry forward, analyze only changed files."""
    phase_start = time.monotonic()
    evidence_dir = config.work_dir or config.src

    prev_fp, prev_evidence_dir = find_previous_fingerprint(evidence_dir, dimension)

    files = _list_all_source_files(config, dimension)
    if not files:
        return None

    from quodeq.analysis.incremental import ClassificationInput
    classification = classify_files(
        inputs=ClassificationInput(
            src=config.src, files=files, prev_fingerprint=prev_fp,
            standards_dir=config.standards_dir, dimension=dimension, language=config.language,
        ),
    )

    _maybe_carry_forward(prev_fp, prev_evidence_dir, classification, dimension, evidence_dir)

    ev = _run_phase1_analysis(config, dimension, idx, ctx, classification)

    prev_analyzed = set(prev_fp.get("analyzed_files", [])) if prev_fp else set()
    phase1_files = set(classification.to_analyze) if classification.to_analyze else set()
    backfill_taken = run_backfill_phase(
        config, dimension, idx, ctx,
        BackfillContext(files=files, prev_analyzed=prev_analyzed, phase1_files=phase1_files,
                        evidence_dir=evidence_dir, phase_start=phase_start),
    )

    all_analyzed = prev_analyzed | phase1_files | backfill_taken
    return _finalize_incremental(
        config, dimension, ctx,
        IncrementalCoverage(
            files=files, all_analyzed=all_analyzed,
            files_read=len(phase1_files) + len(backfill_taken) + len(classification.unchanged),
        ),
    )



# Re-export loop orchestrators from _loops.py for backward compatibility
from quodeq.analysis._loops import (  # noqa: F401
    check_zero_findings,
    run_incremental_loop,
    run_per_dimension_loop,
)
