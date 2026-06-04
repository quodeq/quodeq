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

from pathlib import Path

from quodeq.llm_bridge._ollama import _detect_memory, estimate_max_agents

_log = logging.getLogger(__name__)

_OMLX_BASE = os.environ.get("OMLX_BASE_URL", "http://localhost:8000")
_TIMEOUT_S = 3


def _read_omlx_api_key() -> str:
    """Return the omlx API key from OMLX_API_KEY env var or ~/.omlx/settings.json."""
    env_key = os.environ.get("OMLX_API_KEY", "")
    if env_key:
        return env_key
    try:
        cfg = json.loads((Path.home() / ".omlx" / "settings.json").read_text(encoding="utf-8"))
        return cfg.get("auth", {}).get("api_key", "")
    except (OSError, json.JSONDecodeError):
        return ""


def _normalize_base(base_url: str) -> str:
    """Strip trailing /v1 so /health and /v1/models both work."""
    stripped = base_url.rstrip("/")
    if stripped.endswith("/v1"):
        stripped = stripped[: -len("/v1")]
    return stripped


def get_omlx_status(base_url: str | None = None) -> dict:
    """Check if an omlx server is running and reachable."""
    root = _normalize_base(base_url or _OMLX_BASE)
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


def _list_model_dirs() -> list[dict]:
    """Read ~/.omlx/models/ and return one entry per directory (follows symlinks)."""
    models_dir = Path.home() / ".omlx" / "models"
    try:
        return [
            {"name": entry.name, "size": 0, "quantization": "", "family": ""}
            for entry in sorted(models_dir.iterdir())
            if entry.is_dir()  # is_dir() follows symlinks
        ]
    except OSError:
        return []


def list_omlx_models(base_url: str | None = None, api_key: str | None = None) -> list[dict]:
    """List models available on the omlx server.

    Tries GET /v1/models first. Falls back to reading ~/.omlx/models/ directly
    when the API returns nothing, which handles symlinked model directories that
    omlx does not enumerate via the OpenAI-compatible endpoint.
    """
    root = _normalize_base(base_url or _OMLX_BASE)
    try:
        req = urllib.request.Request(f"{root}/v1/models")
        key = api_key if api_key is not None else _read_omlx_api_key()
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            entries = data.get("data", []) or []
            models = [
                {"name": m.get("id", ""), "size": 0, "quantization": "", "family": ""}
                for m in entries
                if m.get("id")
            ]
            if models:
                return models
    except (urllib.error.URLError, ConnectionRefusedError, OSError, ValueError) as exc:
        _log.warning("Could not list omlx models: %s", exc)
    return _list_model_dirs()


def run_concurrency_test(model: str, base_url: str | None = None, api_key: str | None = None) -> dict:
    """Estimate max parallel agents for the omlx server."""
    gpu_memory = _detect_memory()
    models = list_omlx_models(base_url, api_key)
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
