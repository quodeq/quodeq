"""The exact concurrency payload each local bridge answers, with and without a reason."""
from __future__ import annotations

from unittest.mock import patch

from quodeq.llm_bridge import (
    get_llamacpp_status,
    run_concurrency_test,
    run_llamacpp_concurrency_test,
    run_omlx_concurrency_test,
)

_LLAMACPP = "quodeq.llm_bridge._llamacpp"
_OLLAMA = "quodeq.llm_bridge._ollama"
_OMLX = "quodeq.llm_bridge.omlx"

_GIB = 1024 ** 3


def test_llamacpp_without_a_model_explains_why():
    with patch(f"{_LLAMACPP}.detect_memory", return_value=8 * _GIB), \
            patch(f"{_LLAMACPP}.list_llamacpp_models", return_value=[]):
        assert run_llamacpp_concurrency_test("m") == {
            "recommended": 1, "vram_per_context": 0, "gpu_memory": 8 * _GIB,
            "reason": "llama-server is not running or no model loaded",
        }


def test_llamacpp_without_host_memory_keeps_the_model_size():
    with patch(f"{_LLAMACPP}.detect_memory", return_value=0), \
            patch(f"{_LLAMACPP}.list_llamacpp_models", return_value=[{"name": "m", "size": 5}]):
        assert run_llamacpp_concurrency_test("m") == {
            "recommended": 1, "vram_per_context": 5, "gpu_memory": 0,
            "reason": "Could not detect host memory",
        }


def test_llamacpp_estimate_has_no_reason_key():
    with patch(f"{_LLAMACPP}.detect_memory", return_value=8 * _GIB), \
            patch(f"{_LLAMACPP}.list_llamacpp_models", return_value=[{"name": "m", "size": 0}]):
        assert run_llamacpp_concurrency_test("m") == {
            "recommended": 1, "vram_per_context": 4 * _GIB, "gpu_memory": 8 * _GIB,
        }


def test_omlx_without_host_memory_reports_one_byte_per_context():
    with patch(f"{_OMLX}.detect_memory", return_value=0), \
            patch(f"{_OMLX}.list_omlx_models", return_value=[{"name": "m"}]):
        assert run_omlx_concurrency_test("m") == {
            "recommended": 1, "vram_per_context": 1, "gpu_memory": 0,
            "reason": "Could not detect host memory",
        }


def test_omlx_without_models_explains_why():
    with patch(f"{_OMLX}.detect_memory", return_value=8 * _GIB), \
            patch(f"{_OMLX}.list_omlx_models", return_value=[]):
        assert run_omlx_concurrency_test("m") == {
            "recommended": 1, "vram_per_context": 0, "gpu_memory": 8 * _GIB,
            "reason": "omlx is not running or no models available",
        }


def test_ollama_reason_depends_on_what_is_missing():
    with patch(f"{_OLLAMA}.get_running_model_info", return_value={"size_vram": 3}), \
            patch(f"{_OLLAMA}._get_gpu_memory", return_value=0):
        assert run_concurrency_test("m", "http://localhost:1") == {
            "recommended": 1, "vram_per_context": 3, "gpu_memory": 0, "reason": "Could not detect VRAM",
        }
    with patch(f"{_OLLAMA}.get_running_model_info", return_value=None), \
            patch(f"{_OLLAMA}.list_ollama_models", return_value=[]), \
            patch(f"{_OLLAMA}._get_gpu_memory", return_value=8):
        assert run_concurrency_test("m", "http://localhost:1")["reason"] == "Could not determine model size"


def test_an_unreachable_llamacpp_server_reports_connection_failed():
    with patch(f"{_LLAMACPP}.urllib.request.urlopen", side_effect=OSError("down")):
        assert get_llamacpp_status("http://127.0.0.1:8080/v1/") == {
            "running": False, "error": "Connection failed",
        }
