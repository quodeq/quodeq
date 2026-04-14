"""Tests for CLI argument parsing, helper functions, and input resolution."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from quodeq.cli_parser import build_parser


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestEnvInt:
    def test_returns_default_when_unset(self):
        from quodeq.cli import _env_int
        assert _env_int("NONEXISTENT_VAR_12345", 42, env={}) == 42

    def test_returns_parsed_int(self):
        from quodeq.cli import _env_int
        assert _env_int("MY_VAR", 0, env={"MY_VAR": "100"}) == 100

    def test_returns_default_on_invalid(self):
        from quodeq.cli import _env_int
        assert _env_int("MY_VAR", 7, env={"MY_VAR": "not_a_number"}) == 7

    def test_returns_none_default(self):
        from quodeq.cli import _env_int
        assert _env_int("MISSING", None, env={}) is None

    def test_negative_value(self):
        from quodeq.cli import _env_int
        assert _env_int("NEG", 0, env={"NEG": "-5"}) == -5


class TestSubagentModel:
    def test_returns_none_when_unset(self):
        from quodeq.cli import _subagent_model
        assert _subagent_model(env={}) is None

    def test_returns_model_string(self):
        from quodeq.cli import _subagent_model
        assert _subagent_model(env={"SUBAGENT_MODEL": "gpt-4"}) == "gpt-4"

    def test_returns_none_for_empty_string(self):
        from quodeq.cli import _subagent_model
        assert _subagent_model(env={"SUBAGENT_MODEL": ""}) is None


class TestNoVerify:
    def test_false_by_default(self):
        from quodeq.cli import _no_verify
        args = argparse.Namespace(no_verify=False)
        assert _no_verify(args, env={}) is False

    def test_true_from_flag(self):
        from quodeq.cli import _no_verify
        args = argparse.Namespace(no_verify=True)
        assert _no_verify(args, env={}) is True

    def test_true_from_env(self):
        from quodeq.cli import _no_verify
        args = argparse.Namespace(no_verify=False)
        assert _no_verify(args, env={"QUODEQ_NO_VERIFY": "1"}) is True

    def test_env_value_not_one(self):
        from quodeq.cli import _no_verify
        args = argparse.Namespace(no_verify=False)
        assert _no_verify(args, env={"QUODEQ_NO_VERIFY": "0"}) is False


# ---------------------------------------------------------------------------
# _resolve_repo tests
# ---------------------------------------------------------------------------

class TestResolveRepo:
    def test_local_path_exists(self, tmp_path):
        from quodeq.cli import _resolve_repo
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        args = argparse.Namespace(repo=str(repo_dir), branch=None)
        result = _resolve_repo(args)
        assert result == repo_dir.resolve()

    def test_local_path_not_exists(self, tmp_path, capsys):
        from quodeq.cli import _resolve_repo
        args = argparse.Namespace(repo=str(tmp_path / "nonexistent"), branch=None)
        result = _resolve_repo(args)
        assert result is None
        assert "does not exist" in capsys.readouterr().err

    @patch("quodeq._cli_evaluation.is_repo_url")
    def test_invalid_repo_url(self, mock_is_url, capsys):
        from quodeq.cli import _resolve_repo
        mock_is_url.side_effect = ValueError("Invalid URL")
        args = argparse.Namespace(repo="bad://url")
        result = _resolve_repo(args)
        assert result is None
        assert "Invalid URL" in capsys.readouterr().err

    @patch("quodeq._cli_evaluation.is_repo_url", return_value=True)
    @patch("quodeq._cli_evaluation.prepare_repository", side_effect=OSError("clone failed"))
    def test_remote_clone_failure(self, mock_prep, mock_is_url, capsys):
        from quodeq.cli import _resolve_repo
        args = argparse.Namespace(repo="https://github.com/x/y")
        result = _resolve_repo(args)
        assert result is None
        assert "Failed to clone" in capsys.readouterr().err

    @patch("quodeq._cli_evaluation.is_repo_url", return_value=True)
    @patch("quodeq._cli_evaluation.prepare_repository")
    def test_remote_clone_success(self, mock_prep, mock_is_url, tmp_path):
        from quodeq.cli import _resolve_repo
        repo_dir = tmp_path / "cloned"
        repo_dir.mkdir()
        mock_prep.return_value = str(repo_dir)
        args = argparse.Namespace(repo="https://github.com/x/y", branch=None)
        result = _resolve_repo(args)
        assert result == repo_dir.resolve()

    def test_branch_creates_worktree(self, tmp_path):
        from quodeq.cli import _resolve_repo
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        worktree_dir = tmp_path / "wt"
        worktree_dir.mkdir()
        args = argparse.Namespace(repo=str(repo_dir), branch="feature/x")
        with patch("quodeq._cli_evaluation.is_repo_url", return_value=False), \
             patch("quodeq._cli_evaluation._create_worktree", return_value=worktree_dir) as mock_wt:
            result = _resolve_repo(args)
            assert result == worktree_dir
            assert args._worktree_origin == repo_dir.resolve()
            mock_wt.assert_called_once()

    def test_branch_worktree_failure(self, tmp_path, capsys):
        from quodeq.cli import _resolve_repo
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        args = argparse.Namespace(repo=str(repo_dir), branch="bad-branch")
        with patch("quodeq._cli_evaluation.is_repo_url", return_value=False), \
             patch("quodeq._cli_evaluation._create_worktree", return_value=None):
            result = _resolve_repo(args)
            assert result is None


# ---------------------------------------------------------------------------
# _setup_run_dirs tests
# ---------------------------------------------------------------------------

class TestSetupRunDirs:
    @patch("quodeq._cli_evaluation.resolve_project_uuid", return_value="proj-uuid-123")
    @patch("quodeq._cli_evaluation.is_repo_url", return_value=False)
    @patch("quodeq._cli_evaluation.project_name_from_repo", return_value="myproject")
    def test_creates_directories(self, mock_name, mock_url, mock_uuid, tmp_path):
        from quodeq.cli import _setup_run_dirs
        output_dir = tmp_path / "output"
        src = tmp_path / "src"
        src.mkdir()
        args = argparse.Namespace(repo=str(src), output=str(output_dir), scope=None)
        reports_root, evidence_dir, evaluation_dir = _setup_run_dirs(args, src)
        assert reports_root == output_dir
        assert evidence_dir.exists()
        assert evaluation_dir.exists()
        assert "proj-uuid-123" in str(evidence_dir)


# ---------------------------------------------------------------------------
# _resolve_language tests
# ---------------------------------------------------------------------------

class TestResolveLanguage:
    def test_explicit_language(self, tmp_path):
        from quodeq.cli import _resolve_language
        args = argparse.Namespace(language="python")
        paths = MagicMock()
        result = _resolve_language(args, tmp_path, paths)
        assert result == "python"

    def test_detection_file_missing(self, tmp_path):
        from quodeq.cli import _resolve_language
        args = argparse.Namespace(language=None)
        paths = MagicMock()
        paths.detection_file.exists.return_value = False
        result = _resolve_language(args, tmp_path, paths)
        assert result is None

    @patch("quodeq._cli_evaluation.validate_path_segment", side_effect=ValueError("bad"))
    def test_invalid_language_raises(self, mock_validate):
        from quodeq.cli import _resolve_language
        args = argparse.Namespace(language="../evil")
        with pytest.raises(ValueError):
            _resolve_language(args, Path("/tmp"), MagicMock())


# ---------------------------------------------------------------------------
# Parser edge cases
# ---------------------------------------------------------------------------

class TestParserAdditionalFlags:
    def test_max_turns_flag(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", "/tmp/repo", "--max-turns", "50"])
        assert args.max_turns == 50

    def test_max_duration_flag(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", "/tmp/repo", "--max-duration", "3600"])
        assert args.max_duration == 3600

    def test_n_subagents_flag(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", "/tmp/repo", "--n-subagents", "3"])
        assert args.n_subagents == 3

    def test_max_subagents_alias(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", "/tmp/repo", "--max-subagents", "3"])
        assert args.n_subagents == 3

    def test_no_verify_flag(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", "/tmp/repo", "--no-verify"])
        assert args.no_verify is True

    def test_pool_budget_flag(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", "/tmp/repo", "--pool-budget", "120"])
        assert args.pool_budget == 120

    def test_no_consolidated_flag(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", "/tmp/repo", "--no-consolidated"])
        assert args.no_consolidated is True

    def test_incremental_flag(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", "/tmp/repo", "--incremental"])
        assert args.incremental is True

    def test_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["evaluate", "/tmp/repo"])
        assert args.max_turns is None
        assert args.max_duration is None
        assert args.n_subagents == 5
        assert args.no_verify is False
        assert args.pool_budget is None
        assert args.no_consolidated is False
        assert args.incremental is False
        assert args.no_prescan is False
        assert args.dimensions is None

    def test_combined_flags(self):
        parser = build_parser()
        args = parser.parse_args([
            "evaluate", "/tmp/repo",
            "-l", "java", "-m", "grades", "-d", "security",
            "--no-prescan", "--evidence-only", "--no-verify",
            "--max-turns", "100", "--max-duration", "600",
            "--n-subagents", "10", "--pool-budget", "200",
            "--no-consolidated", "--incremental",
            "--branch", "develop", "--scope", "src/main",
            "-o", "/tmp/output",
        ])
        assert args.language == "java"
        assert args.mode == "grades"
        assert args.dimensions == "security"
        assert args.no_prescan is True
        assert args.evidence_only is True
        assert args.no_verify is True
        assert args.max_turns == 100
        assert args.max_duration == 600
        assert args.n_subagents == 10
        assert args.pool_budget == 200
        assert args.no_consolidated is True
        assert args.incremental is True
        assert args.branch == "develop"
        assert args.scope == "src/main"
        assert args.output == "/tmp/output"
