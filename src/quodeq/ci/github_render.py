"""Render violations into GitHub PR review comments, summary, and verdict."""
from __future__ import annotations

import re
from dataclasses import dataclass

from quodeq.core.types.severity import Severity
from quodeq.shared.serialization import coerce_line


@dataclass(frozen=True, slots=True)
class ReviewOptions:
    """Run-level details the review summary renders around the findings.

    ``duration_seconds`` adds the "completed in" footer, ``baseline_available``
    False adds the first-run note, ``artifact_url`` adds the download link.
    """

    duration_seconds: int | None = None
    baseline_available: bool = True
    artifact_url: str | None = None


# Markdown and HTML control characters that untrusted finding text may carry.
_MD_SPECIAL = re.compile(r"([\\`*_#\[\]<>|~])")
# A list item ("- ", "+ ", "1. ", "2) ") or a thematic break ("---") only
# forms at paragraph start; reason is rendered as its own paragraph.
_LEADING_BLOCK_MARKER = re.compile(r"^(\d+)([.)])|^([-+])")
# GitHub's extended autolinks (http://, https://, www.) and @mentions/email
# links are recognised on the rendered text, after backslash escapes are
# resolved, so escaping cannot defuse them. A zero-width space after the
# trigger breaks the scan while leaving the text readable.
_AUTOLINK_TRIGGER = re.compile(r"(https?://|www\.|@)", re.IGNORECASE)
_ZWSP = "\u200b"


def _escape_leading_marker(match: re.Match) -> str:
    if match.group(1) is not None:
        return f"{match.group(1)}\\{match.group(2)}"
    return f"\\{match.group(3)}"


def _md_escape(text: object) -> str:
    """Neutralise markdown, HTML, autolink, and mention syntax in untrusted text.

    Titles, reasons, and requirement ids come from LLM output that quotes the
    PR's own content, so a crafted finding could inject headings, links, HTML,
    emphasis, or notifications into the review comment. CommonMark treats a
    backslash before any ASCII punctuation as that literal character, which
    GitHub renders plainly. Whitespace runs (including newlines) collapse to a
    single space so no inner line can start a block construct; a marker at the
    very start is escaped separately; autolink and mention triggers get a
    zero-width space so GitHub's post-render scans do not fire.
    """
    flat = " ".join(str(text).split())
    escaped = _MD_SPECIAL.sub(r"\\\1", flat)
    escaped = _LEADING_BLOCK_MARKER.sub(_escape_leading_marker, escaped)
    return _AUTOLINK_TRIGGER.sub(lambda m: m.group(1) + _ZWSP, escaped)


def violation_to_comment(violation: dict, status: str = "new") -> dict:
    """Convert a violation to a GitHub PR review comment dict.

    status: "new" (introduced by this PR) or "existing" (pre-existing baseline issue).
    """
    severity = violation.get("severity", Severity.MINOR)
    title = _md_escape(violation.get("title", "Violation"))
    reason = _md_escape(violation.get("reason", ""))
    req = _md_escape(violation.get("req", ""))

    severity_label = severity.upper()
    status_prefix = "🆕 NEW" if status == "new" else "⚠️ Pre-existing"

    body_parts = [f"{status_prefix} · **{severity_label}** — {title}"]
    if reason:
        body_parts.append(reason)
    if req:
        body_parts.append(f"_Requirement: {req}_")

    comment: dict = {
        "path": violation.get("file", "?"),
        "body": "\n\n".join(body_parts),
    }

    line = violation.get("line")
    if line is not None:
        comment["line"] = coerce_line(line)

    return comment


def _score_summary_lines(reports: list[dict], is_diff_mode: bool, baseline_available: bool) -> list[str]:
    """Baseline note (if applicable) + per-dimension score lines."""
    lines: list[str] = []
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
    return lines


def _violation_breakdown_lines(new_violations: list[dict], existing_violations: list[dict], is_diff_mode: bool) -> list[str]:
    """Headline new/existing counts + a by-severity breakdown of the new ones."""
    lines: list[str] = []
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
            sev = v.get("severity", Severity.MINOR)
            new_severity_counts[sev] = new_severity_counts.get(sev, 0) + 1
        parts = [f"{n} {sev}" for sev, n in new_severity_counts.items() if n > 0]
        if parts:
            lines.append(f"New violations by severity: {', '.join(parts)}")
        lines.append("")
    return lines


