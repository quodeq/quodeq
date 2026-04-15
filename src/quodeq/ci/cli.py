"""CLI handler for the `quodeq ci` subcommand."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def handle_ci(args) -> int:
    """Handle the `quodeq ci` subcommand. Returns exit code."""
    if args.ci_action == "report":
        return _handle_report(args)
    print("Usage: quodeq ci report [options]", file=sys.stderr)
    return 1


def _handle_report(args) -> int:
    """Post evaluation results as a GitHub PR review."""
    from quodeq.ci.reporter import build_review_payload, load_evaluation_reports, post_review

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: --token or GITHUB_TOKEN environment variable required", file=sys.stderr)
        return 1

    evaluation_dir = Path(args.evaluation_dir)
    if not evaluation_dir.is_dir():
        print(f"Error: evaluation directory not found: {evaluation_dir}", file=sys.stderr)
        return 1

    reports = load_evaluation_reports(evaluation_dir)
    if not reports:
        print("No evaluation reports found, skipping review.", file=sys.stderr)
        return 0

    payload = build_review_payload(reports, duration_seconds=args.duration)
    post_review(
        owner=args.owner,
        repo=args.repo,
        pr_number=args.pr,
        payload=payload,
        token=token,
    )

    violation_count = sum(len(r.get("violations", [])) for r in reports)
    print(f"Posted review with {violation_count} violation(s) to PR #{args.pr}")
    return 0
