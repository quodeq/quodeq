"""Tests for quodeq check (local PR review)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_detect_pr_reads_gh_output():
    from quodeq.ci.check import detect_pr
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"number": 42, "baseRefName": "develop"})
    mock_result.returncode = 0
    with patch("quodeq.ci.check.subprocess.run", return_value=mock_result):
        pr, base = detect_pr()
        assert pr == 42
        assert base == "develop"


def test_detect_pr_raises_when_no_pr_found():
    from quodeq.ci.check import detect_pr, CheckError
    import subprocess as sp
    error = sp.CalledProcessError(1, ["gh"], stderr="no pull requests found for branch")
    with patch("quodeq.ci.check.subprocess.run", side_effect=error):
        with pytest.raises(CheckError) as excinfo:
            detect_pr()
        assert "No open PR" in str(excinfo.value)


def test_detect_pr_raises_when_gh_missing():
    from quodeq.ci.check import detect_pr, CheckError
    with patch("quodeq.ci.check.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(CheckError) as excinfo:
            detect_pr()
        assert "gh CLI not found" in str(excinfo.value)


def test_get_github_token_reads_gh_output():
    from quodeq.ci.check import get_github_token
    mock_result = MagicMock()
    mock_result.stdout = "ghp_test_token\n"
    mock_result.returncode = 0
    with patch("quodeq.ci.check.subprocess.run", return_value=mock_result):
        assert get_github_token() == "ghp_test_token"


def test_get_github_token_raises_when_not_logged_in():
    from quodeq.ci.check import get_github_token, CheckError
    import subprocess as sp
    error = sp.CalledProcessError(1, ["gh"], stderr="auth required")
    with patch("quodeq.ci.check.subprocess.run", side_effect=error):
        with pytest.raises(CheckError) as excinfo:
            get_github_token()
        assert "gh auth login" in str(excinfo.value)


def test_get_repo_info_returns_owner_and_name():
    from quodeq.ci.check import get_repo_info
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"owner": {"login": "quodeq"}, "name": "quodeq"})
    mock_result.returncode = 0
    with patch("quodeq.ci.check.subprocess.run", return_value=mock_result):
        owner, repo = get_repo_info()
        assert owner == "quodeq"
        assert repo == "quodeq"


def test_snapshot_run_dirs_empty_when_nonexistent(tmp_path):
    from quodeq.ci.check import snapshot_run_dirs
    result = snapshot_run_dirs(tmp_path / "does-not-exist")
    assert result == set()


def test_snapshot_run_dirs_finds_evaluation_dirs(tmp_path):
    from quodeq.ci.check import snapshot_run_dirs
    # Create a fake structure
    (tmp_path / "project-a" / "run-1" / "evaluation").mkdir(parents=True)
    (tmp_path / "project-a" / "run-2" / "evaluation").mkdir(parents=True)
    (tmp_path / "project-a" / "run-1" / "evidence").mkdir(parents=True)  # not counted
    result = snapshot_run_dirs(tmp_path)
    assert len(result) == 2
    assert all(p.name == "evaluation" for p in result)


def test_check_subcommand_parses(tmp_path):
    """The check subcommand should be registered in the top-level parser."""
    from quodeq.cli_parser import build_parser
    parser = build_parser()
    args = parser.parse_args(["check", "--pr", "42", "--dry-run"])
    assert args.command == "check"
    assert args.pr == 42
    assert args.dry_run is True


def test_check_subcommand_defaults():
    from quodeq.cli_parser import build_parser
    parser = build_parser()
    args = parser.parse_args(["check"])
    assert args.command == "check"
    assert args.pr is None
    assert args.dimensions is None
    assert args.dry_run is False
