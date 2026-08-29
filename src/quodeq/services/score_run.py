"""Use case: score completed evidence after cancellation.

Extracted from ``evaluation_mixin`` so the API layer has a public entry
point instead of importing a private helper.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.config.evidence_env import cwe_url_template
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.data.fs.standards_loader import read_req_to_principle_map
from quodeq.core.scoring.engine import score_evidence
from quodeq.analysis.report import write_dimension_report
from quodeq.services.grade_formula import load_params
from quodeq.services.ports import (
    dimension_queue_file,
    list_dimension_evidence,
    queue_file_exists,
    read_queue_files_count,
    read_scan_total_files,
)

_logger = logging.getLogger(__name__)

def _read_queue_files_count(queue_path: Path) -> int:
    """Sum of files dispatched across all batches in a dim's queue.json.

    Used to populate ``files_read`` when scoring residual evidence —
    without this, ``_score_completed_evidence`` writes eval stubs with
    ``filesRead: 0``, which the ``scoring_view`` trust rule rejects as
    untrustworthy. Returning the queue's taken count yields a faithful
    coverage figure: every file that was actually dispatched to an agent.
    The read mechanics live in ``data.fs.run_files``.
    """
    return read_queue_files_count(queue_path)


def _read_project_source_file_count(reports_dir: str, project: str) -> int:
    """Read ``scan.json`` total_files for the project. Returns 0 on failure."""
    return read_scan_total_files(Path(reports_dir) / project)


def score_completed_evidence(reports_dir: str, job: dict) -> None:
    """Score any dimensions that have evidence but no evaluation report.

    Called after cancellation so completed dimensions are preserved in the
    dashboard even when the overall run was cancelled.

    Populates ``files_read`` from the dim's queue.json (count of dispatched
    files) and ``source_file_count`` from the project's scan.json. Without
    these, the scored eval has ``filesRead: 0``, which ``scoring_view``'s
    trust rule rejects — the user sees the cancelled run's data fall
    through to an older run's stale value despite real findings on disk.
    """
    project = job.get("outputProject")
    run_id = job.get("outputRunId")
    if not project or not run_id:
        return

    _log = _logger

    run_dir = Path(reports_dir) / project / run_id
    evaluation_dir = run_dir / "evaluation"
    evidence_entries = list_dimension_evidence(run_dir)
    if evidence_entries is None:
        return

    evaluation_dir.mkdir(parents=True, exist_ok=True)
    source_file_count = _read_project_source_file_count(reports_dir, project)
    params = load_params()
    # Same standard dirs as a completed run's scoring, so off-standard
    # findings are quarantined here too instead of entering the grade.
    from quodeq.services.evidence_rescore import standard_dirs  # noqa: PLC0415
    compiled_dir, evaluators_dir = standard_dirs()

    from quodeq.data.fs.dimensions_state_store import read_dimensions
    dim_states = read_dimensions(run_dir).get("dimensions", {})

    for dim_id, jsonl_path, evidence_size in evidence_entries:
        eval_file = evaluation_dir / f"{dim_id}.json"
        if eval_file.exists():
            continue  # already scored
        if dim_states.get(dim_id, {}).get("state") == "incomplete":
            _logger.info("Skipping scoring for incomplete dim %s", dim_id)
            continue
        if evidence_size == 0:
            continue  # no findings
        # Only score dimensions that passed verification (analysis queue exists)
        if not queue_file_exists(run_dir, dim_id):
            continue  # verification not completed for this dimension

        files_read = _read_queue_files_count(dimension_queue_file(run_dir, dim_id))
        try:
            evidence = parse_jsonl_to_evidence(jsonl_path, EvidenceContext(
                language="", repository="", date_str="",
                source_file_count=source_file_count, files_read=files_read,
            ), compiled_dir=compiled_dir, evaluators_dir=evaluators_dir,
                req_map_reader=read_req_to_principle_map,
                cwe_url_template=cwe_url_template())
            if evidence is None:
                continue
            scores = score_evidence(evidence, mode="numerical", params=params)
            write_dimension_report(evidence, scores, dim_id, evaluation_dir)
            _log.info(
                "Scored cancelled dimension '%s' for run %s (files_read=%d)",
                dim_id, run_id[:8], files_read,
            )
        except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
            _log.debug("Could not score cancelled dimension '%s': %s", dim_id, exc)
