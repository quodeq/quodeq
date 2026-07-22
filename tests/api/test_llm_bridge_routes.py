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


# ---------------------------------------------------------------------------
# SEC-13 — the OMLX models route takes the API key from the X-Api-Key header,
#          never from the query string (query params leak via access logs,
#          browser history, and referrers).
# ---------------------------------------------------------------------------

class TestOmlxModels:
    def test_api_key_read_from_header(self, client):
        with patch("quodeq.api.llm_bridge_routes.list_omlx_models") as mock:
            mock.return_value = []
            resp = client.get(
                "/api/omlx/models?base_url=http://localhost:10240",
                headers={"X-Api-Key": " sk-header "},
            )
        assert resp.status_code == 200
        mock.assert_called_once_with(base_url="http://localhost:10240", api_key="sk-header")

    def test_api_key_query_param_no_longer_honored(self, client):
        with patch("quodeq.api.llm_bridge_routes.list_omlx_models") as mock:
            mock.return_value = []
            resp = client.get("/api/omlx/models?api_key=sk-leaky")
        assert resp.status_code == 200
        mock.assert_called_once_with(base_url=None, api_key=None)


# ---------------------------------------------------------------------------
# REL-084/085/086/087/088 — POST routes must 400 on a JSON body that parses
# but is not an object (e.g. [1] or "x"), instead of crashing at data.get.
# ---------------------------------------------------------------------------

class TestJsonObjectBodyRequired:
    @pytest.mark.parametrize("route", [
        "/api/ollama/test-concurrency",
        "/api/ollama/estimate-agents",
        "/api/llamacpp/test-concurrency",
        "/api/omlx/test-concurrency",
        "/api/provider/test",
    ])
    def test_array_body_returns_400(self, client, route):
        resp = client.post(route, json=[1], headers={"Origin": "http://localhost"})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    @pytest.mark.parametrize("route", [
        "/api/ollama/test-concurrency",
        "/api/omlx/test-concurrency",
    ])
    def test_string_body_returns_400(self, client, route):
        resp = client.post(route, json="x", headers={"Origin": "http://localhost"})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_omlx_non_string_base_url_returns_400(self, client):
        resp = client.post(
            "/api/omlx/test-concurrency",
            json={"model": "m", "base_url": 123},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_omlx_non_string_api_key_returns_400(self, client):
        resp = client.post(
            "/api/omlx/test-concurrency",
            json={"model": "m", "api_key": ["k"]},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_omlx_valid_string_fields_pass_through(self, client):
        with patch("quodeq.api.llm_bridge_routes.run_omlx_concurrency_test") as mock:
            mock.return_value = {"recommended": 2}
            resp = client.post(
                "/api/omlx/test-concurrency",
                json={"model": "m", "base_url": " http://x ", "api_key": ""},
                headers={"Origin": "http://localhost"},
            )
        assert resp.status_code == 200
        mock.assert_called_once_with("m", base_url="http://x", api_key=None)


# ---------------------------------------------------------------------------
# base_url on the omlx routes must pass the same SSRF validation as
# /api/provider/test: http(s) scheme only (private/LAN hosts stay allowed
# for self-hosted servers).
# ---------------------------------------------------------------------------

class TestOmlxBaseUrlValidation:
    def _get(self, client, route, base_url):
        return client.get(f"{route}?base_url={base_url}")

    @pytest.mark.parametrize("route", ["/api/omlx/status", "/api/omlx/models"])
    def test_non_http_scheme_rejected(self, client, route):
        resp = self._get(client, route, "ftp://internal-host/models")
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_URL"

    @pytest.mark.parametrize("route", ["/api/omlx/status", "/api/omlx/models"])
    def test_missing_hostname_rejected(self, client, route):
        resp = self._get(client, route, "http://")
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_URL"

    def test_post_route_rejects_non_http_scheme(self, client):
        resp = client.post(
            "/api/omlx/test-concurrency",
            json={"model": "m", "base_url": "file:///etc/passwd"},
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_URL"

    def test_localhost_base_url_accepted(self, client):
        with patch("quodeq.api.llm_bridge_routes.get_omlx_status") as mock:
            mock.return_value = {"running": True}
            resp = self._get(client, "/api/omlx/status", "http://127.0.0.1:10240")
        assert resp.status_code == 200
        mock.assert_called_once_with(base_url="http://127.0.0.1:10240")
