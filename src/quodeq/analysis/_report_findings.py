"""Findings flattening and principle-row building for reports."""
from __future__ import annotations

from quodeq.analysis._report_constants import (
    _COMPLIANCE_FIELDS,
    _FIELD_CONFIDENCE_INTERVAL,
    _FIELD_CONFIDENCE_INTERVAL_SNAKE,
    _FIELD_FINAL_SCORE,
    _FIELD_FINAL_SCORE_SNAKE,
    _GRADE_INSUFFICIENT,
    _VIOLATION_FIELDS,
)
from quodeq.analysis._report_scoring import grade_from_score


def _flatten_findings(items: list, label: str, fields: tuple[str, ...]) -> list[dict]:
    """Flatten a list of finding dicts, tagging each with *label* and keeping only *fields*."""
    result: list[dict] = []
    for item in items:
        entry: dict = {"principle": label}
        entry.update({f: item.get(f) for f in fields if item.get(f) is not None})
        result.append(entry)
    return result


def _build_principle_row(raw_key: str, pdata: dict, lookup: dict) -> dict:
    """Build a single principle row dict from evidence and score lookup."""
    label = pdata.get("display_name", raw_key)
    matched = lookup.get(label, {})
    grade = matched.get("grade")
    raw_final = matched.get(_FIELD_FINAL_SCORE)
    if raw_final is None:
        raw_final = matched.get(_FIELD_FINAL_SCORE_SNAKE)
    if grade == _GRADE_INSUFFICIENT:
        formatted_score = None
    else:
        formatted_score = f"{round(raw_final, 1)}/10" if raw_final is not None else None
    row: dict = {
        "name": label,
        "score": formatted_score,
        "grade": grade or grade_from_score(formatted_score),
    }
    ci = matched.get(_FIELD_CONFIDENCE_INTERVAL) or matched.get(_FIELD_CONFIDENCE_INTERVAL_SNAKE)
    gs = matched.get("gradeStability") or matched.get("grade_stability")
    if ci is not None:
        row["confidence_interval"] = ci
    if gs is not None:
        row["grade_stability"] = gs
    raw_metrics = pdata.get("metrics")
    if raw_metrics:
        row["metrics"] = raw_metrics
    return row


def build_principle_rows(
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
        principle_rows.append(_build_principle_row(raw_key, pdata, lookup))

        viols = _flatten_findings(pdata.get("violations", []), label, _VIOLATION_FIELDS)
        flat_violations.extend(viols)
        for v in viols:
            bucket = v.get("severity", "minor")
            if bucket in sev_tally:
                sev_tally[bucket] += 1

        flat_compliance.extend(
            _flatten_findings(pdata.get("compliance", []), label, _COMPLIANCE_FIELDS)
        )

    return principle_rows, flat_violations, flat_compliance, sev_tally
