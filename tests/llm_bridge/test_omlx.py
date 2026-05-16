"""Tests for omlx integration in llm_bridge."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

from quodeq.llm_bridge._omlx import (
    _normalize_base,
    _list_model_dirs,
    get_omlx_status,
    list_omlx_models,
    run_concurrency_test,
)


class TestNormalizeBase:
    def test_strips_v1_suffix(self):
        assert _normalize_base("http://localhost:8000/v1") == "http://localhost:8000"

    def test_strips_trailing_slash(self):
        assert _normalize_base("http://localhost:8000/") == "http://localhost:8000"

    def test_leaves_root_alone(self):
        assert _normalize_base("http://localhost:8000") == "http://localhost:8000"


class TestGetOmlxStatus:
    def test_running(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status":"ok"}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", return_value=mock_resp):
            result = get_omlx_status("http://localhost:8000")

        assert result["running"] is True
        assert result["status"] == "ok"
        assert "8000" in result["address"]

    def test_running_with_v1_suffix(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"{}"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            get_omlx_status("http://localhost:8000/v1")

        called_url = mock_open.call_args[0][0].full_url
        assert called_url.endswith("/health")
        assert "/v1/health" not in called_url

    def test_not_running(self):
        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", side_effect=ConnectionRefusedError):
            result = get_omlx_status()

        assert result["running"] is False
        assert "error" in result


class TestListOmlxModels:
    def test_returns_models(self):
        mock_data = {
            "object": "list",
            "data": [
                {"id": "mlx-community/gemma-3-4b-it-4bit", "object": "model"},
                {"id": "mlx-community/Qwen3-8B-4bit", "object": "model"},
            ],
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", return_value=mock_resp):
            models = list_omlx_models()

        assert len(models) == 2
        assert models[0]["name"] == "mlx-community/gemma-3-4b-it-4bit"
        assert models[0]["size"] == 0
        assert models[0]["quantization"] == ""
        assert models[0]["family"] == ""

    def test_skips_entries_without_id(self):
        mock_data = {"data": [{"object": "model"}, {"id": "mlx-community/valid-model"}]}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", return_value=mock_resp):
            models = list_omlx_models()

        assert len(models) == 1
        assert models[0]["name"] == "mlx-community/valid-model"

    def test_empty_api_response_falls_back_to_dirs(self):
        mock_data = {"data": []}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        dir_models = [{"name": "mlx-community/gemma-3-4b-it-4bit", "size": 0, "quantization": "", "family": ""}]

        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", return_value=mock_resp), \
             patch("quodeq.llm_bridge._omlx._list_model_dirs", return_value=dir_models):
            result = list_omlx_models()

        assert result == dir_models

    def test_empty_api_and_no_dirs(self):
        mock_data = {"data": []}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", return_value=mock_resp), \
             patch("quodeq.llm_bridge._omlx._list_model_dirs", return_value=[]):
            assert list_omlx_models() == []

    def test_server_offline_falls_back_to_dirs(self):
        dir_models = [{"name": "my-model", "size": 0, "quantization": "", "family": ""}]
        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", side_effect=ConnectionRefusedError), \
             patch("quodeq.llm_bridge._omlx._list_model_dirs", return_value=dir_models):
            assert list_omlx_models() == dir_models

    def test_sends_auth_header_when_key_available(self):
        mock_data = {"object": "list", "data": [{"id": "gemma-4-26B", "object": "model"}]}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", return_value=mock_resp) as mock_open, \
             patch("quodeq.llm_bridge._omlx._read_omlx_api_key", return_value="test-key"):
            list_omlx_models()

        req = mock_open.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer test-key"

    def test_no_auth_header_when_no_key(self):
        mock_data = {"object": "list", "data": []}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", return_value=mock_resp) as mock_open, \
             patch("quodeq.llm_bridge._omlx._read_omlx_api_key", return_value=""):
            list_omlx_models()

        req = mock_open.call_args[0][0]
        assert req.get_header("Authorization") is None


class TestListModelDirs:
    def test_returns_directories_including_symlinks(self, tmp_path):
        models_dir = tmp_path / ".omlx" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "real-model").mkdir()
        target = tmp_path / "elsewhere"
        target.mkdir()
        (models_dir / "symlinked-model").symlink_to(target)

        with patch("quodeq.llm_bridge._omlx.Path") as mock_path_cls:
            mock_path_cls.home.return_value = tmp_path
            result = _list_model_dirs()

        names = [m["name"] for m in result]
        assert "real-model" in names
        assert "symlinked-model" in names

    def test_returns_empty_when_dir_missing(self, tmp_path):
        with patch("quodeq.llm_bridge._omlx.Path") as mock_path_cls:
            mock_path_cls.home.return_value = tmp_path  # no .omlx/models subdir
            result = _list_model_dirs()
        assert result == []


class TestConcurrency:
    def test_no_models_available(self):
        with patch("quodeq.llm_bridge._omlx.list_omlx_models", return_value=[]), \
             patch("quodeq.llm_bridge._omlx._detect_memory", return_value=48e9):
            result = run_concurrency_test("any")
        assert result["recommended"] == 1
        assert "reason" in result

    def test_estimates_with_models_available(self):
        mock_models = [{"name": "mlx-community/gemma-3-4b-it-4bit", "size": 0}]
        with patch("quodeq.llm_bridge._omlx.list_omlx_models", return_value=mock_models), \
             patch("quodeq.llm_bridge._omlx._detect_memory", return_value=128e9):
            result = run_concurrency_test("mlx-community/gemma-3-4b-it-4bit")
        assert result["recommended"] >= 1
        assert result["gpu_memory"] == 128e9

    def test_no_host_memory_detected(self):
        mock_models = [{"name": "mlx-community/gemma-3-4b-it-4bit", "size": 0}]
        with patch("quodeq.llm_bridge._omlx.list_omlx_models", return_value=mock_models), \
             patch("quodeq.llm_bridge._omlx._detect_memory", return_value=0):
            result = run_concurrency_test("mlx-community/gemma-3-4b-it-4bit")
        assert result["recommended"] == 1
        assert "reason" in result
