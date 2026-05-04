import pytest

from quodeq.cli import build_parser
from quodeq.shared.utils import get_evaluations_dir

_TEST_REPO = "tmp/repo"
_TEST_LANGUAGE = "python"
_TEST_MODE = "grades"


@pytest.fixture
def parsed_evaluate_args():
    """Parse the standard evaluate command and return the resulting namespace."""
    parser = build_parser()
    return parser.parse_args(["evaluate", _TEST_REPO, "-l", _TEST_LANGUAGE, "-m", _TEST_MODE])


def test_evaluate_command(parsed_evaluate_args):
    assert parsed_evaluate_args.command == "evaluate"


def test_evaluate_repo(parsed_evaluate_args):
    assert parsed_evaluate_args.repo == _TEST_REPO


def test_evaluate_language(parsed_evaluate_args):
    assert parsed_evaluate_args.language == _TEST_LANGUAGE


def test_evaluate_mode(parsed_evaluate_args):
    assert parsed_evaluate_args.mode == _TEST_MODE


def test_evaluate_default_output(parsed_evaluate_args):
    # The parser resolves the default via ``get_evaluations_dir()``, which
    # honours ``QUODEQ_EVALUATIONS_DIR``. Compare against the same helper so
    # the test stays correct under the autouse isolation fixture.
    assert parsed_evaluate_args.output == get_evaluations_dir()


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
            parser.parse_args(["evaluate", _TEST_REPO, "-m", "invalid_mode"])

    def test_numerical_mode(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", _TEST_REPO, "-m", "numerical"])
        assert args.mode == "numerical"

    def test_dimensions_flag(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", _TEST_REPO, "-d", "security,reliability"])
        assert args.dimensions == "security,reliability"

    def test_no_prescan_flag(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", _TEST_REPO, "--no-prescan"])
        assert args.no_prescan is True

    def test_evidence_only_flag(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", _TEST_REPO, "--evidence-only"])
        assert args.evidence_only is True

    def test_dry_run_flag_parsed(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", _TEST_REPO, "--dry-run"])
        assert args.dry_run is True

    def test_dry_run_flag_default_false(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", _TEST_REPO])
        assert args.dry_run is False
