"""Tests for quodeq review (local PR review)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_detect_pr_reads_gh_output():
    from quodeq.ci.review import detect_pr
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"number": 42, "baseRefName": "develop"})
    mock_result.returncode = 0
    with patch("quodeq.ci.review.subprocess.run", return_value=mock_result):
        pr, base = detect_pr()
        assert pr == 42
        assert base == "develop"


def test_detect_pr_raises_when_no_pr_found():
    from quodeq.ci.review import detect_pr, ReviewError
    import subprocess as sp
    error = sp.CalledProcessError(1, ["gh"], stderr="no pull requests found for branch")
    with patch("quodeq.ci.review.subprocess.run", side_effect=error):
        with pytest.raises(ReviewError) as excinfo:
            detect_pr()
        assert "No open PR" in str(excinfo.value)


def test_detect_pr_raises_when_gh_missing():
    from quodeq.ci.review import detect_pr, ReviewError
    with patch("quodeq.ci.review.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(ReviewError) as excinfo:
            detect_pr()
        assert "gh CLI not found" in str(excinfo.value)


def test_get_github_token_reads_gh_output():
    from quodeq.ci.review import get_github_token
    mock_result = MagicMock()
    mock_result.stdout = "ghp_test_token\n"
    mock_result.returncode = 0
    with patch("quodeq.ci.review.subprocess.run", return_value=mock_result):
        assert get_github_token() == "ghp_test_token"


def test_get_github_token_raises_when_not_logged_in():
    from quodeq.ci.review import get_github_token, ReviewError
    import subprocess as sp
    error = sp.CalledProcessError(1, ["gh"], stderr="auth required")
    with patch("quodeq.ci.review.subprocess.run", side_effect=error):
        with pytest.raises(ReviewError) as excinfo:
            get_github_token()
        assert "gh auth login" in str(excinfo.value)


def test_get_repo_info_returns_owner_and_name():
    from quodeq.ci.review import get_repo_info
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"owner": {"login": "quodeq"}, "name": "quodeq"})
    mock_result.returncode = 0
    with patch("quodeq.ci.review.subprocess.run", return_value=mock_result):
        owner, repo = get_repo_info()
        assert owner == "quodeq"
        assert repo == "quodeq"


def test_snapshot_run_dirs_empty_when_nonexistent(tmp_path):
    from quodeq.ci.review import snapshot_run_dirs
    result = snapshot_run_dirs(tmp_path / "does-not-exist")
    assert result == set()


def test_snapshot_run_dirs_finds_evaluation_dirs(tmp_path):
    from quodeq.ci.review import snapshot_run_dirs
    # Create a fake structure
    (tmp_path / "project-a" / "run-1" / "evaluation").mkdir(parents=True)
    (tmp_path / "project-a" / "run-2" / "evaluation").mkdir(parents=True)
    (tmp_path / "project-a" / "run-1" / "evidence").mkdir(parents=True)  # not counted
    result = snapshot_run_dirs(tmp_path)
    assert len(result) == 2
    assert all(p.name == "evaluation" for p in result)


def test_review_subcommand_parses(tmp_path):
    """The review subcommand should be registered in the top-level parser."""
    from quodeq.cli_parser import build_parser
    parser = build_parser()
    args = parser.parse_args(["review", "--pr", "42", "--dry-run"])
    assert args.command == "review"
    assert args.pr == 42
    assert args.dry_run is True


def test_review_subcommand_defaults():
    from quodeq.cli_parser import build_parser
    parser = build_parser()
    args = parser.parse_args(["review"])
    assert args.command == "review"
    assert args.pr is None
    assert args.dimensions is None  # default is all dimensions (no --dimensions flag)
    assert args.dry_run is False


def test_handle_review_default_does_not_pass_dimensions(tmp_path):
    """When no --dimensions flag is given, handle_review must NOT pass --dimensions
    to the evaluate sub-parser, so the evaluate command defaults to all dimensions."""
    from unittest.mock import MagicMock, patch
    import json
    import argparse

    args = argparse.Namespace(
        pr=None,
        dimensions=None,
        pool_budget=None,
        output=str(tmp_path),
        dry_run=True,
    )

    pr_result = MagicMock()
    pr_result.stdout = json.dumps({"number": 7, "baseRefName": "main"})
    repo_result = MagicMock()
    repo_result.stdout = json.dumps({"owner": {"login": "org"}, "name": "repo"})

    captured_argv = []

    def fake_parse_args(argv):
        captured_argv.extend(argv)
        # Return a minimal Namespace so handle_review can continue
        ns = argparse.Namespace(
            dimensions=None,
            repo=".",
            incremental=True,
            output=str(tmp_path),
            pool_budget=300,
            mode=None,
            max_turns=None,
            max_duration=None,
            n_subagents=1,
            no_verify=False,
            no_consolidated=False,
            dry_run=True,
            evidence_only=False,
            no_prescan=False,
            language=None,
            branch=None,
            scope=None,
        )
        return ns

    with patch("quodeq.ci.review.subprocess.run", side_effect=[pr_result, repo_result]), \
         patch("quodeq.cli_parser.build_parser") as mock_build_parser, \
         patch("quodeq._cli_evaluation.run_evaluate", return_value=0):
        mock_parser = MagicMock()
        mock_parser.parse_args.side_effect = fake_parse_args
        mock_build_parser.return_value = mock_parser

        from quodeq.ci.review import handle_review
        handle_review(args)

    assert "--dimensions" not in captured_argv


def test_handle_review_expands_dimension_alias(tmp_path):
    """When --dimensions sec is given, handle_review expands it to 'security'."""
    from unittest.mock import MagicMock, patch
    import json
    import argparse

    args = argparse.Namespace(
        pr=None,
        dimensions="sec",
        pool_budget=None,
        output=str(tmp_path),
        dry_run=True,
    )

    pr_result = MagicMock()
    pr_result.stdout = json.dumps({"number": 7, "baseRefName": "main"})
    repo_result = MagicMock()
    repo_result.stdout = json.dumps({"owner": {"login": "org"}, "name": "repo"})

    captured_argv = []

    def fake_parse_args(argv):
        captured_argv.extend(argv)
        ns = argparse.Namespace(
            dimensions="security",
            repo=".",
            incremental=True,
            output=str(tmp_path),
            pool_budget=300,
            mode=None,
            max_turns=None,
            max_duration=None,
            n_subagents=1,
            no_verify=False,
            no_consolidated=False,
            dry_run=True,
            evidence_only=False,
            no_prescan=False,
            language=None,
            branch=None,
            scope=None,
        )
        return ns

    with patch("quodeq.ci.review.subprocess.run", side_effect=[pr_result, repo_result]), \
         patch("quodeq.cli_parser.build_parser") as mock_build_parser, \
         patch("quodeq._cli_evaluation.run_evaluate", return_value=0):
        mock_parser = MagicMock()
        mock_parser.parse_args.side_effect = fake_parse_args
        mock_build_parser.return_value = mock_parser

        from quodeq.ci.review import handle_review
        handle_review(args)

    idx = captured_argv.index("--dimensions")
    assert captured_argv[idx + 1] == "security"
