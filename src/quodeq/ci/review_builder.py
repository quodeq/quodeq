"""Build GitHub PR review payloads from evaluation reports."""
from __future__ import annotations


def _normalize_snippet(snippet: str) -> str:
    """Normalize whitespace for robust snippet comparison."""
    return " ".join((snippet or "").split())


def classify_violations(
    current: list[dict],
    baseline: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Classify each current violation as NEW or EXISTING based on baseline.

    A violation is EXISTING if the baseline has a violation in the same file
    with a matching (whitespace-normalized) snippet. Otherwise NEW.

    Returns (new_violations, existing_violations).
    """
    # Index baseline by file → set of normalized snippets
    baseline_index: dict[str, set[str]] = {}
    for v in baseline:
        file = v.get("file", "")
        snippet = _normalize_snippet(v.get("snippet", ""))
        if file:
            baseline_index.setdefault(file, set()).add(snippet)

    new_list: list[dict] = []
    existing_list: list[dict] = []
    for v in current:
        file = v.get("file", "")
        snippet = _normalize_snippet(v.get("snippet", ""))
        if snippet and snippet in baseline_index.get(file, set()):
            existing_list.append(v)
        else:
            new_list.append(v)
    return new_list, existing_list


def violation_to_comment(violation: dict, status: str = "new") -> dict:
    """Convert a violation to a GitHub PR review comment dict.

    status: "new" (introduced by this PR) or "existing" (pre-existing baseline issue).
    """
    severity = violation.get("severity", "minor")
    title = violation.get("title", "Violation")
    reason = violation.get("reason", "")
    req = violation.get("req", "")

    severity_label = severity.upper()
    status_prefix = "🆕 NEW" if status == "new" else "⚠️ Pre-existing"

    body_parts = [f"{status_prefix} · **{severity_label}** — {title}"]
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
    new_violations: list[dict],
    existing_violations: list[dict],
    duration_seconds: int | None = None,
    baseline_available: bool = True,
    artifact_url: str | None = None,
) -> str:
    """Build the review body summarizing all dimension results.

    Violations outside the PR's changed lines are omitted entirely — they are
    never posted as comments (GitHub would 422) and are not surfaced in the
    body either. A PR review speaks only to the touched code; out-of-diff
    findings remain available in the full evaluation artifact.
    """
    # Diff mode is signaled by reports with unscored ("N/A") dimensions —
    # PR diff runs skip scoring, so the per-dimension score table and the
    # "no baseline" note (which frames absence-of-baseline as a scoring
    # concern) don't apply. Detect from the data the caller already passes.
    is_diff_mode = bool(reports) and all(
        r.get("overallScore") == "N/A" for r in reports
    )

    lines = ["## Quodeq Evaluation", ""]

    if not baseline_available and not is_diff_mode:
        lines.append(
            "> **Note:** No baseline available — this is the first run. "
            "All violations are shown as new; no baseline comparison was made."
        )
        lines.append("")

    # Per-dimension scores (skipped in diff mode — nothing was scored).
    if not is_diff_mode:
        for report in reports:
            dimension = report.get("dimension", "unknown")
            score = report.get("overallScore", "N/A")
            grade = report.get("overallGrade", "N/A")
            lines.append(f"**{dimension.title()}**: {score} ({grade})")
        lines.append("")

    # Violation breakdown
    new_count = len(new_violations)
    existing_count = len(existing_violations)
    if is_diff_mode:
        lines.append(f"🔍 **{new_count} violation(s) found in PR diff**")
    else:
        lines.append(f"🆕 **{new_count} new** violation(s) introduced by this PR")
        if existing_count > 0:
            lines.append(f"⚠️ **{existing_count} pre-existing** issue(s) in changed files (not introduced by this PR)")
    lines.append("")

    if new_count > 0:
        new_severity_counts: dict[str, int] = {}
        for v in new_violations:
            sev = v.get("severity", "minor")
            new_severity_counts[sev] = new_severity_counts.get(sev, 0) + 1
        parts = [f"{n} {sev}" for sev, n in new_severity_counts.items() if n > 0]
        if parts:
            lines.append(f"New violations by severity: {', '.join(parts)}")
        lines.append("")

    if duration_seconds is not None:
        minutes = duration_seconds // 60
        seconds = duration_seconds % 60
        lines.append(f"_Evaluation completed in {minutes}m {seconds}s_")

    if artifact_url is not None:
        lines.append("")
        lines.append(f"[Download full report]({artifact_url})")

    return "\n".join(lines)


def determine_verdict(new_violations: list[dict]) -> str:
    """Determine the review verdict based on NEW violation severities.

    Existing (pre-existing baseline) violations do not influence the verdict —
    this PR is only responsible for what it introduces.

    Returns: 'COMMENT' or 'REQUEST_CHANGES'.

    Note: GitHub Actions' default token is **not permitted to approve pull
    requests** — submitting a review with event=APPROVE returns HTTP 422
    ("GitHub Actions is not permitted to approve pull requests"). So clean
    runs post a COMMENT review instead; the summary body carries the "no
    new violations" message and no blocking changes are requested.
    """
    if not new_violations:
        return "COMMENT"

    severities = {v.get("severity", "minor") for v in new_violations}
    if severities & {"critical", "high"}:
        return "REQUEST_CHANGES"
    return "COMMENT"
