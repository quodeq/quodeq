from pathlib import Path

import pytest

from quodeq.cli import build_parser


@pytest.fixture
def parsed_evaluate_args():
    """Parse the standard evaluate command and return the resulting namespace."""
    parser = build_parser()
    return parser.parse_args(["evaluate", "tmp/repo", "-l", "python", "-m", "grades"])


def test_evaluate_command(parsed_evaluate_args):
    assert parsed_evaluate_args.command == "evaluate"


def test_evaluate_repo(parsed_evaluate_args):
    assert parsed_evaluate_args.repo == "tmp/repo"


def test_evaluate_language(parsed_evaluate_args):
    assert parsed_evaluate_args.language == "python"


def test_evaluate_mode(parsed_evaluate_args):
    assert parsed_evaluate_args.mode == "grades"


def test_evaluate_default_output(parsed_evaluate_args):
    assert parsed_evaluate_args.output == str(Path.home() / ".quodeq" / "evaluations")


def test_evaluate_no_prescan_default(parsed_evaluate_args):
    assert parsed_evaluate_args.no_prescan is False


def test_evaluate_evidence_only_default(parsed_evaluate_args):
    assert parsed_evaluate_args.evidence_only is False


class TestEvaluateEdgeCases:
    """Edge cases and error handling for the evaluate subcommand."""

    def test_missing_repo_argument(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["evaluate"])

    def test_invalid_mode(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["evaluate", "tmp/repo", "-m", "invalid_mode"])

    def test_numerical_mode(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", "tmp/repo", "-m", "numerical"])
        assert args.mode == "numerical"

    def test_dimensions_flag(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", "tmp/repo", "-d", "security,reliability"])
        assert args.dimensions == "security,reliability"

    def test_no_prescan_flag(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", "tmp/repo", "--no-prescan"])
        assert args.no_prescan is True

    def test_evidence_only_flag(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", "tmp/repo", "--evidence-only"])
        assert args.evidence_only is True
