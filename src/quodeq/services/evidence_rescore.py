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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from quodeq.config.paths import default_paths
from quodeq.config.evidence_env import cwe_url_template
from quodeq.core.evidence.parser import (
    EvidenceContext, EvidenceParseOptions, parse_jsonl_to_evidence)
from quodeq.core.scoring.engine import score_evidence
from quodeq.core.scoring.params import ScoringParams
from quodeq.core.types import ScoringResult
from quodeq.services.wiring import evidence_file_size, load_compiled_refs, read_req_to_principle_map
from quodeq.services.suppression import FindingRef, is_deleted, is_dismissed
from quodeq.shared.validation import validate_path_segment
from quodeq.shared.log_sink import log_malformed_jsonl_line, log_quarantined_findings

_logger = logging.getLogger(__name__)


def standard_dirs() -> tuple[Path | None, Path | None]:
    """(compiled_dir, evaluators_dir) resolved exactly as scan time does.

    Scan runs build RunConfig from default_paths() (see cli_evaluation), so
    resolving here keeps the rescore's PrincipleResolver identical to the one
    that quarantined findings at scan time. Without these dirs the resolver is
    permissive and quarantined findings would re-enter the grade on rescore.
    """
    paths = default_paths()
    standards = paths.standards_dir
    compiled = (standards / "compiled") if standards and standards.exists() else None
    return compiled, paths.evaluators_dir


def _resolve_evidence_jsonl(run_dir: Path, dim_id: str) -> Path | None:
    """Return the dimension's evidence jsonl path, or None if it escapes
    run_dir/evidence (logged) or dim_id fails validation (raises).

    dim_id / run_dir are built from request-supplied values. Guard with the
    path-injection remediation CodeQL recommends: normalize with
    os.path.normpath (a pure-string op, no filesystem access) to collapse any
    ".." segments, then confirm the result stays within run_dir/evidence
    before touching the filesystem. (validate_path_segment additionally
    rejects separators in dim_id at the input.)
    """
    validate_path_segment(dim_id)
    evidence_dir = os.path.normpath(str(run_dir / "evidence"))
    candidate = os.path.normpath(os.path.join(evidence_dir, f"{dim_id}_evidence.jsonl"))
    if not candidate.startswith(evidence_dir + os.sep):
        _logger.debug("Evidence path escapes run dir for %s/%s", run_dir.name, dim_id)
        return None
    return Path(candidate)


def _apply_suppressions(
    evidence, dim_id: str, dismissed: set[tuple], deleted: set[tuple],
) -> int:
    """Drop dismissed/deleted violations from each principle's evidence in
    place, and return how many violations that removed."""
    excluded = 0
    for pe in evidence.principles.values():
        kept = [
            v for v in pe.violations
            if not is_dismissed(dismissed, FindingRef(
                req=v.get("req"), principle=pe.practice_id, file=v.get("file"),
                line=v.get("line"), snippet=v.get("snippet")))
            and not is_deleted(deleted, dimension=dim_id, principle=pe.practice_id,
                               file=v.get("file"))
        ]
        excluded += len(pe.violations) - len(kept)
        pe.violations = kept
    return excluded


def _recompute_metrics(evidence, source_file_count: int) -> None:
    """Recompute every principle's metrics in place.

    Same call shape as core/evidence/parser._build_principles so the
    recomputed metrics (confidence, compliance %) match scan time.
    """
    for pe in evidence.principles.values():
        pe.compute_metrics(source_file_count=source_file_count)


def _parse_evidence_jsonl(jsonl: Path, run_dir: Path, dim_id: str, request: EvidenceScoreRequest):
    """Parse the evidence jsonl into an Evidence object, or None on any
    parse failure (logged at warning)."""
    compiled_dir, evaluators_dir = (request.standard_dirs_fn or standard_dirs)()
    try:
        return parse_jsonl_to_evidence(jsonl, EvidenceContext(
            language="", repository="", date_str="",
            source_file_count=request.source_file_count, files_read=request.files_read,
        ), EvidenceParseOptions(
            compiled_dir=compiled_dir, evaluators_dir=evaluators_dir,
            req_map_reader=request.req_map_reader or read_req_to_principle_map,
            refs_reader=request.refs_reader or load_compiled_refs,
            cwe_url_template=cwe_url_template(),
            on_quarantine=log_quarantined_findings,
            on_malformed_line=log_malformed_jsonl_line))
    except (OSError, ValueError, KeyError) as exc:
        _logger.warning("Evidence rescore parse failed for %s/%s: %s", run_dir.name, dim_id, exc)
        return None


