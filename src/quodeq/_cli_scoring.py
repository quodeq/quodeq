"""Post-scan score printing — suppression-aware rescoring for the CLI.

Split from ``_cli_evaluation.py`` to keep each module under 300 lines.
Re-exported from ``_cli_evaluation.py`` so existing
``quodeq._cli_evaluation.<name>`` imports keep working.

``_print_scores`` calls ``score_dimension_from_evidence``, which tests patch
at ``quodeq._cli_evaluation.score_dimension_from_evidence`` — that call goes
through a deferred ``from quodeq import _cli_evaluation as _facade`` lookup
so a patch on the facade module lands at call time.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from quodeq.config.evidence_env import cwe_url_template
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.core.scoring.params import ScoringParams
from quodeq.core.types import ScoringResult
from quodeq.data.fs.standards_loader import load_compiled_refs, read_req_to_principle_map
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.evidence_rescore import standard_dirs
from quodeq.services.suppression import is_deleted, is_dismissed
from quodeq.shared.log_sink import log_malformed_jsonl_line, log_quarantined_findings

_logger = logging.getLogger(__name__)

_NUMERIC_SCORE_RE = re.compile(r"^-?\d+(?:\.\d+)?/\d+$")


def _count_excluded_findings(
    run_dir: Path, dim_id: str, dismissed: set[tuple], deleted: set[tuple],
) -> int:
    """Count this run's evidence violations for *dim_id* that a dismissal or
    deletion suppresses.

    Mirrors the exclusion predicates in
    ``services.evidence_rescore.score_dimension_from_evidence`` so the count
    matches what the rescore actually drops. Returns 0 when the evidence
    jsonl is missing, empty, or unparseable — the caller then falls back to
    the original score line (no evidence to rescore from).
    """
    jsonl = run_dir / "evidence" / f"{dim_id}_evidence.jsonl"
    if not jsonl.is_file() or jsonl.stat().st_size == 0:
        return 0
    # Same standard dirs as the rescore: a quarantined finding never entered
    # the grade, so a dismissal targeting it must not count as an exclusion.
    compiled_dir, evaluators_dir = standard_dirs()
    try:
        evidence = parse_jsonl_to_evidence(jsonl, EvidenceContext(
            language="", repository="", date_str="",
            source_file_count=0, files_read=0,
        ), compiled_dir=compiled_dir, evaluators_dir=evaluators_dir,
            req_map_reader=read_req_to_principle_map,
            refs_reader=load_compiled_refs,
            cwe_url_template=cwe_url_template(),
            on_quarantine=log_quarantined_findings,
            on_malformed_line=log_malformed_jsonl_line)
    except (OSError, ValueError, KeyError):
        return 0
    if evidence is None:
        return 0

    count = 0
    for pe in evidence.principles.values():
        for v in pe.violations:
            if is_dismissed(dismissed, req=v.get("req"), principle=pe.practice_id,
                            file=v.get("file"), line=v.get("line")) \
                    or is_deleted(deleted, dimension=dim_id,
                                  principle=pe.practice_id, file=v.get("file")):
                count += 1
    return count


def _dim_evidence_counts(evaluation_dir: Path, dim_id: str) -> tuple[int, int]:
    """Read (sourceFileCount, filesRead) from a dimension's just-written report JSON.

    Falls back to (0, 0) when the report is missing or unparseable.
    """
    try:
        data = json.loads((evaluation_dir / f"{dim_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0, 0
    return int(data.get("sourceFileCount") or 0), int(data.get("filesRead") or 0)


def _format_adjusted_score(original: str, result: ScoringResult) -> str | None:
    """Format *result*'s overall value to match *original*'s numeric-vs-grade shape.

    Returns None when no adjusted value is available, so the caller falls
    back to the original line.
    """
    overall = result.overall
    if overall is None:
        return None
    if _NUMERIC_SCORE_RE.match(original):
        if overall.weighted_score is None:
            return None
        denom = original.rsplit("/", 1)[1]
        return f"{overall.weighted_score}/{denom}"
    return overall.grade or overall.weighted_grade


def _print_scores(
    scores: dict[str, str], run_dir: Path, project_dir: Path, params: ScoringParams,
) -> None:
    """Print each dimension's score, noting any dismissed/deleted findings excluded.

    With no active dismissals or deletions for the project, this is
    byte-identical to the historical ``  {dim}: {score}`` line — the common
    case. When a dimension's just-scanned evidence has one or more matching
    suppressions, prints the evidence-based rescore instead (the same basis
    the dashboard rescore uses — see ``services/evidence_rescore.py``), with
    a suffix noting how many findings were excluded. Dimensions with no
    matching suppression, or with evidence too old/missing to rescore from,
    fall back to the original line unchanged.
    """
    if not scores:
        return
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)
    if not dismissed and not deleted:
        for dim, score in scores.items():
            print(f"  {dim}: {score}")
        return

    from quodeq import _cli_evaluation as _facade

    evaluation_dir = run_dir / "evaluation"
    for dim, score in scores.items():
        excluded = _count_excluded_findings(run_dir, dim, dismissed, deleted)
        if excluded <= 0:
            print(f"  {dim}: {score}")
            continue
        source_file_count, files_read = _dim_evidence_counts(evaluation_dir, dim)
        try:
            result = _facade.score_dimension_from_evidence(
                run_dir, dim,
                dismissed=dismissed, deleted=deleted,
                source_file_count=source_file_count, files_read=files_read,
                params=params,
            )
            adjusted = _format_adjusted_score(score, result) if result is not None else None
        except Exception as exc:  # noqa: BLE001 — console embellishment on top of
            # reports already on disk; nothing upstream catches a generic exception
            # (see _run_pipeline_with_cleanup), so fall back instead of crashing.
            _logger.debug("Suppression-aware rescore failed for dim %s: %s", dim, exc)
            adjusted = None
        if adjusted is None:
            print(f"  {dim}: {score}")
            continue
        print(f"  {dim}: {adjusted} ({excluded} dismissed findings excluded)")
