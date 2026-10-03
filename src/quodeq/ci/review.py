"""Local PR review: run quodeq evaluation locally and post results to an open PR."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from quodeq.analysis.dimension_aliases import expand_dimension_aliases
from quodeq.shared.utils import get_evaluations_dir

_logger = logging.getLogger(__name__)


class ReviewError(RuntimeError):
    """Raised when the review command cannot proceed."""


_GH_MISSING = "gh CLI not found. Install with 'brew install gh' and run 'gh auth login'."
_GH_VIEW = "view"  # gh <resource> view
_GH_JSON_FLAG = "--json"
_DEFAULT_POOL_TIME_LIMIT_S = 300  # PR-diff eval budget when the caller sets none
_GH_TIMEOUT_S = 60


def _run_gh(args: list[str]) -> str:
    """Run ``gh`` with *args* and return its stdout.

    A missing gh binary becomes the one ReviewError every caller shares; a
    non-zero exit propagates as ``subprocess.CalledProcessError`` so each
    caller words its own failure. A hung ``gh`` call (bad auth, dead network)
    is bounded to ``_GH_TIMEOUT_S`` rather than blocking the review forever.
    """
    try:
        result = subprocess.run(
            ["gh", *args], capture_output=True, text=True, encoding="utf-8", check=True,
            timeout=_GH_TIMEOUT_S,
        )
    except FileNotFoundError:
        raise ReviewError(_GH_MISSING)
    except subprocess.TimeoutExpired:
        raise ReviewError(f"gh command timed out after {_GH_TIMEOUT_S}s: gh {' '.join(args)}")
    return result.stdout


def _gh_json(args: list[str]) -> dict:
    """Run ``gh`` with *args* and parse its stdout as a JSON object.

    A ``subprocess.CalledProcessError`` from ``_run_gh`` is left for the
    caller to word. Anything else wrong with the output -- invalid JSON, or
    valid JSON that isn't an object -- becomes one ``ReviewError`` here
    instead of three separate decode try blocks at each call site.
    """
    out = _run_gh(args)
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        raise ReviewError(f"gh returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ReviewError("gh returned unexpected JSON (not an object)")
    return data


def detect_pr(pr_override: int | None = None) -> tuple[int, str]:
    """Detect the open PR for the current branch. Returns (pr_number, base_branch).

    Raises ReviewError with a clear message if no PR is found or gh is unavailable.
    """
    if pr_override is not None:
        # Still need baseRefName, so ask gh about this PR.
        try:
            data = _gh_json(["pr", _GH_VIEW, str(pr_override), _GH_JSON_FLAG, "number,baseRefName"])
        except subprocess.CalledProcessError as exc:
            raise ReviewError(f"Could not find PR #{pr_override}: {exc.stderr.strip()}")
        try:
            return data["number"], data["baseRefName"]
        except (KeyError, TypeError) as exc:
            raise ReviewError(f"gh pr view returned unexpected JSON: missing {exc}") from exc

    try:
        data = _gh_json(["pr", _GH_VIEW, _GH_JSON_FLAG, "number,baseRefName"])
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        if "no pull requests found" in stderr.lower():
            raise ReviewError(
                "No open PR found for the current branch. "
                "Open a PR first, or pass --pr <number>."
            )
        raise ReviewError(f"gh pr view failed: {stderr}")
    try:
        return data["number"], data["baseRefName"]
    except (KeyError, TypeError) as exc:
        raise ReviewError(f"gh pr view returned unexpected JSON: missing {exc}") from exc


def get_github_token() -> str:
    """Get a GitHub token via `gh auth token`."""
    try:
        token = _run_gh(["auth", "token"]).strip()
    except subprocess.CalledProcessError:
        raise ReviewError("Not authenticated with GitHub. Run 'gh auth login' first.")
    if not token:
        raise ReviewError("gh auth token returned empty. Run 'gh auth login'.")
    return token


def get_repo_info() -> tuple[str, str]:
    """Get (owner, repo) from the current git repository via gh."""
    try:
        data = _gh_json(["repo", _GH_VIEW, _GH_JSON_FLAG, "owner,name"])
    except subprocess.CalledProcessError:
        raise ReviewError(
            "Could not determine GitHub repo. "
            "Run from inside a GitHub-connected git repo, or use 'gh repo set-default'."
        )
    try:
        return data["owner"]["login"], data["name"]
    except (KeyError, TypeError) as exc:
        raise ReviewError(f"gh repo view returned unexpected JSON: missing {exc}") from exc


def snapshot_run_dirs(output_dir: Path) -> set[Path]:
    """Snapshot existing run directories (those containing an evidence/ subdir).

    Every run shape writes ``evidence/``; diff-mode runs skip ``evaluation/``.
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
    from quodeq.cli_evaluation import run_diff_evaluation
    exit_code = run_diff_evaluation(
        ".",
        base_ref=f"origin/{base_branch}",
        output_dir=output_dir,
        dimensions=expand_dimension_aliases(dims) if dims else None,
        time_limit=pool_budget if pool_budget is not None else _DEFAULT_POOL_TIME_LIMIT_S,
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

    from quodeq.ci.reporter import ReviewOptions, build_review_payload
    payload = build_review_payload(
        [report],
        baseline_violations=[],
        options=ReviewOptions(duration_seconds=duration, baseline_available=False),
    )
    return report, payload


_CONFIRM_ANSWERS = frozenset({"y", "yes"})


def confirm_post(owner: str, repo: str, pr_number: int, *, stdin=None, ask=input) -> bool:
    """Ask before publishing to a shared PR when a person is at the terminal.

    A non-interactive run (CI, a pipe) has no one to ask and keeps posting;
    an interactive one must answer yes. End of input or Ctrl-C declines.
    """
    stream = sys.stdin if stdin is None else stdin
    if stream is None or not getattr(stream, "isatty", lambda: False)():
        return True
    try:
        answer = ask(f"Post this review to {owner}/{repo} PR #{pr_number}? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in _CONFIRM_ANSWERS


def _post_review_or_dry_run(args, payload: dict, owner: str, repo: str, pr_number: int) -> int:
    """Print the review body for --dry-run, else post it to GitHub.

    Posting to a real PR is the irreversible step, so an interactive run is
    asked first unless --yes was given.
    """
    if getattr(args, "dry_run", False):
        print("\n--- Review body (dry-run, not posted) ---")
        print(payload["body"])
        print("--- end review body ---")
        return 0
    if not getattr(args, "yes", False) and not confirm_post(owner, repo, pr_number):
        print("Review not posted. Re-run with --yes to skip the prompt, or --dry-run to print it.")
        return 1
    return _post_to_github(payload, owner, repo, pr_number)


def _post_to_github(payload: dict, owner: str, repo: str, pr_number: int) -> int:
    """Post *payload*; a gh or GitHub API failure prints a worded error, returns 1."""
    try:
        token = get_github_token()
    except ReviewError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    from quodeq.ci.reporter import post_review
    print(f"Posting review to {owner}/{repo} PR #{pr_number}...")
    try:
        post_review(owner=owner, repo=repo, pr_number=pr_number, payload=payload, token=token)
    except RuntimeError as exc:
        print(f"Error: could not post the review: {exc}", file=sys.stderr)
        return 1
    print(f"Review posted to https://github.com/{owner}/{repo}/pull/{pr_number}")
    return 0


def _evaluate_pr_diff(args, base_branch: str) -> tuple[int, Path | None, int]:
    """Run the PR-diff evaluation; (exit_code, evidence_dir, duration), with
    evidence_dir None (and the reason printed) whenever exit_code is non-zero."""
    output_dir = Path(getattr(args, "output", None) or get_evaluations_dir())
    output_dir.mkdir(parents=True, exist_ok=True)
    dims, pool_budget = getattr(args, "dimensions", None), getattr(args, "pool_budget", None)
    exit_code, evidence_dir, duration = _run_pr_diff_and_locate_evidence(
        output_dir, base_branch, dims, pool_budget)
    if exit_code != 0:
        print(f"Evaluation failed with exit code {exit_code}", file=sys.stderr)
        return exit_code, None, duration
    if evidence_dir is None:
        print("Error: no new evaluation directory produced.", file=sys.stderr)
        return 1, None, duration
    return 0, evidence_dir, duration


def _summarize_review(evidence_dir: Path, duration: int) -> dict:
    """Build the review payload and print the violation count and verdict."""
    report, payload = _build_diff_report_and_payload(evidence_dir, duration)
    print(f"Evaluation complete: {len(report['violations'])} violation(s) found in diff")
    print(f"Verdict: {payload['event']}")
    return payload


def handle_review(args) -> int:
    """Entry point for `quodeq review`."""
    resolved = _resolve_pr_and_repo(args)
    if resolved is None:
        return 1
    pr_number, base_branch, owner, repo = resolved
    exit_code, evidence_dir, duration = _evaluate_pr_diff(args, base_branch)
    if evidence_dir is None:
        return exit_code
    payload = _summarize_review(evidence_dir, duration)
    return _post_review_or_dry_run(args, payload, owner, repo, pr_number)
