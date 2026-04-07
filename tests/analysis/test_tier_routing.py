"""Tests for model tier routing through the analysis pipeline."""
from __future__ import annotations
from unittest.mock import MagicMock
from pathlib import Path
import pytest

from quodeq.analysis._types import AnalysisOptions


class TestAnalysisOptionsAiModel:
    def test_default_is_none(self):
        opts = AnalysisOptions()
        assert opts.ai_model is None

    def test_accepts_model_string(self):
        opts = AnalysisOptions(ai_model="qwen3.5:9b")
        assert opts.ai_model == "qwen3.5:9b"


class TestBuildRunConfigAiModel:
    @staticmethod
    def _make_args(**overrides):
        args = MagicMock()
        args.dimensions = None
        args.max_turns = None
        args.max_duration = None
        args.n_subagents = 1
        args.no_verify = False
        args.no_consolidated = False
        args.pool_budget = None
        args.incremental = False
        for k, v in overrides.items():
            setattr(args, k, v)
        return args

    @staticmethod
    def _make_inputs(tmp_path):
        inputs = MagicMock()
        inputs.src = tmp_path
        inputs.language = "python"
        inputs.manifest = None
        inputs.dims_data = None
        return inputs

    def test_reads_ai_model_from_env(self, tmp_path):
        from quodeq.cli import _build_run_config
        args = self._make_args()
        inputs = self._make_inputs(tmp_path)
        env = {"AI_MODEL": "qwen3.5:9b"}
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env=env)
        assert config.options.ai_model == "qwen3.5:9b"

    def test_ai_model_none_when_not_set(self, tmp_path):
        from quodeq.cli import _build_run_config
        args = self._make_args()
        inputs = self._make_inputs(tmp_path)
        env = {}
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env=env)
        assert config.options.ai_model is None

    def test_subagent_model_used_as_fallback(self, tmp_path):
        from quodeq.cli import _build_run_config
        args = self._make_args()
        inputs = self._make_inputs(tmp_path)
        env = {"SUBAGENT_MODEL": "sonnet"}
        config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env=env)
        assert config.options.ai_model == "sonnet"


from unittest.mock import patch
from quodeq.analysis._types import RunConfig, AnalysisOptions, _AnalysisContext
from quodeq.analysis._dimension_steps import _run_dimension_analysis
from quodeq.analysis._config import AnalysisConfig


class TestDimensionAnalysisModel:
    """_run_dimension_analysis should pass ai_model to AnalysisConfig."""

    def test_passes_ai_model_to_analysis_config(self, tmp_path):
        config = RunConfig(
            src=tmp_path,
            language="python",
            options=AnalysisOptions(ai_model="qwen3.5:9b"),
        )
        ctx = _AnalysisContext(
            dimensions_data={},
            date_str="2026-04-03",
            template="",
            subagent_template="",
            total=1,
        )

        with patch("quodeq.analysis._dimension_steps.run_analysis") as mock_run:
            mock_run.return_value = None
            _run_dimension_analysis(config, "security", "test prompt", 0, ctx)

            # run_analysis is called as: run_analysis(work_dir=..., prompt=..., stream_file=..., config=AnalysisConfig(...))
            call_kwargs = mock_run.call_args
            # Find the AnalysisConfig in the call
            analysis_config = call_kwargs.kwargs.get("config")
            if analysis_config is None:
                # Might be positional
                for arg in call_kwargs.args:
                    if isinstance(arg, AnalysisConfig):
                        analysis_config = arg
                        break

            assert analysis_config is not None, "AnalysisConfig not found in run_analysis call"
            assert analysis_config.ai_model == "qwen3.5:9b"

    def test_ai_model_none_when_not_set(self, tmp_path):
        config = RunConfig(
            src=tmp_path,
            language="python",
            options=AnalysisOptions(),
        )
        ctx = _AnalysisContext(
            dimensions_data={},
            date_str="2026-04-03",
            template="",
            subagent_template="",
            total=1,
        )

        with patch("quodeq.analysis._dimension_steps.run_analysis") as mock_run:
            mock_run.return_value = None
            _run_dimension_analysis(config, "security", "test prompt", 0, ctx)

            call_kwargs = mock_run.call_args
            analysis_config = call_kwargs.kwargs.get("config")
            if analysis_config is None:
                for arg in call_kwargs.args:
                    if isinstance(arg, AnalysisConfig):
                        analysis_config = arg
                        break

            assert analysis_config is not None
            assert analysis_config.ai_model is None


from quodeq.analysis.subagents._pool_launcher import _default_subagent_model
from quodeq.analysis.subagents._verify_pool import _fast_model


class TestSubagentModelEnvVar:
    """Subagent model env vars should be standardized."""

    def test_pool_launcher_reads_subagent_model(self):
        env = {"SUBAGENT_MODEL": "sonnet"}
        assert _default_subagent_model(env=env) == "sonnet"

    def test_pool_launcher_falls_back_to_quodeq_prefix(self):
        env = {"QUODEQ_SUBAGENT_MODEL": "haiku"}
        assert _default_subagent_model(env=env) == "haiku"

    def test_pool_launcher_prefers_subagent_model(self):
        env = {"SUBAGENT_MODEL": "sonnet", "QUODEQ_SUBAGENT_MODEL": "haiku"}
        assert _default_subagent_model(env=env) == "sonnet"

    def test_pool_launcher_returns_none_when_unset(self):
        assert _default_subagent_model(env={}) is None

    def test_fast_model_reads_quodeq_fast_model(self):
        env = {"QUODEQ_FAST_MODEL": "qwen3.5:4b"}
        assert _fast_model(env=env) == "qwen3.5:4b"

    def test_fast_model_default_is_haiku(self):
        assert _fast_model(env={}) == "haiku"
