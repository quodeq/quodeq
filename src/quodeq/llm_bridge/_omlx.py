"""omlx-specific integration: server status, model list, VRAM estimation.

omlx is an Apple Silicon-only inference server that serves MLX-format models
with a FastAPI HTTP server. It exposes an OpenAI-compatible API at /v1 and
supports multiple concurrently loaded models.

Endpoints used:
  - GET /health         — omlx health check
  - GET /v1/models      — OpenAI-compatible model list
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error

from quodeq.llm_bridge._ollama import _detect_memory, estimate_max_agents

_log = logging.getLogger(__name__)

_OMLX_BASE = os.environ.get("OMLX_BASE_URL", "http://localhost:8000")
_TIMEOUT_S = 3


def _normalize_base(base_url: str) -> str:
    """Strip trailing /v1 so /health and /v1/models both work."""
    stripped = base_url.rstrip("/")
    if stripped.endswith("/v1"):
        stripped = stripped[: -len("/v1")]
    return stripped


def get_omlx_status(base_url: str = _OMLX_BASE) -> dict:
    """Check if an omlx server is running and reachable."""
    root = _normalize_base(base_url)
    try:
        req = urllib.request.Request(f"{root}/health")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read() or b"{}")
            return {
                "running": True,
                "status": data.get("status", "ok"),
                "address": root.replace("http://", ""),
            }
    except (urllib.error.URLError, ConnectionRefusedError, OSError, ValueError) as exc:
        _log.warning("omlx status check failed: %s", exc)
        return {"running": False, "error": "Connection failed"}


def list_omlx_models(base_url: str = _OMLX_BASE) -> list[dict]:
    """List models available on the omlx server."""
    root = _normalize_base(base_url)
    try:
        req = urllib.request.Request(f"{root}/v1/models")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            entries = data.get("data", []) or []
            return [
                {
                    "name": m.get("id", ""),
                    "size": 0,
                    "quantization": "",
                    "family": "",
                }
                for m in entries
                if m.get("id")
            ]
    except (urllib.error.URLError, ConnectionRefusedError, OSError, ValueError) as exc:
        _log.warning("Could not list omlx models: %s", exc)
        return []


def run_concurrency_test(model: str, base_url: str = _OMLX_BASE) -> dict:
    """Estimate max parallel agents for the omlx server."""
    gpu_memory = _detect_memory()
    models = list_omlx_models(base_url)
    if not models:
        return {
            "recommended": 1,
            "vram_per_context": 0,
            "gpu_memory": gpu_memory,
            "reason": "omlx is not running or no models available",
        }

    if gpu_memory <= 0:
        vram_per_context = 1
        return {
            "recommended": 1,
            "vram_per_context": vram_per_context,
            "gpu_memory": gpu_memory,
            "reason": "Could not detect host memory",
        }

    vram_per_context = max(int(gpu_memory * 0.5), 1)
    result = estimate_max_agents(model_size=vram_per_context, gpu_memory=gpu_memory)
    return {
        "recommended": result["estimate"],
        "vram_per_context": vram_per_context,
        "gpu_memory": gpu_memory,
    }
