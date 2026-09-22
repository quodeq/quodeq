"""The config-layer getters that own the analysis/llm_bridge/context env reads.

Every getter takes an explicit mapping. Each case asserts both directions:
an injected value is used, and an injected ``{}`` means "no variables set"
even when the process environment has the variable exported.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.config import analysis_env, context_env, llm_bridge_env, process_env

# (getter, variable, raw value, expected parse, expected default)
_SCALAR_CASES = [
    (analysis_env.max_api_file_size, "QUODEQ_MAX_API_FILE_SIZE", "42", 42, 15000),
    (analysis_env.max_api_prompt_chars, "QUODEQ_MAX_API_PROMPT_CHARS", "150", 150, 30000),
    (analysis_env.max_standards_chars, "QUODEQ_MAX_STANDARDS_CHARS", "99", 99, 50000),
    (analysis_env.mcp_max_batch, "QUODEQ_MCP_MAX_BATCH", "7", 7, 1000),
    (analysis_env.agent_failure_streak_limit, "QUODEQ_AGENT_FAILURE_STREAK", "2", 2, 5),
    (analysis_env.ai_tools, "QUODEQ_AI_TOOLS", "Read", "Read", "Glob,Grep,Read"),
    (analysis_env.base_ai_args, "QUODEQ_AI_BASE_ARGS", "--json", "--json",
     "--print --output-format stream-json --verbose"),
    (llm_bridge_env.ollama_base_url, "OLLAMA_BASE_URL", "http://o:1", "http://o:1",
     "http://localhost:11434"),
    (llm_bridge_env.llamacpp_base_url, "LLAMACPP_BASE_URL", "http://l:2", "http://l:2",
     "http://localhost:8080"),
    (llm_bridge_env.omlx_base_url, "OMLX_BASE_URL", "http://m:3", "http://m:3",
     "http://localhost:8000"),
    (llm_bridge_env.omlx_api_key, "OMLX_API_KEY", "sk-x", "sk-x", ""),
]


@pytest.mark.parametrize("getter,var,raw,parsed,default", _SCALAR_CASES,
                         ids=[c[1] for c in _SCALAR_CASES])
def test_scalar_getter_honours_injected_env(getter, var, raw, parsed, default, monkeypatch):
    monkeypatch.setenv(var, raw)
    assert getter(env={var: raw}) == parsed
    assert getter(env={}) == default


@pytest.mark.parametrize("var", [
    "QUODEQ_MAX_API_FILE_SIZE", "QUODEQ_MAX_API_PROMPT_CHARS",
    "QUODEQ_MAX_STANDARDS_CHARS", "QUODEQ_MCP_MAX_BATCH",
    "QUODEQ_AGENT_FAILURE_STREAK",
])
def test_malformed_int_falls_back_to_the_default(var):
    getter = {
        "QUODEQ_MAX_API_FILE_SIZE": analysis_env.max_api_file_size,
        "QUODEQ_MAX_API_PROMPT_CHARS": analysis_env.max_api_prompt_chars,
        "QUODEQ_MAX_STANDARDS_CHARS": analysis_env.max_standards_chars,
        "QUODEQ_MCP_MAX_BATCH": analysis_env.mcp_max_batch,
        "QUODEQ_AGENT_FAILURE_STREAK": analysis_env.agent_failure_streak_limit,
    }[var]
    assert getter(env={var: "not-a-number"}) == getter(env={})


def test_mcp_max_batch_rejects_non_positive_values():
    assert analysis_env.mcp_max_batch(env={"QUODEQ_MCP_MAX_BATCH": "0"}) == 1000
    assert analysis_env.mcp_max_batch(env={"QUODEQ_MCP_MAX_BATCH": "-3"}) == 1000


def test_agent_failure_streak_zero_disables_the_backstop():
    assert analysis_env.agent_failure_streak_limit(
        env={"QUODEQ_AGENT_FAILURE_STREAK": "0"}) == 0


def test_non_scout_providers_honours_injected_env(monkeypatch):
    monkeypatch.setenv("QUODEQ_NON_SCOUT_PROVIDERS", "claude")
    assert analysis_env.non_scout_providers(
        env={"QUODEQ_NON_SCOUT_PROVIDERS": " codex , claude "}) == ("codex", "claude")
    assert analysis_env.non_scout_providers(env={}) == ("codex", "gemini")


def test_subagent_model_override_prefers_the_service_variable(monkeypatch):
    monkeypatch.setenv("SUBAGENT_MODEL", "from-process")
    assert analysis_env.subagent_model_override(
        env={"SUBAGENT_MODEL": "a", "QUODEQ_SUBAGENT_MODEL": "b"}) == "a"
    assert analysis_env.subagent_model_override(
        env={"QUODEQ_SUBAGENT_MODEL": "b"}) == "b"
    assert analysis_env.subagent_model_override(env={}) is None


def test_provider_explicitly_configured_honours_injected_env(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    assert analysis_env.provider_explicitly_configured(env={"AI_CMD": "claude"})
    assert analysis_env.provider_explicitly_configured(env={"AI_PROVIDER": "ollama"})
    assert not analysis_env.provider_explicitly_configured(env={})


def test_api_key_honours_injected_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-process")
    assert llm_bridge_env.api_key("OPENROUTER_API_KEY",
                                  {"OPENROUTER_API_KEY": "sk-1"}) == "sk-1"
    assert llm_bridge_env.api_key("OPENROUTER_API_KEY", {}) == ""
    assert llm_bridge_env.api_key("", {"OPENROUTER_API_KEY": "sk-1"}) == ""


def test_local_api_markers_distinguishes_unset_from_empty(monkeypatch):
    monkeypatch.setenv("QUODEQ_LOCAL_API_MARKERS", "from-process")
    assert llm_bridge_env.local_api_markers(
        env={"QUODEQ_LOCAL_API_MARKERS": "a, b"}) == frozenset({"a", "b"})
    # Explicitly empty means exactly no markers, not "fall back to defaults".
    assert llm_bridge_env.local_api_markers(
        env={"QUODEQ_LOCAL_API_MARKERS": ""}) == frozenset()
    assert llm_bridge_env.local_api_markers(env={}) == llm_bridge_env.LOCAL_API_MARKERS_DEFAULT


def test_cache_root_override_honours_injected_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", "/from/process")
    assert context_env.cache_root_override(env={"QUODEQ_CACHE_ROOT": str(tmp_path)}) == tmp_path
    assert context_env.cache_root_override(env={"QUODEQ_CACHE_ROOT": "  "}) is None
    assert context_env.cache_root_override(env={}) is None


def test_online_cache_disabled_honours_injected_env(monkeypatch):
    monkeypatch.setenv("QUODEQ_DISABLE_ONLINE_CACHE", "1")
    for truthy in ("1", "true", "yes", " yes "):
        assert context_env.online_cache_disabled(
            env={"QUODEQ_DISABLE_ONLINE_CACHE": truthy})
    assert not context_env.online_cache_disabled(env={"QUODEQ_DISABLE_ONLINE_CACHE": "0"})
    assert not context_env.online_cache_disabled(env={})


def test_git_child_env_adds_the_lfs_skip_without_mutating_the_input(monkeypatch):
    monkeypatch.setenv("FROM_PROCESS", "1")
    injected = {"PATH": "/bin"}
    child = context_env.git_child_env(injected)
    assert child == {"PATH": "/bin", "GIT_LFS_SKIP_SMUDGE": "1"}
    assert injected == {"PATH": "/bin"}
    assert context_env.git_child_env({}) == {"GIT_LFS_SKIP_SMUDGE": "1"}


def test_process_environment_returns_the_injected_mapping(monkeypatch):
    monkeypatch.setenv("FROM_PROCESS", "1")
    assert process_env.process_environment({"A": "1"}) == {"A": "1"}
    assert process_env.process_environment({}) == {}
    assert process_env.process_environment().get("FROM_PROCESS") == "1"


def test_process_environment_copy_is_detached(monkeypatch):
    monkeypatch.setenv("FROM_PROCESS", "1")
    copied = process_env.process_environment_copy({"A": "1"})
    copied["B"] = "2"
    assert process_env.process_environment_copy({"A": "1"}) == {"A": "1"}
    assert process_env.process_environment_copy({}) == {}
    assert process_env.process_environment_copy()["FROM_PROCESS"] == "1"
