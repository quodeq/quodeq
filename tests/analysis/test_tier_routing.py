"""Tests for model tier routing through the analysis pipeline."""
from __future__ import annotations
from unittest.mock import MagicMock, patch

from quodeq.analysis.run_types import RunConfig, AnalysisOptions, AnalysisContext
from quodeq.analysis._dimension_steps import run_dimension_analysis
from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis.subagents._pool_launcher import default_subagent_model


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
        from quodeq.cli import build_run_config
        args = self._make_args()
        inputs = self._make_inputs(tmp_path)
        env = {"AI_MODEL": "qwen3.5:9b"}
        config = build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env=env)
        assert config.options.ai_model == "qwen3.5:9b"

    def test_ai_model_none_when_not_set(self, tmp_path):
        from quodeq.cli import build_run_config
        args = self._make_args()
        inputs = self._make_inputs(tmp_path)
        env = {}
        config = build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env=env)
        assert config.options.ai_model is None

    def test_subagent_model_used_as_fallback(self, tmp_path):
        from quodeq.cli import build_run_config
        args = self._make_args()
        inputs = self._make_inputs(tmp_path)
        env = {"SUBAGENT_MODEL": "sonnet"}
        config = build_run_config(args, inputs=inputs, evidence_dir=tmp_path, env=env)
        assert config.options.ai_model == "sonnet"


class TestDimensionAnalysisModel:
    """run_dimension_analysis should pass ai_model to AnalysisConfig."""

    def test_passes_ai_model_to_analysis_config(self, tmp_path):
        config = RunConfig(
            src=tmp_path,
            language="python",
            options=AnalysisOptions(ai_model="qwen3.5:9b"),
        )
        ctx = AnalysisContext(
            dimensions_data={},
            date_str="2026-04-03",
            template="",
            subagent_template="",
            total=1,
        )

        with patch("quodeq.analysis._dimension_steps.run_analysis") as mock_run:
            mock_run.return_value = None
            run_dimension_analysis(config, "security", "test prompt", 0, ctx)

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
        ctx = AnalysisContext(
            dimensions_data={},
            date_str="2026-04-03",
            template="",
            subagent_template="",
            total=1,
        )

        with patch("quodeq.analysis._dimension_steps.run_analysis") as mock_run:
            mock_run.return_value = None
            run_dimension_analysis(config, "security", "test prompt", 0, ctx)

            call_kwargs = mock_run.call_args
            analysis_config = call_kwargs.kwargs.get("config")
            if analysis_config is None:
                for arg in call_kwargs.args:
                    if isinstance(arg, AnalysisConfig):
                        analysis_config = arg
                        break

            assert analysis_config is not None
            assert analysis_config.ai_model is None


class TestSubagentModelEnvVar:
    """Subagent model env vars should be standardized."""

    def test_pool_launcher_reads_subagent_model(self):
        env = {"SUBAGENT_MODEL": "sonnet"}
        assert default_subagent_model(env=env) == "sonnet"

    def test_pool_launcher_falls_back_to_quodeq_prefix(self):
        env = {"QUODEQ_SUBAGENT_MODEL": "haiku"}
        assert default_subagent_model(env=env) == "haiku"

    def test_pool_launcher_prefers_subagent_model(self):
        env = {"SUBAGENT_MODEL": "sonnet", "QUODEQ_SUBAGENT_MODEL": "haiku"}
        assert default_subagent_model(env=env) == "sonnet"

    def test_pool_launcher_returns_none_when_unset(self):
        assert default_subagent_model(env={}) is None


class TestCliRunSettingsReachTheDimensionConfig:
    """The CLI resolves the command settings once per run (from the process
    environment here, no injected env) and the single-agent dimension step
    copies them onto the AnalysisConfig it spawns with."""

    @staticmethod
    def _dimension_config(tmp_path, run_config) -> AnalysisConfig:
        ctx = AnalysisContext(
            dimensions_data={}, date_str="2026-04-03", template="", subagent_template="", total=1,
        )
        with patch("quodeq.analysis._dimension_steps.run_analysis") as mock_run:
            run_dimension_analysis(run_config, "security", "test prompt", 0, ctx)
        return mock_run.call_args.kwargs["config"]

    def test_ai_cmd_binary_override_and_cache_root(self, tmp_path, monkeypatch):
        from quodeq.cli import build_run_config

        monkeypatch.setenv("AI_CMD", "codex")
        monkeypatch.setenv("AI_CMD_PATH", "/opt/bin/codex-wrapper")
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "root"))
        args = TestBuildRunConfigAiModel._make_args()
        run_config = build_run_config(
            args, inputs=TestBuildRunConfigAiModel._make_inputs(tmp_path), evidence_dir=tmp_path,
        )
        # Read once per run: a later change to the process env is not seen.
        monkeypatch.setenv("AI_CMD", "gemini")
        monkeypatch.setenv("AI_CMD_PATH", "/elsewhere")
        ac = self._dimension_config(tmp_path, run_config)
        assert ac.ai_cmd == "codex"
        assert ac.ai_cmd_path == "/opt/bin/codex-wrapper"
        assert ac.cache_root == tmp_path / "root" / "results"