@dataclass(frozen=True)
class EvidenceScoreRequest:
    """Inputs for scoring one dimension from its evidence.

    *standard_dirs_fn* resolves ``(compiled_dir, evaluators_dir)``; None keeps
    the module-level :func:`standard_dirs` (global config resolution) so
    existing callers stay valid while tests can substitute fixed dirs.

    *req_map_reader* and *refs_reader* are the same seams
    ``EvidenceParseOptions`` exposes; None keeps the wiring default
    (``read_req_to_principle_map`` / ``load_compiled_refs``) so existing
    callers stay valid while tests can substitute fakes.
    """

    dismissed: set[tuple]
    deleted: set[tuple]
    source_file_count: int
    files_read: int
    params: ScoringParams
    standard_dirs_fn: Callable[[], tuple[Path | None, Path | None]] | None = None
    req_map_reader: Callable | None = None
    refs_reader: Callable | None = None


@dataclass(frozen=True)
class EvidenceRescore:
    """Return shape of ``rescore_dimension_from_evidence``.

    ``result`` is None when the caller should fall back to the stored scan
    score; ``excluded`` is the violation count the suppressions removed and is
    meaningful even then.
    """

    result: ScoringResult | None
    excluded: int


def rescore_dimension_from_evidence(
    run_dir: Path,
    dim_id: str,
    request: EvidenceScoreRequest,
    *,
    score_when_nothing_excluded: bool = True,
) -> EvidenceRescore:
    """`score_dimension_from_evidence` plus the number of violations the
    suppressions removed.

    Parses the evidence jsonl exactly once: the exclusion count and the
    rescored result both come from that same parse (previously the CLI
    counted exclusions with one parse, then rescored with a second).
    Returns ``EvidenceRescore(None, 0)`` when the evidence file is
    missing/empty/unparseable, so the caller can fall back to the legacy
    in-place formula.

    *score_when_nothing_excluded* False stops at the count when no
    suppression matched this run: with zero exclusions the result equals the
    stored scan score by construction, so a caller that only prints an
    adjusted grade (the CLI) has nothing to gain from the metrics recompute
    and the scoring pass. The dashboard callers need the score itself and
    keep the default.
    """
    jsonl = _resolve_evidence_jsonl(run_dir, dim_id)
    if jsonl is None or evidence_file_size(jsonl) == 0:
        return EvidenceRescore(None, 0)
    evidence = _parse_evidence_jsonl(jsonl, run_dir, dim_id, request)
    if evidence is None:
        return EvidenceRescore(None, 0)

    excluded = _apply_suppressions(evidence, dim_id, request.dismissed, request.deleted)
    if excluded == 0 and not score_when_nothing_excluded:
        return EvidenceRescore(None, 0)
    _recompute_metrics(evidence, request.source_file_count)

    # Broad catch on purpose (mirrors mutation_rescore and the CLI print
    # guard): the engine can throw on edge-case evidence, and every consumer
    # (dashboard build, /api/rescore, trend fetcher) treats None as "fall back
    # to the stored score" — one bad dimension must not fail the whole run.
    try:
        result = score_evidence(evidence, mode="numerical", params=request.params)
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        _logger.warning("Evidence rescore failed for %s/%s: %s", run_dir.name, dim_id, exc)
        return EvidenceRescore(None, excluded)
    return EvidenceRescore(result, excluded)


def score_dimension_from_evidence(
    run_dir: Path,
    dim_id: str,
    request: EvidenceScoreRequest,
) -> ScoringResult | None:
    """Score `dim_id` from run_dir's evidence jsonl, excluding suppressed findings.

    Returns None when the evidence file is missing/empty/unparseable so the
    caller can fall back to the legacy in-place formula.
    """
    return rescore_dimension_from_evidence(run_dir, dim_id, request).result
