"""Tests for the llama.cpp log SSE route."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture()
def client():
    from quodeq.api.app import create_app
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


@pytest.fixture()
def isolated_defaults(tmp_path, monkeypatch):
    """Stub the default-path probe so host log files don't leak into tests.

    Without this, a developer who happens to have a real
    ``~/Library/Logs/llama-server.log`` would see the unconfigured tests
    flip to "available" because the fallback found their file.
    """
    monkeypatch.delenv("LLAMACPP_LOG_FILE", raising=False)
    sentinel: list[Path] = [tmp_path / "no-such-default.log"]
    with patch(
        "quodeq.api._llamacpp_log_routes._default_log_paths",
        return_value=sentinel,
    ):
        yield tmp_path


class TestAvailability:
    def test_unconfigured_returns_unavailable(self, client, isolated_defaults):
        resp = client.get("/api/llamacpp/logs/available")
        assert resp.status_code == 200
        assert resp.get_json() == {"available": False}

    def test_configured_but_missing_file(self, client, monkeypatch, tmp_path):
        monkeypatch.setenv("LLAMACPP_LOG_FILE", str(tmp_path / "nope.log"))
        resp = client.get("/api/llamacpp/logs/available")
        assert resp.status_code == 200
        assert resp.get_json() == {"available": False}

    def test_configured_and_present(self, client, monkeypatch, tmp_path):
        log_file = tmp_path / "llama.log"
        log_file.write_text("hello\n")
        monkeypatch.setenv("LLAMACPP_LOG_FILE", str(log_file))
        resp = client.get("/api/llamacpp/logs/available")
        assert resp.status_code == 200
        assert resp.get_json() == {"available": True}

    def test_default_path_picked_up(self, client, isolated_defaults):
        # Re-stub the default probe to a path that actually exists.
        default = isolated_defaults / "llama-server.log"
        default.write_text("starting...\n")
        with patch(
            "quodeq.api._llamacpp_log_routes._default_log_paths",
            return_value=[default],
        ):
            resp = client.get("/api/llamacpp/logs/available")
        assert resp.status_code == 200
        assert resp.get_json() == {"available": True}


class TestStream:
    def test_unconfigured_returns_404(self, client, isolated_defaults):
        resp = client.get("/api/llamacpp/logs/stream")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["code"] == "NOT_FOUND"
        assert "LLAMACPP_LOG_FILE" in body["help"] or "log file" in body["help"].lower()
