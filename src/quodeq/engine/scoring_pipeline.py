"""Full pipeline runner — scores and writes per-dimension reports."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.scoring.engine import score_evidence
from quodeq.analysis.report import write_dimension_report
from quodeq.analysis.runner import RunConfig, run_per_dimension
from quodeq.engine._runner_markers import cleanup_stream

_NUMERICAL_MODE = "numerical"
_NA_LABEL = "N/A"


def run_full(config: RunConfig, output_dir: Path, mode: str = _NUMERICAL_MODE) -> dict:
    """Full pipeline: run per-dimension → score each → write reports.

    Verification runs mechanically before each dimension's subagent pool
    (inside process_dimension_with_subagents), not as a separate phase.

    Returns dict of {dimension: overall_score_str}.
    """
    work_dir = config.work_dir or config.src
    per_dim_evidence = run_per_dimension(config)

    results: dict[str, str] = {}

    for dimension, evidence in per_dim_evidence.items():
        scores = score_evidence(evidence, mode=mode)
        write_dimension_report(evidence, scores, dimension, output_dir)
        # Clean up stream now that the eval JSON exists
        cleanup_stream(work_dir / f"{dimension}_live.stream")
        overall = scores.overall
        if mode == _NUMERICAL_MODE:
            val = overall.weighted_score if overall else None
            results[dimension] = f"{val}/10" if val is not None else _NA_LABEL
        else:
            results[dimension] = (overall.weighted_grade if overall else None) or _NA_LABEL

    return results
