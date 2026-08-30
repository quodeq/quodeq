"""Tests for llm_bridge provider detection."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from quodeq.llm_bridge._providers import (
    get_provider_configs,
    get_provider_type,
    classify_provider,
    resolve_api_key,
    resolve_api_key_env,
    _local_api_markers,
)


class TestGetProviderConfigs:
    def test_returns_dict(self):
        configs = get_provider_configs()
        assert isinstance(configs, dict)

    def test_contains_known_providers(self):
        configs = get_provider_configs()
        assert "claude" in configs or "ollama" in configs


class TestIsLocalApiNullApiBase:
    def test_null_api_base_does_not_crash(self):
        """A provider config whose api_base is null (operator-edited
        ai_providers.json) must not crash on .lower()."""
        from quodeq.llm_bridge import _providers
        cfgs = {"weird": {"type": "api", "api_base": None}}
        with patch.object(_providers, "get_provider_configs", return_value=cfgs):
            assert _providers._is_local_api("weird") is False


class TestLocalApiMarkers:
    """Unset vs set-but-empty QUODEQ_LOCAL_API_MARKERS must resolve differently:
    this gates whether the assistant's web tools (search_web/fetch_url) ever
    get registered for an 'api'-type provider, so unset must not silently
    behave the same as "no markers"."""

    def test_unset_env_returns_defaults(self):
        result = _local_api_markers(env={})
        assert result == frozenset({"11434", "localhost", "127.0.0.1", "ollama"})

    def test_set_but_empty_env_returns_empty_set(self):
        result = _local_api_markers(env={"QUODEQ_LOCAL_API_MARKERS": ""})
        assert result == frozenset()

    def test_set_env_parses_comma_separated_markers(self):
        result = _local_api_markers(env={"QUODEQ_LOCAL_API_MARKERS": "foo, bar"})
        assert result == frozenset({"foo", "bar"})


class TestGetProviderType:
    def test_cli_provider(self):
        assert get_provider_type("claude") == "cli"

    def test_api_provider(self):
        assert get_provider_type("ollama") == "api"

    def test_unknown_defaults_to_cli(self):
        assert get_provider_type("nonexistent-tool") == "cli"


class TestClassifyProvider:
    def test_ollama_is_local_api(self):
        result = classify_provider("ollama")
        assert result == "local-api"

    def test_claude_is_cli(self):
        result = classify_provider("claude")
        assert result == "cli"

    def test_openrouter_is_cloud_api(self):
        result = classify_provider("openrouter")
        assert result == "cloud-api"


_CFGS = {
    "acme": {"type": "api", "api_base": "https://acme.example/v1", "api_key_env": "ACME_API_KEY"},
    "no-key": {"type": "api", "api_base": "https://no-key.example/v1"},
}


class TestResolveApiKeyEnv:
    def test_resolves_by_provider_id(self):
        from quodeq.llm_bridge import _providers
        with patch.object(_providers, "get_provider_configs", return_value=_CFGS):
            assert resolve_api_key_env("acme") == "ACME_API_KEY"

    def test_falls_back_to_api_base_match_when_no_provider_id(self):
        from quodeq.llm_bridge import _providers
        with patch.object(_providers, "get_provider_configs", return_value=_CFGS):
            assert resolve_api_key_env("", "https://acme.example/v1") == "ACME_API_KEY"

    def test_unknown_provider_and_base_returns_empty(self):
        from quodeq.llm_bridge import _providers
        with patch.object(_providers, "get_provider_configs", return_value=_CFGS):
            assert resolve_api_key_env("nonexistent", "https://nowhere.example") == ""

    def test_provider_without_api_key_env_returns_empty(self):
        from quodeq.llm_bridge import _providers
        with patch.object(_providers, "get_provider_configs", return_value=_CFGS):
            assert resolve_api_key_env("no-key") == ""


class TestResolveApiKey:
    def test_reads_key_from_given_env_mapping(self):
        from quodeq.llm_bridge import _providers
        with patch.object(_providers, "get_provider_configs", return_value=_CFGS):
            key, env_name = resolve_api_key("acme", env={"ACME_API_KEY": "sk-123"})
        assert (key, env_name) == ("sk-123", "ACME_API_KEY")

    def test_unset_env_var_returns_empty_key_but_reports_env_name(self):
        from quodeq.llm_bridge import _providers
        with patch.object(_providers, "get_provider_configs", return_value=_CFGS):
            key, env_name = resolve_api_key("acme", env={})
        assert (key, env_name) == ("", "ACME_API_KEY")

    def test_no_resolvable_env_name_returns_empty_key_and_empty_name(self):
        from quodeq.llm_bridge import _providers
        with patch.object(_providers, "get_provider_configs", return_value=_CFGS):
            key, env_name = resolve_api_key("nonexistent", env={})
        assert (key, env_name) == ("", "")

    def test_defaults_to_os_environ_when_no_env_given(self, monkeypatch):
        from quodeq.llm_bridge import _providers
        monkeypatch.setenv("ACME_API_KEY", "sk-from-os-environ")
        with patch.object(_providers, "get_provider_configs", return_value=_CFGS):
            key, env_name = resolve_api_key("acme")
        assert (key, env_name) == ("sk-from-os-environ", "ACME_API_KEY")
