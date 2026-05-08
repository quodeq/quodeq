"""Tests for the opt-in llama.cpp log SSE route."""
from __future__ import annotations

import pytest


@pytest.fixture()
def client():
    from quodeq.api.app import create_app
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


class TestAvailability:
    def test_unconfigured_returns_unavailable(self, client, monkeypatch):
        monkeypatch.delenv("LLAMACPP_LOG_FILE", raising=False)
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


class TestStream:
    def test_unconfigured_returns_404(self, client, monkeypatch):
        monkeypatch.delenv("LLAMACPP_LOG_FILE", raising=False)
        resp = client.get("/api/llamacpp/logs/stream")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["code"] == "NOT_FOUND"
        assert "LLAMACPP_LOG_FILE" in body["help"]
