"""Tests for provider configuration cache and type field."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis._provider_cache import _ProviderConfigCache, get_provider_configs

_OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"


class TestProviderConfigType:
    """Provider configs must include a 'type' field (cli or api)."""

    def test_builtin_providers_have_type(self):
        configs = get_provider_configs()
        for name, cfg in configs.items():
            assert "type" in cfg, f"Provider '{name}' missing 'type' field"
            assert cfg["type"] in ("cli", "api"), f"Provider '{name}' has invalid type: {cfg['type']}"

    def test_claude_is_cli_type(self):
        configs = get_provider_configs()
        assert configs["claude"]["type"] == "cli"

    def test_ollama_is_api_type(self):
        configs = get_provider_configs()
        assert configs["ollama"]["type"] == "api"
        assert configs["ollama"]["api_base"] == "http://localhost:11434/v1"

    def test_openrouter_is_api_type(self):
        configs = get_provider_configs()
        assert configs["openrouter"]["type"] == "api"
        assert configs["openrouter"]["api_key_env"] == _OPENROUTER_API_KEY_ENV

    def test_custom_provider_has_env_interpolation_fields(self):
        configs = get_provider_configs()
        assert configs["custom"]["type"] == "api"
        assert "${AI_MODEL}" in configs["custom"]["model"]

    def test_cache_loads_from_file(self, tmp_path):
        cfg_file = tmp_path / "providers.json"
        cfg_file.write_text(json.dumps({
            "test-cli": {"type": "cli", "cmd": "test", "base_args": "--print"},
            "test-api": {"type": "api", "model": "gpt-4o", "api_base": "http://localhost:8000/v1"},
        }))
        cache = _ProviderConfigCache()
        with patch("quodeq.analysis._provider_cache._AI_PROVIDERS_PATH", cfg_file):
            result = cache.get()
        assert result["test-cli"]["type"] == "cli"
        assert result["test-api"]["type"] == "api"

    def test_fallback_configs_have_type(self):
        """Fallback configs used when JSON is unreadable must also have type."""
        cache = _ProviderConfigCache()
        with patch("quodeq.analysis._provider_cache._AI_PROVIDERS_PATH", Path("/nonexistent")):
            result = cache.get()
        for name, cfg in result.items():
            assert "type" in cfg, f"Fallback provider '{name}' missing 'type'"
