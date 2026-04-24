"""Parser and mutex tests for --diff-from."""
from __future__ import annotations

from quodeq.cli_parser import build_parser


def test_diff_from_accepts_ref() -> None:
    parser = build_parser()
    args = parser.parse_args(["evaluate", ".", "--diff-from", "origin/develop"])
    assert args.diff_from == "origin/develop"


def test_diff_from_defaults_to_none() -> None:
    parser = build_parser()
    args = parser.parse_args(["evaluate", "."])
    assert args.diff_from is None


def test_incremental_and_diff_from_mutually_exclusive(capsys) -> None:
    # The CLI must reject --incremental + --diff-from and exit non-zero
    # *before* running the pipeline. run_evaluate is the enforcement point.
    from quodeq._cli_evaluation import run_evaluate

    parser = build_parser()
    args = parser.parse_args([
        "evaluate", ".", "--incremental", "--diff-from", "origin/develop",
    ])
    exit_code = run_evaluate(args)
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "--incremental" in err and "--diff-from" in err
