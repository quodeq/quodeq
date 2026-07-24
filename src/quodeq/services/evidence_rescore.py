"""Rescore a dimension from its raw evidence, minus dismissed/deleted findings.

This is the single-scoring-basis fix: instead of re-implementing the grade
formula over report-JSON findings (which lose `violation_type`, principle
weights, and evidence metrics — see services/rescore.py history), we replay
the exact scan-time path: parse `<dim>_evidence.jsonl`, drop excluded
judgments, recompute metrics, and run the same scoring engine. With zero
exclusions the result is identical to the stored scan scores by construction.
"""
from __future__ import annotations

import logging
from pathlib import Path

from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.core.scoring.engine import score_evidence
from quodeq.core.scoring.params import ScoringParams
from quodeq.core.types import ScoringResult
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)


def _coerce_line(line: object) -> int:
    try:
        return int(line)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _is_dismissed(v: dict, dismissed: set[tuple]) -> bool:
    return (v.get("req") or "", v.get("file") or "", _coerce_line(v.get("line"))) in dismissed


def _is_deleted(v: dict, dim_id: str, practice_id: str, deleted: set[tuple]) -> bool:
    return (dim_id, practice_id, v.get("file") or "") in deleted


def score_dimension_from_evidence(
    run_dir: Path,
    dim_id: str,
    *,
    dismissed: set[tuple],
    deleted: set[tuple],
    source_file_count: int,
    files_read: int,
    params: ScoringParams,
) -> ScoringResult | None:
    """Score `dim_id` from run_dir's evidence jsonl, excluding suppressed findings.

    Returns None when the evidence file is missing/empty/unparseable so the
    caller can fall back to the legacy in-place formula.
    """
    # dim_id is used to build a filesystem path and can carry request-supplied
    # values; reject separators/traversal before touching the filesystem.
    validate_path_segment(dim_id)
    jsonl = run_dir / "evidence" / f"{dim_id}_evidence.jsonl"
    if not jsonl.is_file() or jsonl.stat().st_size == 0:
        return None
    try:
        evidence = parse_jsonl_to_evidence(jsonl, EvidenceContext(
            language="", repository="", date_str="",
            source_file_count=source_file_count, files_read=files_read,
        ))
    except (OSError, ValueError, KeyError) as exc:
        _logger.debug("Evidence rescore parse failed for %s/%s: %s", run_dir.name, dim_id, exc)
        return None
    if evidence is None:
        return None

    for pe in evidence.principles.values():
        pe.violations = [
            v for v in pe.violations
            if not _is_dismissed(v, dismissed)
            and not _is_deleted(v, dim_id, pe.practice_id, deleted)
        ]
        # Same call shape as core/evidence/parser._build_principles so the
        # recomputed metrics (confidence, compliance %) match scan time.
        pe.compute_metrics(source_file_count=source_file_count)

    return score_evidence(evidence, mode="numerical", params=params)
