"""Tests for shared.provider_env — exporting user-entered API credentials.

The scan subprocess resolves cloud API keys from the env var named by the
provider's ``api_key_env`` (analysis/subprocess._resolve_provider_config).
The dashboard collected the key in Settings but only ever exported it for
omlx, so an OpenRouter key typed in the UI was silently discarded and the
run failed with a missing-key error.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.shared.provider_env import provider_env_exports


@pytest.fixture()
def providers_file(tmp_path: Path, monkeypatch):
    path = tmp_path / "ai_providers.json"
    path.write_text(json.dumps({
        "openrouter": {
            "type": "api",
            "api_base": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API_KEY",
            "api_key_required": True,
        },
        "custom": {
            "type": "api",
            "api_base": "${AI_API_BASE}",
            "api_key_env": "AI_API_KEY",
        },
        "claude": {"type": "cli"},
    }), encoding="utf-8")
    monkeypatch.setenv("QUODEQ_AI_PROVIDERS_PATH", str(path))
    return path


def test_exports_key_under_provider_env_name(providers_file):
    assert provider_env_exports("openrouter", "sk-or-123", None) == {
        "OPENROUTER_API_KEY": "sk-or-123",
    }


def test_custom_provider_exports_key_and_templated_base(providers_file):
    assert provider_env_exports("custom", "k", "http://myhost:9/v1") == {
        "AI_API_KEY": "k",
        "AI_API_BASE": "http://myhost:9/v1",
    }


def test_fixed_base_is_not_exported(providers_file):
    assert provider_env_exports("openrouter", None, "http://elsewhere") == {}


def test_provider_without_key_env_exports_nothing(providers_file):
    assert provider_env_exports("claude", "key", None) == {}


def test_unknown_provider_and_missing_file_are_safe(providers_file, monkeypatch):
    assert provider_env_exports("nope", "key", None) == {}
    monkeypatch.setenv("QUODEQ_AI_PROVIDERS_PATH", "/nonexistent.json")
    assert provider_env_exports("openrouter", "key", None) == {}
