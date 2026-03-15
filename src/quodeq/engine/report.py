"""Report builder — assembles scored evaluation data into JSON report files."""
from __future__ import annotations

import json
import re
from pathlib import Path

from quodeq.core.types import ScoringResult, to_camel_dict
from quodeq.engine.evidence import Evidence
from quodeq.engine.scoring_internals import score_to_grade_label

_REPORT_SCHEMA_VERSION = 1


def grade_from_score(score: str | None) -> str | None:
    """Convert a numeric score string (e.g. '7/10') to a letter grade (Critical..Exemplary)."""
    if not score:
        return None

    hit = re.match(r"(\d+(?:\.\d+)?)", str(score))
    if not hit:
        return None

    return score_to_grade_label(float(hit.group(1)))


def _build_score_lookup(per_principle_scores: dict) -> dict:
    """Index per-principle scores by display_name for joining against evidence.

    Values may be PrincipleScore dataclasses or plain dicts; we normalise to
    dicts via ``to_camel_dict`` so downstream code can use uniform access.
    """
    lookup: dict = {}
    for item in per_principle_scores.values():
        raw = to_camel_dict(item) if not isinstance(item, dict) else item
        key = raw.get("displayName") or raw.get("display_name", "")
        if key:
            lookup[key] = raw
    return lookup


_VIOLATION_FIELDS = ("file", "line", "title", "reason", "snippet", "severity", "req", "req_refs")
_COMPLIANCE_FIELDS = ("file", "line", "title", "reason", "snippet", "req", "req_refs")
_GRADE_INSUFFICIENT = "Insufficient"


def _flatten_findings(items: list, label: str, fields: tuple[str, ...]) -> list[dict]:
    """Flatten a list of finding dicts, tagging each with *label* and keeping only *fields*."""
    result: list[dict] = []
    for item in items:
        entry: dict = {"principle": label}
        entry.update({f: item.get(f) for f in fields if item.get(f) is not None})
        result.append(entry)
    return result


def _build_principle_rows(
    evidence: dict, lookup: dict
) -> tuple[list, list, list, dict]:
    """Build principle rows and flattened violation/compliance lists from evidence.

    Returns (principle_rows, flat_violations, flat_compliance, sev_tally).
    """
    principle_rows: list = []
    flat_violations: list = []
    flat_compliance: list = []
    sev_tally = {"critical": 0, "major": 0, "minor": 0}

    for raw_key, pdata in evidence.get("principles", {}).items():
        label = pdata.get("display_name", raw_key)
        matched = lookup.get(label, {})
        grade = matched.get("grade")
        # Support both snake_case (legacy dict) and camelCase (serialised DTO) keys
        raw_final = matched.get("finalScore") or matched.get("final_score")
        # Insufficient principles have no meaningful score — suppress "0.0/10".
        if grade == _GRADE_INSUFFICIENT:
            formatted_score = None
        else:
            formatted_score = f"{round(raw_final, 1)}/10" if raw_final is not None else None
        row: dict = {
            "name": label,
            "score": formatted_score,
            "grade": grade or grade_from_score(formatted_score),
        }
        ci = matched.get("confidenceInterval") or matched.get("confidence_interval")
        gs = matched.get("gradeStability") or matched.get("grade_stability")
        if ci is not None:
            row["confidence_interval"] = ci
        if gs is not None:
            row["grade_stability"] = gs
        raw_metrics = pdata.get("metrics")
        if raw_metrics:
            row["metrics"] = raw_metrics
        principle_rows.append(row)

        viols = _flatten_findings(pdata.get("violations", []), label, _VIOLATION_FIELDS)
        flat_violations.extend(viols)
        for v in viols:
            bucket = v.get("severity", "minor")
            if bucket in sev_tally:
                sev_tally[bucket] += 1

        flat_compliance.extend(_flatten_findings(pdata.get("compliance", []), label, _COMPLIANCE_FIELDS))

    return principle_rows, flat_violations, flat_compliance, sev_tally


