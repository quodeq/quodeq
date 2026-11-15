"""Tests for MCP server registration and unregistration in _command.py."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch


from quodeq.analysis._command import register_cli_mcp, _unregister_cli_mcp
from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis.run_types import RunConfig
# subprocess.py already imports this for its own run-scoped-registry fallback
# (see _run_cli_analysis); reusing that public re-export here keeps this file
# off the private-imports ratchet instead of importing straight from _command.
from quodeq.analysis.subprocess import DEFAULT_CLI_MCP_REGISTRY


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


class TestReleaseAll:
    """A run removes its CLI-register MCP server when it ends.

    ``gemini mcp add`` writes a persistent registration; without this it
    stayed in the CLI's settings after every scan, pointing at a findings
    server for a run that no longer exists.
    """

    def _register(self, registry, tmp_path, mock_run):
        config = AnalysisConfig(jsonl_file=tmp_path / "findings.jsonl", ai_cmd_path="/opt/gemini")
        mock_run.return_value = MagicMock(returncode=0)
        registry.ensure_registered("gemini", config)

    def test_release_all_removes_what_this_run_registered(self, tmp_path):
        registry = RunConfig(src=tmp_path, language="python").mcp_registry
        with patch("quodeq.analysis._command.subprocess.run") as mock_run, \
             patch("quodeq.analysis._command._get_provider_configs", return_value={"gemini": {"type": "cli"}}):
            self._register(registry, tmp_path, mock_run)
            mock_run.reset_mock()
            registry.release_all()
        assert mock_run.call_args.args[0] == ["/opt/gemini", "mcp", "remove", "quodeq-findings"]
        assert "gemini:quodeq-findings" not in registry

    def test_release_all_is_idempotent_and_noop_when_nothing_registered(self, tmp_path):
        registry = RunConfig(src=tmp_path, language="python").mcp_registry
        with patch("quodeq.analysis._command.subprocess.run") as mock_run:
            registry.release_all()
            registry.release_all()
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Findings server command inside the desktop bundle
# ---------------------------------------------------------------------------

_BUNDLE_FLAG = "--_mcp_findings"


def _frozen(value: bool = True):
    import sys

    return patch.object(sys, "frozen", value, create=True)


def _providers(cfg: dict):
    return patch("quodeq.analysis._command._get_provider_configs", return_value=cfg)


class TestFindingsServerCommandWhenFrozen:
    """The bundle's executable is Quodeq, not Python: every spawn path must
    use the private flag instead of a script path or ``-m``."""

    def setup_method(self):
        DEFAULT_CLI_MCP_REGISTRY.clear()

    def _registered_argv(self, tmp_path, frozen: bool) -> list[str]:
        config = AnalysisConfig(jsonl_file=tmp_path / "findings.jsonl")
        with _frozen(frozen), _providers({"mycli": {"type": "cli"}}), \
             patch("quodeq.analysis._command.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            register_cli_mcp("mycli", config)
        register_cmd = mock_run.call_args_list[-1].args[0]
        return register_cmd[register_cmd.index("--") + 1:]

    def test_cli_register_uses_the_private_flag(self, tmp_path):
        import sys

        argv = self._registered_argv(tmp_path, frozen=True)
        assert argv[:3] == [sys.executable, _BUNDLE_FLAG, str((tmp_path / "findings.jsonl").resolve())]
        assert not any(a.endswith("findings_server.py") for a in argv)

    def test_cli_register_from_source_runs_the_script(self, tmp_path):
        import sys

        argv = self._registered_argv(tmp_path, frozen=False)
        assert argv[0] == sys.executable
        assert argv[1].endswith("findings_server.py")
        assert argv[2] == str((tmp_path / "findings.jsonl").resolve())

    def test_config_file_uses_the_private_flag(self, tmp_path):
        import json
        import sys

        from quodeq.analysis.subprocess import build_ai_cmd

        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(ai_cmd="claude", jsonl_file=jsonl)
        with _frozen(), _providers({"claude": {"type": "cli", "cmd": "claude"}}):
            _, mcp_path = build_ai_cmd("Analyze", config)
        try:
            server = json.loads(mcp_path.read_text())["mcpServers"]["findings"]
        finally:
            mcp_path.unlink(missing_ok=True)
        assert server["command"] == sys.executable
        assert server["args"][:2] == [_BUNDLE_FLAG, str(jsonl.resolve())]

    def test_codex_override_uses_the_private_flag(self, tmp_path):
        import sys
        import tomllib

        from quodeq.analysis.subprocess import build_ai_cmd

        jsonl = tmp_path / "findings.jsonl"
        config = AnalysisConfig(ai_cmd="codex", jsonl_file=jsonl)
        cfg = {"codex": {"type": "cli", "cmd": "codex", "mcp_style": "config-arg"}}
        with _frozen(), _providers(cfg):
            args, _ = build_ai_cmd("Analyze", config)
        override = next(a for a in args if str(a).startswith("mcp_servers.findings="))
        server = tomllib.loads(override)["mcp_servers"]["findings"]
        assert server["command"] == sys.executable
        assert server["args"][:2] == [_BUNDLE_FLAG, str(jsonl.resolve())]
        assert "-m" not in server["args"]
