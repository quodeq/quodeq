from __future__ import annotations

import json
import re
from pathlib import Path

from codecompass.evaluate.lib.common import log_warning


_SCORE_GRADE_BANDS: list[tuple[float, str]] = [
    (9, "Exemplary"),
    (7, "Good"),
    (5, "Adequate"),
    (3, "Poor"),
]


def grade_from_score(score: str | None) -> str | None:
    # Nothing to map if the input is falsy
    if not score:
        return None

    # Accept both "7/10" and plain "7" — pull the leading number out
    hit = re.match(r"(\d+(?:\.\d+)?)", str(score))
    if not hit:
        return None

    numeric = float(hit.group(1))

    for threshold, label in _SCORE_GRADE_BANDS:
        if numeric >= threshold:
            return label
    return "Critical"


def _build_scores_lookup(scores: dict | None) -> tuple[dict, dict]:
    """Extract per-principle scores lookup and aggregate from scores payload."""
    if not scores:
        return {}, {}
    per_principle = scores.get("principles", {})
    lookup: dict = {}
    for item in per_principle.values():
        key = item.get("display_name", "")
        if key:
            lookup[key] = item
    return lookup, scores.get("overall", {})


def _flatten_principles(
    evidence: dict, lookup: dict,
) -> tuple[list[dict], list[dict], list[dict], dict[str, int]]:
    """Walk evidence principles to build rows, flat violations, flat compliance, and severity tally."""
    principle_rows: list = []
    flat_violations: list = []
    flat_compliance: list = []
    sev_tally = {"critical": 0, "major": 0, "minor": 0}

    for raw_key, pdata in evidence.get("principles", {}).items():
        label = pdata.get("display_name", raw_key)
        matched = lookup.get(label, {})

        raw_final = matched.get("final_score")
        formatted_score = f"{round(raw_final, 1)}/10" if raw_final is not None else None
        resolved_grade = matched.get("grade") or grade_from_score(formatted_score)

        row: dict = {"name": label, "score": formatted_score, "grade": resolved_grade}
        if matched.get("confidence_interval") is not None:
            row["confidence_interval"] = matched["confidence_interval"]
        if matched.get("grade_stability") is not None:
            row["grade_stability"] = matched["grade_stability"]
        raw_metrics = pdata.get("metrics")
        if raw_metrics:
            row["metrics"] = raw_metrics
        principle_rows.append(row)

        for viol in pdata.get("violations", []):
            flat_entry: dict = {"principle": label}
            flat_entry.update({field: viol.get(field) for field in ("file", "line", "reason", "snippet", "severity")})
            flat_violations.append(flat_entry)
            bucket = viol.get("severity", "minor")
            if bucket in sev_tally:
                sev_tally[bucket] += 1

        for comp in pdata.get("compliance", []):
            flat_entry = {"principle": label}
            flat_entry.update({field: comp.get(field) for field in ("file", "line", "reason", "snippet")})
            flat_compliance.append(flat_entry)

    return principle_rows, flat_violations, flat_compliance, sev_tally


def _resolve_overall(aggregate: dict) -> tuple[str | None, str | None]:
    """Derive top-level score and grade strings from the aggregate block."""
    weighted = aggregate.get("weighted_score")
    if weighted is not None:
        top_score = f"{round(weighted, 1)}/10"
        top_grade = aggregate.get("grade") or grade_from_score(top_score)
        return top_score, top_grade
    return None, None


def build_report_json(dimension: str, evidence: dict, scores: dict | None) -> dict:
    lookup, aggregate = _build_scores_lookup(scores)
    principle_rows, flat_violations, flat_compliance, sev_tally = _flatten_principles(evidence, lookup)
    top_score, top_grade = _resolve_overall(aggregate)
    raw_meta = evidence.get("meta", {})

    return {
        "dimension": dimension,
        "project": evidence.get("repository", ""),
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


def write_report_json(
    evidence_file: str,
    output_file: str,
    scores_file: str | None = None,
) -> None:
    with open(evidence_file, encoding="utf-8") as fh:
        evidence_data = json.load(fh)

    # Strip the conventional "_evidence" suffix to get the dimension name
    file_stem = Path(evidence_file).stem
    dimension_name = file_stem[:-9] if file_stem.endswith("_evidence") else file_stem

    scores_data = None
    if scores_file:
        scores_path = Path(scores_file)
        if scores_path.exists():
            try:
                with open(scores_path, encoding="utf-8") as sh:
                    scores_data = json.load(sh)
            except Exception as exc:
                log_warning(f"Could not load scores file {scores_file}: {exc}")

    report = build_report_json(dimension_name, evidence_data, scores_data)

    # Recover the run identifier from the output path.
    # Convention: .../evaluation/<run_id>/... means "evaluation" is parts[-2]
    # when the output file sits directly inside the evaluation folder.
    # More precisely: parts[idx - 1] where parts[idx] == "evaluation".
    path_parts = Path(output_file).parts
    try:
        eval_idx = path_parts.index("evaluation")
        report["runId"] = path_parts[eval_idx - 1]
    except (ValueError, IndexError):
        pass

    Path(output_file).write_text(json.dumps(report, indent=2), encoding="utf-8")
