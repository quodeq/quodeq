"""Tests for MCP server registration and unregistration in _command.py."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch


from quodeq.analysis._command import (
    register_cli_mcp,
    _unregister_cli_mcp,
    DEFAULT_CLI_MCP_REGISTRY,
)
from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis.run_types import RunConfig


# ---------------------------------------------------------------------------
# register_cli_mcp / _unregister_cli_mcp
# ---------------------------------------------------------------------------

class TestRegisterCliMcp:
    def setup_method(self):
        # Clear the process-default registry between tests
        DEFAULT_CLI_MCP_REGISTRY.clear()

    def test_register_success(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {"type": "cli"}}):
            mock_run.return_value = MagicMock(returncode=0)
            name = register_cli_mcp("mycli", config)
        assert name == "quodeq-findings"

    def test_register_cached_on_second_call(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {"type": "cli"}}):
            mock_run.return_value = MagicMock(returncode=0)
            register_cli_mcp("mycli", config)
            register_cli_mcp("mycli", config)
        # Only called for unregister + register on first call, second call is cached
        # unregister is run(check=False), register is run(check=True)
        assert mock_run.call_count == 2  # 1 unregister + 1 register

    def test_register_returns_none_on_failure(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {"type": "cli"}}):
            mock_run.side_effect = [MagicMock(), subprocess.CalledProcessError(1, "mycli")]
            name = register_cli_mcp("mycli", config)
        assert name is None

    def test_register_returns_none_on_timeout(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {"type": "cli"}}):
            mock_run.side_effect = [MagicMock(), subprocess.TimeoutExpired("mycli", 10)]
            name = register_cli_mcp("mycli", config)
        assert name is None

    def test_register_returns_none_on_file_not_found(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {"type": "cli"}}):
            mock_run.side_effect = [MagicMock(), FileNotFoundError("mycli")]
            name = register_cli_mcp("mycli", config)
        assert name is None

    def test_no_separator_when_configured(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        provider = {"gemini": {"mcp_add_separator": False, "type": "cli"}}
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value=provider):
            mock_run.return_value = MagicMock(returncode=0)
            register_cli_mcp("gemini", config)
        register_call = mock_run.call_args_list[-1]
        cmd_args = register_call.args[0]
        assert "--" not in cmd_args


class TestUnregisterCliMcp:
    def test_unregister_runs_command(self):
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {"type": "cli"}}):
            mock_run.return_value = MagicMock()
            _unregister_cli_mcp("mycli", "quodeq-findings")
            mock_run.assert_called_once()
            cmd = mock_run.call_args.args[0]
            assert cmd == ["mycli", "mcp", "remove", "quodeq-findings"]

    def test_unregister_handles_timeout(self):
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {"type": "cli"}}):
            mock_run.side_effect = subprocess.TimeoutExpired("mycli", 10)
            # Should not raise
            _unregister_cli_mcp("mycli", "quodeq-findings")

    def test_unregister_handles_file_not_found(self):
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {"type": "cli"}}):
            mock_run.side_effect = FileNotFoundError("mycli")
            _unregister_cli_mcp("mycli", "quodeq-findings")


class TestRunScopedCliMcpRegistry:
    """The registry is a ``RunConfig`` field (``mcp_registry``), so every
    pool worker thread of one run shares one instance -- see
    ``subprocess._run_cli_analysis``."""

    def test_two_analysis_configs_on_one_run_share_the_registry(self, tmp_path):
        run_config = RunConfig(src=tmp_path, language="python")
        cfg_a = AnalysisConfig(jsonl_file=tmp_path / "a.jsonl", run_config=run_config)
        cfg_b = AnalysisConfig(jsonl_file=tmp_path / "b.jsonl", run_config=run_config)
        assert cfg_a.run_config.mcp_registry is cfg_b.run_config.mcp_registry

    def test_two_run_configs_have_isolated_registries(self, tmp_path):
        a = RunConfig(src=tmp_path, language="python")
        b = RunConfig(src=tmp_path, language="python")
        assert a.mcp_registry is not b.mcp_registry

    def test_registering_same_cmd_twice_through_one_run_registry_runs_the_remove_then_add_once(
        self, tmp_path,
    ):
        """Second call through the SAME run-scoped registry is a cache hit:
        exactly one unregister (check=False) + one register (check=True),
        never doubled."""
        config = AnalysisConfig(jsonl_file=tmp_path / "findings.jsonl")
        registry = RunConfig(src=tmp_path, language="python").mcp_registry
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {"type": "cli"}}):
            mock_run.return_value = MagicMock(returncode=0)
            first = registry.ensure_registered("mycli", config)
            second = registry.ensure_registered("mycli", config)

        assert first == second == "quodeq-findings"
        assert mock_run.call_count == 2  # 1 unregister + 1 register, not 4
