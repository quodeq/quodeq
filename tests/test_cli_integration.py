"""Tests for CLI integration scenarios — pipeline cleanup, worktrees, evaluation input resolution."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _run_pipeline_with_cleanup tests
# ---------------------------------------------------------------------------

class TestRunPipelineWithCleanup:
    @patch("quodeq._cli_evaluation._execute_pipeline", return_value=0)
    @patch("quodeq._cli_evaluation._build_run_config")
    @patch("quodeq._cli_evaluation._save_manifest")
    @patch("quodeq._cli_evaluation.emit_marker")
    @patch("quodeq._cli_resolution.is_repo_url", return_value=False)
    def test_local_repo_no_cleanup(self, mock_url, mock_marker, mock_save, mock_config, mock_exec, tmp_path):
        from quodeq.cli import _run_pipeline_with_cleanup, ResolvedInputs
        evidence_dir = tmp_path / "proj-uuid" / "run-id" / "evidence"
        evaluation_dir = tmp_path / "proj-uuid" / "run-id" / "evaluation"
        evidence_dir.mkdir(parents=True)
        evaluation_dir.mkdir(parents=True)
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        args = argparse.Namespace(repo=str(tmp_path))
        result = _run_pipeline_with_cleanup(
            args, inputs, (tmp_path, evidence_dir, evaluation_dir)
        )
        assert result == 0

    @patch("quodeq._cli_evaluation._execute_pipeline", return_value=0)
    @patch("quodeq._cli_evaluation._build_run_config")
    @patch("quodeq._cli_evaluation._save_manifest")
    @patch("quodeq._cli_evaluation.emit_marker")
    @patch("quodeq._cli_resolution.is_repo_url", return_value=True)
    @patch("quodeq._cli_evaluation.cleanup_cloned_repo")
    def test_remote_repo_cleanup(self, mock_cleanup, mock_url, mock_marker, mock_save, mock_config, mock_exec, tmp_path):
        from quodeq.cli import _run_pipeline_with_cleanup, ResolvedInputs
        evidence_dir = tmp_path / "proj-uuid" / "run-id" / "evidence"
        evaluation_dir = tmp_path / "proj-uuid" / "run-id" / "evaluation"
        evidence_dir.mkdir(parents=True)
        evaluation_dir.mkdir(parents=True)
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        args = argparse.Namespace(repo="https://github.com/x/y")
        _run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))
        mock_cleanup.assert_called_once()

    @patch("quodeq._cli_evaluation._execute_pipeline", return_value=0)
    @patch("quodeq._cli_evaluation._build_run_config")
    @patch("quodeq._cli_evaluation._save_manifest")
    @patch("quodeq._cli_evaluation.emit_marker")
    @patch("quodeq._cli_resolution.is_repo_url", return_value=False)
    @patch("quodeq._cli_evaluation._cleanup_worktree")
    def test_worktree_cleanup(self, mock_wt_cleanup, mock_url, mock_marker, mock_save, mock_config, mock_exec, tmp_path):
        from quodeq.cli import _run_pipeline_with_cleanup, ResolvedInputs
        evidence_dir = tmp_path / "proj-uuid" / "run-id" / "evidence"
        evaluation_dir = tmp_path / "proj-uuid" / "run-id" / "evaluation"
        evidence_dir.mkdir(parents=True)
        evaluation_dir.mkdir(parents=True)
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        args = argparse.Namespace(repo=str(tmp_path))
        args._worktree_dir = tmp_path / "wt"
        args._worktree_origin = tmp_path / "origin"
        _run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))
        mock_wt_cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# _create_worktree / _cleanup_worktree (mocked subprocess)
# ---------------------------------------------------------------------------

class TestWorktreeMocked:
    @patch("quodeq._cli_resolution.subprocess.run")
    def test_create_worktree_success(self, mock_run, tmp_path):
        from quodeq.cli import _create_worktree
        mock_run.return_value = MagicMock(returncode=0)
        result = _create_worktree(tmp_path, "main")
        assert result is not None
        mock_run.assert_called_once()

    @patch("quodeq._cli_resolution.subprocess.run", side_effect=subprocess.CalledProcessError(1, "git"))
    def test_create_worktree_failure(self, mock_run, tmp_path, capsys):
        from quodeq.cli import _create_worktree
        result = _create_worktree(tmp_path, "bad-branch")
        assert result is None
        assert "Failed to create worktree" in capsys.readouterr().err

    @patch("quodeq._cli_resolution.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30))
    def test_create_worktree_timeout(self, mock_run, tmp_path, capsys):
        from quodeq.cli import _create_worktree
        result = _create_worktree(tmp_path, "slow-branch")
        assert result is None

    @patch("quodeq._cli_resolution.subprocess.run")
    def test_cleanup_worktree_success(self, mock_run, tmp_path):
        from quodeq.cli import _cleanup_worktree
        _cleanup_worktree(tmp_path, tmp_path / "wt")
        mock_run.assert_called_once()

    @patch("quodeq._cli_resolution.subprocess.run", side_effect=OSError("fail"))
    def test_cleanup_worktree_error_silenced(self, mock_run, tmp_path):
        from quodeq.cli import _cleanup_worktree
        _cleanup_worktree(tmp_path, tmp_path / "wt")  # should not raise


# ---------------------------------------------------------------------------
# _resolve_evaluation_inputs tests
# ---------------------------------------------------------------------------

class TestResolveEvaluationInputs:
    @patch("quodeq._cli_resolution._resolve_repo", return_value=None)
    def test_returns_none_on_repo_failure(self, mock_repo):
        from quodeq.cli import _resolve_evaluation_inputs
        args = argparse.Namespace()
        assert _resolve_evaluation_inputs(args) is None

    @patch("quodeq._cli_resolution.default_paths")
    @patch("quodeq._cli_resolution._resolve_repo")
    def test_returns_none_when_config_missing(self, mock_repo, mock_paths, tmp_path):
        from quodeq.cli import _resolve_evaluation_inputs
        mock_repo.return_value = tmp_path
        paths_obj = MagicMock()
        paths_obj.detection_file.exists.return_value = False
        paths_obj.dimensions_file.exists.return_value = False
        mock_paths.return_value = paths_obj
        args = argparse.Namespace(scope=None)
        result = _resolve_evaluation_inputs(args)
        assert result is None

    @patch("quodeq._cli_resolution._build_manifest", return_value=None)
    @patch("quodeq._cli_resolution._resolve_language", return_value="python")
    @patch("quodeq._cli_resolution.default_paths")
    @patch("quodeq._cli_resolution._resolve_repo")
    def test_returns_none_when_language_detection_fails(self, mock_repo, mock_paths, mock_lang, mock_manifest, tmp_path):
        from quodeq.cli import _resolve_evaluation_inputs
        mock_repo.return_value = tmp_path
        mock_lang.return_value = None
        paths_obj = MagicMock()
        paths_obj.detection_file.exists.return_value = True
        paths_obj.dimensions_file.exists.return_value = True
        mock_paths.return_value = paths_obj
        args = argparse.Namespace(scope=None, language=None)
        # Override mock_lang to return None for this test
        mock_lang.return_value = None
        result = _resolve_evaluation_inputs(args)
        assert result is None

    @patch("quodeq._cli_resolution._build_manifest", return_value=None)
    @patch("quodeq._cli_resolution.load_universal_dimensions", return_value={"dims": []})
    @patch("quodeq._cli_resolution._resolve_language", return_value="python")
    @patch("quodeq._cli_resolution.default_paths")
    @patch("quodeq._cli_resolution._resolve_repo")
    def test_success_path(self, mock_repo, mock_paths, mock_lang, mock_dims, mock_manifest, tmp_path):
        from quodeq.cli import _resolve_evaluation_inputs
        mock_repo.return_value = tmp_path
        paths_obj = MagicMock()
        paths_obj.detection_file.exists.return_value = True
        paths_obj.dimensions_file.exists.return_value = True
        mock_paths.return_value = paths_obj
        args = argparse.Namespace(scope=None, language="python", no_prescan=True)
        result = _resolve_evaluation_inputs(args)
        assert result is not None
        assert result.language == "python"
        assert result.src == tmp_path

    @patch("quodeq._cli_resolution._build_manifest", return_value=None)
    @patch("quodeq._cli_resolution.load_universal_dimensions", return_value={"dims": []})
    @patch("quodeq._cli_resolution._resolve_language", return_value="python")
    @patch("quodeq._cli_resolution.default_paths")
    @patch("quodeq._cli_resolution._resolve_repo")
    def test_scope_nonexistent(self, mock_repo, mock_paths, mock_lang, mock_dims, mock_manifest, tmp_path, capsys):
        from quodeq.cli import _resolve_evaluation_inputs
        mock_repo.return_value = tmp_path
        paths_obj = MagicMock()
        paths_obj.detection_file.exists.return_value = True
        paths_obj.dimensions_file.exists.return_value = True
        mock_paths.return_value = paths_obj
        args = argparse.Namespace(scope="nonexistent/path", language="python", no_prescan=True)
        result = _resolve_evaluation_inputs(args)
        assert result is None
        assert "Scope path does not exist" in capsys.readouterr().err

    @patch("quodeq._cli_resolution._build_manifest", return_value=None)
    @patch("quodeq._cli_resolution.load_universal_dimensions", return_value={})
    @patch("quodeq._cli_resolution._resolve_language", return_value="python")
    @patch("quodeq._cli_resolution.default_paths")
    @patch("quodeq._cli_resolution._resolve_repo")
    def test_scope_success(self, mock_repo, mock_paths, mock_lang, mock_dims, mock_manifest, tmp_path, capsys):
        from quodeq.cli import _resolve_evaluation_inputs
        mock_repo.return_value = tmp_path
        scope_dir = tmp_path / "src" / "backend"
        scope_dir.mkdir(parents=True)
        paths_obj = MagicMock()
        paths_obj.detection_file.exists.return_value = True
        paths_obj.dimensions_file.exists.return_value = True
        mock_paths.return_value = paths_obj
        args = argparse.Namespace(scope="src/backend", language="python", no_prescan=True)
        result = _resolve_evaluation_inputs(args)
        assert result is not None
        err = capsys.readouterr().err
        assert "Scoped evaluation" in err

    @patch("quodeq._cli_resolution._build_manifest", return_value=None)
    @patch("quodeq._cli_resolution.load_universal_dimensions", side_effect=ValueError("bad dims"))
    @patch("quodeq._cli_resolution._resolve_language", return_value="python")
    @patch("quodeq._cli_resolution.default_paths")
    @patch("quodeq._cli_resolution._resolve_repo")
    def test_invalid_dimensions_config(self, mock_repo, mock_paths, mock_lang, mock_dims, mock_manifest, tmp_path, capsys):
        from quodeq.cli import _resolve_evaluation_inputs
        mock_repo.return_value = tmp_path
        paths_obj = MagicMock()
        paths_obj.detection_file.exists.return_value = True
        paths_obj.dimensions_file.exists.return_value = True
        mock_paths.return_value = paths_obj
        args = argparse.Namespace(scope=None, language="python", no_prescan=True)
        result = _resolve_evaluation_inputs(args)
        assert result is None
        assert "Invalid dimensions config" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main() dispatch tests
# ---------------------------------------------------------------------------

class TestMainDispatch:
    @patch("quodeq.cli.load_env_file")
    @patch("quodeq.cli.default_paths")
    @patch("quodeq.cli.run_evaluate", return_value=0)
    def test_evaluate_dispatch(self, mock_eval, mock_paths, mock_env):
        from quodeq.cli import main
        result = main(["evaluate", "/tmp/repo", "-l", "python"])
        assert result == 0
        mock_eval.assert_called_once()

    @patch("quodeq.cli.load_env_file")
    @patch("quodeq.cli.default_paths")
    @patch("quodeq.cli.dashboard_main", return_value=0)
    def test_dashboard_dispatch(self, mock_dash, mock_paths, mock_env):
        from quodeq.cli import main
        result = main(["dashboard"])
        assert result == 0

    @patch("quodeq.cli.load_env_file")
    @patch("quodeq.cli.default_paths")
    def test_unknown_command_returns_1(self, mock_paths, mock_env):
        from quodeq.cli import main
        # Force an unknown handler_command
        with patch("quodeq.cli.build_parser") as mock_parser:
            mock_ns = argparse.Namespace(handler_command="nonexistent")
            mock_parser.return_value.parse_known_args.return_value = (mock_ns, [])
            result = main(["nonexistent"])
            assert result == 1
