"""Tests for subprocess.py — provider dispatch, env building, source gathering, standards loading."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis.subprocess import (
    _get_provider_type,
    _load_standards_text,
    _render_standards_grouped,
    _resolve_provider_config,
    _run_api_analysis_bridge,
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
# _render_standards_grouped
# ---------------------------------------------------------------------------

class TestRenderStandardsGrouped:
    def test_returns_empty_for_no_principles(self):
        assert _render_standards_grouped({}) == ""
        assert _render_standards_grouped({"principles": []}) == ""

    def test_renders_json_array(self):
        data = {
            "principles": [
                {
                    "name": "Input Validation",
                    "requirements": [
                        {"id": "S-INP-1", "text": "Validate all inputs"},
                        {"id": "S-INP-2", "text": "Sanitize SQL"},
                    ],
                }
            ]
        }
        result = _render_standards_grouped(data)
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["principle"] == "Input Validation"
        assert len(parsed[0]["requirements"]) == 2
        assert parsed[0]["requirements"][0]["id"] == "S-INP-1"

    def test_handles_missing_name(self):
        data = {"principles": [{"requirements": [{"id": "X-1", "text": "rule"}]}]}
        result = _render_standards_grouped(data)
        parsed = json.loads(result)
        assert parsed[0]["principle"] == "Unknown"

    def test_resolves_default_params_when_no_overrides(self):
        """With no override file, placeholders must be replaced by defaults — no raw templates in output."""
        data = {
            "principles": [{
                "name": "Analyzability",
                "requirements": [{
                    "id": "M-ANA-2",
                    "text": "Functions MUST NOT exceed {max_lines} lines",
                    "params": {"max_lines": {"label": "Max function lines", "type": "int",
                                            "default": 50, "min": 10, "max": 500}},
                }],
            }],
        }
        result = _render_standards_grouped(data, overrides=None)
        parsed = json.loads(result)
        rule = parsed[0]["requirements"][0]["rule"]
        assert "{max_lines}" not in rule, f"raw placeholder still present: {rule!r}"
        assert "50" in rule

    def test_resolves_overridden_value(self):
        """With an override, the tuned value appears in the emitted text."""
        data = {
            "principles": [{
                "name": "Analyzability",
                "requirements": [{
                    "id": "M-ANA-2",
                    "text": "Functions MUST NOT exceed {max_lines} lines",
                    "params": {"max_lines": {"label": "Max function lines", "type": "int",
                                            "default": 50, "min": 10, "max": 500}},
                }],
            }],
        }
        result = _render_standards_grouped(data, overrides={"M-ANA-2": {"max_lines": 80}})
        parsed = json.loads(result)
        rule = parsed[0]["requirements"][0]["rule"]
        assert "80" in rule
        assert "{max_lines}" not in rule


# ---------------------------------------------------------------------------
# _load_standards_text (override threading)
# ---------------------------------------------------------------------------

class TestLoadStandardsTextOverrides:
    _DIM = {
        "principles": [{
            "name": "Analyzability",
            "requirements": [{
                "id": "M-ANA-2",
                "text": "Functions MUST NOT exceed {max_lines} lines",
                "params": {"max_lines": {"label": "Max function lines", "type": "int",
                                         "default": 50, "min": 10, "max": 500}},
            }],
        }],
    }

    def test_no_override_file_uses_default(self, tmp_path):
        """No placeholder braces in output when analyzed repo has no override file."""
        (tmp_path / "compiled").mkdir()
        (tmp_path / "compiled" / "maintainability.json").write_text(json.dumps(self._DIM))
        result = _load_standards_text(tmp_path / "compiled", "maintainability", overrides=None)
        assert "{max_lines}" not in result
        assert "50" in result

    def test_override_value_appears_in_text(self, tmp_path):
        """When an override is supplied, the overridden value appears in the emitted text."""
        (tmp_path / "compiled").mkdir()
        (tmp_path / "compiled" / "maintainability.json").write_text(json.dumps(self._DIM))
        result = _load_standards_text(
            tmp_path / "compiled", "maintainability",
            overrides={"M-ANA-2": {"max_lines": 75}},
        )
        assert "75" in result
        assert "{max_lines}" not in result


# ---------------------------------------------------------------------------
# _load_standards_text
# ---------------------------------------------------------------------------

class TestLoadStandardsText:
    def test_returns_empty_when_no_dir(self):
        assert _load_standards_text(None, "security") == ""

    def test_returns_empty_when_no_dimension(self, tmp_path):
        assert _load_standards_text(tmp_path, None) == ""

    def test_loads_from_json(self, tmp_path):
        data = {
            "principles": [
                {"name": "Auth", "requirements": [{"id": "A-1", "text": "Use tokens"}]}
            ]
        }
        (tmp_path / "security.json").write_text(json.dumps(data))
        result = _load_standards_text(tmp_path, "security")
        assert "Auth" in result
        assert "A-1" in result

    def test_falls_back_to_md(self, tmp_path):
        md_content = "# Security Standards\n- Validate inputs"
        (tmp_path / "security.md").write_text(md_content)
        result = _load_standards_text(tmp_path, "security")
        assert "Security Standards" in result

    def test_truncates_long_json_standards(self, tmp_path):
        data = {
            "principles": [
                {"name": f"Principle{i}", "requirements": [{"id": f"P-{i}", "text": "x" * 5000}]}
                for i in range(20)
            ]
        }
        (tmp_path / "security.json").write_text(json.dumps(data))
        result = _load_standards_text(tmp_path, "security")
        assert "[... standards truncated for context limits ...]" in result

    def test_truncates_long_md_standards(self, tmp_path):
        (tmp_path / "security.md").write_text("x" * 60_000)
        result = _load_standards_text(tmp_path, "security")
        assert "[... standards truncated for context limits ...]" in result

    def test_returns_empty_on_invalid_json(self, tmp_path):
        (tmp_path / "security.json").write_text("not valid json{{{")
        result = _load_standards_text(tmp_path, "security")
        # Falls back to md, which doesn't exist
        assert result == ""

    def test_returns_empty_when_files_missing(self, tmp_path):
        assert _load_standards_text(tmp_path, "nonexistent") == ""


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
# _run_api_analysis_bridge
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("openai"),
    reason="requires the openai SDK",
)
class TestRunApiAnalysisBridge:
    def test_raises_when_no_model(self, tmp_path):
        stream = tmp_path / "stream.json"
        cfg = AnalysisConfig(ai_cmd="ollama")
        provider = {"ollama": {"type": "api", "api_base": "http://localhost:11434/v1"}}

        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider), \
             pytest.raises(Exception, match="No model configured"):
            _run_api_analysis_bridge(tmp_path, "test", stream, cfg)

    def test_raises_when_no_api_base(self, tmp_path):
        stream = tmp_path / "stream.json"
        cfg = AnalysisConfig(ai_cmd="ollama", ai_model="llama3.1")
        provider = {"ollama": {"type": "api", "model": "llama3.1"}}

        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider), \
             pytest.raises(Exception, match="No API base URL configured"):
            _run_api_analysis_bridge(tmp_path, "test", stream, cfg)

    def test_empty_queue_writes_complete_marker_and_preserves_shared_jsonl(self, tmp_path):
        """Empty queue: write the per-agent stream 'complete' marker, but
        leave the SHARED `{dim}_evidence.jsonl` alone — other pool agents
        append findings to it via MCP and would lose them otherwise.
        """
        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        # Pre-populate the shared JSONL with findings from other agents
        jsonl.write_text('{"t":"violation","p":"X","file":"a.py","line":1}\n')
        queue_path = tmp_path / "queue.json"
        queue_path.write_text(json.dumps({"version": 1, "pending": [], "taken": [], "max_files_per_agent": 10}))

        cfg = AnalysisConfig(
            ai_cmd="ollama", ai_model="llama3.1",
            jsonl_file=jsonl, queue_path=queue_path,
        )
        provider = {"ollama": {"type": "api", "model": "llama3.1", "api_base": "http://localhost:11434/v1"}}

        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider):
            _run_api_analysis_bridge(tmp_path, "test", stream, cfg)

        assert "complete" in stream.read_text()
        assert jsonl.read_text() == '{"t":"violation","p":"X","file":"a.py","line":1}\n'

    def test_calls_run_api_analysis(self, tmp_path):
        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        (tmp_path / "main.py").write_text("x = 1")

        cfg = AnalysisConfig(ai_cmd="ollama", ai_model="llama3.1", jsonl_file=jsonl)
        provider = {"ollama": {"type": "api", "model": "llama3.1", "api_base": "http://localhost:11434/v1"}}

        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider), \
             patch("quodeq.analysis.api_prompt_assembly.assemble_api_prompt", return_value="prompt"), \
             patch("quodeq.analysis._api_runner.run_api_analysis") as mock_api:
            _run_api_analysis_bridge(tmp_path, "test", stream, cfg)
            mock_api.assert_called_once()
            assert stream.read_text().strip() != ""


# ---------------------------------------------------------------------------
# run_analysis dispatch
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _resolve_provider_config
# ---------------------------------------------------------------------------

class TestResolveProviderConfig:
    def test_reads_api_key_from_env(self, monkeypatch):
        provider = {"myprovider": {"type": "api", "model": "m", "api_base": "http://x", "api_key_env": "MY_KEY"}}
        monkeypatch.setenv("MY_KEY", "secret")
        cfg = AnalysisConfig(ai_cmd="myprovider", ai_model="m")
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider):
            _, _, key = _resolve_provider_config(cfg)
        assert key == "secret"

    def test_required_api_key_missing_raises(self, monkeypatch):
        provider = {"openrouter": {
            "type": "api", "model": "m", "api_base": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API_KEY", "api_key_required": True,
        }}
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = AnalysisConfig(ai_cmd="openrouter", ai_model="m")
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider):
            with pytest.raises(Exception, match="OPENROUTER_API_KEY"):
                _resolve_provider_config(cfg)

    def test_omlx_falls_back_to_read_omlx_api_key(self):
        provider = {"omlx": {"type": "api", "model": "m", "api_base": "http://localhost:8000/v1"}}
        cfg = AnalysisConfig(ai_cmd="omlx", ai_model="m")
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider), \
             patch("quodeq.llm_bridge._omlx._read_omlx_api_key", return_value="omlx-key"):
            _, _, key = _resolve_provider_config(cfg)
        assert key == "omlx-key"

    def test_omlx_empty_key_when_not_configured(self):
        provider = {"omlx": {"type": "api", "model": "m", "api_base": "http://localhost:8000/v1"}}
        cfg = AnalysisConfig(ai_cmd="omlx", ai_model="m")
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider), \
             patch("quodeq.llm_bridge._omlx._read_omlx_api_key", return_value=""):
            _, _, key = _resolve_provider_config(cfg)
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
                _, _, key = _resolve_provider_config(cfg)
            assert key == "registry-key"
        finally:
            _CREDENTIAL_LOADERS.pop("testprovider", None)

    def test_unknown_provider_not_in_registry_returns_empty_key(self):
        """Fix C: an unknown provider not in _CREDENTIAL_LOADERS falls through
        to an empty key (existing behavior preserved)."""
        provider = {"newprovider": {"type": "api", "model": "m", "api_base": "http://np/v1"}}
        cfg = AnalysisConfig(ai_cmd="newprovider", ai_model="m")
        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider):
            _, _, key = _resolve_provider_config(cfg)
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


