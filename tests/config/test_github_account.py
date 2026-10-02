"""GitHub account storage mirrors the provider-key path: keyring, then opt-in cleartext."""
from __future__ import annotations

import json

import keyring.errors
import pytest

from quodeq.config import ai_provider, github_account
from quodeq.config.ai_provider_errors import PlaintextKeyRefusedError
from quodeq.config.github_account import (
    ACCOUNT_KEY, GitHubAccount, TokenMethod, delete_account, is_expired, load_account, store_account,
)
from quodeq.config.paths import ConfigPaths

_ACCT = GitHubAccount(token="gho_x", login="victor", method=TokenMethod.OAUTH_DEVICE, expires_at=100.0, refresh_token="ghr_y", scope="repo")


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    cfg = ConfigPaths.from_root(tmp_path)
    monkeypatch.setattr(ai_provider, "default_paths", lambda: cfg)
    return cfg


@pytest.fixture()
def fake_keyring(monkeypatch):
    store = {}
    monkeypatch.setattr(ai_provider.keyring, "set_password", lambda s, k, v: store.__setitem__((s, k), v))
    monkeypatch.setattr(ai_provider.keyring, "get_password", lambda s, k: store.get((s, k)))

    def delete(s, k):
        if (s, k) not in store:
            raise keyring.errors.PasswordDeleteError("not found")  # what real backends raise
        del store[(s, k)]
    monkeypatch.setattr(github_account.keyring, "delete_password", delete)
    return store


@pytest.fixture()
def no_keyring(monkeypatch):
    def boom(*_a, **_k):
        raise keyring.errors.KeyringError("no backend")
    monkeypatch.setattr(ai_provider.keyring, "set_password", boom)
    monkeypatch.setattr(ai_provider.keyring, "get_password", boom)
    monkeypatch.setattr(github_account.keyring, "delete_password", boom)


def test_round_trip_through_keyring(paths, fake_keyring):
    assert store_account(_ACCT) == (True, True)
    assert fake_keyring[("quodeq", ACCOUNT_KEY)] == json.dumps(_ACCT.__dict__, sort_keys=True)
    assert load_account() == _ACCT
    assert not paths.env_file.exists()


def test_delete_removes_the_entry(paths, fake_keyring):
    store_account(_ACCT)
    delete_account()
    assert load_account() is None
    delete_account()  # idempotent


def test_no_keyring_without_opt_in_refuses(paths, no_keyring, monkeypatch):
    monkeypatch.delenv("QUODEQ_ALLOW_PLAINTEXT_KEY", raising=False)
    with pytest.raises(PlaintextKeyRefusedError):
        store_account(_ACCT)
    assert load_account() is None


def test_no_keyring_with_opt_in_uses_cleartext(paths, no_keyring, monkeypatch):
    monkeypatch.setenv("QUODEQ_ALLOW_PLAINTEXT_KEY", "1")
    assert store_account(_ACCT) == (True, False)
    assert "export GITHUB_ACCOUNT_API_KEY=" in paths.env_file.read_text()
    assert load_account() == _ACCT
    delete_account()
    assert load_account() is None


def test_corrupt_entry_loads_as_none(paths, fake_keyring):
    fake_keyring[("quodeq", ACCOUNT_KEY)] = "{not json"
    assert load_account() is None
    fake_keyring[("quodeq", ACCOUNT_KEY)] = json.dumps({"token": "t"})  # missing fields
    assert load_account() is None


def test_is_expired():
    assert is_expired(_ACCT, now=100.0) is True
    assert is_expired(_ACCT, now=99.0) is False
    assert is_expired(GitHubAccount("t", "l", TokenMethod.PASTED), now=1e12) is False
