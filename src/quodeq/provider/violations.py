"""Violation resolution and aggregation for the filesystem action provider."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.adapters.fs.report_parser import parse_eval_from_json, parse_eval_markdown
from quodeq.provider.violation_context import ViolationContext  # noqa: F401 — re-export
from quodeq.provider.violations_parsing import (
    parse_violations_from_evidence,
    parse_violations_from_jsonl,
    parse_violations_from_stream,
)

_MAX_VIOLATION_FILES = 20


def resolve_dimension_eval(
    base: Path, project: str, run_id: str, dimension: str,
) -> dict[str, Any] | None:
    """Try successive file formats to load evaluation data for a dimension."""

    eval_path = base / "evaluation" / f"{dimension}.json"
    if eval_path.exists():
        return parse_eval_from_json(eval_path, project, run_id, dimension)

    markdown_path = base / "evaluation" / f"{dimension}_eval.md"
    if markdown_path.exists():
        try:
            content = markdown_path.read_text()
        except OSError:
            return None
        return parse_eval_markdown(content, project, run_id, dimension)

    ctx = ViolationContext(project=project, run_id=run_id, dimension=dimension)

    evidence_path = base / "evidence" / f"{dimension}_evidence.json"
    if evidence_path.exists():
        return parse_violations_from_evidence(evidence_path, ctx)

    jsonl_path = base / "evidence" / f"{dimension}_evidence.jsonl"
    stream_path = base / "evidence" / f"{dimension}_live.stream"
    if jsonl_path.exists() and jsonl_path.stat().st_size > 0:
        return parse_violations_from_jsonl(jsonl_path, stream_path, ctx)

    if stream_path.exists():
        return parse_violations_from_stream(stream_path, ctx)

    return None


def aggregate_violations(dashboard: dict[str, Any]) -> dict[str, Any]:
    """Aggregate violation counts and top files from dashboard dimensions."""
    summary: dict[str, Any] = {"total": 0, "critical": 0, "major": 0, "minor": 0, "byFile": {}}
    for dim in dashboard.get("dimensions", []) or []:
        summary["total"] += dim.get("totals", {}).get("violationCount", 0)
        severity = dim.get("totals", {}).get("severity", {})
        for sev_key in ("critical", "major", "minor"):
            summary[sev_key] += severity.get(sev_key, 0)
        for violation in dim.get("violations", []) or []:
            file_path = violation.get("file")
            if not file_path:
                continue
            entry = summary["byFile"].setdefault(
                file_path, {"path": file_path, "count": 0, "critical": 0, "major": 0, "minor": 0}
            )
            entry["count"] += 1
            sev = violation.get("severity", "minor")
            if sev in entry:
                entry[sev] += 1
    summary["files"] = sorted(summary["byFile"].values(), key=lambda item: item["count"], reverse=True)[:_MAX_VIOLATION_FILES]
    summary.pop("byFile", None)
    return summary
