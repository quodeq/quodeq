"""Tests for quodeq review (local PR review): gh lookups, run snapshots, CLI parsing."""
from __future__ import annotations

import argparse
import ast
import json
import subprocess as sp
import sys
from pathlib import Path
from types import SimpleNamespace
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
    assert args.yes is False


def test_review_subcommand_parses_yes():
    parser = build_parser()
    assert parser.parse_args(["review", "--yes"]).yes is True


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


def test_run_gh_raises_review_error_on_timeout():
    with patch(
        "quodeq.ci.review.subprocess.run",
        side_effect=sp.TimeoutExpired(["gh"], 60),
    ):
        with pytest.raises(ReviewError, match="timed out"):
            review_module._run_gh(["pr", "view"])


def test_run_gh_passes_a_60s_timeout():
    mock_result = MagicMock()
    mock_result.stdout = ""
    with patch("quodeq.ci.review.subprocess.run", return_value=mock_result) as mock_run:
        review_module._run_gh(["pr", "view"])
    _args, kwargs = mock_run.call_args
    assert kwargs["timeout"] == 60


@pytest.mark.parametrize("stdout, match", [
    ("not json {{{", "invalid JSON"),
    (json.dumps([1, 2, 3]), "not an object"),
])
def test_detect_pr_raises_on_bad_gh_json(stdout, match):
    mock_result = MagicMock()
    mock_result.stdout = stdout
    with patch("quodeq.ci.review.subprocess.run", return_value=mock_result):
        with pytest.raises(ReviewError, match=match):
            detect_pr()


def test_detect_pr_raises_when_gh_json_missing_expected_keys():
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"number": 42})  # no baseRefName
    with patch("quodeq.ci.review.subprocess.run", return_value=mock_result):
        with pytest.raises(ReviewError, match="unexpected JSON"):
            detect_pr()


def test_get_repo_info_raises_on_non_object_gh_json():
    mock_result = MagicMock()
    mock_result.stdout = json.dumps("just a string")
    with patch("quodeq.ci.review.subprocess.run", return_value=mock_result):
        with pytest.raises(ReviewError, match="not an object"):
            get_repo_info()


def test_gh_is_spawned_from_one_place():
    tree = ast.parse(Path(review_module.__file__).read_text(encoding="utf-8"))
    runs = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run" and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]
    assert len(runs) == 1


class TestConfirmPost:
    """Publishing to a shared PR asks first, but only when someone can answer."""

    @staticmethod
    def _tty(answer: str):
        return SimpleNamespace(isatty=lambda: True), lambda prompt: answer

    def test_non_interactive_input_posts_without_asking(self):
        from quodeq.ci.review import confirm_post
        asked = []
        stream = SimpleNamespace(isatty=lambda: False)
        assert confirm_post("o", "r", 7, stdin=stream, ask=lambda p: asked.append(p) or "n") is True
        assert asked == []

    def test_pytest_stdin_is_not_a_terminal_so_the_default_posts(self):
        from quodeq.ci.review import confirm_post
        assert not sys.stdin.isatty()
        assert confirm_post("o", "r", 7, ask=lambda p: "n") is True

    @pytest.mark.parametrize("answer, expected", [("y", True), ("YES", True), ("", False), ("n", False)])
    def test_terminal_answer_decides(self, answer, expected):
        from quodeq.ci.review import confirm_post
        stream, ask = self._tty(answer)
        assert confirm_post("o", "r", 7, stdin=stream, ask=ask) is expected

    def test_terminal_prompt_names_the_target(self):
        from quodeq.ci.review import confirm_post
        prompts = []
        stream = SimpleNamespace(isatty=lambda: True)
        confirm_post("acme", "widgets", 42, stdin=stream, ask=lambda p: prompts.append(p) or "y")
        assert prompts == ["Post this review to acme/widgets PR #42? [y/N] "]

    @pytest.mark.parametrize("exc", [EOFError, KeyboardInterrupt])
    def test_end_of_input_declines(self, exc):
        from quodeq.ci.review import confirm_post

        def _ask(prompt):
            raise exc

        assert confirm_post("o", "r", 7, stdin=SimpleNamespace(isatty=lambda: True), ask=_ask) is False


class TestPostGate:
    def _args(self, **kw):
        return argparse.Namespace(dry_run=False, **kw)

    def test_declined_confirmation_posts_nothing(self, monkeypatch, capsys):
        from quodeq.ci import review
        monkeypatch.setattr(review, "confirm_post", lambda *a, **k: False)
        posted = []
        monkeypatch.setattr("quodeq.ci.reporter.post_review", lambda **k: posted.append(k))
        code = review._post_review_or_dry_run(self._args(), {"body": "b"}, "o", "r", 7)
        assert code == 1 and posted == []
        assert "Review not posted" in capsys.readouterr().out

    def test_yes_skips_the_confirmation(self, monkeypatch):
        from quodeq.ci import review
        asked = []
        monkeypatch.setattr(review, "confirm_post", lambda *a, **k: asked.append(a) or False)
        monkeypatch.setattr(review, "get_github_token", lambda: "tok")
        posted = []
        monkeypatch.setattr("quodeq.ci.reporter.post_review", lambda **k: posted.append(k))
        code = review._post_review_or_dry_run(self._args(yes=True), {"body": "b"}, "o", "r", 7)
        assert code == 0 and asked == [] and posted[0]["pr_number"] == 7

    def test_a_github_api_failure_prints_a_worded_error(self, monkeypatch, capsys):
        from quodeq.ci import review
        monkeypatch.setattr(review, "get_github_token", lambda: "tok")

        def _fail(**_):
            raise RuntimeError("GitHub API returned HTTP 422 (Unprocessable)")

        monkeypatch.setattr("quodeq.ci.reporter.post_review", _fail)
        code = review._post_review_or_dry_run(self._args(yes=True), {"body": "b"}, "o", "r", 7)
        err = capsys.readouterr().err
        assert code == 1 and "could not post the review" in err and "HTTP 422" in err
