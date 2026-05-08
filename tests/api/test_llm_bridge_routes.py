"""Tests for llm_bridge API routes."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

_TEST_API_KEY = "sk-test"


@pytest.fixture()
def client(tmp_path):
    from quodeq.api.app import create_app
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


class TestOllamaStatus:
    def test_returns_status(self, client):
        with patch("quodeq.api.llm_bridge_routes.get_ollama_status") as mock:
            mock.return_value = {"running": True, "version": "0.20.2", "address": "localhost:11434"}
            resp = client.get("/api/ollama/status")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["running"] is True


class TestOllamaModels:
    def test_returns_models(self, client):
        with patch("quodeq.api.llm_bridge_routes.list_ollama_models") as mock:
            mock.return_value = [{"name": "gemma4:26b", "size": 34e9, "quantization": "Q4_K_M", "family": "gemma4"}]
            resp = client.get("/api/ollama/models")

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["models"]) == 1


class TestLlamacppRoutes:
    def test_status(self, client):
        with patch("quodeq.api.llm_bridge_routes.get_llamacpp_status") as mock:
            mock.return_value = {"running": True, "status": "ok", "address": "localhost:8080"}
            resp = client.get("/api/llamacpp/status")
        assert resp.status_code == 200
        assert resp.get_json()["running"] is True

    def test_models(self, client):
        with patch("quodeq.api.llm_bridge_routes.list_llamacpp_models") as mock:
            mock.return_value = [{"name": "qwen3.gguf", "size": 0, "quantization": "", "family": ""}]
            resp = client.get("/api/llamacpp/models")
        assert resp.status_code == 200
        assert len(resp.get_json()["models"]) == 1

    def test_concurrency(self, client):
        with patch("quodeq.api.llm_bridge_routes.run_llamacpp_concurrency_test") as mock:
            mock.return_value = {"recommended": 3, "vram_per_context": 0, "gpu_memory": 128e9}
            resp = client.post(
                "/api/llamacpp/test-concurrency",
                json={"model": "qwen3.gguf"},
                headers={"Origin": "http://localhost"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["recommended"] == 3

    def test_concurrency_rejects_path_traversal(self, client):
        resp = client.post(
            "/api/llamacpp/test-concurrency",
            json={"model": "../etc/passwd"},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400


class TestProviderTest:
    def test_success(self, client):
        with patch("quodeq.api.llm_bridge_routes.check_cloud_connection") as mock:
            mock.return_value = {"success": True, "model": "test", "latency_ms": 200}
            resp = client.post("/api/provider/test", json={
                "provider": "openrouter",
                "model": "test",
                "api_base": "https://example.com/v1",
                "api_key": _TEST_API_KEY,
            }, headers={"Origin": "http://localhost"})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True


class TestKnownModels:
    def test_returns_models(self, client):
        resp = client.get("/api/known-models")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "claude" in data
