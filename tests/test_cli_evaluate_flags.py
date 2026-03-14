from pathlib import Path

from quodeq.cli import build_parser


def test_evaluate_command():
    parser = build_parser()
    args = parser.parse_args(["evaluate", "/tmp/repo", "-p", "python", "-m", "grades"])
    assert args.command == "evaluate"


def test_evaluate_repo():
    parser = build_parser()
    args = parser.parse_args(["evaluate", "/tmp/repo", "-p", "python", "-m", "grades"])
    assert args.repo == "/tmp/repo"


def test_evaluate_plugin():
    parser = build_parser()
    args = parser.parse_args(["evaluate", "/tmp/repo", "-p", "python", "-m", "grades"])
    assert args.plugin == "python"


def test_evaluate_mode():
    parser = build_parser()
    args = parser.parse_args(["evaluate", "/tmp/repo", "-p", "python", "-m", "grades"])
    assert args.mode == "grades"


def test_evaluate_default_output():
    parser = build_parser()
    args = parser.parse_args(["evaluate", "/tmp/repo", "-p", "python", "-m", "grades"])
    assert args.output == str(Path.home() / ".quodeq" / "evaluations")


def test_evaluate_no_prescan_default():
    parser = build_parser()
    args = parser.parse_args(["evaluate", "/tmp/repo", "-p", "python", "-m", "grades"])
    assert args.no_prescan is False


def test_evaluate_evidence_only_default():
    parser = build_parser()
    args = parser.parse_args(["evaluate", "/tmp/repo", "-p", "python", "-m", "grades"])
    assert args.evidence_only is False
