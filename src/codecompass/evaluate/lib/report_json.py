from __future__ import annotations

import json
import re
from pathlib import Path

from codecompass.evaluate.lib.common import log_warning


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
        formatted_score = f"{raw_final}/10" if raw_final is not None else None

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
            flat_entry: dict = {"principle": label}
            flat_entry.update(
                {field: viol.get(field) for field in ("file", "line", "reason", "snippet", "severity")}
            )
            flat_violations.append(flat_entry)

            bucket = viol.get("severity", "minor")
            if bucket in sev_tally:
                sev_tally[bucket] += 1

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
        top_score = f"{round(weighted)}/10"
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