def build_report_json(dimension: str, evidence: dict, scores: ScoringResult | dict | None) -> dict:
    """Build a complete JSON report dict from evidence and scoring data for one dimension."""
    per_principle_scores: dict = {}
    aggregate: dict = {}
    if scores:
        if isinstance(scores, dict):
            per_principle_scores = scores.get("principles", {})
            aggregate = scores.get("overall", {})
        else:
            per_principle_scores = scores.principles
            aggregate = to_camel_dict(scores.overall) if scores.overall else {}

    lookup = _build_score_lookup(per_principle_scores)
    principle_rows, flat_violations, flat_compliance, sev_tally = _build_principle_rows(evidence, lookup)

    # Support both snake_case (legacy dict) and camelCase (serialised DTO) keys
    weighted = aggregate.get("weightedScore") or aggregate.get("weighted_score")
    if weighted is not None:
        top_score = f"{round(weighted, 1)}/10"
        top_grade = aggregate.get("grade") or grade_from_score(top_score)
    else:
        top_score = None
        top_grade = None

    raw_meta = evidence.get("meta", {})
    return {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "dimension": dimension,
        "project": evidence.get("repository", ""),
        # runId is always empty here; write_report_json fills it in from the path
        "runId": "",
        "discipline": evidence.get("discipline", ""),
        "date": evidence.get("date", ""),
        "sourceFileCount": evidence.get("source_file_count"),
        "filesRead": evidence.get("files_read", 0),
        "coveragePct": evidence.get("coverage_pct", 0.0),
        "meta": {
            "analysis_prompt_version": raw_meta.get("analysis_prompt_version"),
            "scoring_prompt_version": raw_meta.get("scoring_prompt_version"),
            "mapping_file_hash": raw_meta.get("mapping_file_hash"),
            "quodeq_version": raw_meta.get("quodeq_version"),
        },
        "overallScore": top_score,
        "overallGrade": top_grade,
        "principles": principle_rows,
        "violations": flat_violations,
        "compliance": flat_compliance,
        "totals": {
            "violationCount": len(flat_violations),
            "complianceCount": len(flat_compliance),
            "severity": sev_tally,
        },
    }


def build_full_report(evidence: Evidence, scores: ScoringResult | dict) -> dict:
    """Build report with engine metadata fields."""
    ev_dict = evidence.to_evidence_dict()
    base = build_report_json(evidence.plugin_id, ev_dict, scores)
    base["dismissed_count"] = evidence.dismissed_count
    base["evidence_summary"] = evidence.summary()
    return base


def build_dashboard_report(evidence: Evidence, scores: ScoringResult | dict) -> dict:
    """Build web dashboard report format."""
    ev_dict = evidence.to_evidence_dict()
    return build_report_json(evidence.plugin_id, ev_dict, scores)


def write_reports(evidence: Evidence, scores: ScoringResult | dict, output_dir: Path) -> None:
    """Write report files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    full_report = build_full_report(evidence, scores)
    dashboard_report = build_dashboard_report(evidence, scores)

    dim = evidence.plugin_id
    if ".." in dim or "/" in dim or "\\" in dim:
        raise ValueError(f"Invalid plugin_id for report output: {dim!r}")
    try:
        (output_dir / f"{dim}_full.json").write_text(json.dumps(full_report, indent=2))
        (output_dir / f"{dim}.json").write_text(json.dumps(dashboard_report, indent=2))
    except OSError as exc:
        raise OSError(f"Failed to write report files to {output_dir}: {exc}") from exc


def write_dimension_report(evidence: Evidence, scores: ScoringResult | dict, dimension: str, output_dir: Path) -> None:
    """Write a per-dimension report file: <dimension>.json."""
    output_dir.mkdir(parents=True, exist_ok=True)

    report = build_dashboard_report(evidence, scores)
    report["dimension"] = dimension
    try:
        (output_dir / f"{dimension}.json").write_text(json.dumps(report, indent=2))
    except OSError as exc:
        raise OSError(f"Failed to write dimension report {dimension} to {output_dir}: {exc}") from exc
