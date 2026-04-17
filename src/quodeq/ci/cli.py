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
    from quodeq.ci.review_builder import classify_violations

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

    baseline_violations: list[dict] = []
    baseline_available = False
    if args.baseline_dir:
        baseline_dir = Path(args.baseline_dir)
        if baseline_dir.is_dir():
            baseline_reports = load_evaluation_reports(baseline_dir)
            for r in baseline_reports:
                baseline_violations.extend(r.get("violations", []))
            baseline_available = True
        else:
            print(f"Warning: baseline directory not found: {baseline_dir}", file=sys.stderr)

    artifact_url: str | None = getattr(args, "artifact_url", None)

    payload = build_review_payload(
        reports,
        baseline_violations=baseline_violations,
        duration_seconds=args.duration,
        baseline_available=baseline_available,
        artifact_url=artifact_url,
    )
    post_review(
        owner=args.owner,
        repo=args.repo,
        pr_number=args.pr,
        payload=payload,
        token=token,
    )

    all_current: list[dict] = []
    for r in reports:
        all_current.extend(r.get("violations", []))
    new_v, existing_v = classify_violations(all_current, baseline_violations)
    print(f"Posted review to PR #{args.pr}: {len(new_v)} new, {len(existing_v)} pre-existing")
    return 0
