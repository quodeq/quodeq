"""Extended tests for _command.py: tools, base args, env building and _build_ai_cmd edge cases."""
from __future__ import annotations

from unittest.mock import patch

from quodeq.analysis._command import (
    _build_ai_cmd,
    _build_analysis_env,
    _build_base_args,
    _get_ai_tools,
    _get_base_ai_args,
    _mcp_server_name,
)
from quodeq.analysis._config import AnalysisConfig


# ---------------------------------------------------------------------------
# _get_ai_tools / _get_base_ai_args
# ---------------------------------------------------------------------------

class TestGetAiTools:
    def test_default_tools(self):
        assert _get_ai_tools({}) == "Glob,Grep,Read"

    def test_custom_tools_from_env(self):
        assert _get_ai_tools({"QUODEQ_AI_TOOLS": "Bash,Read"}) == "Bash,Read"


class TestGetBaseAiArgs:
    def test_default_args(self):
        args = _get_base_ai_args({})
        assert "--print" in args
        assert "--output-format" in args
        assert "stream-json" in args
        assert "--verbose" in args

    def test_custom_args_from_env(self):
        args = _get_base_ai_args({"QUODEQ_AI_BASE_ARGS": "--json --quiet"})
        assert args == ("--json", "--quiet")


class TestEnvInjectionIsolation:
    """An explicit ``env={}`` must not leak the host environment."""

    def test_get_ai_tools_ignores_host_env(self):
        with patch.dict("os.environ", {"QUODEQ_AI_TOOLS": "Bash,Write"}):
            assert _get_ai_tools({}) == "Glob,Grep,Read"

    def test_get_base_ai_args_ignores_host_env(self):
        with patch.dict("os.environ", {"QUODEQ_AI_BASE_ARGS": "--leaked"}):
            assert "--leaked" not in _get_base_ai_args({})

    def test_build_base_args_threads_injected_env(self):
        with patch.dict("os.environ", {"QUODEQ_AI_TOOLS": "Bash,Write",
                                       "QUODEQ_AI_BASE_ARGS": "--leaked"}):
            args = _build_base_args("claude", {}, env={})
        assert "--leaked" not in args
        assert "Bash,Write" not in args
        assert "Glob,Grep,Read" in args

    def test_build_base_args_reads_injected_env(self):
        with patch.dict("os.environ", {}, clear=True):
            args = _build_base_args(
                "claude", {}, env={"QUODEQ_AI_TOOLS": "Read", "QUODEQ_AI_BASE_ARGS": "--json"},
            )
        assert args == ["claude", "--json", "--tools", "Read"]


# ---------------------------------------------------------------------------
# _build_analysis_env
# ---------------------------------------------------------------------------

