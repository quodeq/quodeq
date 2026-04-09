"""Tests for shared.ai_cli — AI CLI subprocess runner."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from quodeq.shared.ai_cli import (
    _AI_CLI_FALLBACK_ERROR,
    _DEFAULT_AI_CLI_TIMEOUT,
    _ai_cli_timeout,
    run_ai_cli,
)


class TestAiCliTimeout:
    def test_default_value(self):
        assert _ai_cli_timeout() == _DEFAULT_AI_CLI_TIMEOUT

    def test_override(self):
        assert _ai_cli_timeout(override=60) == 60

    def test_env_variable(self):
        assert _ai_cli_timeout(env={"QUODEQ_AI_CLI_TIMEOUT": "120"}) == 120

    def test_env_invalid_falls_back(self):
        assert _ai_cli_timeout(env={"QUODEQ_AI_CLI_TIMEOUT": "abc"}) == _DEFAULT_AI_CLI_TIMEOUT

    def test_env_missing_uses_default(self):
        assert _ai_cli_timeout(env={}) == _DEFAULT_AI_CLI_TIMEOUT


class TestRunAiCli:
    @patch("quodeq.shared.ai_cli.get_ai_cmd", return_value="fake-ai")
    @patch("quodeq.shared.ai_cli.subprocess.run")
    def test_success(self, mock_run, mock_cmd):
        mock_run.return_value = MagicMock(stdout="AI response here")
        stdout, err = run_ai_cli("test prompt", timeout=10)
        assert stdout == "AI response here"
        assert err is None
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert args[0][0] == ["fake-ai", "--print", "-p", "test prompt"]
        assert args[1]["timeout"] == 10

    @patch("quodeq.shared.ai_cli.get_ai_cmd", return_value="fake-ai")
    @patch("quodeq.shared.ai_cli.subprocess.run", side_effect=FileNotFoundError)
    def test_command_not_found(self, mock_run, mock_cmd):
        stdout, err = run_ai_cli("prompt")
        assert stdout is None
        assert "not found" in err

    @patch("quodeq.shared.ai_cli.get_ai_cmd", return_value="fake-ai")
    @patch("quodeq.shared.ai_cli.subprocess.run")
    def test_called_process_error_with_stderr(self, mock_run, mock_cmd):
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "fake-ai", stderr="API key invalid"
        )
        stdout, err = run_ai_cli("prompt")
        assert stdout is None
        assert err is not None  # sanitized stderr or fallback

    @patch("quodeq.shared.ai_cli.get_ai_cmd", return_value="fake-ai")
    @patch("quodeq.shared.ai_cli.subprocess.run")
    def test_called_process_error_empty_stderr(self, mock_run, mock_cmd):
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "fake-ai", stderr=""
        )
        stdout, err = run_ai_cli("prompt")
        assert stdout is None
        assert err == _AI_CLI_FALLBACK_ERROR

    @patch("quodeq.shared.ai_cli.get_ai_cmd", return_value="fake-ai")
    @patch("quodeq.shared.ai_cli.subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5))
    def test_timeout(self, mock_run, mock_cmd):
        stdout, err = run_ai_cli("prompt", timeout=5)
        assert stdout is None
        assert "timed out" in err
