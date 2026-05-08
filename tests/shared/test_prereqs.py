import subprocess
from unittest.mock import patch

import pytest

from quodeq.shared.prereqs import (
    check_node, check_npm, check_dashboard_prereqs, check_evaluate_prereqs,
    _check_cli_provider, _check_api_provider, _is_provider_explicitly_configured,
)


class TestCheckNode:
    def test_missing_node_raises(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="Node.js"):
                check_node()

    def test_old_node_raises(self):
        result = subprocess.CompletedProcess([], 0, stdout="16.20.0\n")
        with patch("subprocess.run", return_value=result):
            with pytest.raises(RuntimeError, match="18"):
                check_node()

    def test_valid_node_passes(self):
        result = subprocess.CompletedProcess([], 0, stdout="v20.11.0\n")
        with patch("subprocess.run", return_value=result):
            check_node()


class TestCheckNpm:
    def test_missing_npm_raises(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="npm"):
                check_npm()

    def test_old_npm_raises(self):
        result = subprocess.CompletedProcess([], 0, stdout="8.19.0\n")
        with patch("subprocess.run", return_value=result):
            with pytest.raises(RuntimeError, match="9"):
                check_npm()

    def test_valid_npm_passes(self):
        result = subprocess.CompletedProcess([], 0, stdout="10.2.0\n")
        with patch("subprocess.run", return_value=result):
            check_npm()


class TestCheckCliProvider:
    def test_missing_claude_raises(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="configured as your AI provider but was not found"):
                _check_cli_provider("claude")

    def test_missing_provider_includes_settings_hint(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="dashboard Settings"):
                _check_cli_provider("codex")

    def test_valid_claude_passes(self):
        result = subprocess.CompletedProcess([], 0, stdout="1.0.0\n")
        with patch("subprocess.run", return_value=result):
            _check_cli_provider("claude")


class TestCheckApiProvider:
    def test_ollama_not_running_raises(self):
        with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
            with pytest.raises(RuntimeError, match="server is not running"):
                _check_api_provider("ollama")

    def test_llamacpp_not_running_raises(self):
        with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
            with pytest.raises(RuntimeError, match="llama-server is not running"):
                _check_api_provider("llamacpp")

    def test_non_ollama_api_passes(self):
        # Cloud API providers have no connectivity check
        _check_api_provider("openrouter")


class TestIsProviderExplicitlyConfigured:
    def test_no_env_returns_false(self):
        with patch.dict("os.environ", {}, clear=True):
            assert not _is_provider_explicitly_configured()

    def test_ai_provider_set_returns_true(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "ollama"}):
            assert _is_provider_explicitly_configured()

    def test_ai_cmd_set_returns_true(self):
        with patch.dict("os.environ", {"AI_CMD": "claude"}):
            assert _is_provider_explicitly_configured()


class TestCompositeChecks:
    def test_dashboard_prereqs_checks_node_and_npm(self):
        node_result = subprocess.CompletedProcess([], 0, stdout="v20.11.0\n")
        npm_result = subprocess.CompletedProcess([], 0, stdout="10.2.0\n")
        with patch("subprocess.run", side_effect=[node_result, npm_result]):
            check_dashboard_prereqs()

    def test_dashboard_prereqs_reports_both_missing_in_one_error(self):
        """Both node and npm missing — user should see both in a single message."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError) as excinfo:
                check_dashboard_prereqs()
        msg = str(excinfo.value)
        assert "Node.js" in msg
        assert "npm" in msg
        # Ubuntu/Debian hint must include both packages in one apt command
        assert "apt install -y nodejs npm" in msg

    def test_dashboard_prereqs_reports_only_npm_when_only_npm_missing(self):
        """Node OK, npm missing — error should mention npm but not falsely claim Node is missing."""
        node_result = subprocess.CompletedProcess([], 0, stdout="v20.11.0\n")
        with patch("subprocess.run", side_effect=[node_result, FileNotFoundError()]):
            with pytest.raises(RuntimeError) as excinfo:
                check_dashboard_prereqs()
        msg = str(excinfo.value)
        assert "npm" in msg
        assert "Node.js 18+ not found" not in msg  # don't falsely claim node is missing

    def test_evaluate_no_provider_configured_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="No AI provider configured"):
                check_evaluate_prereqs()

    def test_evaluate_with_cli_provider_checks_binary(self):
        result = subprocess.CompletedProcess([], 0, stdout="1.0.0\n")
        with patch.dict("os.environ", {"AI_PROVIDER": "claude"}):
            with patch("subprocess.run", return_value=result):
                with patch(
                    "quodeq.analysis._provider_cache.get_provider_configs",
                    return_value={"claude": {"type": "cli", "cmd": "claude"}},
                ):
                    check_evaluate_prereqs()
