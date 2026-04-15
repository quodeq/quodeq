"""Tests for the `quodeq ci` CLI subcommand."""
from __future__ import annotations


def test_ci_report_args_parsed():
    from quodeq.cli_parser import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "ci", "report",
        "--evaluation-dir", "/tmp/eval",
        "--owner", "quodeq",
        "--repo", "quodeq",
        "--pr", "42",
    ])
    assert args.evaluation_dir == "/tmp/eval"
    assert args.owner == "quodeq"
    assert args.repo == "quodeq"
    assert args.pr == 42
