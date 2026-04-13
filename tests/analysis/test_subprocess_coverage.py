"""Tests for subprocess.py — provider dispatch, env building, source gathering, standards loading."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis.subprocess import (
    _get_provider_type,
    _gather_source_files,
    _load_standards_text,
    _render_standards_grouped,
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
# _gather_source_files
# ---------------------------------------------------------------------------

class TestGatherSourceFiles:
    def test_collects_code_files(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1")
        (tmp_path / "app.js").write_text("const x = 1;")
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        assert "main.py" in names
        assert "app.js" in names

    def test_skips_dotdirs(self, tmp_path):
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text("x = 1")
        (tmp_path / "visible.py").write_text("y = 2")
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        assert "secret.py" not in names
        assert "visible.py" in names

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {};")
        (tmp_path / "app.js").write_text("const x = 1;")
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        assert "index.js" not in names
        assert "app.js" in names

    def test_skips_empty_files(self, tmp_path):
        (tmp_path / "empty.py").write_text("")
        (tmp_path / "real.py").write_text("x = 1")
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        assert "empty.py" not in names
        assert "real.py" in names

    def test_skips_oversized_files(self, tmp_path):
        (tmp_path / "big.py").write_text("x" * 20_000)
        (tmp_path / "small.py").write_text("y = 1")
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        assert "big.py" not in names
        assert "small.py" in names

    def test_prioritizes_code_over_markup(self, tmp_path):
        # Create code files that fill the budget (< 15KB each, > 30KB total)
        for i in range(4):
            (tmp_path / f"mod{i}.py").write_text("x" * 10_000)
        (tmp_path / "style.css").write_text("b" * 10_000)
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        # Code files should be prioritized over markup
        code_count = sum(1 for f in result if f.suffix == ".py")
        markup_count = sum(1 for f in result if f.suffix == ".css")
        assert code_count >= markup_count

    def test_respects_char_budget(self, tmp_path):
        # Create many files that exceed budget
        for i in range(50):
            (tmp_path / f"mod{i}.py").write_text("x" * 1000)
        result = _gather_source_files(tmp_path)
        total = sum(f.stat().st_size for f in result)
        assert total <= 30_000

    def test_includes_markup_files(self, tmp_path):
        (tmp_path / "page.html").write_text("<html></html>")
        (tmp_path / "style.css").write_text("body{}")
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        assert "page.html" in names
        assert "style.css" in names


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
    not __import__("importlib").util.find_spec("instructor"),
    reason="requires quodeq[api] extra",
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

    def test_empty_queue_writes_empty_files(self, tmp_path):
        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        queue_path = tmp_path / "queue.json"
        # Create a queue that returns no files
        queue_path.write_text(json.dumps({"version": 1, "pending": [], "taken": [], "max_files_per_agent": 10}))

        cfg = AnalysisConfig(
            ai_cmd="ollama", ai_model="llama3.1",
            jsonl_file=jsonl, queue_path=queue_path,
        )
        provider = {"ollama": {"type": "api", "model": "llama3.1", "api_base": "http://localhost:11434/v1"}}

        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider):
            _run_api_analysis_bridge(tmp_path, "test", stream, cfg)

        assert jsonl.read_text() == ""
        assert "complete" in stream.read_text()

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


# ---------------------------------------------------------------------------
# _load_skip_dirs
# ---------------------------------------------------------------------------

class TestLoadSkipDirs:
    def test_returns_frozenset(self):
        from quodeq.analysis.subprocess import _SKIP_DIRS
        assert isinstance(_SKIP_DIRS, frozenset)
        # Should at minimum contain common dirs
        assert "node_modules" in _SKIP_DIRS or len(_SKIP_DIRS) > 0
