"""Full pipeline runner — scores and writes per-dimension reports."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.scoring.engine import score_evidence
from quodeq.analysis.report import write_dimension_report
from quodeq.analysis.runner import RunConfig, run_per_dimension
from quodeq.engine._runner_markers import cleanup_stream
from quodeq.services.grade_formula import load_params

_NUMERICAL_MODE = "numerical"
_NA_LABEL = "N/A"
_MAX_SCORE = 10


def run_full(config: RunConfig, output_dir: Path, mode: str = _NUMERICAL_MODE) -> dict:
    """Full pipeline: run per-dimension → score each → write reports.

    Each dimension is scored and written to disk as soon as it completes,
    so completed dimensions survive if the process is cancelled mid-run.

    Returns dict of {dimension: overall_score_str}.
    """
    work_dir = config.work_dir or config.src
    results: dict[str, str] = {}
    params = load_params()

    def _score_dimension(dimension: str, evidence: "Evidence") -> None:
        scores = score_evidence(evidence, mode=mode, params=params)
        write_dimension_report(evidence, scores, dimension, output_dir)
        cleanup_stream(work_dir / f"{dimension}_live.stream")
        overall = scores.overall
        if mode == _NUMERICAL_MODE:
            val = overall.weighted_score if overall else None
            results[dimension] = f"{val}/{_MAX_SCORE}" if val is not None else _NA_LABEL
        else:
            results[dimension] = (overall.weighted_grade if overall else None) or _NA_LABEL

    run_per_dimension(config, on_dimension_done=_score_dimension)

    return results