class TestBuildAnalysisEnv:
    def test_removes_sensitive_keys(self):
        env = {"PATH": "/usr/bin", "QUODEQ_API_KEY": "secret", "DATABASE_URL": "db://"}
        with patch("quodeq.analysis._command._get_provider_configs", return_value={}):
            result = _build_analysis_env("claude", env)
        assert "PATH" in result
        assert "QUODEQ_API_KEY" not in result
        assert "DATABASE_URL" not in result

    def test_sets_missing_env_vars(self):
        env = {"PATH": "/usr/bin"}
        provider = {"claude": {"env_set_if_missing": {"ANTHROPIC_API_KEY": "fallback"}}}
        with patch("quodeq.analysis._command._get_provider_configs", return_value=provider):
            result = _build_analysis_env("claude", env)
        assert result["ANTHROPIC_API_KEY"] == "fallback"

    def test_does_not_overwrite_existing_env_vars(self):
        env = {"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "real-key"}
        provider = {"claude": {"env_set_if_missing": {"ANTHROPIC_API_KEY": "fallback"}}}
        with patch("quodeq.analysis._command._get_provider_configs", return_value=provider):
            result = _build_analysis_env("claude", env)
        assert result["ANTHROPIC_API_KEY"] == "real-key"

    def test_removes_provider_specific_keys(self):
        env = {"PATH": "/usr/bin", "OPENAI_API_KEY": "sk-xxx"}
        provider = {"codex": {"env_remove": ["OPENAI_API_KEY"]}}
        with patch("quodeq.analysis._command._get_provider_configs", return_value=provider):
            result = _build_analysis_env("codex", env)
        assert "OPENAI_API_KEY" not in result

    def test_handles_none_ai_cmd(self):
        env = {"PATH": "/usr/bin"}
        with patch("quodeq.analysis._command._get_provider_configs", return_value={}):
            result = _build_analysis_env(None, env)
        assert "PATH" in result


# ---------------------------------------------------------------------------
# _build_ai_cmd — additional edge cases
# ---------------------------------------------------------------------------

_MINIMAL_PROVIDER = {
    "minimal": {
        "type": "cli",
        "cmd_subcommand": "",
        "base_args": "",
        "prompt_style": "flag",
        "prompt_flag": "-p",
        "supports_tools": True,
        "supports_budget": True,
        "supports_turns": True,
    }
}


class TestBuildAiCmdEdgeCases:
    def _patch(self, cfg):
        return patch("quodeq.analysis._command._get_provider_configs", return_value=cfg)

    def test_no_model_skips_model_flag(self):
        config = AnalysisConfig(ai_cmd="minimal", ai_model=None)
        with self._patch(_MINIMAL_PROVIDER), \
             patch("quodeq.analysis._command.get_ai_model", return_value=None):
            args, _ = _build_ai_cmd("test", config)
        assert "--model" not in args

    def test_budget_included_when_set(self):
        config = AnalysisConfig(ai_cmd="minimal", ai_model="m", analysis_budget="3.50")
        with self._patch(_MINIMAL_PROVIDER):
            args, _ = _build_ai_cmd("test", config)
        assert "--max-budget-usd" in args
        idx = args.index("--max-budget-usd")
        assert args[idx + 1] == "3.50"

    def test_turns_included_when_set(self):
        config = AnalysisConfig(ai_cmd="minimal", ai_model="m", max_turns=25)
        with self._patch(_MINIMAL_PROVIDER):
            args, _ = _build_ai_cmd("test", config)
        assert "--max-turns" in args
        idx = args.index("--max-turns")
        assert args[idx + 1] == "25"

    def test_no_budget_when_none(self):
        config = AnalysisConfig(ai_cmd="minimal", ai_model="m", analysis_budget=None)
        with self._patch(_MINIMAL_PROVIDER):
            args, _ = _build_ai_cmd("test", config)
        assert "--max-budget-usd" not in args

    def test_queue_path_adds_get_next_files_to_allowed(self, tmp_path):
        jsonl = tmp_path / "f.jsonl"
        jsonl.touch()
        queue = tmp_path / "queue.json"
        config = AnalysisConfig(
            ai_cmd="minimal", ai_model="m",
            jsonl_file=jsonl, compiled_dir=tmp_path, dimension="security",
            queue_path=queue,
        )
        with self._patch(_MINIMAL_PROVIDER):
            args, _ = _build_ai_cmd("test", config)
        # Should include both tools in allowedTools
        at_idx = args.index("--allowedTools")
        allowed = args[at_idx + 1]
        assert "report_finding" in allowed
        assert "get_next_files" in allowed

    def test_positional_prompt_style(self):
        cfg = {"pos": {"prompt_style": "positional", "supports_tools": False, "supports_budget": False, "supports_turns": False}}
        config = AnalysisConfig(ai_cmd="pos", ai_model="m")
        with self._patch(cfg):
            args, _ = _build_ai_cmd("my prompt", config)
        assert args[-1] == "my prompt"

    def test_custom_prompt_flag(self):
        cfg = {"custom": {"prompt_style": "flag", "prompt_flag": "--prompt", "supports_tools": False, "supports_budget": False, "supports_turns": False}}
        config = AnalysisConfig(ai_cmd="custom", ai_model="m")
        with self._patch(cfg):
            args, _ = _build_ai_cmd("my prompt", config)
        assert "--prompt" in args
        idx = args.index("--prompt")
        assert args[idx + 1] == "my prompt"


# ---------------------------------------------------------------------------
# _mcp_server_name
# ---------------------------------------------------------------------------

class TestMcpServerName:
    def test_returns_prefix(self):
        name = _mcp_server_name()
        assert name == "quodeq-findings"
