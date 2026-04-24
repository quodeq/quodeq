"""Local PR review: run quodeq evaluation locally and post results to an open PR."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from quodeq.analysis._dimension_aliases import expand_dimension_aliases
from quodeq.shared.utils import get_evaluations_dir

_logger = logging.getLogger(__name__)


class ReviewError(RuntimeError):
    """Raised when the review command cannot proceed."""


def detect_pr(pr_override: int | None = None) -> tuple[int, str]:
    """Detect the open PR for the current branch. Returns (pr_number, base_branch).

    Raises ReviewError with a clear message if no PR is found or gh is unavailable.
    """
    if pr_override is not None:
        # Still need baseRefName — query gh for this PR
        try:
            result = subprocess.run(
                ["gh", "pr", "view", str(pr_override), "--json", "number,baseRefName"],
                capture_output=True, text=True, check=True,
            )
        except FileNotFoundError:
            raise ReviewError("gh CLI not found. Install with 'brew install gh' and run 'gh auth login'.")
        except subprocess.CalledProcessError as exc:
            raise ReviewError(f"Could not find PR #{pr_override}: {exc.stderr.strip()}")
        data = json.loads(result.stdout)
        return data["number"], data["baseRefName"]

    try:
        result = subprocess.run(
            ["gh", "pr", "view", "--json", "number,baseRefName"],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        raise ReviewError("gh CLI not found. Install with 'brew install gh' and run 'gh auth login'.")
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        if "no pull requests found" in stderr.lower():
            raise ReviewError(
                "No open PR found for the current branch. "
                "Open a PR first, or pass --pr <number>."
            )
        raise ReviewError(f"gh pr view failed: {stderr}")

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
        raise ReviewError("gh CLI not found. Install with 'brew install gh' and run 'gh auth login'.")
    except subprocess.CalledProcessError as exc:
        raise ReviewError(
            "Not authenticated with GitHub. Run 'gh auth login' first."
        )
    token = result.stdout.strip()
    if not token:
        raise ReviewError("gh auth token returned empty. Run 'gh auth login'.")
    return token


def get_repo_info() -> tuple[str, str]:
    """Get (owner, repo) from the current git repository via gh."""
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "owner,name"],
            capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise ReviewError(
            "Could not determine GitHub repo. "
            "Run from inside a GitHub-connected git repo, or use 'gh repo set-default'."
        )
    data = json.loads(result.stdout)
    return data["owner"]["login"], data["name"]


def snapshot_run_dirs(output_dir: Path) -> set[Path]:
    """Snapshot existing run directories (those containing an evidence/ subdir).

    Both full/incremental runs and diff-mode runs write ``evidence/``, so
    globbing on it catches every run shape. Diff-mode runs do not write
    ``evaluation/``, so the old "glob on evaluation" approach would miss
    them.
    """
    if not output_dir.exists():
        return set()
    return {p.parent for p in output_dir.rglob("evidence") if p.is_dir()}


def handle_review(args) -> int:
    """Entry point for `quodeq review`."""
    try:
        pr_number, base_branch = detect_pr(pr_override=getattr(args, "pr", None))
    except ReviewError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Detected PR #{pr_number} (base: {base_branch})")

    try:
        owner, repo = get_repo_info()
    except ReviewError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output_dir = Path(getattr(args, "output", None) or get_evaluations_dir())
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_runs = snapshot_run_dirs(output_dir)

    from quodeq.cli_parser import build_parser
    eval_parser_argv = [
        "evaluate", ".",
        "--diff-from", f"origin/{base_branch}",
        "--output", str(output_dir),
    ]
    dims = getattr(args, "dimensions", None)
    if dims:
        eval_parser_argv.extend(["--dimensions", expand_dimension_aliases(dims)])
    pool_budget = getattr(args, "pool_budget", None) or 300
    eval_parser_argv.extend(["--pool-budget", str(pool_budget)])

    parser = build_parser()
    eval_args = parser.parse_args(eval_parser_argv)

    print(f"Running PR diff evaluation (base: origin/{base_branch})...")
    start = time.time()
    from quodeq._cli_evaluation import run_evaluate
    exit_code = run_evaluate(eval_args)
    duration = int(time.time() - start)

    if exit_code != 0:
        print(f"Evaluation failed with exit code {exit_code}", file=sys.stderr)
        return exit_code

    all_runs = snapshot_run_dirs(output_dir)
    new_runs = all_runs - baseline_runs
    if not new_runs:
        print("Error: no new evaluation directory produced.", file=sys.stderr)
        return 1
    current_run_dir = max(new_runs, key=lambda p: p.stat().st_mtime)
    evidence_dir = current_run_dir / "evidence"

    from quodeq.ci._evidence_reader import load_violations_from_evidence
    violations = load_violations_from_evidence(evidence_dir)

    reports = [{
        "dimension": "pr-diff",
        "violations": violations,
        "overallScore": "N/A",
        "overallGrade": "N/A",
    }]

    from quodeq.ci.reporter import build_review_payload
    payload = build_review_payload(
        reports,
        baseline_violations=[],
        duration_seconds=duration,
        baseline_available=False,
    )

    total_violations = len(violations)
    print(f"Evaluation complete: {total_violations} violation(s) found in diff")
    print(f"Verdict: {payload['event']}")

    if getattr(args, "dry_run", False):
        print("\n--- Review body (dry-run, not posted) ---")
        print(payload["body"])
        print("--- end review body ---")
        return 0

    try:
        token = get_github_token()
    except ReviewError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    from quodeq.ci.reporter import post_review
    print(f"Posting review to {owner}/{repo} PR #{pr_number}...")
    post_review(owner=owner, repo=repo, pr_number=pr_number, payload=payload, token=token)
    print(f"Review posted to https://github.com/{owner}/{repo}/pull/{pr_number}")
    return 0
