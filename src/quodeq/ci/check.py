"""Local PR review: run quodeq evaluation locally and post results to an open PR."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from quodeq.ci.reporter import build_review_payload, load_evaluation_reports, post_review
from quodeq.shared.utils import get_evaluations_dir

_logger = logging.getLogger(__name__)


class CheckError(RuntimeError):
    """Raised when the check command cannot proceed."""


def detect_pr(pr_override: int | None = None) -> tuple[int, str]:
    """Detect the open PR for the current branch. Returns (pr_number, base_branch).

    Raises CheckError with a clear message if no PR is found or gh is unavailable.
    """
    if pr_override is not None:
        # Still need baseRefName — query gh for this PR
        try:
            result = subprocess.run(
                ["gh", "pr", "view", str(pr_override), "--json", "number,baseRefName"],
                capture_output=True, text=True, check=True,
            )
        except FileNotFoundError:
            raise CheckError("gh CLI not found. Install with 'brew install gh' and run 'gh auth login'.")
        except subprocess.CalledProcessError as exc:
            raise CheckError(f"Could not find PR #{pr_override}: {exc.stderr.strip()}")
        data = json.loads(result.stdout)
        return data["number"], data["baseRefName"]

    try:
        result = subprocess.run(
            ["gh", "pr", "view", "--json", "number,baseRefName"],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        raise CheckError("gh CLI not found. Install with 'brew install gh' and run 'gh auth login'.")
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        if "no pull requests found" in stderr.lower():
            raise CheckError(
                "No open PR found for the current branch. "
                "Open a PR first, or pass --pr <number>."
            )
        raise CheckError(f"gh pr view failed: {stderr}")

    data = json.loads(result.stdout)
    return data["number"], data["baseRefName"]


def get_github_token() -> str:
    """Get a GitHub token via `gh auth token`."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        raise CheckError("gh CLI not found. Install with 'brew install gh' and run 'gh auth login'.")
    except subprocess.CalledProcessError as exc:
        raise CheckError(
            "Not authenticated with GitHub. Run 'gh auth login' first."
        )
    token = result.stdout.strip()
    if not token:
        raise CheckError("gh auth token returned empty. Run 'gh auth login'.")
    return token


def get_repo_info() -> tuple[str, str]:
    """Get (owner, repo) from the current git repository via gh."""
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "owner,name"],
            capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise CheckError(
            "Could not determine GitHub repo. "
            "Run from inside a GitHub-connected git repo, or use 'gh repo set-default'."
        )
    data = json.loads(result.stdout)
    return data["owner"]["login"], data["name"]


def snapshot_run_dirs(output_dir: Path) -> set[Path]:
    """Snapshot existing evaluation run directories."""
    if not output_dir.exists():
        return set()
    return {p for p in output_dir.rglob("evaluation") if p.is_dir()}


def handle_check(args) -> int:
    """Entry point for `quodeq check`."""
    try:
        pr_number, base_branch = detect_pr(pr_override=getattr(args, "pr", None))
    except CheckError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Detected PR #{pr_number} (base: {base_branch})")

    try:
        owner, repo = get_repo_info()
    except CheckError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Determine output dir (use default or user-specified)
    output_dir = Path(getattr(args, "output", None) or get_evaluations_dir())
    output_dir.mkdir(parents=True, exist_ok=True)

    # Snapshot existing runs before evaluation
    baseline_runs = snapshot_run_dirs(output_dir)

    # Build evaluate args and call run_evaluate directly
    from quodeq.cli_parser import build_parser
    eval_parser_argv = [
        "evaluate", ".",
        "--incremental",
        "--output", str(output_dir),
    ]
    dims = getattr(args, "dimensions", None)
    if dims:
        eval_parser_argv.extend(["--dimensions", dims])
    else:
        # Default for check: security only
        eval_parser_argv.extend(["--dimensions", "security"])
    # Pool budget default (short for local dev)
    pool_budget = getattr(args, "pool_budget", None) or 300
    eval_parser_argv.extend(["--pool-budget", str(pool_budget)])

    parser = build_parser()
    eval_args = parser.parse_args(eval_parser_argv)

    print(f"Running evaluation ({eval_args.dimensions})...")
    start = time.time()
    from quodeq._cli_evaluation import run_evaluate
    exit_code = run_evaluate(eval_args)
    duration = int(time.time() - start)

    if exit_code != 0:
        print(f"Evaluation failed with exit code {exit_code}", file=sys.stderr)
        return exit_code

    # Find the new run (set difference)
    all_runs = snapshot_run_dirs(output_dir)
    new_runs = all_runs - baseline_runs
    if not new_runs:
        print("Error: no new evaluation directory produced.", file=sys.stderr)
        return 1
    # Latest new run by mtime
    current_eval_dir = max(new_runs, key=lambda p: p.stat().st_mtime)

    # Baseline: latest pre-existing run (if any)
    baseline_eval_dir = None
    baseline_available = False
    if baseline_runs:
        baseline_eval_dir = max(baseline_runs, key=lambda p: p.stat().st_mtime)
        baseline_available = True

    # Load reports
    current_reports = load_evaluation_reports(current_eval_dir)
    baseline_violations: list[dict] = []
    if baseline_eval_dir:
        for r in load_evaluation_reports(baseline_eval_dir):
            baseline_violations.extend(r.get("violations", []))

    # Build payload
    payload = build_review_payload(
        current_reports,
        baseline_violations=baseline_violations,
        duration_seconds=duration,
        baseline_available=baseline_available,
    )

    # Summarize findings
    total_violations = sum(len(r.get("violations", [])) for r in current_reports)
    new_count = sum(1 for c in payload.get("comments", []) if "NEW" in c.get("body", ""))
    existing_count = len(payload.get("comments", [])) - new_count
    print(f"Evaluation complete: {total_violations} violation(s) total "
          f"({new_count} new, {existing_count} pre-existing)")
    print(f"Verdict: {payload['event']}")

    if getattr(args, "dry_run", False):
        print("\n--- Review body (dry-run, not posted) ---")
        print(payload["body"])
        print("--- end review body ---")
        return 0

    # Get token and post
    try:
        token = get_github_token()
    except CheckError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Posting review to {owner}/{repo} PR #{pr_number}...")
    post_review(owner=owner, repo=repo, pr_number=pr_number, payload=payload, token=token)
    print(f"Review posted to https://github.com/{owner}/{repo}/pull/{pr_number}")
    return 0
