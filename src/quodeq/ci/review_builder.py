"""Build GitHub PR review payloads from evaluation reports."""
from __future__ import annotations


def violation_to_comment(violation: dict) -> dict:
    """Convert a single violation to a GitHub PR review comment dict.

    Returns a dict with 'path', 'body', and optionally 'line'.
    """
    severity = violation.get("severity", "minor")
    title = violation.get("title", "Violation")
    reason = violation.get("reason", "")
    req = violation.get("req", "")

    severity_label = severity.upper()
    body_parts = [f"**{severity_label}** — {title}"]
    if reason:
        body_parts.append(reason)
    if req:
        body_parts.append(f"_Requirement: {req}_")

    comment: dict = {
        "path": violation["file"],
        "body": "\n\n".join(body_parts),
    }

    line = violation.get("line")
    if line is not None:
        comment["line"] = int(line)

    return comment


def build_review_summary(
    reports: list[dict],
    duration_seconds: int | None = None,
) -> str:
    """Build the review body summarizing all dimension results."""
    lines = ["## Quodeq Evaluation", ""]

    for report in reports:
        dimension = report.get("dimension", "unknown")
        score = report.get("overallScore", "N/A")
        grade = report.get("overallGrade", "N/A")
        totals = report.get("totals", {})
        severity = totals.get("severity", {})

        lines.append(f"**{dimension.title()}**: {score} ({grade})")
        severity_parts = []
        for level in ("critical", "major", "minor"):
            count = severity.get(level, 0)
            if count > 0:
                severity_parts.append(f"{count} {level}")
        if severity_parts:
            lines.append(f"Violations: {', '.join(severity_parts)}")
        lines.append("")

    if duration_seconds is not None:
        minutes = duration_seconds // 60
        seconds = duration_seconds % 60
        lines.append(f"_Evaluation completed in {minutes}m {seconds}s_")

    return "\n".join(lines)


def determine_verdict(violations: list[dict]) -> str:
    """Determine the review verdict based on violation severities.

    Returns: 'APPROVE', 'COMMENT', or 'REQUEST_CHANGES'.
    """
    if not violations:
        return "APPROVE"

    severities = {v.get("severity", "minor") for v in violations}
    if severities & {"critical", "high"}:
        return "REQUEST_CHANGES"
    return "COMMENT"
