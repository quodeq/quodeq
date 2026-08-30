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
from pathlib import Path

from quodeq.config.paths import default_paths
from quodeq.config.evidence_env import cwe_url_template
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.data.fs.standards_loader import read_req_to_principle_map
from quodeq.core.scoring.engine import score_evidence
from quodeq.core.scoring.params import ScoringParams
from quodeq.core.types import ScoringResult
from quodeq.services.ports import evidence_file_size
from quodeq.services.suppression import is_deleted, is_dismissed
from quodeq.shared.validation import validate_path_segment
from quodeq.shared.log_sink import log_malformed_jsonl_line, log_quarantined_findings

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


def score_dimension_from_evidence(
    run_dir: Path,
    dim_id: str,
    *,
    dismissed: set[tuple],
    deleted: set[tuple],
    source_file_count: int,
    files_read: int,
    params: ScoringParams,
    standard_dirs_fn: Callable[[], tuple[Path | None, Path | None]] | None = None,
) -> ScoringResult | None:
    """Score `dim_id` from run_dir's evidence jsonl, excluding suppressed findings.

    Returns None when the evidence file is missing/empty/unparseable so the
    caller can fall back to the legacy in-place formula.

    *standard_dirs_fn* resolves ``(compiled_dir, evaluators_dir)``; None keeps
    the module-level :func:`standard_dirs` (global config resolution) so
    existing callers stay valid while tests can substitute fixed dirs.
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
    if evidence_file_size(jsonl) == 0:
        return None
    compiled_dir, evaluators_dir = (standard_dirs_fn or standard_dirs)()
    try:
        evidence = parse_jsonl_to_evidence(jsonl, EvidenceContext(
            language="", repository="", date_str="",
            source_file_count=source_file_count, files_read=files_read,
        ), compiled_dir=compiled_dir, evaluators_dir=evaluators_dir,
            req_map_reader=read_req_to_principle_map,
            cwe_url_template=cwe_url_template(),
            on_quarantine=log_quarantined_findings,
            on_malformed_line=log_malformed_jsonl_line)
    except (OSError, ValueError, KeyError) as exc:
        _logger.debug("Evidence rescore parse failed for %s/%s: %s", run_dir.name, dim_id, exc)
        return None
    if evidence is None:
        return None

    for pe in evidence.principles.values():
        pe.violations = [
            v for v in pe.violations
            if not is_dismissed(dismissed, req=v.get("req"), principle=pe.practice_id,
                                file=v.get("file"), line=v.get("line"))
            and not is_deleted(deleted, dimension=dim_id, principle=pe.practice_id,
                               file=v.get("file"))
        ]
        # Same call shape as core/evidence/parser._build_principles so the
        # recomputed metrics (confidence, compliance %) match scan time.
        pe.compute_metrics(source_file_count=source_file_count)

    # Broad catch on purpose (mirrors mutation_rescore and the CLI print
    # guard): the engine can throw on edge-case evidence, and every consumer
    # (dashboard build, /api/rescore, trend fetcher) treats None as "fall back
    # to the stored score" — one bad dimension must not fail the whole run.
    try:
        return score_evidence(evidence, mode="numerical", params=params)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Evidence rescore failed for %s/%s: %s", run_dir.name, dim_id, exc)
        return None
