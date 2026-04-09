"""Comprehensive tests for quodeq.cli — covers argument parsing, helper functions, and command dispatch."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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

    @patch("quodeq.cli.is_repo_url")
    def test_invalid_repo_url(self, mock_is_url, capsys):
        from quodeq.cli import _resolve_repo
        mock_is_url.side_effect = ValueError("Invalid URL")
        args = argparse.Namespace(repo="bad://url")
        result = _resolve_repo(args)
        assert result is None
        assert "Invalid URL" in capsys.readouterr().err

    @patch("quodeq.cli.is_repo_url", return_value=True)
    @patch("quodeq.cli.prepare_repository", side_effect=OSError("clone failed"))
    def test_remote_clone_failure(self, mock_prep, mock_is_url, capsys):
        from quodeq.cli import _resolve_repo
        args = argparse.Namespace(repo="https://github.com/x/y")
        result = _resolve_repo(args)
        assert result is None
        assert "Failed to clone" in capsys.readouterr().err

    @patch("quodeq.cli.is_repo_url", return_value=True)
    @patch("quodeq.cli.prepare_repository")
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
        with patch("quodeq.cli.is_repo_url", return_value=False), \
             patch("quodeq.cli._create_worktree", return_value=worktree_dir) as mock_wt:
            result = _resolve_repo(args)
            assert result == worktree_dir
            assert args._worktree_origin == repo_dir.resolve()
            mock_wt.assert_called_once()

    def test_branch_worktree_failure(self, tmp_path, capsys):
        from quodeq.cli import _resolve_repo
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        args = argparse.Namespace(repo=str(repo_dir), branch="bad-branch")
        with patch("quodeq.cli.is_repo_url", return_value=False), \
             patch("quodeq.cli._create_worktree", return_value=None):
            result = _resolve_repo(args)
            assert result is None


# ---------------------------------------------------------------------------
# _setup_run_dirs tests
# ---------------------------------------------------------------------------

class TestSetupRunDirs:
    @patch("quodeq.cli.resolve_project_uuid", return_value="proj-uuid-123")
    @patch("quodeq.cli.is_repo_url", return_value=False)
    @patch("quodeq.cli.project_name_from_repo", return_value="myproject")
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

    @patch("quodeq.cli.validate_path_segment", side_effect=ValueError("bad"))
    def test_invalid_language_raises(self, mock_validate):
        from quodeq.cli import _resolve_language
        args = argparse.Namespace(language="../evil")
        with pytest.raises(ValueError):
            _resolve_language(args, Path("/tmp"), MagicMock())


# ---------------------------------------------------------------------------
# _build_manifest tests
# ---------------------------------------------------------------------------

class TestBuildManifest:
    def test_no_prescan_returns_none(self):
        from quodeq.cli import _build_manifest
        args = argparse.Namespace(no_prescan=True)
        result = _build_manifest(args, Path("/tmp"), MagicMock())
        assert result is None

    def test_detection_file_missing_returns_none(self):
        from quodeq.cli import _build_manifest
        args = argparse.Namespace(no_prescan=False)
        paths = MagicMock()
        paths.detection_file.exists.return_value = False
        result = _build_manifest(args, Path("/tmp"), paths)
        assert result is None


# ---------------------------------------------------------------------------
# _execute_pipeline tests
# ---------------------------------------------------------------------------

class TestExecutePipeline:
    @patch("quodeq.cli.run")
    @patch("quodeq.cli.write_text")
    def test_evidence_only_success(self, mock_write, mock_run, tmp_path):
        from quodeq.cli import _execute_pipeline
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=True, mode="numerical")
        mock_evidence = MagicMock()
        mock_evidence.to_evidence_dict.return_value = {"data": "test"}
        mock_run.return_value = mock_evidence
        config = MagicMock()
        config.language = "python"
        result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
        assert result == 0
        mock_run.assert_called_once_with(config)

    @patch("quodeq.cli.run")
    @patch("quodeq.cli.write_text", side_effect=OSError("disk full"))
    def test_evidence_only_write_failure(self, mock_write, mock_run, tmp_path, capsys):
        from quodeq.cli import _execute_pipeline
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=True, mode="numerical")
        mock_evidence = MagicMock()
        mock_evidence.to_evidence_dict.return_value = {}
        mock_run.return_value = mock_evidence
        config = MagicMock()
        config.language = "python"
        result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
        assert result == 1
        assert "Failed to write" in capsys.readouterr().err

    @patch("quodeq.cli.run_full")
    def test_full_pipeline_success(self, mock_run_full, tmp_path):
        from quodeq.cli import _execute_pipeline
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=False, mode="numerical")
        mock_run_full.return_value = {"security": 8.5, "reliability": 7.0}
        config = MagicMock()
        result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
        assert result == 0

    @patch("quodeq.cli.run_full")
    def test_pipeline_analysis_error(self, mock_run_full, tmp_path, capsys):
        from quodeq.cli import _execute_pipeline
        from quodeq.analysis.subprocess import AnalysisError
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=False, mode="numerical")
        mock_run_full.side_effect = AnalysisError("AI failed")
        config = MagicMock()
        result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
        assert result == 1
        assert "AI failed" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# _save_manifest tests
# ---------------------------------------------------------------------------

class TestSaveManifest:
    @patch("quodeq.cli.write_text")
    def test_saves_when_manifest_exists(self, mock_write, tmp_path):
        from quodeq.cli import _save_manifest
        manifest = MagicMock()
        manifest.to_dict.return_value = {"targets": []}
        _save_manifest(manifest, tmp_path)
        mock_write.assert_called_once()

    def test_none_manifest_no_op(self, tmp_path):
        from quodeq.cli import _save_manifest
        _save_manifest(None, tmp_path)  # should not raise

    @patch("quodeq.cli.write_text", side_effect=OSError("fail"))
    def test_os_error_silenced(self, mock_write, tmp_path):
        from quodeq.cli import _save_manifest
        manifest = MagicMock()
        manifest.to_dict.return_value = {}
        _save_manifest(manifest, tmp_path)  # should not raise


# ---------------------------------------------------------------------------
# _build_run_config tests
# ---------------------------------------------------------------------------

class TestBuildRunConfig:
    @patch("quodeq.cli.default_paths")
    @patch("quodeq.cli.get_ai_model", return_value="claude-3")
    def test_basic_config(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import _build_run_config, ResolvedInputs
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = True
        mock_paths_obj.evaluators_dir = tmp_path / "evaluators"
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, incremental=False,
        )
        inputs = ResolvedInputs(
            src=tmp_path, language="python", manifest=None, dims_data={}
        )
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env={})
        assert config.language == "python"
        assert config.options.verify_findings is True

    @patch("quodeq.cli.default_paths")
    @patch("quodeq.cli.get_ai_model", return_value=None)
    def test_subagent_model_fallback(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import _build_run_config, ResolvedInputs
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path / "evaluators"
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions="security,reliability", no_consolidated=False,
            no_verify=True, max_turns=10, max_duration=300,
            n_subagents=3, pool_budget=120, incremental=True,
        )
        inputs = ResolvedInputs(
            src=tmp_path, language="java", manifest=None, dims_data={}
        )
        env = {"SUBAGENT_MODEL": "ollama/llama3"}
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env=env)
        assert config.options.ai_model == "ollama/llama3"
        assert config.options.dimensions == ["security", "reliability"]
        assert config.options.max_turns == 10
        assert config.options.max_duration == 300
        assert config.options.pool_budget == 120
        assert config.options.incremental is True
        assert config.options.verify_findings is False
        assert config.standards_dir is None

    @patch("quodeq.cli.default_paths")
    @patch("quodeq.cli.get_ai_model", return_value="model-x")
    def test_single_file_disables_consolidated(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import _build_run_config, ResolvedInputs
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, incremental=False, _single_file=True,
        )
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env={})
        assert config.options.consolidated is False

    @patch("quodeq.cli.default_paths")
    @patch("quodeq.cli.get_ai_model", return_value="model-x")
    def test_env_no_consolidate(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import _build_run_config, ResolvedInputs
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, incremental=False,
        )
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env={"QUODEQ_NO_CONSOLIDATE": "1"})
        assert config.options.consolidated is False

    @patch("quodeq.cli.default_paths")
    @patch("quodeq.cli.get_ai_model", return_value="model-x")
    def test_env_overrides_for_turns_and_duration(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import _build_run_config, ResolvedInputs
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, incremental=False,
        )
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        env = {"QUODEQ_MAX_TURNS": "50", "QUODEQ_MAX_DURATION": "900", "QUODEQ_POOL_BUDGET": "300"}
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env=env)
        assert config.options.max_turns == 50
        assert config.options.max_duration == 900
        assert config.options.pool_budget == 300


# ---------------------------------------------------------------------------
# run_evaluate tests
# ---------------------------------------------------------------------------

class TestRunEvaluate:
    @patch("quodeq.shared.prereqs.check_evaluate_prereqs", side_effect=RuntimeError("no claude"))
    def test_prereqs_failure(self, mock_prereqs, capsys):
        from quodeq.cli import run_evaluate
        args = argparse.Namespace()
        result = run_evaluate(args)
        assert result == 1
        assert "no claude" in capsys.readouterr().err

    @patch("quodeq.cli._resolve_evaluation_inputs", return_value=None)
    @patch("quodeq.shared.prereqs.check_evaluate_prereqs")
    def test_resolve_inputs_none(self, mock_prereqs, mock_resolve):
        from quodeq.cli import run_evaluate
        args = argparse.Namespace()
        result = run_evaluate(args)
        assert result == 1

    @patch("quodeq.cli._run_pipeline_with_cleanup", return_value=0)
    @patch("quodeq.cli._setup_run_dirs")
    @patch("quodeq.cli._resolve_evaluation_inputs")
    @patch("quodeq.shared.prereqs.check_evaluate_prereqs")
    def test_successful_evaluate(self, mock_prereqs, mock_resolve, mock_dirs, mock_pipeline):
        from quodeq.cli import run_evaluate, ResolvedInputs
        mock_resolve.return_value = ResolvedInputs(
            src=Path("/tmp/repo"), language="python", manifest=None, dims_data={}
        )
        mock_dirs.return_value = (Path("/tmp/out"), Path("/tmp/ev"), Path("/tmp/eval"))
        args = argparse.Namespace()
        result = run_evaluate(args)
        assert result == 0
        mock_pipeline.assert_called_once()


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


# ---------------------------------------------------------------------------
# _run_pipeline_with_cleanup tests
# ---------------------------------------------------------------------------

class TestRunPipelineWithCleanup:
    @patch("quodeq.cli._execute_pipeline", return_value=0)
    @patch("quodeq.cli._build_run_config")
    @patch("quodeq.cli._save_manifest")
    @patch("quodeq.engine._runner_markers.emit_marker")
    @patch("quodeq.cli.is_repo_url", return_value=False)
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

    @patch("quodeq.cli._execute_pipeline", return_value=0)
    @patch("quodeq.cli._build_run_config")
    @patch("quodeq.cli._save_manifest")
    @patch("quodeq.engine._runner_markers.emit_marker")
    @patch("quodeq.cli.is_repo_url", return_value=True)
    @patch("quodeq.cli.cleanup_cloned_repo")
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

    @patch("quodeq.cli._execute_pipeline", return_value=0)
    @patch("quodeq.cli._build_run_config")
    @patch("quodeq.cli._save_manifest")
    @patch("quodeq.engine._runner_markers.emit_marker")
    @patch("quodeq.cli.is_repo_url", return_value=False)
    @patch("quodeq.cli._cleanup_worktree")
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
    @patch("quodeq.cli.subprocess.run")
    def test_create_worktree_success(self, mock_run, tmp_path):
        from quodeq.cli import _create_worktree
        mock_run.return_value = MagicMock(returncode=0)
        result = _create_worktree(tmp_path, "main")
        assert result is not None
        mock_run.assert_called_once()

    @patch("quodeq.cli.subprocess.run", side_effect=subprocess.CalledProcessError(1, "git"))
    def test_create_worktree_failure(self, mock_run, tmp_path, capsys):
        from quodeq.cli import _create_worktree
        result = _create_worktree(tmp_path, "bad-branch")
        assert result is None
        assert "Failed to create worktree" in capsys.readouterr().err

    @patch("quodeq.cli.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30))
    def test_create_worktree_timeout(self, mock_run, tmp_path, capsys):
        from quodeq.cli import _create_worktree
        result = _create_worktree(tmp_path, "slow-branch")
        assert result is None

    @patch("quodeq.cli.subprocess.run")
    def test_cleanup_worktree_success(self, mock_run, tmp_path):
        from quodeq.cli import _cleanup_worktree
        _cleanup_worktree(tmp_path, tmp_path / "wt")
        mock_run.assert_called_once()

    @patch("quodeq.cli.subprocess.run", side_effect=OSError("fail"))
    def test_cleanup_worktree_error_silenced(self, mock_run, tmp_path):
        from quodeq.cli import _cleanup_worktree
        _cleanup_worktree(tmp_path, tmp_path / "wt")  # should not raise


# ---------------------------------------------------------------------------
# _resolve_evaluation_inputs tests
# ---------------------------------------------------------------------------

class TestResolveEvaluationInputs:
    @patch("quodeq.cli._resolve_repo", return_value=None)
    def test_returns_none_on_repo_failure(self, mock_repo):
        from quodeq.cli import _resolve_evaluation_inputs
        args = argparse.Namespace()
        assert _resolve_evaluation_inputs(args) is None

    @patch("quodeq.cli.default_paths")
    @patch("quodeq.cli._resolve_repo")
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

    @patch("quodeq.cli._build_manifest", return_value=None)
    @patch("quodeq.cli._resolve_language", return_value="python")
    @patch("quodeq.cli.default_paths")
    @patch("quodeq.cli._resolve_repo")
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

    @patch("quodeq.cli._build_manifest", return_value=None)
    @patch("quodeq.analysis.runner.load_universal_dimensions", return_value={"dims": []})
    @patch("quodeq.cli._resolve_language", return_value="python")
    @patch("quodeq.cli.default_paths")
    @patch("quodeq.cli._resolve_repo")
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

    @patch("quodeq.cli._build_manifest", return_value=None)
    @patch("quodeq.analysis.runner.load_universal_dimensions", return_value={"dims": []})
    @patch("quodeq.cli._resolve_language", return_value="python")
    @patch("quodeq.cli.default_paths")
    @patch("quodeq.cli._resolve_repo")
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

    @patch("quodeq.cli._build_manifest", return_value=None)
    @patch("quodeq.analysis.runner.load_universal_dimensions", return_value={})
    @patch("quodeq.cli._resolve_language", return_value="python")
    @patch("quodeq.cli.default_paths")
    @patch("quodeq.cli._resolve_repo")
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

    @patch("quodeq.cli._build_manifest", return_value=None)
    @patch("quodeq.analysis.runner.load_universal_dimensions", side_effect=ValueError("bad dims"))
    @patch("quodeq.cli._resolve_language", return_value="python")
    @patch("quodeq.cli.default_paths")
    @patch("quodeq.cli._resolve_repo")
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
