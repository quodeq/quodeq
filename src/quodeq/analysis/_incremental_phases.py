"""Incremental analysis — phase execution helpers."""
from __future__ import annotations

from copy import copy
from pathlib import Path

from quodeq.analysis._incremental_context import IncrementalCoverage
from quodeq.analysis._incremental_evidence import parse_evidence_from_jsonl, save_dimension_fingerprint
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.fingerprint import build_fingerprint, save_fingerprint
from quodeq.analysis.incremental import carry_forward_findings
from quodeq.analysis.subagents.runner import _list_source_files
from quodeq.core.evidence.model import Evidence
from quodeq.shared.logging import log_info


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
        return parse_evidence_from_jsonl(config, dimension, ctx, jsonl_file, len(classification.unchanged))

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
        ev = parse_evidence_from_jsonl(
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
    ev = parse_evidence_from_jsonl(config, dimension, ctx, output_jsonl, coverage.files_read)
    new_fp = build_fingerprint(config.src, coverage.files, dimension, config.standards_dir, analyzed_files=all_analyzed or None)
    save_fingerprint(new_fp, evidence_dir)
    coverage_pct = len(all_analyzed) * 100 // len(coverage.files) if coverage.files else 100
    log_info(f"  [{dimension}] Coverage: {len(all_analyzed)}/{len(coverage.files)} files ({coverage_pct}%)")
    return ev


def _can_carry_forward(
    prev_fp: dict | None, prev_evidence_dir: Path | None, classification: object,
) -> bool:
    """Return True when previous findings exist and can be reused."""
    return bool(
        prev_fp and prev_evidence_dir
        and not classification.full_reanalysis
        and classification.unchanged
    )


def _maybe_carry_forward(
    prev_fp: dict | None, prev_evidence_dir: Path | None,
    classification: object, dimension: str, evidence_dir: Path,
) -> None:
    """Carry forward findings for unchanged files if conditions are met."""
    if not _can_carry_forward(prev_fp, prev_evidence_dir, classification):
        return
    prev_jsonl = prev_evidence_dir / f"{dimension}_evidence.jsonl"
    output_jsonl = evidence_dir / f"{dimension}_evidence.jsonl"
    carried = carry_forward_findings(prev_jsonl, output_jsonl, classification.unchanged)
    log_info(f"  [{dimension}] Carried forward {carried} findings for {len(classification.unchanged)} unchanged files")


def _list_all_source_files(config: RunConfig, dimension: str) -> list[str]:
    """List all source files, ignoring any active incremental filter."""
    files, _extensions = _list_source_files(config, dimension, ignore_file_filter=True)
    return files
