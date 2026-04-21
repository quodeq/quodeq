"""Post evaluation results as GitHub PR reviews."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
import urllib.error
from urllib.request import Request, urlopen

from quodeq.ci.review_builder import (
    build_review_summary,
    classify_violations,
    determine_verdict,
    violation_to_comment,
)

_logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_FILES_PAGE_SIZE = 100
_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _parse_hunks(patch: str | None) -> set[int]:
    """Extract RIGHT-side line numbers covered by any hunk in a unified diff.

    Lines starting with '+' (added) or ' ' (context) advance the RIGHT-side
    counter; '-' (removed) lines do not. '\\ No newline at end of file'
    markers are ignored. Returns the set of line numbers in the new file that
    appear anywhere inside a hunk — these are the lines GitHub will accept as
    review-comment anchors.
    """
    if not patch:
        return set()
    lines: set[int] = set()
    current_line = 0
    for raw in patch.splitlines():
        if raw.startswith("@@"):
            m = _HUNK_HEADER_RE.match(raw)
            if not m:
                current_line = 0
                continue
            current_line = int(m.group(1))
            continue
        if current_line <= 0:
            continue
        if raw.startswith("\\"):
            continue  # "No newline at end of file" marker
        if raw.startswith("+"):
            lines.add(current_line)
            current_line += 1
        elif raw.startswith("-"):
            continue  # LEFT-only; doesn't advance RIGHT-side counter
        else:
            # Context line (" foo") or empty line at bottom of hunk — both advance.
            lines.add(current_line)
            current_line += 1
    return lines


def _github_get(url: str, token: str) -> list | dict:
    """Authenticated GET to the GitHub API. Returns parsed JSON."""
    req = Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    with urlopen(req) as resp:
        return json.loads(resp.read())


def fetch_pr_changed_lines(
    owner: str, repo: str, pr_number: int, token: str,
) -> dict[str, set[int]]:
    """Return ``{filename: set of RIGHT-side line numbers in hunks}`` for a PR.

    Paginates through ``GET /repos/{owner}/{repo}/pulls/{pr_number}/files``.
    Files with no ``patch`` (binary, too-large, rename-only) are skipped —
    they remain un-annotable by line-anchored review comments.
    """
    result: dict[str, set[int]] = {}
    page = 1
    while True:
        url = (
            f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files"
            f"?per_page={_FILES_PAGE_SIZE}&page={page}"
        )
        data = _github_get(url, token)
        if not isinstance(data, list) or not data:
            break
        for entry in data:
            name = entry.get("filename")
            patch = entry.get("patch")
            if not name or not patch:
                continue
            lines = _parse_hunks(patch)
            if lines:
                result.setdefault(name, set()).update(lines)
        if len(data) < _FILES_PAGE_SIZE:
            break
        page += 1
    return result


def filter_comments_to_diff(
    comments: list[dict],
    changed_lines: dict[str, set[int]],
) -> tuple[list[dict], int]:
    """Keep only comments whose path+line falls within ``changed_lines``.

    Returns ``(kept, dropped_count)``. Comments missing a ``line`` key are
    always dropped — GitHub requires a line anchor for review comments.
    """
    kept: list[dict] = []
    dropped = 0
    for c in comments:
        path = c.get("path")
        line = c.get("line")
        if path and line is not None and line in changed_lines.get(path, set()):
            kept.append(c)
        else:
            dropped += 1
    return kept, dropped


def load_evaluation_reports(evaluation_dir: Path) -> list[dict]:
    """Load dashboard report JSONs from the evaluation directory.

    Reads {dimension}.json files, skipping {dimension}_full.json.
    """
    reports = []
    for path in sorted(evaluation_dir.glob("*.json")):
        if path.stem.endswith("_full"):
            continue
        with open(path) as f:
            reports.append(json.load(f))
    return reports


def build_review_payload(
    reports: list[dict],
    baseline_violations: list[dict] | None = None,
    duration_seconds: int | None = None,
    baseline_available: bool = True,
    artifact_url: str | None = None,
    changed_lines: dict[str, set[int]] | None = None,
) -> dict:
    """Build the full GitHub PR review API payload from evaluation reports.

    baseline_violations: violations from the last nightly evaluation on the base
    branch. When provided, current violations are classified as NEW or EXISTING.
    When omitted, all violations are treated as NEW.
    baseline_available: when False, a note is added to the summary explaining
    that no baseline comparison was made (first-run scenario).
    artifact_url: when provided, a download link is appended to the summary.
    changed_lines: when provided, review comments are filtered to only those
    whose path+line fall within the PR's changed hunks. GitHub rejects
    comments outside the diff with HTTP 422, so the CLI must fetch the PR's
    files and pass this mapping. Dropped comments are counted in the summary.
    """
    all_violations: list[dict] = []
    for report in reports:
        all_violations.extend(report.get("violations", []))

    new_violations, existing_violations = classify_violations(
        all_violations, baseline_violations or []
    )

    all_comments = [violation_to_comment(v, status="new") for v in new_violations]
    all_comments += [violation_to_comment(v, status="existing") for v in existing_violations]

    if changed_lines is None:
        comments = all_comments
        out_of_diff_count = 0
    else:
        comments, out_of_diff_count = filter_comments_to_diff(all_comments, changed_lines)

    summary = build_review_summary(
        reports,
        new_violations,
        existing_violations,
        duration_seconds=duration_seconds,
        baseline_available=baseline_available,
        artifact_url=artifact_url,
        out_of_diff_count=out_of_diff_count,
    )
    verdict = determine_verdict(new_violations)

    return {
        "body": summary,
        "event": verdict,
        "comments": comments,
    }


def post_review(
    owner: str,
    repo: str,
    pr_number: int,
    payload: dict,
    token: str,
) -> dict:
    """Post a pull request review to GitHub."""
    url = f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
    return _github_request(url, payload, token)


def _github_request(url: str, payload: dict, token: str) -> dict:
    """Make an authenticated POST to the GitHub API."""
    data = json.dumps(payload).encode()
    req = Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")

    try:
        with urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        _logger.error("GitHub API request failed: HTTP %s %s – %s", exc.code, exc.reason, body)
        raise RuntimeError(
            f"GitHub API returned HTTP {exc.code} ({exc.reason}): {body}"
        ) from exc
