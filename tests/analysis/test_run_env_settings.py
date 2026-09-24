"""Env overrides still reach the run after moving out of the inner layers.

The API-call knobs are resolved once per dimension by ``run_analysis`` (from
its environment) instead of per model call; the provider id, model, binary
override and cache root are resolved once per run by the CLI, or by
``run_analysis`` for a direct caller. Each case exports the variable in the
process environment and observes it at the far end: the OpenAI client call,
or the spawned argv.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis.subprocess import AnalysisConfig, run_analysis

_OLLAMA = {"ollama": {"type": "api", "model": "m", "api_base": "http://localhost:11434/v1"}}
_CLAUDE = {"claude": {"type": "cli", "base_args": "--claude-entry", "supports_tools": False}}


class _FakeClient:
    """OpenAI-compatible stand-in: records the constructor and create kwargs."""

    def __init__(self, responses: list[str], **kwargs):
        self.kwargs = kwargs
        self.calls: list[dict] = []
        self._responses = responses
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = self._responses[min(len(self.calls), len(self._responses)) - 1]
        msg = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=msg)])


def _run_api(tmp_path: Path, responses: list[str] | None = None) -> list[_FakeClient]:
    """Drive ``run_analysis`` down the API path to the (faked) OpenAI client."""
    pytest.importorskip("openai", reason="requires the openai SDK")
    (tmp_path / "main.py").write_text("x = 1\n")
    built: list[_FakeClient] = []

    def factory(**kwargs):
        built.append(_FakeClient(responses or ['{"findings": []}'], **kwargs))
        return built[-1]

    cfg = AnalysisConfig(ai_cmd="ollama", ai_model="m", jsonl_file=tmp_path / "e.jsonl")
    with patch("quodeq.analysis.subprocess.get_provider_configs", return_value=_OLLAMA), \
         patch("quodeq.analysis._api_batch.assemble_api_prompt", return_value="prompt"), \
         patch("openai.OpenAI", side_effect=factory):
        run_analysis(tmp_path, "unused", tmp_path / "s.stream", cfg)
    return built


class TestApiCallSettingsReachTheClient:
    def test_max_output_tokens(self, tmp_path, monkeypatch):
        monkeypatch.setenv("QUODEQ_MAX_OUTPUT_TOKENS", "4096")
        assert _run_api(tmp_path)[0].calls[0]["max_tokens"] == 4096

    def test_api_read_timeout(self, tmp_path, monkeypatch):
        monkeypatch.setenv("QUODEQ_API_READ_TIMEOUT", "900")
        assert _run_api(tmp_path)[0].kwargs["timeout"].read == 900.0

    def test_context_size(self, tmp_path, monkeypatch):
        monkeypatch.setenv("QUODEQ_CONTEXT_SIZE", "16384")
        assert _run_api(tmp_path)[0].calls[0]["extra_body"]["num_ctx"] == 16384

    def test_disable_finding_repair(self, tmp_path, monkeypatch):
        snippetless = json.dumps({"findings": [{
            "req": "B-2", "t": "violation", "file": "main.py", "line": 1,
            "severity": "minor", "w": "x", "reason": "r",
        }]})
        assert len(_run_api(tmp_path, [snippetless])[0].calls) == 2  # repair re-ask
        monkeypatch.setenv("QUODEQ_DISABLE_FINDING_REPAIR", "1")
        assert len(_run_api(tmp_path, [snippetless])[0].calls) == 1


def _spawned_argv(tmp_path: Path, cfg: AnalysisConfig) -> list[str]:
    """Drive ``run_analysis`` down the CLI path and return the spawned argv."""
    (tmp_path / "s.stream").touch()
    process = MagicMock(returncode=0)
    process.poll.return_value = 0
    process.wait.return_value = 0
    with patch("quodeq.analysis._command._get_provider_configs", return_value=_CLAUDE), \
         patch("quodeq.analysis.subprocess.get_provider_configs", return_value=_CLAUDE), \
         patch("quodeq.analysis._process.subprocess.Popen", return_value=process) as popen:
        try:
            run_analysis(tmp_path, "prompt", tmp_path / "s.stream", cfg)
        except (OSError, RuntimeError, ValueError):
            pass  # only the spawned argv matters here
    return popen.call_args[0][0]


class TestDirectCallerFallbacks:
    """``run_analysis`` fills what a direct caller left unset from its env."""

    def test_ai_cmd_ai_model_and_binary_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AI_CMD", "claude")
        monkeypatch.setenv("AI_MODEL", "sonnet-4")
        monkeypatch.setenv("AI_CMD_PATH", "/opt/bin/claude-api")
        argv = _spawned_argv(tmp_path, AnalysisConfig())
        assert argv[0] == "/opt/bin/claude-api"
        assert "--claude-entry" in argv  # AI_CMD keyed the provider config
        assert argv[argv.index("--model") + 1] == "sonnet-4"

    def test_cache_root(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AI_CMD", "claude")
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "root"))
        with patch("quodeq.analysis._mcp_arg_builders.create_mcp_config") as create:
            _spawned_argv(tmp_path, AnalysisConfig(jsonl_file=tmp_path / "e.jsonl"))
        agent_params = create.call_args[0][3]
        assert agent_params.cache_root == tmp_path / "root" / "results"


def _cli_run_config(tmp_path: Path):
    from quodeq.cli import ResolvedInputs, build_run_config

    args = argparse.Namespace(
        dimensions=None, no_consolidated=False, no_verify=False,
        max_turns=None, max_duration=None, n_subagents=1,
        pool_budget=None, clean_scan=False, legacy_incremental=False,
    )
    inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
    return build_run_config(args, inputs=inputs, evidence_dir=tmp_path)


class TestRunScopedSettings:
    """What the CLI resolves once per run is what every agent spawns with."""

    def test_pool_agents_inherit_the_resolved_command_settings(self, tmp_path):
        from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool

        base = AnalysisConfig(ai_cmd="codex", ai_cmd_path="/opt/bin/codex", cache_root=tmp_path)
        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=tmp_path / "q"),
            options=PoolOptions(n_agents=1, prompt="p", dimension="security"),
            config=base,
        )
        ac, _, _ = pool._build_agent_config(0)
        assert (ac.ai_cmd, ac.ai_cmd_path, ac.cache_root) == ("codex", "/opt/bin/codex", tmp_path)

    def test_dispatch_policy_is_the_runs_snapshot(self, tmp_path, monkeypatch):
        from quodeq.analysis.subagents.source_files import list_source_files

        (tmp_path / "small.py").write_text("x" * 10)
        (tmp_path / "big.py").write_text("x" * 100)
        monkeypatch.setenv("AI_CMD", "ollama")
        monkeypatch.setenv("QUODEQ_MAX_API_FILE_SIZE", "50")
        monkeypatch.setattr(
            "quodeq.analysis.dispatch_policy.get_provider_configs", lambda: _OLLAMA)
        run_config = _cli_run_config(tmp_path)
        run_config.manifest = SimpleNamespace(source_files=["small.py", "big.py"], language_stats={})
        # Read once per run: raising the cap after the run config is built
        # does not re-admit the big file.
        monkeypatch.setenv("QUODEQ_MAX_API_FILE_SIZE", "1000")
        files, _ext, excluded = list_source_files(run_config, "security", prioritize=False)
        assert (files, excluded) == (["small.py"], ["big.py"])
