"""POST /api/provider/key with no OS keyring and no plaintext opt-in.

The cleartext `.quodeq.env` fallback needs QUODEQ_ALLOW_PLAINTEXT_KEY=1.
Without it the route answers a coded 409 the UI can turn into copy that
tells the user what to do, and the key never reaches the disk.
"""
from __future__ import annotations

import keyring.errors
import pytest

from quodeq.api.app import create_app
from quodeq.config import ai_provider
from quodeq.config.paths import ConfigPaths

_ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture()
def cfg_paths(tmp_path, monkeypatch):
    paths = ConfigPaths.from_root(tmp_path)
    monkeypatch.setattr(ai_provider, "default_paths", lambda: paths)

    def raise_keyring_error(*args, **kwargs):
        raise keyring.errors.KeyringError("no backend available")

    monkeypatch.setattr(ai_provider.keyring, "set_password", raise_keyring_error)
    return paths


@pytest.fixture()
def client():
    with create_app(test_config={"TESTING": True}).test_client() as c:
        yield c


def test_no_opt_in_is_a_coded_409_naming_the_env_var(client, cfg_paths, monkeypatch):
    monkeypatch.delenv("QUODEQ_ALLOW_PLAINTEXT_KEY", raising=False)
    resp = client.post(
        "/api/provider/key", json={"provider": "gemini", "apiKey": "sk-gated"}, headers=_ORIGIN,
    )
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["code"] == "KEYRING_UNAVAILABLE"
    assert body["envVar"] == "GEMINI_API_KEY"
    assert "GEMINI_API_KEY" in body["error"]
    assert "QUODEQ_ALLOW_PLAINTEXT_KEY=1" in body["error"]
    assert "sk-gated" not in resp.get_data(as_text=True)
    assert not cfg_paths.env_file.exists()


def test_opt_in_keeps_the_success_contract(client, cfg_paths, monkeypatch):
    monkeypatch.setenv("QUODEQ_ALLOW_PLAINTEXT_KEY", "1")
    resp = client.post(
        "/api/provider/key", json={"provider": "gemini", "apiKey": "sk-opted-in"}, headers=_ORIGIN,
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"stored": True, "secure": False}
