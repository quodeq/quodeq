"""Tests for API provider discovery in tooling mixin."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from quodeq.services.tooling_mixin import FsToolingMixin


class TestGetAiClientsIncludesApiProviders:
    """get_ai_clients should include API providers alongside CLI tools."""

    def test_includes_api_providers_from_config(self):
        mixin = FsToolingMixin()
        with patch("quodeq.services.tooling_mixin.get_provider_configs") as mock_cfg:
            mock_cfg.return_value = {
                "ollama": {"type": "api", "model": "llama3.1", "api_base": "http://localhost:11434/v1"},
                "openrouter": {"type": "api", "model": "claude-sonnet-4", "api_key_env": "OPENROUTER_API_KEY"},
                "claude": {"type": "cli", "cmd": "claude"},
            }
            with patch("shutil.which", return_value=None):
                result = mixin.get_ai_clients()
        client_ids = [c["id"] for c in result["clients"]]
        assert "ollama" in client_ids
        assert "openrouter" in client_ids

    def test_api_providers_have_type_label(self):
        mixin = FsToolingMixin()
        with patch("quodeq.services.tooling_mixin.get_provider_configs") as mock_cfg:
            mock_cfg.return_value = {
                "ollama": {"type": "api", "model": "llama3.1", "api_base": "http://localhost:11434/v1"},
            }
            with patch("shutil.which", return_value=None):
                result = mixin.get_ai_clients()
        ollama = [c for c in result["clients"] if c["id"] == "ollama"][0]
        assert ollama["type"] == "api"

    def test_llamacpp_label_is_dotted(self):
        mixin = FsToolingMixin()
        with patch("quodeq.services.tooling_mixin.get_provider_configs") as mock_cfg:
            mock_cfg.return_value = {
                "llamacpp": {"type": "api", "model": "", "api_base": "http://localhost:8080/v1"},
            }
            with patch("shutil.which", return_value=None):
                result = mixin.get_ai_clients()
        llamacpp = next((c for c in result["clients"] if c["id"] == "llamacpp"), None)
        assert llamacpp is not None
        assert llamacpp["label"] == "llama.cpp"

    def test_cli_providers_marked_uninstalled_when_missing(self):
        mixin = FsToolingMixin()
        with patch("quodeq.services.tooling_mixin.get_provider_configs") as mock_cfg:
            mock_cfg.return_value = {
                "claude": {"type": "cli", "cmd": "claude"},
            }
            with patch("shutil.which", return_value=None):
                result = mixin.get_ai_clients()
        claude = next((c for c in result["clients"] if c["id"] == "claude"), None)
        assert claude is not None
        assert claude["installed"] is False
