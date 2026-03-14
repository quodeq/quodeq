from pathlib import Path

from quodeq.cli import build_parser


def test_evaluate_flags():
    parser = build_parser()
    args = parser.parse_args(["evaluate", "/tmp/repo", "-p", "python", "-m", "grades"])

    assert args.command == "evaluate"
    assert args.repo == "/tmp/repo"
    assert args.plugin == "python"
    assert args.mode == "grades"
    assert args.output == str(Path.home() / ".quodeq" / "evaluations")
    assert args.no_prescan is False
    assert args.evidence_only is False