def _outside_diff_lines(outside: list[dict]) -> list[str]:
    """List NEW violations that fall outside the PR's changed hunks."""
    if not outside:
        return []
    lines: list[str] = []
    n = len(outside)
    noun = "finding" if n == 1 else "findings"
    lines.append(
        f"**{n} {noun} outside the changed lines** "
        "(GitHub can't anchor an inline comment to unchanged lines, so "
        "they're listed here):"
    )
    lines.append("")
    for v in outside:
        file = v.get("file", "?")
        line = v.get("line")
        loc = f"{file}:{line}" if line is not None else file
        severity = str(v.get("severity", Severity.MINOR)).upper()
        title = _md_escape(v.get("title") or "Violation")
        lines.append(f"- `{loc}` — **{severity}** {title}")
    lines.append("")
    return lines


def build_review_summary(
    reports: list[dict],
    new_violations: list[dict],
    existing_violations: list[dict],
    options: ReviewOptions | None = None,
    outside_diff_violations: list[dict] | None = None,
) -> str:
    """Build the review body summarizing all dimension results.

    options: run-level footer/note details (see :class:`ReviewOptions`);
    omitted means defaults.
    outside_diff_violations: NEW violations whose file:line falls outside the
    PR's changed hunks. GitHub can't anchor an inline comment there, so they're
    listed in a dedicated section with file:line + description instead of being
    silently dropped. The headline count and severity breakdown then reflect
    only the in-diff (inline-anchorable) violations, so the number shown agrees
    with the inline comments actually posted.
    """
    if options is None:
        options = ReviewOptions()
    outside = outside_diff_violations or []
    _outside_ids = {id(v) for v in outside}
    # Count and break down only the violations shown as inline comments; the
    # out-of-diff ones get their own listed section below.
    new_violations = [v for v in new_violations if id(v) not in _outside_ids]
    # Diff mode is signaled by reports with unscored ("N/A") dimensions —
    # PR diff runs skip scoring, so the per-dimension score table and the
    # "no baseline" note (which frames absence-of-baseline as a scoring
    # concern) don't apply. Detect from the data the caller already passes.
    is_diff_mode = bool(reports) and all(
        r.get("overallScore") == "N/A" for r in reports
    )

    lines = ["## Quodeq Evaluation", ""]
    lines += _score_summary_lines(reports, is_diff_mode, options.baseline_available)
    lines += _violation_breakdown_lines(new_violations, existing_violations, is_diff_mode)
    lines += _outside_diff_lines(outside)

    if options.duration_seconds is not None:
        minutes = options.duration_seconds // 60
        seconds = options.duration_seconds % 60
        lines.append(f"_Evaluation completed in {minutes}m {seconds}s_")

    if options.artifact_url is not None:
        lines.append("")
        lines.append(f"[Download full report]({options.artifact_url})")

    return "\n".join(lines)


# Findings in these dimensions are posted as review comments but never turn
# the verdict into REQUEST_CHANGES: the bot runs them on a local model to flag
# regressions early, and one noisy critical must not block a merge.
_COMMENT_ONLY_DIMENSIONS = frozenset({"performance"})


def determine_verdict(new_violations: list[dict]) -> str:
    """Determine the review verdict based on NEW violation severities.

    Existing (pre-existing baseline) violations do not influence the verdict —
    this PR is only responsible for what it introduces. Findings in
    _COMMENT_ONLY_DIMENSIONS (performance) never request changes; a violation
    without a dimension counts.

    Returns: 'COMMENT' or 'REQUEST_CHANGES'.

    Note: GitHub Actions' default token is **not permitted to approve pull
    requests** — submitting a review with event=APPROVE returns HTTP 422
    ("GitHub Actions is not permitted to approve pull requests"). So clean
    runs post a COMMENT review instead; the summary body carries the "no
    new violations" message and no blocking changes are requested.
    """
    blocking = [v for v in new_violations if v.get("dimension") not in _COMMENT_ONLY_DIMENSIONS]
    if not blocking:
        return "COMMENT"

    severities = {v.get("severity", Severity.MINOR) for v in blocking}
    if severities & {"critical", "high"}:
        return "REQUEST_CHANGES"
    return "COMMENT"
