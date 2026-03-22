"""Argument parser setup for the Quodeq CLI."""
from __future__ import annotations

import argparse

from quodeq.shared.utils import get_evaluations_dir

_DEFAULT_N_SUBAGENTS = 5
_MODE_NUMERICAL = "numerical"
_MODE_GRADES = "grades"


def _add_evaluate_args(parser: argparse.ArgumentParser) -> None:
    """Register arguments for the evaluate subcommand."""
    parser.add_argument("repo", help="Path or URL to the repository")
    parser.add_argument(
        "-l", "--language", default=None, help="Language (overrides auto-detection)"
    )
    parser.add_argument(
        "-o", "--output", default=get_evaluations_dir(), help="Reports output directory"
    )
    parser.add_argument(
        "-m", "--mode", default=_MODE_NUMERICAL,
        choices=[_MODE_NUMERICAL, _MODE_GRADES], help="Scoring mode",
    )
    parser.add_argument(
        "--no-prescan", action="store_true", help="Skip source-file counting"
    )
    parser.add_argument(
        "-d", "--dimensions", default=None,
        help="Comma-separated dimensions to evaluate (default: all)",
    )
    parser.add_argument(
        "--evidence-only", action="store_true",
        help="Produce evidence JSON only (skip scoring)",
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


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with all subcommands."""
    parser = argparse.ArgumentParser(prog="quodeq")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dashboard_parser = subparsers.add_parser("dashboard", help="Run the dashboard")
    dashboard_parser.set_defaults(handler_command="dashboard")

    evaluate_parser = subparsers.add_parser(
        "evaluate", help="Run evaluation (auto-detects language)"
    )
    _add_evaluate_args(evaluate_parser)
    evaluate_parser.set_defaults(handler_command="evaluate")

    return parser
