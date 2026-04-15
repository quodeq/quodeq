"""Post evaluation results as GitHub PR reviews."""
from __future__ import annotations

import json
import logging
from pathlib import Path
import urllib.error
from urllib.request import Request, urlopen

from quodeq.ci.review_builder import (
    build_review_summary,
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
    duration_seconds: int | None = None,
) -> dict:
    """Build the full GitHub PR review API payload from evaluation reports."""
    all_violations = []
    for report in reports:
        all_violations.extend(report.get("violations", []))

    comments = [violation_to_comment(v) for v in all_violations]
    summary = build_review_summary(reports, duration_seconds=duration_seconds)
    verdict = determine_verdict(all_violations)

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
