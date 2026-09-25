"""Tests for llm_bridge API routes."""
from __future__ import annotations

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


class TestOllamaConcurrency:
    def test_empty_model_returns_400_missing_param(self, client):
        """Unlike llamacpp/omlx, ollama rejects an empty model string as missing."""
        resp = client.post(
            "/api/ollama/test-concurrency",
            json={"model": ""},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "MISSING_PARAM"


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

    def test_concurrency_accepts_empty_model(self, client):
        """Unlike ollama, llamacpp accepts an empty model string (INVALID_PARAM
        only fires on a non-string; empty string is not rejected)."""
        with patch("quodeq.api.llm_bridge_routes.run_llamacpp_concurrency_test") as mock:
            mock.return_value = {"recommended": 3, "vram_per_context": 0, "gpu_memory": 128e9}
            resp = client.post(
                "/api/llamacpp/test-concurrency",
                json={"model": ""},
                headers={"Origin": "http://localhost"},
            )
        assert resp.status_code == 200

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

    def test_missing_api_key_reports_env_var(self, client, monkeypatch):
        # No api_key in the body and the provider's env var unset: the wire
        # body is a frozen contract the UI keys off (success/code/error).
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        resp = client.post("/api/provider/test", json={
            "provider": "openrouter",
            "model": "test",
        }, headers={"Origin": "http://localhost"})

        assert resp.status_code == 200
        assert resp.get_json() == {
            "success": False,
            "code": "MISSING_API_KEY",
            "error": "OPENROUTER_API_KEY is not set in the dashboard's environment. "
                     "Export it in your shell (e.g. ~/.zshrc) and relaunch the dashboard from that terminal.",
        }


class TestProviderEnvCheck:
    def test_omlx_stays_absent_no_api_key_env_entry(self, client):
        # omlx has no `api_key_env` (it takes base_url/api_key per-request,
        # not from a settings env var), so it must never appear in the
        # env-check payload — only providers with a configured env var do.
        resp = client.get("/api/provider/env-check")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "omlx" not in data
        assert "openrouter" in data
        assert "custom" in data


class TestKnownModels:
    def test_returns_models(self, client):
        resp = client.get("/api/known-models")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "claude" in data


# ---------------------------------------------------------------------------
# #335 — estimate-agents must return 400 when model_size/gpu_memory are
#         non-numeric (e.g. strings from a crafted JSON body)
# ---------------------------------------------------------------------------

class TestEstimateAgentsValidation:
    def test_string_model_size_returns_400(self, client):
        resp = client.post(
            "/api/ollama/estimate-agents",
            json={"model_size": "big", "gpu_memory": 32},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400

    def test_string_gpu_memory_returns_400(self, client):
        resp = client.post(
            "/api/ollama/estimate-agents",
            json={"model_size": 7, "gpu_memory": "all"},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400

    def test_null_model_size_returns_400(self, client):
        resp = client.post(
            "/api/ollama/estimate-agents",
            json={"model_size": None, "gpu_memory": 32},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400

    def test_valid_numeric_inputs_pass_through(self, client):
        with patch("quodeq.api.llm_bridge_routes.estimate_max_agents") as mock:
            mock.return_value = {"agents": 3}
            resp = client.post(
                "/api/ollama/estimate-agents",
                json={"model_size": 7, "gpu_memory": 32},
                headers={"Origin": "http://localhost"},
            )
        assert resp.status_code == 200
        mock.assert_called_once_with(model_size=7, gpu_memory=32)

    def test_bool_model_size_returns_400(self, client):
        # bool is a subclass of int in Python; must be rejected explicitly.
        resp = client.post(
            "/api/ollama/estimate-agents",
            json={"model_size": True, "gpu_memory": 32000000000},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"


class TestProviderTestFieldTypes:
    """A non-string provider/api_base/api_key/model must 400, not 500."""

    @pytest.mark.parametrize("body", [
        {"provider": ["x"]},
        {"api_base": 5},
        {"api_key": 1},
        {"model": {}},
    ])
    def test_non_string_field_returns_400(self, client, body):
        resp = client.post(
            "/api/provider/test", json=body, headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_null_api_key_is_treated_as_absent(self, client, monkeypatch):
        """An explicit JSON null for api_key is not a type error (it's the
        same as omitting the field): the route falls through to env-var
        resolution instead of 400ing."""
        monkeypatch.setenv("OPENROUTER_API_KEY", _TEST_API_KEY)
        with patch("quodeq.api.llm_bridge_routes.check_cloud_connection") as mock_check:
            mock_check.return_value = {"success": True, "model": "test", "latency_ms": 200}
            resp = client.post("/api/provider/test", json={
                "provider": "openrouter",
                "model": "test",
                "api_base": "https://example.com/v1",
                "api_key": None,
            }, headers={"Origin": "http://localhost"})

        assert resp.status_code == 200
        mock_check.assert_called_once()
        assert mock_check.call_args.kwargs["api_key"] == _TEST_API_KEY
