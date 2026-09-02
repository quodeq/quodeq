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
from quodeq.data.fs.standards_loader import load_compiled_refs, read_req_to_principle_map
from quodeq.core.scoring.engine import score_evidence
from quodeq.services.grade_formula import load_params
from quodeq.shared.log_sink import log_malformed_jsonl_line, log_quarantined_findings
from quodeq.services._wiring import (
    dimension_queue_file,
    dimension_report_exists,
    ensure_dir,
    list_dimension_evidence,
    queue_file_exists,
    read_dimensions,
    read_queue_files_count,
    read_scan_total_files,
    write_dimension_report,
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


def _score_one_dimension(
    dim_id: str, jsonl_path: Path, run_id: str, evaluation_dir: Path,
    source_file_count: int, files_read: int,
    compiled_dir: Path | None, evaluators_dir: Path | None, params,
    *, parser, scorer, reporter, log,
) -> None:
    """Score one dimension's evidence and write its report. Logs and
    swallows any parse/score failure (fail-soft: one bad dimension must not
    stop scoring the rest)."""
    try:
        evidence = parser(jsonl_path, EvidenceContext(
            language="", repository="", date_str="",
            source_file_count=source_file_count, files_read=files_read,
        ), compiled_dir=compiled_dir, evaluators_dir=evaluators_dir,
            req_map_reader=read_req_to_principle_map,
            refs_reader=load_compiled_refs,
            cwe_url_template=cwe_url_template(),
            on_quarantine=log_quarantined_findings,
            on_malformed_line=log_malformed_jsonl_line)
        if evidence is None:
            return
        scores = scorer(evidence, mode="numerical", params=params)
        reporter(evidence, scores, dim_id, evaluation_dir)
        log.info(
            "Scored cancelled dimension '%s' for run %s (files_read=%d)",
            dim_id, run_id[:8], files_read,
        )
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        log.debug("Could not score cancelled dimension '%s': %s", dim_id, exc)


def _should_score_dimension(
    dim_id: str, evidence_size: int, run_dir: Path, evaluation_dir: Path, dim_states: dict,
) -> bool:
    if dimension_report_exists(evaluation_dir, dim_id):
        return False  # already scored
    if dim_states.get(dim_id, {}).get("state") == "incomplete":
        _logger.info("Skipping scoring for incomplete dim %s", dim_id)
        return False
    if evidence_size == 0:
        return False  # no findings
    # Only score dimensions that passed verification (analysis queue exists)
    if not queue_file_exists(run_dir, dim_id):
        return False  # verification not completed for this dimension
    return True


def _setup_scoring_context(reports_dir: str, project: str, run_dir: Path, evaluation_dir: Path):
    """Resolve the scoring inputs shared across every dimension in this run.

    Returns (evidence_entries, source_file_count, params, compiled_dir,
    evaluators_dir, dim_states), or None when there's no evidence to score.
    """
    evidence_entries = list_dimension_evidence(run_dir)
    if evidence_entries is None:
        return None

    ensure_dir(evaluation_dir)
    source_file_count = _read_project_source_file_count(reports_dir, project)
    params = load_params()
    # Same standard dirs as a completed run's scoring, so off-standard
    # findings are quarantined here too instead of entering the grade.
    from quodeq.services.evidence_rescore import standard_dirs  # noqa: PLC0415
    compiled_dir, evaluators_dir = standard_dirs()

    dim_states = read_dimensions(run_dir).get("dimensions", {})
    return evidence_entries, source_file_count, params, compiled_dir, evaluators_dir, dim_states


def score_completed_evidence(
    reports_dir: str, job: dict,
    *,
    parser=parse_jsonl_to_evidence,
    scorer=score_evidence,
    reporter=write_dimension_report,
) -> None:
    """Score any dimensions that have evidence but no evaluation report.

    Called after cancellation so completed dimensions are preserved in the
    dashboard even when the overall run was cancelled.

    Populates ``files_read`` from the dim's queue.json (count of dispatched
    files) and ``source_file_count`` from the project's scan.json. Without
    these, the scored eval has ``filesRead: 0``, which ``scoring_view``'s
    trust rule rejects — the user sees the cancelled run's data fall
    through to an older run's stale value despite real findings on disk.

    *parser*, *scorer* and *reporter* are injection seams for tests: each
    defaults to the production collaborator it replaces
    (``parse_jsonl_to_evidence``, ``score_evidence``, ``write_dimension_report``).
    """
    project = job.get("outputProject")
    run_id = job.get("outputRunId")
    if not project or not run_id:
        return

    run_dir = Path(reports_dir) / project / run_id
    evaluation_dir = run_dir / "evaluation"
    ctx = _setup_scoring_context(reports_dir, project, run_dir, evaluation_dir)
    if ctx is None:
        return
    evidence_entries, source_file_count, params, compiled_dir, evaluators_dir, dim_states = ctx

    for dim_id, jsonl_path, evidence_size in evidence_entries:
        if not _should_score_dimension(dim_id, evidence_size, run_dir, evaluation_dir, dim_states):
            continue
        files_read = _read_queue_files_count(dimension_queue_file(run_dir, dim_id))
        _score_one_dimension(
            dim_id, jsonl_path, run_id, evaluation_dir, source_file_count, files_read,
            compiled_dir, evaluators_dir, params,
            parser=parser, scorer=scorer, reporter=reporter, log=_logger,
        )
