"""Tests for CLI run-config building — build_run_config and the --clean-scan / --incremental flags."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest


class TestBuildRunConfig:
    @patch("quodeq.cli_evaluation.default_paths")
    @patch("quodeq.cli_evaluation.get_ai_model", return_value="claude-3")
    def test_basic_config(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import ResolvedInputs, build_run_config
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = True
        mock_paths_obj.evaluators_dir = tmp_path / "evaluators"
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, clean_scan=True, legacy_incremental=False,
        )
        inputs = ResolvedInputs(
            src=tmp_path, language="python", manifest=None, dims_data={}
        )
        config = build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env={})
        assert config.language == "python"
        assert config.options.verify_findings is True

    @pytest.fixture()
    def _fallback_config(self, tmp_path):
        """Build a run config with no explicit ai_model (so it must fall back
        to SUBAGENT_MODEL) and a representative mix of other flags. Each test
        below checks one field of the result."""
        with patch("quodeq.cli_evaluation.default_paths") as mock_paths, \
             patch("quodeq.cli_evaluation.get_ai_model", return_value=None):
            from quodeq.cli import ResolvedInputs, build_run_config
            mock_paths_obj = MagicMock()
            mock_paths_obj.standards_dir.exists.return_value = False
            mock_paths_obj.evaluators_dir = tmp_path / "evaluators"
            mock_paths.return_value = mock_paths_obj
            args = argparse.Namespace(
                dimensions="security,reliability", no_consolidated=False,
                no_verify=True, max_turns=10, max_duration=300,
                n_subagents=3, pool_budget=120, clean_scan=False, legacy_incremental=False,
            )
            inputs = ResolvedInputs(
                src=tmp_path, language="java", manifest=None, dims_data={}
            )
            env = {"SUBAGENT_MODEL": "ollama/llama3"}
            return build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env=env)

    def test_subagent_model_fallback(self, _fallback_config):
        assert _fallback_config.options.ai_model == "ollama/llama3"

    def test_subagent_model_fallback_parses_dimensions(self, _fallback_config):
        assert _fallback_config.options.dimensions == ["security", "reliability"]

    def test_subagent_model_fallback_keeps_max_turns(self, _fallback_config):
        assert _fallback_config.options.max_turns == 10

    def test_subagent_model_fallback_keeps_max_duration(self, _fallback_config):
        assert _fallback_config.options.max_duration == 300

    def test_subagent_model_fallback_keeps_time_limit(self, _fallback_config):
        assert _fallback_config.options.time_limit == 120

    def test_subagent_model_fallback_clean_scan_false_means_incremental(self, _fallback_config):
        assert _fallback_config.options.incremental is True

    def test_subagent_model_fallback_keeps_no_verify(self, _fallback_config):
        assert _fallback_config.options.verify_findings is False

    def test_subagent_model_fallback_standards_dir_absent(self, _fallback_config):
        assert _fallback_config.standards_dir is None

    @patch("quodeq.cli_evaluation.default_paths")
    @patch("quodeq.cli_evaluation.get_ai_model", return_value="model-x")
    def test_single_file_disables_consolidated(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import ResolvedInputs, build_run_config
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, clean_scan=True, legacy_incremental=False,
        )
        inputs = ResolvedInputs(
            src=tmp_path, language="python", manifest=None, dims_data={}, single_file=True,
        )
        config = build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env={})
        assert config.options.consolidated is False

    @patch("quodeq.cli_evaluation.default_paths")
    @patch("quodeq.cli_evaluation.get_ai_model", return_value="model-x")
    def test_env_no_consolidate(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import ResolvedInputs, build_run_config
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, clean_scan=True, legacy_incremental=False,
        )
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        config = build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env={"QUODEQ_NO_CONSOLIDATE": "1"})
        assert config.options.consolidated is False

    @patch("quodeq.cli_evaluation.default_paths")
    @patch("quodeq.cli_evaluation.get_ai_model", return_value="model-x")
    def test_env_overrides_for_turns_and_duration(self, mock_model, mock_paths, tmp_path):
        from quodeq.cli import ResolvedInputs, build_run_config
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, clean_scan=True, legacy_incremental=False,
        )
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        env = {"QUODEQ_MAX_TURNS": "50", "QUODEQ_MAX_DURATION": "900", "QUODEQ_POOL_BUDGET": "300"}
        config = build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env=env)
        assert config.options.max_turns == 50
        assert config.options.max_duration == 900
        # Legacy QUODEQ_POOL_BUDGET still routes into time_limit via the env-var fallback.
        assert config.options.time_limit == 300

    @patch("quodeq.cli_evaluation.default_paths")
    @patch("quodeq.cli_evaluation.get_ai_model", return_value="model-x")
    def test_env_time_limit_zero_is_unlimited(self, mock_model, mock_paths, tmp_path):
        # Contract pin: the dashboard propagates unlimited as
        # QUODEQ_TIME_LIMIT=0. It must resolve to 0 (not None), otherwise
        # the pool substitutes its 600s default and unlimited runs die at
        # 10 minutes.
        from quodeq.cli import ResolvedInputs, build_run_config
        mock_paths_obj = MagicMock()
        mock_paths_obj.standards_dir.exists.return_value = False
        mock_paths_obj.evaluators_dir = tmp_path
        mock_paths.return_value = mock_paths_obj
        args = argparse.Namespace(
            dimensions=None, no_consolidated=False, no_verify=False,
            max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, clean_scan=True, legacy_incremental=False,
        )
        inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
        config = build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env={"QUODEQ_TIME_LIMIT": "0"})
        assert config.options.time_limit == 0
