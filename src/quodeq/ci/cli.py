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


def _resolve_report_token(args: argparse.Namespace) -> str | None:
    """Validate and return the GitHub token, printing an error if missing."""
    if args.token:
        print(
            "Warning: --token exposes the credential in shell history and "
            "process listings; prefer the GITHUB_TOKEN environment variable.",
            file=sys.stderr,
        )
    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: --token or GITHUB_TOKEN environment variable required", file=sys.stderr)
        return None
    return token


def _load_evidence_mode_report(evaluation_dir: Path) -> list[dict]:
    """Build the single-report list for --from-evidence mode."""
    from quodeq.ci._evidence_reader import load_violations_from_evidence
    from quodeq.ci._suppressions import filter_suppressed_violations

    # Evidence mode: read raw JSONL, no scored reports, no baseline.
    # Always produce a report tuple — even with zero violations, we post
    # an approving review so the PR shows "Quodeq ran and found nothing"
    # rather than silence (which CI cannot distinguish from "job broken").
    violations = load_violations_from_evidence(evaluation_dir / "evidence")
    # In --from-evidence mode, `evaluation_dir` IS the run directory (its
    # "evidence" subfolder holds the JSONL) -- see the --from-evidence
    # help text and .github/workflows/quodeq-review.yml, which passes the
    # parent of evidence/ as --evaluation-dir. That's one level shallower
    # than the scored-report "evaluation" folder used in the else branch
    # below, so project_dir is one parent up here, not two.
    project_dir = evaluation_dir.parent
    report = filter_suppressed_violations({
        "dimension": "pr-diff",
        "violations": violations,
        "overallScore": "N/A",
        "overallGrade": "N/A",
    }, project_dir)
    return [report]


def _load_scored_mode_reports(args: argparse.Namespace, evaluation_dir: Path):
    """Return (reports, baseline_violations, baseline_available) for scored
    mode, or None if no evaluation reports exist."""
    from quodeq.ci.reporter import load_evaluation_reports

    reports = load_evaluation_reports(evaluation_dir)
    if not reports:
        return None
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
    return reports, baseline_violations, baseline_available


def _fetch_report_changed_lines(args: argparse.Namespace, token: str) -> dict[str, set[int]]:
    """Fetch the PR's changed lines so we only post comments GitHub will
    accept. GitHub rejects the WHOLE review with HTTP 422 if any comment
    references a path or line outside the PR's diff. On fetch failure, fall
    back to a summary-only review (comments=[]) rather than crashing the
    action."""
    from quodeq.ci.reporter import fetch_pr_changed_lines

    try:
        return fetch_pr_changed_lines(
            owner=args.owner, repo=args.repo, pr_number=args.pr, token=token,
        )
    except Exception as exc:
        print(
            f"Warning: could not fetch PR diff to scope comments ({exc.__class__.__name__}: {exc}); "
            "posting summary-only review.",
            file=sys.stderr,
        )
        return {}  # empty dict → all comments filtered out; summary still posts


def _post_report_review(args: argparse.Namespace, reports, baseline_violations, baseline_available, changed_lines) -> None:
    """Build the review payload, post it, and print the run summary."""
    from quodeq.ci.reporter import build_review_payload, post_review
    from quodeq.ci.review_builder import classify_violations

    artifact_url: str | None = getattr(args, "artifact_url", None)
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
        token=args.token or os.environ.get("GITHUB_TOKEN"),
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


def _handle_report(args: argparse.Namespace) -> int:
    """Post evaluation results as a GitHub PR review."""
    token = _resolve_report_token(args)
    if token is None:
        return 1

    evaluation_dir = Path(args.evaluation_dir)
    if not evaluation_dir.is_dir():
        print(f"Error: evaluation directory not found: {evaluation_dir}", file=sys.stderr)
        return 1

    from_evidence = getattr(args, "from_evidence", False)

    if from_evidence:
        reports = _load_evidence_mode_report(evaluation_dir)
        baseline_violations: list[dict] = []
        baseline_available = False
    else:
        loaded = _load_scored_mode_reports(args, evaluation_dir)
        if loaded is None:
            print("No evaluation reports found, skipping review.", file=sys.stderr)
            return 0
        reports, baseline_violations, baseline_available = loaded

    changed_lines = _fetch_report_changed_lines(args, token)
    _post_report_review(args, reports, baseline_violations, baseline_available, changed_lines)
    return 0
