"""Tests for provider-aware AI CLI command builder."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis._command import _build_ai_cmd
from quodeq.analysis._config import AnalysisConfig


# Read-only test fixtures — no test mutates these dicts, so module-level sharing is safe.
_CLAUDE_CFG = {
    "claude": {
        "type": "cli",
        "cmd": "claude",
        "cmd_subcommand": "",
        "base_args": "--print --output-format stream-json --verbose",
        "prompt_style": "flag",
        "prompt_flag": "-p",
        "supports_mcp": True,
        "supports_tools": True,
        "supports_budget": True,
        "supports_turns": True,
        "mcp_permission_args": ["--permission-mode", "bypassPermissions"],
        "env_set_if_missing": {},
        "env_remove": [],
    }
}

_CODEX_CFG = {
    "codex": {
        "type": "cli",
        "cmd": "codex",
        "cmd_subcommand": "exec",
        "base_args": "--json --dangerously-bypass-approvals-and-sandbox",
        "prompt_style": "positional",
        "mcp_style": "config-arg",
        "supports_tools": False,
        "supports_budget": False,
        "supports_turns": False,
        "mcp_permission_args": [],
        "env_set_if_missing": {},
        "env_remove": [],
    }
}


_GEMINI_CFG = {
    "gemini": {
        "type": "cli",
        "cmd": "gemini",
        "cmd_subcommand": "",
        "base_args": "--output-format stream-json --yolo",
        "prompt_style": "flag",
        "prompt_flag": "-p",
        "mcp_style": "cli-register",
        "mcp_add_separator": False,
        "mcp_permission_args": ["--allowed-mcp-server-names", "quodeq-findings"],
        "supports_tools": False,
        "supports_budget": False,
        "supports_turns": False,
        "env_set_if_missing": {},
        "env_remove": [],
    }
}


def _patch_providers(cfg: dict):
    return patch("quodeq.analysis._command._get_provider_configs", return_value=cfg)


class TestBuildAiCmdClaude:
    """Claude provider command building."""

    def test_uses_print_and_stream_json(self):
        config = AnalysisConfig(ai_cmd="claude", ai_model="sonnet-4")
        with _patch_providers(_CLAUDE_CFG):
            args, _ = _build_ai_cmd("Analyze this", config)
        assert "--print" in args
        assert "--output-format" in args
        idx = args.index("--output-format")
        assert args[idx + 1] == "stream-json"
        assert "--model" in args
        midx = args.index("--model")
        assert args[midx + 1] == "sonnet-4"
        # prompt via -p flag
        assert "-p" in args
        pidx = args.index("-p")
        assert args[pidx + 1] == "Analyze this"

    def test_includes_mcp_config_when_jsonl_set(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        jsonl.touch()
        config = AnalysisConfig(
            ai_cmd="claude", ai_model="sonnet-4",
            jsonl_file=jsonl, compiled_dir=tmp_path, dimension="security",
        )
        with _patch_providers(_CLAUDE_CFG):
            args, mcp_path = _build_ai_cmd("Analyze", config)
        assert mcp_path is not None
        assert "--mcp-config" in args
        assert "--allowedTools" in args
        assert "--permission-mode" in args
        assert "bypassPermissions" in args


class TestBuildAiCmdCodex:
    """Codex provider command building."""

    def test_uses_exec_subcommand_and_json(self):
        config = AnalysisConfig(ai_cmd="codex", ai_model="gpt-5.4")
        with _patch_providers(_CODEX_CFG):
            args, _ = _build_ai_cmd("Analyze this", config)
        # "exec" must appear right after binary
        assert args[0] == "codex"
        assert args[1] == "exec"
        assert "--json" in args
        # positional prompt at the very end
        assert args[-1] == "Analyze this"
        # no MCP
        assert "--mcp-config" not in args

    def test_no_print_flag(self):
        config = AnalysisConfig(ai_cmd="codex", ai_model="gpt-5.4")
        with _patch_providers(_CODEX_CFG):
            args, _ = _build_ai_cmd("Analyze", config)
        assert "--print" not in args
        assert "--output-format" not in args
        assert "-p" not in args

    def test_skips_budget_and_turns(self):
        config = AnalysisConfig(
            ai_cmd="codex", ai_model="gpt-5.4",
            analysis_budget="5.00", max_turns=50,
        )
        with _patch_providers(_CODEX_CFG):
            args, _ = _build_ai_cmd("Analyze", config)
        assert "--max-budget-usd" not in args
        assert "--max-turns" not in args

    def test_includes_model_flag(self):
        config = AnalysisConfig(ai_cmd="codex", ai_model="gpt-5.4")
        with _patch_providers(_CODEX_CFG):
            args, _ = _build_ai_cmd("Analyze", config)
        assert "--model" in args
        idx = args.index("--model")
        assert args[idx + 1] == "gpt-5.4"

    def test_normalizes_numeric_model_shorthand(self):
        config = AnalysisConfig(ai_cmd="codex", ai_model="5.4")
        with _patch_providers(_CODEX_CFG):
            args, _ = _build_ai_cmd("Analyze", config)
        idx = args.index("--model")
        assert args[idx + 1] == "gpt-5.4"

    def test_inlines_codex_mcp_config_arg_with_jsonl(self, tmp_path):
        import sys
        import tomllib

        jsonl = tmp_path / "findings.jsonl"
        jsonl.touch()
        queue = tmp_path / "queue.json"
        config = AnalysisConfig(
            ai_cmd="codex", ai_model="gpt-5.4",
            jsonl_file=jsonl, compiled_dir=tmp_path, dimension="security",
            queue_path=queue, agent_id="agent-0",
        )
        with _patch_providers(_CODEX_CFG):
            args, mcp_path = _build_ai_cmd("Analyze", config)

        assert mcp_path is None
        assert "--mcp-config" not in args
        assert args[-1] == "Analyze"

        mcp_arg = next(a for a in args if str(a).startswith("mcp_servers.findings="))
        assert args[args.index(mcp_arg) - 1] == "-c"
        server = tomllib.loads(mcp_arg)["mcp_servers"]["findings"]
        assert server["command"] == sys.executable
        assert "quodeq.analysis.mcp.findings_server" in server["args"]
        assert str(jsonl.resolve()) in server["args"]
        assert "--queue" in server["args"] and str(queue.resolve()) in server["args"]
        assert "--agent-id" in server["args"] and "agent-0" in server["args"]


class TestBuildAiCmdGemini:
    """Gemini provider command building (cli-register MCP style)."""

    def test_cli_register_emits_permission_args_with_jsonl(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        jsonl.touch()
        config = AnalysisConfig(
            ai_cmd="gemini", ai_model="gemini-2.5-pro",
            jsonl_file=jsonl, compiled_dir=tmp_path, dimension="security",
        )
        with _patch_providers(_GEMINI_CFG):
            args, mcp_path = _build_ai_cmd("Analyze", config)
        # Server registration happens out-of-band (`gemini mcp add`), so no
        # config file or inline config — but the CLI must still be told the
        # registered server is allowed, or every tool call is blocked.
        assert mcp_path is None
        assert "--mcp-config" not in args
        assert "-c" not in args
        idx = args.index("--allowed-mcp-server-names")
        assert args[idx + 1] == "quodeq-findings"

    def test_cli_register_no_mcp_args_without_jsonl(self):
        config = AnalysisConfig(ai_cmd="gemini", ai_model="gemini-2.5-pro")
        with _patch_providers(_GEMINI_CFG):
            args, mcp_path = _build_ai_cmd("Analyze", config)
        assert mcp_path is None
        assert "--allowed-mcp-server-names" not in args

    def test_prompt_via_flag_and_stream_json(self):
        config = AnalysisConfig(ai_cmd="gemini", ai_model="gemini-2.5-pro")
        with _patch_providers(_GEMINI_CFG):
            args, _ = _build_ai_cmd("Analyze this", config)
        assert args[0] == "gemini"
        assert "--yolo" in args
        pidx = args.index("-p")
        assert args[pidx + 1] == "Analyze this"
