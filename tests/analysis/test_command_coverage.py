"""Extended tests for _command.py — env building, MCP registration, edge cases."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis._command import (
    _build_ai_cmd,
    _build_analysis_env,
    _build_mcp_server_args,
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
# _build_mcp_server_args
# ---------------------------------------------------------------------------

class TestBuildMcpServerArgs:
    def test_basic_args(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        args = _build_mcp_server_args(config)
        assert str(jsonl.resolve()) in args

    def test_includes_compiled_dir_and_dimension(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        compiled = tmp_path / "compiled"
        config = AnalysisConfig(jsonl_file=jsonl, compiled_dir=compiled, dimension="security")
        args = _build_mcp_server_args(config)
        assert "--compiled-dir" in args
        assert "--dimension" in args
        assert "security" in args

    def test_includes_queue(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        queue = tmp_path / "queue.json"
        config = AnalysisConfig(jsonl_file=jsonl, queue_path=queue)
        args = _build_mcp_server_args(config)
        assert "--queue" in args

    def test_includes_agent_id(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl, agent_id="agent-1")
        args = _build_mcp_server_args(config)
        assert "--agent-id" in args
        assert "agent-1" in args

    def test_skip_agent_id(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl, agent_id="agent-1")
        args = _build_mcp_server_args(config, skip_agent_id=True)
        assert "--agent-id" not in args

    def test_includes_work_dir(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl, work_dir=tmp_path)
        args = _build_mcp_server_args(config)
        assert "--work-dir" in args

    def test_work_dir_fallback(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        args = _build_mcp_server_args(config, work_dir=tmp_path)
        assert "--work-dir" in args

    def test_includes_cache_root_model_id_language(self, tmp_path):
        """Task 3.5 #6: the args list passed to findings_server.py MUST include
        --cache-root, --model-id, and --language so the subprocess can build a
        cache writer with the same fingerprint inputs as the parent's
        classify_files_via_cache. Without these flags, CLI-path and API-path
        cache keys diverge for the same project state.
        """
        from types import SimpleNamespace

        jsonl = tmp_path / "findings.jsonl"
        # Synthesise a minimal RunConfig-shaped carrier the helper can read.
        run_config = SimpleNamespace(
            language="kotlin",
            options=SimpleNamespace(subagent_model="sonnet", ai_model="opus"),
        )
        config = AnalysisConfig(jsonl_file=jsonl, run_config=run_config)
        args = _build_mcp_server_args(config)

        assert "--cache-root" in args
        assert "--model-id" in args
        assert "--language" in args
        # Values
        model_idx = args.index("--model-id")
        assert args[model_idx + 1] == "sonnet"
        lang_idx = args.index("--language")
        assert args[lang_idx + 1] == "kotlin"
        # Cache root defaults to ~/.quodeq/cache/results. Compare via
        # Path so the assertion is platform-agnostic — on Windows the
        # produced path uses backslashes, so a literal forward-slash
        # tail check would fail there.
        cr_idx = args.index("--cache-root")
        expected_tail = str(Path(".quodeq") / "cache" / "results")
        assert args[cr_idx + 1].endswith(expected_tail)

    def test_cache_flags_fall_back_when_no_run_config(self, tmp_path):
        """Without a RunConfig carrier, --cache-root is still emitted, model_id
        comes from AnalysisConfig.ai_model, and language is empty — matching
        Task 5's contract that language="" means "unset" rather than missing.
        """
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl, ai_model="haiku")
        args = _build_mcp_server_args(config)

        assert "--cache-root" in args
        model_idx = args.index("--model-id")
        assert args[model_idx + 1] == "haiku"
        lang_idx = args.index("--language")
        assert args[lang_idx + 1] == ""

    def test_model_id_falls_back_to_unknown(self, tmp_path):
        """No ai_model and no run_config => model_id is 'unknown' (reference
        from cache.dimension_helpers._model_id_from).
        """
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        args = _build_mcp_server_args(config)

        model_idx = args.index("--model-id")
        assert args[model_idx + 1] == "unknown"


# ---------------------------------------------------------------------------
# _mcp_server_name
# ---------------------------------------------------------------------------

class TestMcpServerName:
    def test_returns_prefix(self):
        config = AnalysisConfig()
        name = _mcp_server_name(config)
        assert name == "quodeq-findings"


