"""Tests for quodeq review (local PR review): gh lookups, run snapshots, CLI parsing."""
from __future__ import annotations

import ast
import json
import subprocess as sp
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import quodeq.ci.review as review_module
from quodeq.ci.review import (
    ReviewError,
    detect_pr,
    get_github_token,
    get_repo_info,
    snapshot_run_dirs,
)
from quodeq.cli_parser import build_parser


def test_detect_pr_reads_gh_output():
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"number": 42, "baseRefName": "develop"})
    mock_result.returncode = 0
    with patch("quodeq.ci.review.subprocess.run", return_value=mock_result):
        pr, base = detect_pr()
        assert pr == 42
        assert base == "develop"


def test_detect_pr_raises_when_no_pr_found():
    error = sp.CalledProcessError(1, ["gh"], stderr="no pull requests found for branch")
    with patch("quodeq.ci.review.subprocess.run", side_effect=error):
        with pytest.raises(ReviewError) as excinfo:
            detect_pr()
        assert "No open PR" in str(excinfo.value)


def test_detect_pr_raises_when_gh_missing():
    with patch("quodeq.ci.review.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(ReviewError) as excinfo:
            detect_pr()
        assert "gh CLI not found" in str(excinfo.value)


def test_get_github_token_reads_gh_output():
    mock_result = MagicMock()
    mock_result.stdout = "ghp_test_token\n"
    mock_result.returncode = 0
    with patch("quodeq.ci.review.subprocess.run", return_value=mock_result):
        assert get_github_token() == "ghp_test_token"


def test_get_github_token_raises_when_not_logged_in():
    error = sp.CalledProcessError(1, ["gh"], stderr="auth required")
    with patch("quodeq.ci.review.subprocess.run", side_effect=error):
        with pytest.raises(ReviewError) as excinfo:
            get_github_token()
        assert "gh auth login" in str(excinfo.value)


def test_get_repo_info_returns_owner_and_name():
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"owner": {"login": "quodeq"}, "name": "quodeq"})
    mock_result.returncode = 0
    with patch("quodeq.ci.review.subprocess.run", return_value=mock_result):
        owner, repo = get_repo_info()
        assert owner == "quodeq"
        assert repo == "quodeq"


def test_snapshot_run_dirs_empty_when_nonexistent(tmp_path):
    result = snapshot_run_dirs(tmp_path / "does-not-exist")
    assert result == set()


def test_snapshot_run_dirs_finds_run_dirs_by_evidence(tmp_path):

    (tmp_path / "project-a" / "run-1" / "evidence").mkdir(parents=True)
    (tmp_path / "project-a" / "run-2" / "evidence").mkdir(parents=True)

    result = snapshot_run_dirs(tmp_path)
    assert len(result) == 2
    # snapshot returns run dirs (parents of evidence/), not evidence dirs themselves
    assert all(p.parent.name == "project-a" for p in result)
    assert {p.name for p in result} == {"run-1", "run-2"}


def test_review_subcommand_parses(tmp_path):
    """The review subcommand should be registered in the top-level parser."""
    parser = build_parser()
    args = parser.parse_args(["review", "--pr", "42", "--dry-run"])
    assert args.command == "review"
    assert args.pr == 42
    assert args.dry_run is True


def test_review_subcommand_defaults():
    parser = build_parser()
    args = parser.parse_args(["review"])
    assert args.command == "review"
    assert args.pr is None
    assert args.dimensions is None  # default is all dimensions (no --dimensions flag)
    assert args.dry_run is False


@pytest.mark.parametrize("call", [
    detect_pr,
    lambda: detect_pr(pr_override=7),
    get_github_token,
    get_repo_info,
])
def test_every_gh_call_reports_a_missing_gh_the_same_way(call):
    with patch("quodeq.ci.review.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(ReviewError, match="gh CLI not found"):
            call()


def test_gh_is_spawned_from_one_place():
    tree = ast.parse(Path(review_module.__file__).read_text(encoding="utf-8"))
    runs = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run" and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]
    assert len(runs) == 1
