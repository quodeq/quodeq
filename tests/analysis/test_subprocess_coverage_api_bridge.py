"""Tests for subprocess.py: the _run_api_analysis_bridge provider path."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis.subprocess import _run_api_analysis_bridge


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
            _run_api_analysis_bridge(tmp_path, stream, cfg, {})

    def test_raises_when_no_api_base(self, tmp_path):
        stream = tmp_path / "stream.json"
        cfg = AnalysisConfig(ai_cmd="ollama", ai_model="llama3.1")
        provider = {"ollama": {"type": "api", "model": "llama3.1"}}

        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider), \
             pytest.raises(Exception, match="No API base URL configured"):
            _run_api_analysis_bridge(tmp_path, stream, cfg, {})

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
            _run_api_analysis_bridge(tmp_path, stream, cfg, {})

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
            _run_api_analysis_bridge(tmp_path, stream, cfg, {})
            mock_api.assert_called_once()
            assert stream.read_text().strip() != ""

    def test_passes_subagent_count_from_run_config(self, tmp_path):
        """The pool's RunConfig carrier feeds max_subagents into the API
        runner config so the read timeout can scale with queue depth."""
        from types import SimpleNamespace

        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        (tmp_path / "main.py").write_text("x = 1")

        run_config = SimpleNamespace(options=SimpleNamespace(max_subagents=3))
        cfg = AnalysisConfig(
            ai_cmd="ollama", ai_model="llama3.1",
            jsonl_file=jsonl, run_config=run_config,
        )
        provider = {"ollama": {"type": "api", "model": "llama3.1", "api_base": "http://localhost:11434/v1"}}

        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider), \
             patch("quodeq.analysis.api_prompt_assembly.assemble_api_prompt", return_value="prompt"), \
             patch("quodeq.analysis._api_runner.run_api_analysis") as mock_api:
            _run_api_analysis_bridge(tmp_path, stream, cfg, {})

        assert mock_api.call_args.kwargs["config"].n_subagents == 3

    def test_defaults_subagent_count_without_run_config(self, tmp_path):
        """Legacy callers pass no RunConfig carrier: timeout stays unscaled."""
        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        (tmp_path / "main.py").write_text("x = 1")

        cfg = AnalysisConfig(ai_cmd="ollama", ai_model="llama3.1", jsonl_file=jsonl)
        provider = {"ollama": {"type": "api", "model": "llama3.1", "api_base": "http://localhost:11434/v1"}}

        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider), \
             patch("quodeq.analysis.api_prompt_assembly.assemble_api_prompt", return_value="prompt"), \
             patch("quodeq.analysis._api_runner.run_api_analysis") as mock_api:
            _run_api_analysis_bridge(tmp_path, stream, cfg, {})

        assert mock_api.call_args.kwargs["config"].n_subagents == 1

    def test_trust_model_reaches_assemble_api_prompt(self, tmp_path):
        """C2: ``_dispatch_one_batch`` in ``_api_batch.py`` passes
        ``trust_model=ctx.trust_model`` in its ``ProjectBrief``, fed from
        ``resolve_trust_model(work_dir)``
        in the same module's ``build_api_batch_context``. That is one of three
        live wiring points for the declared trust model.
        Nothing failed when a reviewer set all three to None at once and the
        full suite stayed green -- this closes that gap by asserting the
        resolved model, from a real declared profile, actually reaches
        assemble_api_prompt's kwargs.

        Patched at ``quodeq.analysis._api_batch.assemble_api_prompt``
        (the name _api_batch.py imported into its OWN namespace via
        ``from ... import assemble_api_prompt``), not at
        ``quodeq.analysis.api_prompt_assembly.assemble_api_prompt`` -- the
        latter only rebinds the origin module's attribute and would silently
        fail to intercept the call _api_batch.py already bound at import
        time.
        """
        stream = tmp_path / "stream.json"
        jsonl = tmp_path / "evidence.jsonl"
        (tmp_path / "main.py").write_text("x = 1")
        profile_dir = tmp_path / ".quodeq"
        profile_dir.mkdir()
        (profile_dir / "project-profile.json").write_text(json.dumps({
            "version": 1, "multiTenant": False, "networkExposure": "loopback",
        }))

        cfg = AnalysisConfig(ai_cmd="ollama", ai_model="llama3.1", jsonl_file=jsonl)
        provider = {"ollama": {"type": "api", "model": "llama3.1", "api_base": "http://localhost:11434/v1"}}

        with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=provider), \
             patch("quodeq.analysis._api_batch.assemble_api_prompt", return_value="prompt") as mock_assemble, \
             patch("quodeq.analysis._api_runner.run_api_analysis"):
            _run_api_analysis_bridge(tmp_path, stream, cfg, {})

        mock_assemble.assert_called_once()
        trust_model = mock_assemble.call_args.kwargs["project"].trust_model
        assert trust_model is not None
        assert trust_model.multi_tenant is False
        assert trust_model.network_exposure == "loopback"
