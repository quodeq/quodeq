"""Tests for store_api_key_secure/get_api_key_secure (keyring + cleartext fallback)."""
from __future__ import annotations

import keyring.errors
import pytest

from quodeq.config import ai_provider
from quodeq.config.ai_provider import get_api_key_secure, store_api_key_secure
from quodeq.config.paths import ConfigPaths


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    cfg_paths = ConfigPaths.from_root(tmp_path)
    monkeypatch.setattr(ai_provider, "default_paths", lambda: cfg_paths)
    return cfg_paths


class TestStoreApiKeySecure:
    def test_keyring_success_does_not_touch_cleartext_file(self, paths, monkeypatch):
        calls = {}

        def fake_set_password(service, provider, key):
            calls["args"] = (service, provider, key)

        monkeypatch.setattr(ai_provider.keyring, "set_password", fake_set_password)
        result = store_api_key_secure("claude", "sk-secret")

        assert result is True
        assert calls["args"] == ("quodeq", "claude", "sk-secret")
        assert not paths.env_file.exists()

    def test_keyring_error_falls_back_to_cleartext(self, paths, monkeypatch):
        def raise_keyring_error(service, provider, key):
            raise keyring.errors.KeyringError("no backend available")

        monkeypatch.setattr(ai_provider.keyring, "set_password", raise_keyring_error)
        result = store_api_key_secure("claude", "sk-fallback")

        assert result is True
        assert paths.env_file.exists()
        content = paths.env_file.read_text()
        assert "export ANTHROPIC_API_KEY=sk-fallback" in content

    def test_generic_exception_falls_back_to_cleartext(self, paths, monkeypatch):
        def raise_runtime_error(service, provider, key):
            raise RuntimeError("dbus not available")

        monkeypatch.setattr(ai_provider.keyring, "set_password", raise_runtime_error)
        result = store_api_key_secure("openrouter", "sk-fallback2")

        assert result is True
        assert "export OPENROUTER_API_KEY=sk-fallback2" in paths.env_file.read_text()

    def test_both_paths_failing_returns_false(self, paths, monkeypatch):
        def raise_keyring_error(service, provider, key):
            raise keyring.errors.KeyringError("no backend")

        def raise_write_error(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(ai_provider.keyring, "set_password", raise_keyring_error)
        monkeypatch.setattr(ai_provider, "_write_env", raise_write_error)
        result = store_api_key_secure("claude", "sk-doomed")

        assert result is False

    def test_unknown_provider_derives_env_var_name(self, paths, monkeypatch):
        def raise_keyring_error(service, provider, key):
            raise keyring.errors.KeyringError("no backend")

        monkeypatch.setattr(ai_provider.keyring, "set_password", raise_keyring_error)
        result = store_api_key_secure("mystery-provider", "sk-mystery")

        assert result is True
        assert "export MYSTERY-PROVIDER_API_KEY=sk-mystery" in paths.env_file.read_text()


class TestGetApiKeySecure:
    def test_returns_keyring_value_when_present(self, paths, monkeypatch):
        monkeypatch.setattr(ai_provider.keyring, "get_password", lambda service, provider: "sk-from-keyring")
        assert get_api_key_secure("claude") == "sk-from-keyring"

    def test_keyring_error_falls_back_to_cleartext_file(self, paths, monkeypatch):
        def raise_keyring_error(service, provider):
            raise keyring.errors.KeyringError("no backend")

        monkeypatch.setattr(ai_provider.keyring, "get_password", raise_keyring_error)
        ai_provider._write_env(paths, "claude", "ANTHROPIC_API_KEY", "sk-cleartext")

        assert get_api_key_secure("claude") == "sk-cleartext"

    def test_keyring_none_falls_back_to_cleartext_file(self, paths, monkeypatch):
        monkeypatch.setattr(ai_provider.keyring, "get_password", lambda service, provider: None)
        ai_provider._write_env(paths, "codex", "CODEX_API_KEY", "sk-codex")

        assert get_api_key_secure("codex") == "sk-codex"

    def test_neither_backend_has_key_returns_none(self, paths, monkeypatch):
        monkeypatch.setattr(ai_provider.keyring, "get_password", lambda service, provider: None)
        assert get_api_key_secure("claude") is None

    def test_no_env_file_returns_none(self, paths, monkeypatch):
        monkeypatch.setattr(ai_provider.keyring, "get_password", lambda service, provider: None)
        assert not paths.env_file.exists()
        assert get_api_key_secure("gemini") is None


class TestRoundTrip:
    def test_store_then_get_via_cleartext_fallback(self, paths, monkeypatch):
        """The keyring-failure fallback path, exercised end-to-end."""
        def raise_keyring_error_set(service, provider, key):
            raise keyring.errors.KeyringError("no backend")

        def raise_keyring_error_get(service, provider):
            raise keyring.errors.KeyringError("no backend")

        monkeypatch.setattr(ai_provider.keyring, "set_password", raise_keyring_error_set)
        monkeypatch.setattr(ai_provider.keyring, "get_password", raise_keyring_error_get)

        assert store_api_key_secure("gemini", "sk-roundtrip") is True
        assert get_api_key_secure("gemini") == "sk-roundtrip"
