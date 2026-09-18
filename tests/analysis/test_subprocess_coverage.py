"""Tests for subprocess.py: provider dispatch, CLI analysis and credential resolution."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis.subprocess import (
    _get_provider_type,
    _resolve_provider_config,
    _run_cli_analysis,
    count_files_from_stream,
    run_analysis,
)


# ---------------------------------------------------------------------------
# _get_provider_type
# ---------------------------------------------------------------------------

class TestGetProviderType:
    def test_returns_cli_for_unknown_provider(self):
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value={}):
            assert _get_provider_type("unknown") == "cli"

    def test_returns_api_when_configured(self):
        cfg = {"ollama": {"type": "api", "model": "llama3.1"}}
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=cfg):
            assert _get_provider_type("ollama") == "api"

    def test_returns_cli_when_configured(self):
        cfg = {"claude": {"type": "cli"}}
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=cfg):
            assert _get_provider_type("claude") == "cli"

    def test_defaults_to_cli_when_type_missing(self):
        cfg = {"some-tool": {"model": "x"}}
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=cfg):
            assert _get_provider_type("some-tool") == "cli"


# ---------------------------------------------------------------------------
# count_files_from_stream
# ---------------------------------------------------------------------------

class TestCountFilesFromStream:
    def test_delegates_to_count_files_in_stream(self, tmp_path):
        stream = tmp_path / "stream.json"
        with patch("quodeq.analysis.subprocess.count_files_in_stream", return_value={"a.py", "b.py"}):
            assert count_files_from_stream(stream) == 2


# ---------------------------------------------------------------------------
# _run_cli_analysis
# ---------------------------------------------------------------------------

class TestRunCliAnalysis:
    def test_calls_spawn_and_monitor(self, tmp_path):
        stream = tmp_path / "stream.json"
        cfg = AnalysisConfig(ai_cmd="claude", ai_model="sonnet-4")
        mock_process = MagicMock()
        mock_process.returncode = 0

        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value={"claude": {"type": "cli"}}), \
             patch("quodeq.analysis.subprocess._build_ai_cmd", return_value=(["claude", "-p", "test"], None)), \
             patch("quodeq.analysis.subprocess._build_analysis_env", return_value={}), \
             patch("quodeq.analysis.subprocess._spawn_and_monitor", return_value=(mock_process, False)) as mock_spawn, \
             patch("quodeq.analysis.subprocess._check_process_result"):
            _run_cli_analysis(tmp_path, "test prompt", stream, cfg)
            mock_spawn.assert_called_once()

    def test_cleans_up_mcp_config(self, tmp_path):
        """MCP config file should be deleted after the run."""
        stream = tmp_path / "stream.json"
        mcp_path = tmp_path / "mcp_config.json"
        mcp_path.write_text("{}")

        cfg = AnalysisConfig(ai_cmd="claude", ai_model="sonnet-4", jsonl_file=tmp_path / "f.jsonl")
        mock_process = MagicMock()
        mock_process.returncode = 0

        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value={"claude": {"type": "cli"}}), \
             patch("quodeq.analysis.subprocess._build_ai_cmd", return_value=(["claude", "-p", "test"], mcp_path)), \
             patch("quodeq.analysis.subprocess._build_analysis_env", return_value={}), \
             patch("quodeq.analysis.subprocess._spawn_and_monitor", return_value=(mock_process, False)), \
             patch("quodeq.analysis.subprocess._check_process_result"):
            _run_cli_analysis(tmp_path, "test", stream, cfg)
        assert not mcp_path.exists()

    def test_skips_check_when_timed_out(self, tmp_path):
        stream = tmp_path / "stream.json"
        cfg = AnalysisConfig(ai_cmd="claude")
        mock_process = MagicMock()

        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value={}), \
             patch("quodeq.analysis.subprocess._build_ai_cmd", return_value=(["claude", "-p", "test"], None)), \
             patch("quodeq.analysis.subprocess._build_analysis_env", return_value={}), \
             patch("quodeq.analysis.subprocess._spawn_and_monitor", return_value=(mock_process, True)), \
             patch("quodeq.analysis.subprocess._check_process_result") as mock_check:
            _run_cli_analysis(tmp_path, "test", stream, cfg)
            mock_check.assert_not_called()

    def test_registers_cli_mcp_for_cli_register_style(self, tmp_path):
        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        cfg = AnalysisConfig(ai_cmd="codex", jsonl_file=jsonl)
        mock_process = MagicMock()
        mock_process.returncode = 0

        provider_cfg = {"codex": {"type": "cli", "mcp_style": "cli-register"}}
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider_cfg), \
             patch("quodeq.analysis.subprocess._register_cli_mcp", return_value="quodeq-findings") as mock_reg, \
             patch("quodeq.analysis.subprocess._build_ai_cmd", return_value=(["codex", "exec", "test"], None)), \
             patch("quodeq.analysis.subprocess._build_analysis_env", return_value={}), \
             patch("quodeq.analysis.subprocess._spawn_and_monitor", return_value=(mock_process, False)), \
             patch("quodeq.analysis.subprocess._check_process_result"):
            _run_cli_analysis(tmp_path, "test", stream, cfg)
            mock_reg.assert_called_once()


# ---------------------------------------------------------------------------
# _resolve_provider_config
# ---------------------------------------------------------------------------

class TestResolveProviderConfig:
    def test_reads_api_key_from_injected_env(self, monkeypatch):
        provider = {"myprovider": {"type": "api", "model": "m", "api_base": "http://x", "api_key_env": "MY_KEY"}}
        # The injected mapping is the only credential source: a conflicting
        # process env var must be ignored.
        monkeypatch.setenv("MY_KEY", "process-env-value")
        cfg = AnalysisConfig(ai_cmd="myprovider", ai_model="m")
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider):
            _, _, key = _resolve_provider_config(cfg, {"MY_KEY": "secret"})
        assert key == "secret"

    def test_required_api_key_missing_raises(self):
        provider = {"openrouter": {
            "type": "api", "model": "m", "api_base": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API_KEY", "api_key_required": True,
        }}
        cfg = AnalysisConfig(ai_cmd="openrouter", ai_model="m")
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider):
            with pytest.raises(Exception, match="OPENROUTER_API_KEY"):
                _resolve_provider_config(cfg, {})

    def test_omlx_falls_back_to_read_omlx_api_key(self):
        provider = {"omlx": {"type": "api", "model": "m", "api_base": "http://localhost:8000/v1"}}
        cfg = AnalysisConfig(ai_cmd="omlx", ai_model="m")
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider), \
             patch("quodeq.llm_bridge._omlx._read_omlx_api_key", return_value="omlx-key"):
            _, _, key = _resolve_provider_config(cfg, {})
        assert key == "omlx-key"

    def test_omlx_empty_key_when_not_configured(self):
        provider = {"omlx": {"type": "api", "model": "m", "api_base": "http://localhost:8000/v1"}}
        cfg = AnalysisConfig(ai_cmd="omlx", ai_model="m")
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider), \
             patch("quodeq.llm_bridge._omlx._read_omlx_api_key", return_value=""):
            _, _, key = _resolve_provider_config(cfg, {})
        assert key == ""

    def test_credential_registry_dispatches_registered_provider(self, monkeypatch):
        """Fix C (#2291): a provider registered in _CREDENTIAL_LOADERS is
        dispatched through the registry rather than via a hard-coded branch."""
        from quodeq.analysis.subprocess import _CREDENTIAL_LOADERS
        # Patch a fake provider into the registry for the duration of the test.
        _CREDENTIAL_LOADERS["testprovider"] = lambda: "registry-key"
        try:
            provider = {"testprovider": {"type": "api", "model": "m", "api_base": "http://tp/v1"}}
            cfg = AnalysisConfig(ai_cmd="testprovider", ai_model="m")
            with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider):
                _, _, key = _resolve_provider_config(cfg, {})
            assert key == "registry-key"
        finally:
            _CREDENTIAL_LOADERS.pop("testprovider", None)

    def test_unknown_provider_not_in_registry_returns_empty_key(self):
        """Fix C: an unknown provider not in _CREDENTIAL_LOADERS falls through
        to an empty key (existing behavior preserved)."""
        provider = {"newprovider": {"type": "api", "model": "m", "api_base": "http://np/v1"}}
        cfg = AnalysisConfig(ai_cmd="newprovider", ai_model="m")
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider):
            _, _, key = _resolve_provider_config(cfg, {})
        assert key == ""


# ---------------------------------------------------------------------------
# run_analysis dispatch
# ---------------------------------------------------------------------------

class TestRunAnalysisDispatch:
    def test_defaults_to_empty_config(self, tmp_path):
        stream = tmp_path / "stream.json"
        with patch("quodeq.analysis.subprocess._get_provider_type", return_value="cli"), \
             patch("quodeq.analysis.subprocess._run_cli_analysis") as mock_cli:
            run_analysis(tmp_path, "test", stream)
            mock_cli.assert_called_once()
            # config arg should be an AnalysisConfig
            _, _, _, passed_cfg = mock_cli.call_args.args
            assert isinstance(passed_cfg, AnalysisConfig)
