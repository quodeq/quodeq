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
import os
from pathlib import Path

from quodeq.config.paths import default_paths
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.core.scoring.engine import score_evidence
from quodeq.core.scoring.params import ScoringParams
from quodeq.core.types import ScoringResult
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)


def standard_dirs() -> tuple[Path | None, Path | None]:
    """(compiled_dir, evaluators_dir) resolved exactly as scan time does.

    Scan runs build RunConfig from default_paths() (see _cli_evaluation), so
    resolving here keeps the rescore's PrincipleResolver identical to the one
    that quarantined findings at scan time. Without these dirs the resolver is
    permissive and quarantined findings would re-enter the grade on rescore.
    """
    paths = default_paths()
    standards = paths.standards_dir
    compiled = (standards / "compiled") if standards and standards.exists() else None
    return compiled, paths.evaluators_dir


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
    # dim_id / run_dir are built from request-supplied values. Guard with the
    # path-injection remediation CodeQL recommends: normalize with
    # os.path.normpath (a pure-string op, no filesystem access) to collapse any
    # ".." segments, then confirm the result stays within run_dir/evidence
    # before touching the filesystem. (validate_path_segment additionally
    # rejects separators in dim_id at the input.)
    validate_path_segment(dim_id)
    evidence_dir = os.path.normpath(str(run_dir / "evidence"))
    candidate = os.path.normpath(os.path.join(evidence_dir, f"{dim_id}_evidence.jsonl"))
    if not candidate.startswith(evidence_dir + os.sep):
        _logger.debug("Evidence path escapes run dir for %s/%s", run_dir.name, dim_id)
        return None
    jsonl = Path(candidate)
    if not jsonl.is_file() or jsonl.stat().st_size == 0:
        return None
    compiled_dir, evaluators_dir = standard_dirs()
    try:
        evidence = parse_jsonl_to_evidence(jsonl, EvidenceContext(
            language="", repository="", date_str="",
            source_file_count=source_file_count, files_read=files_read,
        ), compiled_dir=compiled_dir, evaluators_dir=evaluators_dir)
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
