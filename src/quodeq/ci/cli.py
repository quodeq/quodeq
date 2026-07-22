"""CLI handler for the `quodeq ci` subcommand."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def handle_ci(args: argparse.Namespace) -> int:
    """Handle the `quodeq ci` subcommand. Returns exit code."""
    if args.ci_action == "report":
        return _handle_report(args)
    print("Usage: quodeq ci report [options]", file=sys.stderr)
    return 1


def _handle_report(args: argparse.Namespace) -> int:
    """Post evaluation results as a GitHub PR review."""
    from quodeq.ci._evidence_reader import load_violations_from_evidence
    from quodeq.ci.reporter import (
        build_review_payload,
        fetch_pr_changed_lines,
        load_evaluation_reports,
        post_review,
    )
    from quodeq.ci.review_builder import classify_violations

    if args.token:
        print(
            "Warning: --token exposes the credential in shell history and "
            "process listings; prefer the GITHUB_TOKEN environment variable.",
            file=sys.stderr,
        )
    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: --token or GITHUB_TOKEN environment variable required", file=sys.stderr)
        return 1

    evaluation_dir = Path(args.evaluation_dir)
    if not evaluation_dir.is_dir():
        print(f"Error: evaluation directory not found: {evaluation_dir}", file=sys.stderr)
        return 1

    from_evidence = getattr(args, "from_evidence", False)

    if from_evidence:
        # Evidence mode: read raw JSONL, no scored reports, no baseline.
        # Always produce a report tuple — even with zero violations, we post
        # an approving review so the PR shows "Quodeq ran and found nothing"
        # rather than silence (which CI cannot distinguish from "job broken").
        violations = load_violations_from_evidence(evaluation_dir / "evidence")
        reports = [{
            "dimension": "pr-diff",
            "violations": violations,
            "overallScore": "N/A",
            "overallGrade": "N/A",
        }]
        baseline_violations: list[dict] = []
        baseline_available = False
    else:
        reports = load_evaluation_reports(evaluation_dir)
        if not reports:
            print("No evaluation reports found, skipping review.", file=sys.stderr)
            return 0
        baseline_violations = []
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

    # Fetch the PR's changed lines so we only post comments GitHub will accept.
    # GitHub rejects the WHOLE review with HTTP 422 if any comment references
    # a path or line outside the PR's diff. On fetch failure, fall back to a
    # summary-only review (comments=[]) rather than crashing the action.
    changed_lines: dict[str, set[int]] | None
    try:
        changed_lines = fetch_pr_changed_lines(
            owner=args.owner, repo=args.repo, pr_number=args.pr, token=token,
        )
    except Exception as exc:
        print(
            f"Warning: could not fetch PR diff to scope comments ({exc.__class__.__name__}: {exc}); "
            "posting summary-only review.",
            file=sys.stderr,
        )
        changed_lines = {}  # empty dict → all comments filtered out; summary still posts

    payload = build_review_payload(
        reports,
        baseline_violations=baseline_violations,
        duration_seconds=args.duration,
        baseline_available=baseline_available,
        artifact_url=artifact_url,
        changed_lines=changed_lines,
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
    in_diff = len(payload["comments"])
    print(
        f"Posted review to PR #{args.pr}: {len(new_v)} new, {len(existing_v)} pre-existing "
        f"({in_diff} inline comment(s) in diff scope)"
    )
    return 0
