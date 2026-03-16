"""Violation resolution and aggregation for the filesystem action provider."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from quodeq.adapters.fs.report_parser import parse_eval_from_json, parse_eval_markdown
from quodeq.core.types import ViolationFileEntry, ViolationResponse, ViolationSummary
from quodeq.shared.utils import read_text
from quodeq.services.violation_context import ViolationContext  # noqa: F401 — re-export
from quodeq.services.violations_parsing import (
    parse_violations_from_evidence,
    parse_violations_from_jsonl,
    parse_violations_from_stream,
)

_DEFAULT_MAX_VIOLATION_FILES = 20


def _max_violation_files(override: int | None = None, env: dict[str, str] | None = None) -> int:
    """Return the max number of violation files to include. *override* bypasses env for testing."""
    if override is not None:
        return override
    return int((env or os.environ).get("QUODEQ_MAX_VIOLATION_FILES", str(_DEFAULT_MAX_VIOLATION_FILES)))


def resolve_dimension_eval(
    base: Path, project: str, run_id: str, dimension: str,
    compiled_dir: Path | None = None,
) -> ViolationResponse | dict[str, Any] | None:
    """Try successive file formats to load evaluation data for a dimension."""

    eval_path = base / "evaluation" / f"{dimension}.json"
    if eval_path.exists():
        return parse_eval_from_json(eval_path, project, run_id, dimension)

    markdown_path = base / "evaluation" / f"{dimension}_eval.md"
    if markdown_path.exists():
        try:
            content = read_text(markdown_path)
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
        return parse_violations_from_jsonl(jsonl_path, stream_path, ctx, compiled_dir=compiled_dir)

    if stream_path.exists():
        return parse_violations_from_stream(stream_path, ctx)

    return None


def aggregate_violations(dashboard: dict[str, Any]) -> ViolationSummary:
    """Aggregate violation counts and top files from dashboard dimensions."""
    total = 0
    critical = 0
    major = 0
    minor = 0
    by_file: dict[str, dict[str, Any]] = {}
    for dim in dashboard.get("dimensions", []) or []:
        total += dim.get("totals", {}).get("violationCount", 0)
        severity = dim.get("totals", {}).get("severity", {})
        critical += severity.get("critical", 0)
        major += severity.get("major", 0)
        minor += severity.get("minor", 0)
        for violation in dim.get("violations", []) or []:
            file_path = violation.get("file")
            if not file_path:
                continue
            entry = by_file.setdefault(
                file_path, {"path": file_path, "count": 0, "critical": 0, "major": 0, "minor": 0}
            )
            entry["count"] += 1
            sev = violation.get("severity", "minor")
            if sev in entry:
                entry[sev] += 1
    top_files = sorted(
        by_file.values(), key=lambda item: item["count"], reverse=True,
    )[:_max_violation_files()]
    return ViolationSummary(
        total=total,
        critical=critical,
        major=major,
        minor=minor,
        files=[ViolationFileEntry(**f) for f in top_files],
    )
