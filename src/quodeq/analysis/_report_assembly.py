"""Report assembly -- builds complete JSON report dicts from evidence and scores."""
from __future__ import annotations

from dataclasses import dataclass

from quodeq.core.types import ScoringResult
from quodeq.core.evidence.model import Evidence

from quodeq.analysis._report_constants import (
    _FIELD_WEIGHTED_SCORE,
    _FIELD_WEIGHTED_SCORE_SNAKE,
    _REPORT_SCHEMA_VERSION,
)
from quodeq.analysis._report_scoring import (
    build_score_lookup,
    extract_scores,
    grade_from_score,
)
from quodeq.analysis._report_findings import build_principle_rows


@dataclass
class _ReportData:
    """Grouped components for assembling a report dict."""

    dimension: str
    evidence: dict
    top_score: str | None
    top_grade: str | None
    principle_rows: list
    flat_violations: list
    flat_compliance: list
    sev_tally: dict


def _assemble_report_dict(data: _ReportData) -> dict:
    """Assemble the final report dict from pre-computed components."""
    raw_meta = data.evidence.get("meta", {})
    report: dict = {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "dimension": data.dimension,
        "project": data.evidence.get("repository", ""),
        "runId": "",
        "discipline": data.evidence.get("discipline", ""),
        "date": data.evidence.get("date", ""),
        "sourceFileCount": data.evidence.get("source_file_count"),
        "filesRead": data.evidence.get("files_read", 0),
        "coveragePct": data.evidence.get("coverage_pct", 0.0),
        "meta": {
            "analysis_prompt_version": raw_meta.get("analysis_prompt_version"),
            "scoring_prompt_version": raw_meta.get("scoring_prompt_version"),
            "mapping_file_hash": raw_meta.get("mapping_file_hash"),
            "quodeq_version": raw_meta.get("quodeq_version"),
        },
        "overallScore": data.top_score,
        "overallGrade": data.top_grade,
        "principles": data.principle_rows,
        "violations": data.flat_violations,
        "compliance": data.flat_compliance,
        "totals": {
            "violationCount": len(data.flat_violations),
            "complianceCount": len(data.flat_compliance),
            "severity": data.sev_tally,
        },
    }
    module = data.evidence.get("module")
    if module:
        report["module"] = module
    return report


def build_report_json(
    dimension: str, evidence: dict, scores: ScoringResult | dict | None,
) -> dict:
    """Build a complete JSON report dict from evidence and scoring data for one dimension."""
    per_principle_scores, aggregate = extract_scores(scores)
    lookup = build_score_lookup(per_principle_scores)
    principle_rows, flat_violations, flat_compliance, sev_tally = build_principle_rows(
        evidence, lookup,
    )

    weighted = aggregate.get(_FIELD_WEIGHTED_SCORE) or aggregate.get(_FIELD_WEIGHTED_SCORE_SNAKE)
    if weighted is not None:
        top_score = f"{round(weighted, 1)}/10"
        top_grade = aggregate.get("grade") or grade_from_score(top_score)
    else:
        top_score = None
        top_grade = None

    return _assemble_report_dict(_ReportData(
        dimension=dimension, evidence=evidence, top_score=top_score,
        top_grade=top_grade, principle_rows=principle_rows,
        flat_violations=flat_violations, flat_compliance=flat_compliance,
        sev_tally=sev_tally,
    ))


def build_full_report(evidence: Evidence, scores: ScoringResult | dict) -> dict:
    """Build report with engine metadata fields."""
    ev_dict = evidence.to_evidence_dict()
    base = build_report_json(evidence.language, ev_dict, scores)
    base["dismissed_count"] = evidence.dismissed_count
    base["evidence_summary"] = evidence.summary()
    return base


def build_dashboard_report(evidence: Evidence, scores: ScoringResult | dict) -> dict:
    """Build web dashboard report format."""
    ev_dict = evidence.to_evidence_dict()
    return build_report_json(evidence.language, ev_dict, scores)
