"""Report assembly -- builds complete JSON report dicts from evidence and scores."""
from __future__ import annotations

from dataclasses import dataclass

from quodeq.core.scoring._constants import MAX_SCORE
from quodeq.core.types import ScoringResult
from quodeq.core.evidence.model import Evidence, violations_per_100_files
from quodeq.data.fs.dimension_report._report_taxonomy import unmapped_types

from quodeq.data.fs.dimension_report._report_constants import (
    FIELD_WEIGHTED_SCORE,
    FIELD_WEIGHTED_SCORE_SNAKE,
    REPORT_SCHEMA_VERSION,
)
from quodeq.data.fs.dimension_report._report_scoring import (
    build_score_lookup,
    extract_scores,
    grade_from_score,
)
from quodeq.data.fs.dimension_report._report_findings import build_principle_rows


@dataclass
class ReportData:
    """Grouped components for assembling a report dict."""

    dimension: str
    evidence: dict
    top_score: str | None
    top_grade: str | None
    principle_rows: list
    flat_violations: list
    flat_compliance: list
    sev_tally: dict


def assemble_report_dict(data: ReportData) -> dict:
    """Assemble the final report dict from pre-computed components."""
    raw_meta = data.evidence.get("meta", {})
    report: dict = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "dimension": data.dimension,
        "project": data.evidence.get("repository", ""),
        "runId": "",
        "discipline": data.evidence.get("discipline", ""),
        "date": data.evidence.get("date", ""),
        "sourceFileCount": data.evidence.get("source_file_count"),
        "filesRead": data.evidence.get("files_read", 0),
        "coveragePct": data.evidence.get("coverage_pct", 0.0),
        # Trust metadata, not a findings bucket: how many findings never reached
        # scoring because they named a principle outside the standard.
        "quarantinedCount": data.evidence.get("quarantined_count", 0),
        "exitReason": data.evidence.get("exit_reason"),
        "meta": {
            "analysis_prompt_version": raw_meta.get("analysis_prompt_version"),
            "scoring_prompt_version": raw_meta.get("scoring_prompt_version"),
            "mapping_file_hash": raw_meta.get("mapping_file_hash"),
            "quodeq_version": raw_meta.get("quodeq_version"),
            # Tags the taxonomy could not place (spec 2026-09-15, section 7).
            "unmappedTypes": unmapped_types(data.evidence.get("principles") or {}),
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
            "violationsPer100Files": violations_per_100_files(
                len(data.flat_violations), data.evidence.get("files_read", 0),
            ),
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

    weighted = aggregate.get(FIELD_WEIGHTED_SCORE) or aggregate.get(FIELD_WEIGHTED_SCORE_SNAKE)
    if weighted is not None:
        top_score = f"{round(weighted, 1)}/{MAX_SCORE}"
        top_grade = aggregate.get("grade") or grade_from_score(top_score)
    else:
        top_score = None
        top_grade = None

    return assemble_report_dict(ReportData(
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
