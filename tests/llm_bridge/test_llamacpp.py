"""Tests for llama.cpp integration in llm_bridge."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

from quodeq.llm_bridge._llamacpp import (
    _normalize_base,
    get_llamacpp_status,
    list_llamacpp_models,
    run_concurrency_test,
)


class TestNormalizeBase:
    def test_strips_v1_suffix(self):
        assert _normalize_base("http://localhost:8080/v1") == "http://localhost:8080"

    def test_strips_trailing_slash(self):
        assert _normalize_base("http://localhost:8080/") == "http://localhost:8080"

    def test_leaves_root_alone(self):
        assert _normalize_base("http://localhost:8080") == "http://localhost:8080"


class TestGetLlamacppStatus:
    def test_running(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status":"ok"}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._llamacpp.urllib.request.urlopen", return_value=mock_resp):
            result = get_llamacpp_status("http://localhost:8080")

        assert result["running"] is True
        assert result["status"] == "ok"
        assert "8080" in result["address"]

    def test_running_with_v1_suffix(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._llamacpp.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            get_llamacpp_status("http://localhost:8080/v1")

        # /health must be called on the root, not under /v1
        called_url = mock_open.call_args[0][0].full_url
        assert called_url.endswith("/health")
        assert "/v1/health" not in called_url

    def test_not_running(self):
        with patch("quodeq.llm_bridge._llamacpp.urllib.request.urlopen", side_effect=ConnectionRefusedError):
            result = get_llamacpp_status()

        assert result["running"] is False
        assert "error" in result


class TestListLlamacppModels:
    def test_returns_loaded_model(self):
        mock_data = {
            "object": "list",
            "data": [
                {"id": "qwen3-coder-30b.gguf", "object": "model"},
            ],
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._llamacpp.urllib.request.urlopen", return_value=mock_resp):
            models = list_llamacpp_models()

        assert len(models) == 1
        assert models[0]["name"] == "qwen3-coder-30b.gguf"

    def test_skips_entries_without_id(self):
        mock_data = {"data": [{"object": "model"}, {"id": "real.gguf"}]}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._llamacpp.urllib.request.urlopen", return_value=mock_resp):
            models = list_llamacpp_models()

        assert len(models) == 1
        assert models[0]["name"] == "real.gguf"

    def test_server_offline(self):
        with patch("quodeq.llm_bridge._llamacpp.urllib.request.urlopen", side_effect=ConnectionRefusedError):
            assert list_llamacpp_models() == []


class TestConcurrency:
    def test_no_model_loaded(self):
        with patch("quodeq.llm_bridge._llamacpp.list_llamacpp_models", return_value=[]), \
             patch("quodeq.llm_bridge._llamacpp._detect_memory", return_value=48e9):
            result = run_concurrency_test("any")
        assert result["recommended"] == 1
        assert "reason" in result

    def test_estimates_with_loaded_model(self):
        with patch(
            "quodeq.llm_bridge._llamacpp.list_llamacpp_models",
            return_value=[{"name": "model.gguf", "size": 0}],
        ), patch("quodeq.llm_bridge._llamacpp._detect_memory", return_value=128e9):
            result = run_concurrency_test("model.gguf")
        assert result["recommended"] >= 1
        assert result["gpu_memory"] == 128e9

    def test_no_host_memory_detected(self):
        with patch(
            "quodeq.llm_bridge._llamacpp.list_llamacpp_models",
            return_value=[{"name": "model.gguf", "size": 0}],
        ), patch("quodeq.llm_bridge._llamacpp._detect_memory", return_value=0):
            result = run_concurrency_test("model.gguf")
        assert result["recommended"] == 1
