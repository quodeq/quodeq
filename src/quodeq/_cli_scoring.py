"""Post-scan score printing — suppression-aware rescoring for the CLI.

Split from ``cli_evaluation.py`` to keep each module under 300 lines.
Re-exported from ``cli_evaluation.py`` so existing
``quodeq.cli_evaluation.<name>`` imports keep working.

``_adjusted_score`` calls ``rescore_dimension_from_evidence``, which tests
patch at ``quodeq.cli_evaluation.rescore_dimension_from_evidence`` — that
call goes through a deferred ``from quodeq import cli_evaluation as
_facade`` lookup so a patch on the facade module lands at call time. That one
call also reports how many suppressions excluded, so a dimension's evidence
jsonl is parsed exactly once per print, not once to count exclusions and
again to rescore.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from quodeq.core.scoring.params import ScoringParams
from quodeq.core.types import ScoringResult
from quodeq.core.types.severity import Severity
from quodeq.data.fs.report_parser.finding_details import read_eval_report
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.violations import filter_dismissed_from_result
from quodeq.services.evidence_rescore import EvidenceScoreRequest, standard_dirs

_logger = logging.getLogger(__name__)

_NUMERIC_SCORE_RE = re.compile(r"^-?\d+(?:\.\d+)?/\d+$")


def _as_int(value: object) -> int:
    """Coerce *value* to int, falling back to 0 on junk input."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def dim_evidence_counts(evaluation_dir: Path, dim_id: str) -> tuple[int, int]:
    """Read (sourceFileCount, filesRead) from a dimension's just-written report JSON.

    Falls back to (0, 0) when the report is missing or unparseable.
    """
    data = _read_report(evaluation_dir, dim_id)
    return int(data.get("sourceFileCount") or 0), int(data.get("filesRead") or 0)


def _read_report(evaluation_dir: Path, dim_id: str) -> dict:
    """The dimension's report dict, or {} when missing or unparseable."""
    try:
        data = read_eval_report(evaluation_dir, dim_id)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _active_violations(report: dict, dim: str, dismissed: object, deleted: set) -> list[dict]:
    """The report's violations minus the project's dismissals and deletions."""
    if not report:
        return []
    filtered = filter_dismissed_from_result(
        {"violations": list(report.get("violations") or [])}, dismissed, deleted, dim,
    )
    return list((filtered or {}).get("violations") or [])


def _severity_tally(findings: list[dict]) -> dict[str, int]:
    tally = {Severity.CRITICAL: 0, Severity.MAJOR: 0, Severity.MINOR: 0}
    for finding in findings:
        key = finding.get("severity")
        tally[key if key in tally else Severity.MINOR] += 1
    return {str(k): v for k, v in tally.items()}


def _format_score_line(
    dim: str, score: str, totals: dict, suffix: str = "",
    *, open_types: int | None = None, coverage_pct: float | None = None,
) -> str:
    """One summary line: grade first, then the numbers that only move when
    the code moves (majors, open requirement types, density, coverage).

    The raw count is not on this line: it rises with coverage and sampling,
    not with the code. The numbers are the report's as written; a
    dismissed-findings suffix does not subtract from them.
    """
    if not totals:
        return f"  {dim}: {score}{suffix}"
    severity = totals.get("severity") or {}
    majors = _as_int(severity.get("major") or 0) + _as_int(severity.get("critical") or 0)
    parts = [f"{majors} major"]
    if open_types is not None:
        parts.append(f"{open_types} open type{'s' if open_types != 1 else ''}")
    per_100 = totals.get("violationsPer100Files")
    if per_100 is not None:
        parts.append(f"{per_100} per 100 files")
    if coverage_pct is not None:
        parts.append(f"{round(coverage_pct)}% coverage")
    return f"  {dim}: {score}  ({', '.join(parts)}){suffix}"


def format_adjusted_score(original: str, result: ScoringResult) -> str | None:
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


def _adjusted_score(
    run_dir: Path, dim: str, suppressions: tuple[set[tuple], set[tuple]],
    score: str, params: ScoringParams,
) -> tuple[str | None, int]:
    """Evidence-based rescore of *dim*: (adjusted score or None to fall back,
    count of violations the suppressions excluded).

    Goes through the ``cli_evaluation`` facade so tests can patch
    ``quodeq.cli_evaluation.rescore_dimension_from_evidence`` (module docstring).
    """
    from quodeq import cli_evaluation as _facade

    dismissed, deleted = suppressions
    source_file_count, files_read = dim_evidence_counts(run_dir / "evaluation", dim)
    try:
        rescored = _facade.rescore_dimension_from_evidence(
            run_dir, dim, EvidenceScoreRequest(
                dismissed=dismissed, deleted=deleted,
                source_file_count=source_file_count, files_read=files_read,
                params=params, standard_dirs_fn=standard_dirs,
            ),
            # Nothing excluded means the stored grade already is the answer
            # (see the return below), so don't pay for a scoring pass.
            score_when_nothing_excluded=False,
        )
    except ValueError as exc:
        # The only unguarded raise in this call chain: _resolve_evidence_jsonl's
        # validate_path_segment(dim_id) rejects a path-traversal/separator
        # character. Everything else rescore_dimension_from_evidence calls is
        # already fail-soft internally (evidence_rescore._parse_evidence_jsonl
        # catches (OSError, ValueError, KeyError) and returns None; the
        # score_evidence call site catches (ValueError, KeyError, TypeError,
        # ArithmeticError)).
        _logger.warning("suppression-aware rescore failed for dim %s: %s", dim, exc, exc_info=True)
        return None, 0
    if rescored.excluded == 0 or rescored.result is None:
        return None, rescored.excluded
    return format_adjusted_score(score, rescored.result), rescored.excluded


def print_scores(
    scores: dict[str, str], run_dir: Path, project_dir: Path, params: ScoringParams,
) -> None:
    """Print each dimension's score with its volume, noting excluded findings.

    Every line carries the report's violation count, major count and
    violations per 100 files read when the report exists. When a dimension's
    just-scanned evidence has one or more matching suppressions, the
    evidence-based rescore (the same basis the dashboard uses, see
    ``services/evidence_rescore.py``) replaces the grade and a suffix notes
    how many findings were excluded. Missing evidence or a rescore failure
    falls back to the original grade.
    """
    if not scores:
        return
    evaluation_dir = run_dir / "evaluation"
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)
    for dim, score in scores.items():
        report = _read_report(evaluation_dir, dim)
        totals = report.get("totals") if isinstance(report.get("totals"), dict) else {}
        adjusted, excluded = (
            _adjusted_score(run_dir, dim, (dismissed, deleted), score, params)
            if (dismissed or deleted) else (None, 0)
        )
        if adjusted is None:
            # The score is the report's own, so the counts are the report's own too.
            shown, suffix, counted = score, "", list(report.get("violations") or [])
        else:
            # The score excludes the suppressed findings, so the majors and the open types do too.
            shown, suffix = adjusted, f" ({excluded} dismissed findings excluded)"
            counted = _active_violations(report, dim, dismissed, deleted)
            totals = {**totals, "severity": _severity_tally(counted)}
        open_types = len({v.get("req") for v in counted if v.get("req")})
        print(_format_score_line(dim, shown, totals, suffix,
                                 open_types=open_types if report else None,
                                 coverage_pct=report.get("coveragePct")))
