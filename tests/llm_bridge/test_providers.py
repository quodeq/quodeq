"""Tests for llm_bridge provider detection."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from quodeq.llm_bridge._providers import (
    get_provider_configs,
    get_provider_type,
    classify_provider,
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
