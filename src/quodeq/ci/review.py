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
                capture_output=True, text=True, encoding="utf-8", check=True,
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
            capture_output=True, text=True, encoding="utf-8", check=True,
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
            capture_output=True, text=True, encoding="utf-8", check=True,
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
            capture_output=True, text=True, encoding="utf-8", check=True,
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


def _resolve_pr_and_repo(args) -> tuple[int, str, str, str] | None:
    """Detect the PR and its GitHub owner/repo. Prints and returns None on failure."""
    try:
        pr_number, base_branch = detect_pr(pr_override=getattr(args, "pr", None))
    except ReviewError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return None

    print(f"Detected PR #{pr_number} (base: {base_branch})")

    try:
        owner, repo = get_repo_info()
    except ReviewError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return None
    return pr_number, base_branch, owner, repo


def _run_pr_diff_and_locate_evidence(
    output_dir: Path, base_branch: str, dims: str | None, pool_budget: int | None,
) -> tuple[int, Path | None, int]:
    """Run the PR-diff evaluation and locate the new run's evidence dir.

    Returns (exit_code, evidence_dir, duration_seconds). evidence_dir is None
    when the run failed (exit_code != 0) or produced no new run directory.
    """
    baseline_runs = snapshot_run_dirs(output_dir)

    print(f"Running PR diff evaluation (base: origin/{base_branch})...")
    start = time.time()
    from quodeq._cli_evaluation import run_diff_evaluation
    exit_code = run_diff_evaluation(
        ".",
        base_ref=f"origin/{base_branch}",
        output_dir=output_dir,
        dimensions=expand_dimension_aliases(dims) if dims else None,
        time_limit=pool_budget if pool_budget is not None else 300,
    )
    duration = int(time.time() - start)
    if exit_code != 0:
        return exit_code, None, duration

    all_runs = snapshot_run_dirs(output_dir)
    new_runs = all_runs - baseline_runs
    if not new_runs:
        return exit_code, None, duration
    current_run_dir = max(new_runs, key=lambda p: p.stat().st_mtime)
    return exit_code, current_run_dir / "evidence", duration


def _build_diff_report_and_payload(evidence_dir: Path, duration: int) -> tuple[dict, dict]:
    """Load evidence violations, filter suppressions, and build the review payload."""
    from quodeq.ci._evidence_reader import load_violations_from_evidence
    from quodeq.ci._suppressions import filter_suppressed_violations
    violations = load_violations_from_evidence(evidence_dir)

    # evidence_dir = current_run_dir / "evidence", so its parent is the run
    # dir and .parent.parent is the project dir (layout:
    # <reports_root>/<project>/<run>/evidence) -- same project_dir the
    # dashboard's dismiss/delete actions.jsonl and deleted.json live under.
    project_dir = evidence_dir.parent.parent
    report = filter_suppressed_violations({
        "dimension": "pr-diff",
        "violations": violations,
        "overallScore": "N/A",
        "overallGrade": "N/A",
    }, project_dir)

    from quodeq.ci.reporter import build_review_payload
    payload = build_review_payload(
        [report],
        baseline_violations=[],
        duration_seconds=duration,
        baseline_available=False,
    )
    return report, payload


def _post_review_or_dry_run(args, payload: dict, owner: str, repo: str, pr_number: int) -> int:
    """Print the review body for --dry-run, else post it to GitHub."""
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


def handle_review(args) -> int:
    """Entry point for `quodeq review`."""
    resolved = _resolve_pr_and_repo(args)
    if resolved is None:
        return 1
    pr_number, base_branch, owner, repo = resolved

    output_dir = Path(getattr(args, "output", None) or get_evaluations_dir())
    output_dir.mkdir(parents=True, exist_ok=True)

    dims = getattr(args, "dimensions", None)
    pool_budget = getattr(args, "pool_budget", None)
    exit_code, evidence_dir, duration = _run_pr_diff_and_locate_evidence(
        output_dir, base_branch, dims, pool_budget,
    )
    if exit_code != 0:
        print(f"Evaluation failed with exit code {exit_code}", file=sys.stderr)
        return exit_code
    if evidence_dir is None:
        print("Error: no new evaluation directory produced.", file=sys.stderr)
        return 1

    report, payload = _build_diff_report_and_payload(evidence_dir, duration)
    total_violations = len(report["violations"])
    print(f"Evaluation complete: {total_violations} violation(s) found in diff")
    print(f"Verdict: {payload['event']}")

    return _post_review_or_dry_run(args, payload, owner, repo, pr_number)
