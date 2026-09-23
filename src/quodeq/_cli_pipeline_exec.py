"""Running the evidence/scoring pipeline and saving the run's manifest.

Split from ``cli_evaluation.py`` to keep each module under 300 lines.
Both names are re-exported from ``cli_evaluation`` because
``_lifecycle_hooks`` reads them off that module at call time, so
``quodeq.cli_evaluation.execute_pipeline`` and ``.save_manifest`` stay
valid patch targets. The collaborators they call (``run``, ``run_full``,
``write_text``, ``manifest_to_dict``) are looked up here, so patch them at
``quodeq._cli_pipeline_exec.<name>``.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from quodeq.analysis.manifest_serialization import manifest_to_dict
from quodeq.analysis.runner import RunConfig, run
from quodeq.analysis.scoring_pipeline import run_full
from quodeq.services.grade_formula import load_params
from quodeq.shared.logging import log_error, log_info
from quodeq.shared.utils import write_text
from quodeq._cli_scoring import print_scores

_logger = logging.getLogger(__name__)


def execute_pipeline(args: argparse.Namespace, config: RunConfig, evidence_dir: Path, evaluation_dir: Path) -> int:
    """Execute the evidence/scoring pipeline and print results.

    Three modes: scoring (default, run_full → scored evaluation/<dim>.json
    reports), --evidence-only (run() → merged <language>_evidence.json, no
    scoring), PR diff / skip_scoring (run() → per-dimension JSONL only, no
    merged json, no scoring).

    Domain errors (AnalysisError, EvaluationError) are intentionally *not*
    caught here — they propagate to run_pipeline_with_cleanup so that
    RunLifecycleContext.__exit__ can write state=failed before the error is
    mapped to exit code 1.
    """
    if args.evidence_only or config.options.skip_scoring:
        label = "PR diff" if config.options.skip_scoring else "evidence collection"
        log_info(f"Starting {label} (this may take several minutes per dimension)...")
        evidence = run(config)
        if config.options.skip_scoring:
            # PR diff mode: per-dimension JSONL is already written by the pipeline.
            # No merged whole-repo artifact — PR reviews consume the JSONL directly.
            log_info(f"PR diff evaluation complete — evidence written to {evidence_dir}/")
        else:
            # --evidence-only: write the merged whole-repo Evidence JSON.
            out_file = evidence_dir / f"{config.language}_evidence.json"
            try:
                write_text(out_file, json.dumps(evidence.to_evidence_dict(), indent=2))
            except OSError as exc:
                log_error(f"Failed to write evidence file {out_file}: {exc}")
                return 1
            log_info(f"Evidence written to {out_file}")
        return 0

    log_info("Starting evaluation (this may take several minutes per dimension)...")
    scores = run_full(config, evaluation_dir, mode=args.mode)
    log_info(f"Report path: {evaluation_dir}/")
    log_info(f"Reports written to {evaluation_dir}/")
    run_dir = evaluation_dir.parent
    project_dir = run_dir.parent
    print_scores(scores, run_dir, project_dir, load_params())
    return 0


def save_manifest(manifest, evidence_dir: Path) -> None:
    """Save manifest for debugging (best-effort)."""
    if manifest and evidence_dir:
        try:
            write_text(evidence_dir / "manifest.json", json.dumps(manifest_to_dict(manifest), indent=2))
        except OSError as exc:
            _logger.debug("Could not write manifest: %s", exc)
