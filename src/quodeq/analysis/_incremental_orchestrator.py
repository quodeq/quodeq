"""Incremental analysis — top-level orchestrator for a single dimension."""
from __future__ import annotations

import time

from quodeq.analysis._backfill import BackfillContext, run_backfill_phase
from quodeq.analysis._incremental_context import IncrementalCoverage
from quodeq.analysis._incremental_phases import (
    _finalize_incremental, _list_all_source_files,
    _maybe_carry_forward, _run_phase1_analysis,
)
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.fingerprint import find_previous_fingerprint
from quodeq.core.evidence.model import Evidence


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

    from quodeq.analysis.incremental import ClassificationInput, classify_files
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
