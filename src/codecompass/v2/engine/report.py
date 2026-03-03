from __future__ import annotations

import json
import re
from pathlib import Path

from codecompass.v2.engine.evidence import Evidence


_SEVERITY_MAP = {
    "critical": "critical",
    "high": "critical",
    "major": "major",
    "medium": "major",
    "minor": "minor",
    "low": "minor",
}


def _normalize_severity(raw: str | None) -> str:
    """Map AI judge severities (high/medium/low) to dashboard severities (critical/major/minor)."""
    return _SEVERITY_MAP.get((raw or "").lower(), "minor")


def grade_from_score(score: str | None) -> str | None:
    # Nothing to map if the input is falsy
    if not score:
        return None

    # Accept both "7/10" and plain "7" — pull the leading number out
    hit = re.match(r"(\d+(?:\.\d+)?)", str(score))
    if not hit:
        return None

    numeric = float(hit.group(1))

    # Thresholds are exclusive lower bounds for the next tier
    if numeric < 3:
        return "Critical"
    if numeric < 5:
        return "Poor"
    if numeric < 7:
        return "Adequate"
    if numeric < 9:
        return "Good"
    return "Exemplary"


def build_report_json(dimension: str, evidence: dict, scores: dict | None) -> dict:
    # Pull the two sub-dicts out of the scores payload when it exists
    per_principle_scores: dict = {}
    aggregate: dict = {}
    if scores:
        per_principle_scores = scores.get("principles", {})
        aggregate = scores.get("overall", {})

    # Index scores by display_name so we can join them against evidence entries
    lookup: dict = {}
    for item in per_principle_scores.values():
        key = item.get("display_name", "")
        if key:
            lookup[key] = item

    principle_rows: list = []
    flat_violations: list = []
    flat_compliance: list = []

    # Track severity bucket counts as we iterate through violations
    sev_tally = {"critical": 0, "major": 0, "minor": 0}

    for raw_key, pdata in evidence.get("principles", {}).items():
        label = pdata.get("display_name", raw_key)
        matched = lookup.get(label, {})

        # Build the score string only when a numeric value is present
        raw_final = matched.get("final_score")
        formatted_score = f"{round(raw_final, 1)}/10" if raw_final is not None else None

        # Prefer grade already computed by the scorer, fall back to our own mapping
        resolved_grade = matched.get("grade") or grade_from_score(formatted_score)

        row: dict = {
            "name": label,
            "score": formatted_score,
            "grade": resolved_grade,
        }

        # Optional fields — only include when the scorer provided them
        if matched.get("confidence_interval") is not None:
            row["confidence_interval"] = matched["confidence_interval"]
        if matched.get("grade_stability") is not None:
            row["grade_stability"] = matched["grade_stability"]

        # Metrics live on the evidence side, not the scores side
        raw_metrics = pdata.get("metrics")
        if raw_metrics:
            row["metrics"] = raw_metrics

        principle_rows.append(row)

        # Flatten violations, stamping each with the principle name
        for viol in pdata.get("violations", []):
            normalized_sev = _normalize_severity(viol.get("severity"))
            flat_entry: dict = {"principle": label}
            flat_entry.update(
                {field: viol.get(field) for field in ("file", "line", "reason", "snippet")}
            )
            flat_entry["severity"] = normalized_sev
            flat_violations.append(flat_entry)

            if normalized_sev in sev_tally:
                sev_tally[normalized_sev] += 1

        # Flatten compliance examples the same way
        for comp in pdata.get("compliance", []):
            flat_entry = {"principle": label}
            flat_entry.update(
                {field: comp.get(field) for field in ("file", "line", "reason", "snippet")}
            )
            flat_compliance.append(flat_entry)

    # Overall score only exists when the scorer produced a weighted value
    weighted = aggregate.get("weighted_score")
    if weighted is not None:
        top_score = f"{round(weighted, 1)}/10"
        top_grade = aggregate.get("grade") or grade_from_score(top_score)
    else:
        top_score = None
        top_grade = None

    # Pull the meta block; forward only the known versioning fields
    raw_meta = evidence.get("meta", {})

    return {
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
            "codecompass_version": raw_meta.get("codecompass_version"),
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


def build_report(evidence: Evidence, scores: dict, dimension: str | None = None) -> dict:
    """Build the scored evaluation report for the dashboard."""
    v1_evidence = evidence.to_v1_evidence_dict()
    dim_label = dimension or evidence.plugin_id
    return build_report_json(dim_label, v1_evidence, scores)


def _split_evidence_by_dimension(evidence: Evidence) -> dict[str, Evidence]:
    """Split a single Evidence into per-dimension Evidence objects."""
    from codecompass.v2.engine.evidence import Evidence as Ev, PrincipleEvidence

    dim_principles: dict[str, dict[str, PrincipleEvidence]] = {}
    for key, pe in evidence.principles.items():
        dim = pe.dimension or evidence.plugin_id
        dim_principles.setdefault(dim, {})[key] = pe

    result: dict[str, Ev] = {}
    for dim, principles in dim_principles.items():
        result[dim] = Ev(
            repository=evidence.repository,
            plugin_id=evidence.plugin_id,
            date=evidence.date,
            source_file_count=evidence.source_file_count,
            files_read=evidence.files_read,
            coverage_pct=evidence.coverage_pct,
            principles=principles,
            dismissed_count=evidence.dismissed_count,
            meta=evidence.meta,
        )
    return result


def write_reports(
    evidence: Evidence,
    scores: dict,
    run_dir: Path,
    dimensions: list[str] | None = None,
) -> None:
    """Write per-dimension evaluation and evidence files.

    Output structure under *run_dir*::

        evaluation/<dimension>.json        — scored report
        evidence/<dimension>_evidence.json  — raw findings

    *dimensions* is the list requested via ``-d``; when the judge produces
    no principles we still write one file per requested dimension.
    """
    from codecompass.v2.engine.scoring import score_evidence

    eval_dir = run_dir / "evaluation"
    evidence_dir = run_dir / "evidence"
    eval_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    per_dim = _split_evidence_by_dimension(evidence)

    if not per_dim:
        # No principles — write one file per requested dimension (or plugin_id)
        dim_names = dimensions if dimensions else [evidence.plugin_id]
        for dim in dim_names:
            report = build_report(evidence, scores, dimension=dim)
            (eval_dir / f"{dim}.json").write_text(json.dumps(report, indent=2))
            ev_dict = evidence.to_v1_evidence_dict()
            (evidence_dir / f"{dim}_evidence.json").write_text(json.dumps(ev_dict, indent=2))
        return

    for dim, dim_evidence in per_dim.items():
        dim_scores = score_evidence(dim_evidence, mode=scores.get("mode", "numerical"))
        report = build_report(dim_evidence, dim_scores, dimension=dim)
        (eval_dir / f"{dim}.json").write_text(json.dumps(report, indent=2))
        ev_dict = dim_evidence.to_v1_evidence_dict()
        (evidence_dir / f"{dim}_evidence.json").write_text(json.dumps(ev_dict, indent=2))
