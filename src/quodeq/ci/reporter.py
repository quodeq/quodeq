"""Post evaluation results as GitHub PR reviews."""
from __future__ import annotations

import json
import logging
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
) -> dict:
    """Build the full GitHub PR review API payload from evaluation reports.

    baseline_violations: violations from the last nightly evaluation on the base
    branch. When provided, current violations are classified as NEW or EXISTING.
    When omitted, all violations are treated as NEW.
    baseline_available: when False, a note is added to the summary explaining
    that no baseline comparison was made (first-run scenario).
    artifact_url: when provided, a download link is appended to the summary.
    """
    all_violations: list[dict] = []
    for report in reports:
        all_violations.extend(report.get("violations", []))

    new_violations, existing_violations = classify_violations(
        all_violations, baseline_violations or []
    )

    comments = [violation_to_comment(v, status="new") for v in new_violations]
    comments += [violation_to_comment(v, status="existing") for v in existing_violations]
    summary = build_review_summary(
        reports,
        new_violations,
        existing_violations,
        duration_seconds=duration_seconds,
        baseline_available=baseline_available,
        artifact_url=artifact_url,
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
