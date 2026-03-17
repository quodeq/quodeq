"""Full pipeline runner — scores and writes per-dimension reports."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.scoring.engine import score_evidence
from quodeq.engine.report import write_dimension_report
from quodeq.engine.runner import RunConfig, run_per_dimension, cleanup_stream
from quodeq.shared.logging import log_info

_NUMERICAL_MODE = "numerical"
_NA_LABEL = "N/A"


def _verify_single_dimension(
    config: RunConfig, dimension: str, files_read: int,
    ctx: object, compiled_dir: Path | None,
) -> tuple[str, object]:
    """Run verification for one dimension and return (dimension, updated_evidence)."""
    from quodeq.analysis.subagents.verify import run_verification_pass
    from quodeq.engine.evidence_parser import EvidenceContext, parse_jsonl_to_evidence

    work_dir = config.work_dir or config.src
    run_verification_pass(config, dimension, ctx, work_dir)
    jsonl_path = work_dir / f"{dimension}_evidence.jsonl"
    ev = parse_jsonl_to_evidence(
        jsonl_path,
        EvidenceContext(
            plugin_id=config.plugin_id,
            repository=str(config.src),
            date_str=ctx.date_str,
            source_file_count=config.source_file_count,
            files_read=files_read,
        ),
        compiled_dir=compiled_dir,
    )
    ev.plugin_name = ctx.plugin_name
    return dimension, ev


def _run_verification(config: RunConfig, per_dim_evidence: dict) -> dict:
    """Run verification pass on all dimensions in parallel."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from quodeq.analysis.runner import load_plugin_context

    work_dir = config.work_dir or config.src
    _dims, ctx = load_plugin_context(config)
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None

    log_info(f"Starting verification pass ({len(per_dim_evidence)} dimensions in parallel)...")
    with ThreadPoolExecutor(max_workers=len(per_dim_evidence)) as pool:
        futures = {
            pool.submit(
                _verify_single_dimension,
                config, dim, per_dim_evidence[dim].files_read, ctx, compiled_dir,
            ): dim
            for dim in per_dim_evidence
        }
        for future in as_completed(futures):
            dim, ev = future.result()
            per_dim_evidence[dim] = ev

    return per_dim_evidence


def run_full(config: RunConfig, output_dir: Path, mode: str = _NUMERICAL_MODE) -> dict:
    """Full pipeline: run per-dimension → verify → score each → write reports.

    Returns dict of {dimension: overall_score_str}.
    """
    work_dir = config.work_dir or config.src
    per_dim_evidence = run_per_dimension(config)

    # Verification pass: re-check violations + hunt for compliance evidence
    if config.options.verify_findings and config.options.n_subagents > 1:
        per_dim_evidence = _run_verification(config, per_dim_evidence)

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
