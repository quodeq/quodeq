"""Tests for CLI command dispatch — build_manifest, execute_pipeline, save_manifest, build_run_config, run_evaluate, main()."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


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
    @patch("quodeq._cli_evaluation.run")
    @patch("quodeq._cli_evaluation.write_text")
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
        config.options.skip_scoring = False
        result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
        assert result == 0
        mock_run.assert_called_once_with(config)

    @patch("quodeq._cli_evaluation.run")
    @patch("quodeq._cli_evaluation.write_text", side_effect=OSError("disk full"))
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
        config.options.skip_scoring = False
        result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
        assert result == 1
        assert "Failed to write" in capsys.readouterr().err

    @patch("quodeq._cli_evaluation.run_full")
    def test_full_pipeline_success(self, mock_run_full, tmp_path):
        from quodeq.cli import _execute_pipeline
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=False, mode="numerical")
        mock_run_full.return_value = {"security": 8.5, "reliability": 7.0}
        config = MagicMock()
        config.options.skip_scoring = False
        result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
        assert result == 0

    @patch("quodeq._cli_evaluation.run_full")
    def test_pipeline_analysis_error(self, mock_run_full, tmp_path, capsys):
        # AnalysisError propagates from _execute_pipeline so that the outer
        # RunLifecycleContext can write state=failed.  The caller
        # (_run_pipeline_with_cleanup) is responsible for mapping it to exit 1.
        import pytest
        from quodeq.cli import _execute_pipeline
        from quodeq.analysis.subprocess import AnalysisError
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=False, mode="numerical")
        mock_run_full.side_effect = AnalysisError("AI failed")
        config = MagicMock()
        config.options.skip_scoring = False
        with pytest.raises(AnalysisError, match="AI failed"):
            _execute_pipeline(args, config, evidence_dir, evaluation_dir)


# ---------------------------------------------------------------------------
# _save_manifest tests
# ---------------------------------------------------------------------------

class TestSaveManifest:
    @patch("quodeq._cli_evaluation.write_text")
    def test_saves_when_manifest_exists(self, mock_write, tmp_path):
        from quodeq.cli import _save_manifest
        manifest = MagicMock()
        manifest.to_dict.return_value = {"targets": []}
        _save_manifest(manifest, tmp_path)
        mock_write.assert_called_once()

    def test_none_manifest_no_op(self, tmp_path):
        from quodeq.cli import _save_manifest
        _save_manifest(None, tmp_path)  # should not raise

    @patch("quodeq._cli_evaluation.write_text", side_effect=OSError("fail"))
    def test_os_error_silenced(self, mock_write, tmp_path):
        from quodeq.cli import _save_manifest
        manifest = MagicMock()
        manifest.to_dict.return_value = {}
        _save_manifest(manifest, tmp_path)  # should not raise


# ---------------------------------------------------------------------------
# _build_run_config tests
# ---------------------------------------------------------------------------

class TestBuildRunConfig:
    @patch("quodeq._cli_evaluation.default_paths")
    @patch("quodeq._cli_evaluation.get_ai_model", return_value="claude-3")
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

    @patch("quodeq._cli_evaluation.default_paths")
    @patch("quodeq._cli_evaluation.get_ai_model", return_value=None)
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

    @patch("quodeq._cli_evaluation.default_paths")
    @patch("quodeq._cli_evaluation.get_ai_model", return_value="model-x")
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

    @patch("quodeq._cli_evaluation.default_paths")
    @patch("quodeq._cli_evaluation.get_ai_model", return_value="model-x")
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

    @patch("quodeq._cli_evaluation.default_paths")
    @patch("quodeq._cli_evaluation.get_ai_model", return_value="model-x")
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
    @patch("quodeq._cli_evaluation.check_evaluate_prereqs", side_effect=RuntimeError("no claude"))
    def test_prereqs_failure(self, mock_prereqs, capsys):
        from quodeq.cli import run_evaluate
        args = argparse.Namespace()
        result = run_evaluate(args)
        assert result == 1
        assert "no claude" in capsys.readouterr().err

    @patch("quodeq._cli_evaluation._resolve_evaluation_inputs", return_value=None)
    @patch("quodeq._cli_evaluation.check_evaluate_prereqs")
    def test_resolve_inputs_none(self, mock_prereqs, mock_resolve):
        from quodeq.cli import run_evaluate
        args = argparse.Namespace()
        result = run_evaluate(args)
        assert result == 1

    @patch("quodeq._cli_evaluation._run_pipeline_with_cleanup", return_value=0)
    @patch("quodeq._cli_evaluation._setup_run_dirs")
    @patch("quodeq._cli_evaluation._resolve_evaluation_inputs")
    @patch("quodeq._cli_evaluation.check_evaluate_prereqs")
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


