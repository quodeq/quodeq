"""Argument parser setup for the Quodeq CLI."""
from __future__ import annotations

import argparse

from quodeq.shared.utils import get_evaluations_dir

_DEFAULT_N_SUBAGENTS = 5
_MODE_NUMERICAL = "numerical"
_MODE_GRADES = "grades"


def _add_output_args(parser: argparse.ArgumentParser) -> None:
    """Register output and scoring mode arguments."""
    parser.add_argument(
        "-o", "--output", default=get_evaluations_dir(), help="Reports output directory"
    )
    parser.add_argument(
        "-m", "--mode", default=_MODE_NUMERICAL,
        choices=[_MODE_NUMERICAL, _MODE_GRADES], help="Scoring mode",
    )
    parser.add_argument(
        "--evidence-only", action="store_true",
        help="Produce evidence JSON only (skip scoring)",
    )


def _add_evaluate_args(parser: argparse.ArgumentParser) -> None:
    """Register arguments for the evaluate subcommand."""
    parser.add_argument("repo", help="Path or URL to the repository")
    parser.add_argument(
        "-l", "--language", default=None, help="Language (overrides auto-detection)"
    )
    _add_output_args(parser)
    parser.add_argument(
        "--no-prescan", action="store_true", help="Skip source-file counting"
    )
    parser.add_argument(
        "-d", "--dimensions", default=None,
        help="Comma-separated dimensions to evaluate (default: all)",
    )
    parser.add_argument(
        "--max-turns", type=int, default=None,
        help="Max AI conversation turns per dimension (default: 200)",
    )
    parser.add_argument(
        "--max-duration", type=int, default=None,
        help="Max seconds per dimension before terminating (default: 1800)",
    )
    parser.add_argument(
        "--n-subagents", "--max-subagents", type=int, default=_DEFAULT_N_SUBAGENTS,
        dest="n_subagents",
        help="Max parallel subagents per dimension (default: %(default)s)",
    )
    parser.add_argument(
        "--no-verify", action="store_true",
        help="Skip post-analysis verification pass",
    )
    parser.add_argument(
        "--pool-budget", type=int, default=None,
        help="Total time budget for agent pool in seconds (default: 600)",
    )
    parser.add_argument(
        "--no-consolidated", action="store_true",
        help="Disable multi-dimension consolidation (evaluate dimensions separately)",
    )
    parser.add_argument(
        "--incremental", action="store_true",
        help="Only analyze files changed since last evaluation (carry forward cached findings)",
    )
    parser.add_argument(
        "--branch", default=None,
        help="Git branch to analyze (creates a temporary worktree)",
    )
    parser.add_argument(
        "--scope", default=None,
        help="Subdirectory to analyze (relative to repo root)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip AI calls and generate placeholder findings (for CI pipeline testing)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with all subcommands."""
    parser = argparse.ArgumentParser(prog="quodeq")
    subparsers = parser.add_subparsers(dest="command")

    dashboard_parser = subparsers.add_parser("dashboard", help="Run the dashboard")
    dashboard_parser.set_defaults(handler_command="dashboard")

    evaluate_parser = subparsers.add_parser(
        "evaluate", help="Run evaluation (auto-detects language)"
    )
    _add_evaluate_args(evaluate_parser)
    evaluate_parser.set_defaults(handler_command="evaluate")

    ci_parser = subparsers.add_parser("ci", help="CI integration commands")
    ci_sub = ci_parser.add_subparsers(dest="ci_action")
    report_parser = ci_sub.add_parser("report", help="Post evaluation results as PR review")
    report_parser.add_argument("--evaluation-dir", required=True, help="Path to evaluation output directory")
    report_parser.add_argument("--owner", required=True, help="GitHub repository owner")
    report_parser.add_argument("--repo", required=True, help="GitHub repository name")
    report_parser.add_argument("--pr", type=int, required=True, help="Pull request number")
    report_parser.add_argument("--token", help="GitHub token (default: GITHUB_TOKEN env var)")
    report_parser.add_argument("--duration", type=int, help="Evaluation duration in seconds")

    return parser
