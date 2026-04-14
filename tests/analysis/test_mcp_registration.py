"""Tests for MCP server registration and unregistration in _command.py."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis._command import (
    _register_cli_mcp,
    _unregister_cli_mcp,
    _cli_mcp_registered,
)
from quodeq.analysis._config import AnalysisConfig


# ---------------------------------------------------------------------------
# _register_cli_mcp / _unregister_cli_mcp
# ---------------------------------------------------------------------------

class TestRegisterCliMcp:
    def setup_method(self):
        # Clear the global registry between tests
        _cli_mcp_registered.clear()

    def test_register_success(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {}}):
            mock_run.return_value = MagicMock(returncode=0)
            name = _register_cli_mcp("mycli", config)
        assert name == "quodeq-findings"

    def test_register_cached_on_second_call(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {}}):
            mock_run.return_value = MagicMock(returncode=0)
            _register_cli_mcp("mycli", config)
            _register_cli_mcp("mycli", config)
        # Only called for unregister + register on first call, second call is cached
        # unregister is run(check=False), register is run(check=True)
        assert mock_run.call_count == 2  # 1 unregister + 1 register

    def test_register_returns_none_on_failure(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {}}):
            mock_run.side_effect = [MagicMock(), subprocess.CalledProcessError(1, "mycli")]
            name = _register_cli_mcp("mycli", config)
        assert name is None

    def test_register_returns_none_on_timeout(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {}}):
            mock_run.side_effect = [MagicMock(), subprocess.TimeoutExpired("mycli", 10)]
            name = _register_cli_mcp("mycli", config)
        assert name is None

    def test_register_returns_none_on_file_not_found(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"mycli": {}}):
            mock_run.side_effect = [MagicMock(), FileNotFoundError("mycli")]
            name = _register_cli_mcp("mycli", config)
        assert name is None

    def test_no_separator_when_configured(self, tmp_path):
        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(jsonl_file=jsonl)
        provider = {"gemini": {"mcp_add_separator": False}}
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value=provider):
            mock_run.return_value = MagicMock(returncode=0)
            _register_cli_mcp("gemini", config)
        register_call = mock_run.call_args_list[-1]
        cmd_args = register_call.args[0]
        assert "--" not in cmd_args


class TestUnregisterCliMcp:
    def test_unregister_runs_command(self):
        with patch("quodeq.analysis._command.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            _unregister_cli_mcp("mycli", "quodeq-findings")
            mock_run.assert_called_once()
            cmd = mock_run.call_args.args[0]
            assert cmd == ["mycli", "mcp", "remove", "quodeq-findings"]

    def test_unregister_handles_timeout(self):
        with patch("quodeq.analysis._command.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("mycli", 10)
            # Should not raise
            _unregister_cli_mcp("mycli", "quodeq-findings")

    def test_unregister_handles_file_not_found(self):
        with patch("quodeq.analysis._command.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("mycli")
            _unregister_cli_mcp("mycli", "quodeq-findings")
