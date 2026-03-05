from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from codecompass.evaluate.lib.common import log_banner, log_divider, log_error, log_info, log_success
from codecompass.evaluate.lib.evaluation import compute_prompt_hash, run_two_phase_dimension
from codecompass.evaluate.lib.evaluator_renderer import (
    extract_analysis_context,
)


@dataclass(frozen=True)
class DimensionRunContext:
    """All context needed to evaluate a set of dimensions."""
    work_dir: str
    discipline: str
    project_name: str
    today: str
    evidence_dir: Path
    evaluation_dir: Path
    evaluators_dir: Path
    analysis_template: str
    scoring_template: str
    analysis_hash: str
    scoring_hash: str
    source_file_count: int = 0
    prescan_metrics: str = ""
    codecompass_version: str = "unknown"
    evidence_only: bool = False
    numerical: bool = False


def run_dimensions(dimensions: list[str], ctx: DimensionRunContext) -> tuple[int, int]:
    """Run the two-phase evaluation for each dimension sequentially.

    Returns:
        Tuple of (success_count, fail_count)
    """
    success = 0
    failed = 0
    total = len(dimensions)

    for i, dimension in enumerate(dimensions):
        log_divider(f"[{i + 1}/{total}] {dimension}")
        evaluator_file = ctx.evaluators_dir / ctx.discipline / f"{dimension}.json"

        if not evaluator_file.exists():
            log_error(f"Evaluator file not found: {evaluator_file}")
            failed += 1
            continue

        # Load and extract evaluator contexts
        try:
            evaluator_text = evaluator_file.read_text()
            evaluator_data = json.loads(evaluator_text)
        except Exception as exc:
            log_error(f"Failed to read evaluator {evaluator_file}: {exc}")
            failed += 1
            continue

        analysis_standards = json.dumps(extract_analysis_context(evaluator_data), indent=2)
        evaluator_hash = compute_prompt_hash(evaluator_text)

        evidence_file = str(ctx.evidence_dir / f"{dimension}_evidence.json")
        eval_file = str(ctx.evaluation_dir / f"{dimension}_eval.md")

        ok = run_two_phase_dimension(
            work_dir=ctx.work_dir,
            dimension=dimension,
            discipline=ctx.discipline,
            project_name=ctx.project_name,
            today=ctx.today,
            evidence_file=evidence_file,
            eval_file=eval_file,
            analysis_template=ctx.analysis_template,
            scoring_template=ctx.scoring_template,
            analysis_standards=analysis_standards,
            source_file_count=ctx.source_file_count,
            analysis_hash=ctx.analysis_hash,
            scoring_hash=ctx.scoring_hash,
            mapping_hash=evaluator_hash,
            codecompass_version=ctx.codecompass_version,
            prescan_metrics=ctx.prescan_metrics,
            evidence_only=ctx.evidence_only,
            numerical=ctx.numerical,
            mapping_file=str(evaluator_file),
        )

        if ok:
            success += 1
        else:
            log_error(f"[{dimension}] Failed")
            failed += 1

    status = f"Assessment complete  ·  {success} passed  ·  {failed} failed"
    log_banner([status])

    return success, failed
