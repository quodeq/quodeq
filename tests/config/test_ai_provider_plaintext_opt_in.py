"""The cleartext `.quodeq.env` key fallback is opt-in (QUODEQ_ALLOW_PLAINTEXT_KEY).

Without an OS keyring and without the opt-in, no path writes the key to
disk: store_api_key raises PlaintextKeyRefusedError naming the provider's
env var and the opt-in, store_api_key_secure logs it and returns False, and
a direct _write_env refuses too.
"""
from __future__ import annotations

import sys

import keyring.errors
import pytest

from quodeq.config import ai_provider
from quodeq.config.ai_provider_errors import PlaintextKeyRefusedError
from quodeq.config.credentials_env import plaintext_key_fallback_allowed
from quodeq.config.paths import ConfigPaths


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    cfg_paths = ConfigPaths.from_root(tmp_path)
    monkeypatch.setattr(ai_provider, "default_paths", lambda: cfg_paths)

    def raise_set(service, provider, key):
        raise keyring.errors.KeyringError("no backend")

    monkeypatch.setattr(ai_provider.keyring, "set_password", raise_set)
    monkeypatch.delenv("QUODEQ_ALLOW_PLAINTEXT_KEY", raising=False)
    return cfg_paths


def test_no_keyring_and_no_opt_in_stores_nothing(paths):
    with pytest.raises(PlaintextKeyRefusedError) as caught:
        ai_provider.store_api_key("gemini", "sk-gated")

    assert not paths.env_file.exists()
    assert caught.value.env_var == "GEMINI_API_KEY"
    message = str(caught.value)
    assert "GEMINI_API_KEY" in message and "QUODEQ_ALLOW_PLAINTEXT_KEY=1" in message
    assert "sk-gated" not in message


def test_secure_wrapper_logs_the_refusal_and_returns_false(paths, monkeypatch):
    errors: list[str] = []
    monkeypatch.setattr(ai_provider, "log_error", errors.append)
    assert ai_provider.store_api_key_secure("claude", "sk-gated") is False
    assert errors and "ANTHROPIC_API_KEY" in errors[0]


def test_gated_save_leaves_an_existing_env_file_untouched(paths):
    paths.env_file.write_text("export AI_PROVIDER=claude\n")
    assert ai_provider.store_api_key_secure("claude", "sk-gated") is False
    assert paths.env_file.read_text() == "export AI_PROVIDER=claude\n"


def test_direct_env_write_of_a_key_is_refused(paths):
    with pytest.raises(PlaintextKeyRefusedError, match="QUODEQ_ALLOW_PLAINTEXT_KEY"):
        ai_provider._write_env(paths, None, "ANTHROPIC_API_KEY", "sk-gated")
    assert not paths.env_file.exists()


def test_provider_only_write_needs_no_opt_in(paths):
    assert ai_provider.configure_provider_noninteractive("claude", paths) == 0
    assert "export AI_PROVIDER=claude" in paths.env_file.read_text()


def test_opt_in_keeps_the_0600_cleartext_fallback_with_a_warning(paths, monkeypatch):
    monkeypatch.setenv("QUODEQ_ALLOW_PLAINTEXT_KEY", "1")
    warnings: list[str] = []
    monkeypatch.setattr(ai_provider, "log_warning", warnings.append)

    assert ai_provider.store_api_key("claude", "sk-opted-in") == (True, False)

    assert "export ANTHROPIC_API_KEY=sk-opted-in" in paths.env_file.read_text()
    assert warnings and "cleartext" in warnings[0]
    if sys.platform != "win32":  # POSIX mode bits; os.fchmod exists on 3.13 Windows but is a no-op for them
        assert paths.env_file.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("raw, allowed", [
    ("1", True), ("true", True), ("YES", True), (" on ", True),
    ("", False), ("0", False), ("false", False), ("no", False),
])
def test_opt_in_values(raw, allowed):
    assert plaintext_key_fallback_allowed({"QUODEQ_ALLOW_PLAINTEXT_KEY": raw}) is allowed


def test_opt_in_unset_is_off():
    assert plaintext_key_fallback_allowed({}) is False
