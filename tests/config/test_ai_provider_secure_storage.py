"""Tests for store_api_key_secure/get_api_key_secure (keyring + cleartext fallback)."""
from __future__ import annotations

import sys

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


@pytest.fixture()
def no_keyring(monkeypatch):
    """Force the cleartext fallback for both directions."""
    def raise_set(service, provider, key):
        raise keyring.errors.KeyringError("no backend")

    def raise_get(service, provider):
        raise keyring.errors.KeyringError("no backend")

    monkeypatch.setattr(ai_provider.keyring, "set_password", raise_set)
    monkeypatch.setattr(ai_provider.keyring, "get_password", raise_get)


class TestCleartextFallbackPreservesExistingContent:
    """Regression: _build_env_lines rebuilt .quodeq.env from a fixed template
    on every call, so saving one provider's key wiped every other provider's
    key and silently reset AI_PROVIDER to whichever provider was saved."""

    def test_second_provider_save_keeps_first_providers_key(self, paths, no_keyring):
        assert store_api_key_secure("claude", "sk-anthropic") is True
        assert store_api_key_secure("gemini", "sk-gemini") is True

        content = paths.env_file.read_text()
        assert "export ANTHROPIC_API_KEY=sk-anthropic" in content
        assert "export GEMINI_API_KEY=sk-gemini" in content
        assert get_api_key_secure("claude") == "sk-anthropic"
        assert get_api_key_secure("gemini") == "sk-gemini"

    def test_key_save_never_switches_the_active_provider(self, paths, no_keyring):
        ai_provider.configure_provider_noninteractive("codex", paths)
        assert ai_provider.get_current_provider(paths) == "codex"

        store_api_key_secure("claude", "sk-anthropic")
        store_api_key_secure("gemini", "sk-gemini")

        assert ai_provider.get_current_provider(paths) == "codex"
        assert "export AI_PROVIDER=gemini" not in paths.env_file.read_text()

    def test_resaving_a_provider_replaces_rather_than_duplicates(self, paths, no_keyring):
        store_api_key_secure("claude", "sk-old")
        store_api_key_secure("claude", "sk-new")

        content = paths.env_file.read_text()
        assert "sk-old" not in content
        assert content.count("export ANTHROPIC_API_KEY=") == 1
        assert get_api_key_secure("claude") == "sk-new"

    def test_provider_switch_keeps_stored_keys(self, paths, no_keyring):
        store_api_key_secure("claude", "sk-anthropic")
        ai_provider.configure_provider_noninteractive("gemini", paths)

        assert ai_provider.get_current_provider(paths) == "gemini"
        assert get_api_key_secure("claude") == "sk-anthropic"

    @pytest.mark.skipif(
        sys.platform == "win32", reason="POSIX-mode semantics differ on Windows"
    )
    def test_env_file_stays_owner_only_after_a_merge(self, paths, no_keyring):
        store_api_key_secure("claude", "sk-anthropic")
        store_api_key_secure("gemini", "sk-gemini")
        assert paths.env_file.stat().st_mode & 0o777 == 0o600


class TestProviderNameValidation:
    """Regression: _API_KEY_FORBIDDEN_CHARS was checked against the api key
    only, while the client-controlled provider name was interpolated into two
    `export …` lines. A newline there injects env vars that _env_loader then
    pushes into os.environ."""

    @pytest.mark.parametrize("provider", [
        "gemini\nexport EVIL=1",
        "gemini\rexport EVIL=1",
        "gemini\0",
        "gem ini",
        "gemini;rm -rf /",
        "",
        # A TRAILING newline specifically: `$` matches just before one, so a
        # `match()`-based check accepts this and only the api_key_var check
        # downstream stops it reaching the file. The validator must reject it
        # itself (hence fullmatch), or the guard is one refactor from useless.
        "gemini\n",
    ])
    def test_rejects_non_identifier_provider_names(self, paths, no_keyring, provider):
        with pytest.raises(ValueError):
            ai_provider._store_api_key(provider, "sk-injected")
        assert not paths.env_file.exists()

    def test_rejection_happens_before_the_keyring_is_touched(self, paths, monkeypatch):
        calls = []
        monkeypatch.setattr(
            ai_provider.keyring, "set_password",
            lambda *a: calls.append(a),
        )
        with pytest.raises(ValueError):
            ai_provider._store_api_key("gemini\nexport EVIL=1", "sk-injected")
        assert calls == []

    def test_injection_attempt_leaves_an_existing_file_untouched(self, paths, no_keyring):
        store_api_key_secure("claude", "sk-anthropic")
        before = paths.env_file.read_text()
        with pytest.raises(ValueError):
            ai_provider._store_api_key("x\nexport EVIL=1", "sk-injected")
        assert paths.env_file.read_text() == before

    def test_provider_without_an_api_key_var_is_rejected_cleanly(self, paths, no_keyring):
        """PROVIDERS maps ollama to "", which would write `export =<key>`."""
        assert ai_provider._api_key_var_for("ollama") == ""
        stored, secure = ai_provider._store_api_key("ollama", "sk-nowhere")
        assert (stored, secure) == (False, False)
        assert not paths.env_file.exists()

    def test_configure_provider_noninteractive_still_writes_keyless_providers(self, paths):
        assert ai_provider.configure_provider_noninteractive("ollama", paths) == 0
        content = paths.env_file.read_text()
        assert "export AI_PROVIDER=ollama" in content
        assert "export =" not in content


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
