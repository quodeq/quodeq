from pathlib import Path

import pytest

from quodeq.cli import build_parser


@pytest.fixture
def parsed_evaluate_args():
    """Parse the standard evaluate command and return the resulting namespace."""
    parser = build_parser()
    return parser.parse_args(["evaluate", "/tmp/repo", "-p", "python", "-m", "grades"])


def test_evaluate_command(parsed_evaluate_args):
    assert parsed_evaluate_args.command == "evaluate"


def test_evaluate_repo(parsed_evaluate_args):
    assert parsed_evaluate_args.repo == "/tmp/repo"


def test_evaluate_plugin(parsed_evaluate_args):
    assert parsed_evaluate_args.plugin == "python"


def test_evaluate_mode(parsed_evaluate_args):
    assert parsed_evaluate_args.mode == "grades"


def test_evaluate_default_output(parsed_evaluate_args):
    assert parsed_evaluate_args.output == str(Path.home() / ".quodeq" / "evaluations")


def test_evaluate_no_prescan_default(parsed_evaluate_args):
    assert parsed_evaluate_args.no_prescan is False


def test_evaluate_evidence_only_default(parsed_evaluate_args):
    assert parsed_evaluate_args.evidence_only is False
