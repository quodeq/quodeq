"""Tests for llm_bridge provider detection."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from quodeq.llm_bridge._providers import (
    get_provider_configs,
    get_provider_type,
    classify_provider,
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
