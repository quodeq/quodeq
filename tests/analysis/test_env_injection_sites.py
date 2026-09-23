"""Analysis-layer seams take an explicit env mapping and never read os.environ.

Each case exports the variable in the process environment first, so a test
that passes ``env={}`` and still sees the default proves the read went
through the injected mapping and not through ``os.environ``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.analysis import dispatch_policy
from quodeq.analysis._api_standards_text import api_prompt_char_budget, standards_char_budget
from quodeq.analysis._command import build_analysis_env
from quodeq.analysis._mcp_arg_builders import get_ai_tools, get_base_ai_args
from quodeq.analysis.mcp.handlers import _max_file_batch_size
from quodeq.analysis.prereqs import _check_api_provider, _is_provider_explicitly_configured
from quodeq.analysis.subagents._pool_launcher import (
    default_subagent_model,
    _non_scout_providers,
)
from quodeq.analysis.subagents._pool_scaling import _agent_failure_streak_limit


def test_api_file_size_cap_honours_injected_env(monkeypatch):
    monkeypatch.setenv("QUODEQ_MAX_API_FILE_SIZE", "11")
    assert dispatch_policy.api_file_size_cap(env={"QUODEQ_MAX_API_FILE_SIZE": "42"}) == 42
    assert dispatch_policy.api_file_size_cap(env={}) == 15000


def test_prompt_and_standards_budgets_honour_injected_env(monkeypatch):
    monkeypatch.setenv("QUODEQ_MAX_API_PROMPT_CHARS", "11")
    monkeypatch.setenv("QUODEQ_MAX_STANDARDS_CHARS", "11")
    assert api_prompt_char_budget(env={"QUODEQ_MAX_API_PROMPT_CHARS": "150"}) == 150
    assert api_prompt_char_budget(env={}) == 30000
    assert standards_char_budget(env={"QUODEQ_MAX_STANDARDS_CHARS": "99"}) == 99
    assert standards_char_budget(env={}) == 50000


def test_mcp_batch_ceiling_honours_injected_env(monkeypatch):
    monkeypatch.setenv("QUODEQ_MCP_MAX_BATCH", "11")
    assert _max_file_batch_size(env={"QUODEQ_MCP_MAX_BATCH": "7"}) == 7
    assert _max_file_batch_size(env={}) == 1000


def test_ai_tools_and_base_args_honour_injected_env(monkeypatch):
    monkeypatch.setenv("QUODEQ_AI_TOOLS", "FromProcess")
    monkeypatch.setenv("QUODEQ_AI_BASE_ARGS", "--from-process")
    assert get_ai_tools(env={"QUODEQ_AI_TOOLS": "Read"}) == "Read"
    assert get_ai_tools(env={}) == "Glob,Grep,Read"
    assert get_base_ai_args(env={"QUODEQ_AI_BASE_ARGS": "-a -b"}) == ("-a", "-b")
    assert get_base_ai_args(env={}) == (
        "--print", "--output-format", "stream-json", "--verbose")


def test_non_scout_providers_honours_injected_env(monkeypatch):
    monkeypatch.setenv("QUODEQ_NON_SCOUT_PROVIDERS", "claude")
    assert _non_scout_providers(env={"QUODEQ_NON_SCOUT_PROVIDERS": "codex"}) == ("codex",)
    assert _non_scout_providers(env={}) == ("codex", "gemini")


def test_default_subagent_model_honours_injected_env(monkeypatch):
    monkeypatch.setenv("SUBAGENT_MODEL", "from-process")
    assert default_subagent_model(env={"QUODEQ_SUBAGENT_MODEL": "m"}) == "m"
    assert default_subagent_model(env={}) is None


def test_agent_failure_streak_limit_honours_injected_env(monkeypatch):
    monkeypatch.setenv("QUODEQ_AGENT_FAILURE_STREAK", "11")
    assert _agent_failure_streak_limit(env={"QUODEQ_AGENT_FAILURE_STREAK": "2"}) == 2
    assert _agent_failure_streak_limit(env={}) == 5


def test_provider_explicitly_configured_honours_injected_env(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    assert _is_provider_explicitly_configured(env={"AI_CMD": "claude"})
    assert not _is_provider_explicitly_configured(env={})


def test_cloud_provider_key_check_honours_injected_env(monkeypatch):
    """The missing-key error is driven by the injected mapping, not the process."""
    monkeypatch.setenv("FAKE_API_KEY", "from-process")
    cfg = {"fake": {"type": "api", "api_key_required": True, "api_key_env": "FAKE_API_KEY"}}
    monkeypatch.setattr(
        "quodeq.analysis.prereqs.get_provider_configs", lambda: cfg)

    # Injected key present: no error.
    _check_api_provider("fake", env={"FAKE_API_KEY": "sk-1"})
    # Injected mapping empty: the exported process value must NOT rescue it.
    with pytest.raises(RuntimeError, match="FAKE_API_KEY"):
        _check_api_provider("fake", env={})


def test_omlx_credential_loader_honours_the_injected_env(monkeypatch, tmp_path: Path):
    """The registry loader reads the run's mapping, not the process.

    Before the loaders took an ``env``, ``read_omlx_api_key`` defaulted to
    ``os.environ`` on every call, so an injected ``{}`` still picked up an
    exported OMLX_API_KEY.
    """
    from quodeq.analysis._config import AnalysisConfig
    from quodeq.analysis.subprocess import _resolve_provider_config

    monkeypatch.setenv("OMLX_API_KEY", "from-process")
    # ~/.omlx/settings.json is the loader's other source; point it at an
    # empty dir so the mapping is the only thing that can supply a key.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    provider = {"omlx": {"type": "api", "model": "m", "api_base": "http://localhost:8000/v1"}}
    monkeypatch.setattr(
        "quodeq.analysis.subprocess.get_provider_configs", lambda: provider)
    cfg = AnalysisConfig(ai_cmd="omlx", ai_model="m")

    assert _resolve_provider_config(cfg, {"OMLX_API_KEY": "sk-injected"})[2] == "sk-injected"
    assert _resolve_provider_config(cfg, {})[2] == ""


def test_build_analysis_env_uses_the_injected_mapping(monkeypatch):
    monkeypatch.setenv("FROM_PROCESS", "1")
    built = build_analysis_env(None, {"KEEP": "yes"})
    assert built["KEEP"] == "yes"
    assert "FROM_PROCESS" not in built
    assert build_analysis_env(None, {}) == {}


def test_build_analysis_env_does_not_mutate_the_injected_mapping():
    injected = {"KEEP": "yes"}
    build_analysis_env(None, injected)
    assert injected == {"KEEP": "yes"}


def test_run_analysis_passes_the_injected_env_to_the_api_bridge(
    tmp_path: Path, monkeypatch,
):
    from quodeq.analysis import subprocess as analysis_subprocess

    seen: list[object] = []
    monkeypatch.setattr(analysis_subprocess, "get_provider_type", lambda _cmd: "api")
    monkeypatch.setattr(
        analysis_subprocess, "_run_api_analysis_bridge",
        lambda *args: seen.append(args[-1]))
    monkeypatch.setenv("FROM_PROCESS", "1")

    analysis_subprocess.run_analysis(
        tmp_path, "prompt", tmp_path / "s.jsonl", None, {"ONLY": "this"})
    assert seen == [{"ONLY": "this"}]

    seen.clear()
    analysis_subprocess.run_analysis(tmp_path, "prompt", tmp_path / "s.jsonl", None)
    assert seen[0].get("FROM_PROCESS") == "1"
