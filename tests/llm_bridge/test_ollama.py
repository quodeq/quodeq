"""Tests for Ollama integration in llm_bridge."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from quodeq.llm_bridge._ollama import (
    get_ollama_status,
    list_ollama_models,
    estimate_max_agents,
    run_concurrency_test,
)


class TestGetOllamaStatus:
    def test_running(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"version":"0.20.2"}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._ollama.urllib.request.urlopen", return_value=mock_resp):
            result = get_ollama_status()

        assert result["running"] is True
        assert result["version"] == "0.20.2"

    def test_not_running(self):
        with patch("quodeq.llm_bridge._ollama.urllib.request.urlopen", side_effect=ConnectionRefusedError):
            result = get_ollama_status()

        assert result["running"] is False
        assert "error" in result


class TestListOllamaModels:
    def test_returns_models(self):
        mock_data = {
            "models": [
                {
                    "name": "gemma4:26b",
                    "size": 34088653984,
                    "details": {"quantization_level": "Q4_K_M", "family": "gemma4"},
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._ollama.urllib.request.urlopen", return_value=mock_resp):
            models = list_ollama_models()

        assert len(models) == 1
        assert models[0]["name"] == "gemma4:26b"
        assert models[0]["size"] == 34088653984

    def test_server_offline(self):
        with patch("quodeq.llm_bridge._ollama.urllib.request.urlopen", side_effect=ConnectionRefusedError):
            models = list_ollama_models()

        assert models == []


class TestEstimateMaxAgents:
    def test_small_model_high_memory(self):
        result = estimate_max_agents(model_size=14e9, gpu_memory=48e9)
        assert result["estimate"] >= 2

    def test_large_model_limited_memory(self):
        result = estimate_max_agents(model_size=34e9, gpu_memory=48e9)
        assert result["estimate"] >= 1

    def test_model_exceeds_memory(self):
        result = estimate_max_agents(model_size=80e9, gpu_memory=48e9)
        assert result["estimate"] == 1


class TestConcurrency:
    def test_estimates_from_vram(self):
        # Model using 17GB VRAM, system has 48GB
        with patch("quodeq.llm_bridge._ollama.get_running_model_info") as mock_ps, \
             patch("quodeq.llm_bridge._ollama._get_gpu_memory", return_value=48e9):
            mock_ps.return_value = {"name": "gemma4:26b", "size": 34e9, "size_vram": 17e9}
            result = run_concurrency_test("gemma4:26b")

        assert "recommended" in result
        assert result["recommended"] >= 1
        assert result["vram_per_context"] == 17e9
        assert result["gpu_memory"] == 48e9

    def test_falls_back_to_model_list(self):
        # No model loaded, falls back to model size from list
        with patch("quodeq.llm_bridge._ollama.get_running_model_info", return_value=None), \
             patch("quodeq.llm_bridge._ollama.list_ollama_models") as mock_list, \
             patch("quodeq.llm_bridge._ollama._get_gpu_memory", return_value=48e9):
            mock_list.return_value = [{"name": "gemma4:26b", "size": 34e9}]
            result = run_concurrency_test("gemma4:26b")

        assert result["recommended"] == 1  # 34GB model in 48GB = 1 context

    def test_server_offline(self):
        with patch("quodeq.llm_bridge._ollama.get_running_model_info", return_value=None), \
             patch("quodeq.llm_bridge._ollama.list_ollama_models", return_value=[]), \
             patch("quodeq.llm_bridge._ollama._get_gpu_memory", return_value=0):
            result = run_concurrency_test("gemma4:26b")

        assert result["recommended"] == 1
