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
import urllib.request
import urllib.error

from collections.abc import Mapping
from pathlib import Path

from quodeq.config.llm_bridge_env import omlx_api_key, omlx_base_url
from quodeq.llm_bridge._constants import LOCAL_SERVER_PROBE_TIMEOUT_S
from quodeq.llm_bridge._local_server import (
    bare_model_entry,
    concurrency_result,
    normalize_base,
    server_address,
)
from quodeq.llm_bridge._ollama import DEFAULT_MEMORY_FRACTION, HEALTH_OK, detect_memory, estimate_max_agents
from quodeq.shared.url_validation import validate_url_safe

_log = logging.getLogger(__name__)


def _omlx_home() -> Path:
    """omlx's own settings and models directory, ``~/.omlx``."""
    return Path.home() / ".omlx"


def read_omlx_api_key(env: Mapping[str, str] | None = None) -> str:
    """Return the omlx API key from OMLX_API_KEY env var or ~/.omlx/settings.json.

    *env* is resolved by the config layer; the variable is read per call
    (not at import), so a key exported after this module loads is honoured.
    """
    env_key = omlx_api_key(env)
    if env_key:
        return env_key
    try:
        cfg = json.loads((_omlx_home() / "settings.json").read_text(encoding="utf-8"))
        api_key = cfg.get("auth", {}).get("api_key", "")
        if api_key:
            _log.warning(
                "OMLX API key read from ~/.omlx/settings.json in cleartext; "
                "prefer setting OMLX_API_KEY instead."
            )
        return api_key
    except (OSError, json.JSONDecodeError):
        return ""


def _safe_request(url: str) -> urllib.request.Request:
    """Build a Request for *url* after validating it is safe to fetch.

    Loopback addresses (localhost, 127.x.x.x) are allowed because omlx
    normally runs on localhost.  Private-range IPs (10.x, 192.168.x) and
    link-local/metadata addresses (169.254.x) are rejected to prevent SSRF.

    Raises ``ValueError`` for unsafe URLs.
    """
    validate_url_safe(url, allow_loopback=True)
    return urllib.request.Request(url)


def get_omlx_status(base_url: str | None = None) -> dict:
    """Check if an omlx server is running and reachable."""
    root = normalize_base(base_url or omlx_base_url())
    try:
        req = _safe_request(f"{root}/health")
        with urllib.request.urlopen(req, timeout=LOCAL_SERVER_PROBE_TIMEOUT_S) as resp:
            data = json.loads(resp.read() or b"{}")
            if not isinstance(data, dict):
                data = {}
            return {
                "running": True,
                "status": data.get("status", HEALTH_OK),
                "address": server_address(root),
            }
    except (urllib.error.URLError, ConnectionRefusedError, OSError, ValueError) as exc:
        _log.warning("omlx status check failed: %s", exc)
        return {"running": False, "error": "Connection failed"}


def _list_model_dirs() -> list[dict]:
    """Read ~/.omlx/models/ and return one entry per directory (follows symlinks)."""
    models_dir = _omlx_home() / "models"
    try:
        return [
            bare_model_entry(entry.name)
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
    root = normalize_base(base_url or omlx_base_url())
    try:
        req = _safe_request(f"{root}/v1/models")
        key = api_key if api_key is not None else read_omlx_api_key()
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=LOCAL_SERVER_PROBE_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            entries = (data.get("data") or []) if isinstance(data, dict) else []
            models = [
                bare_model_entry(m.get("id", ""))
                for m in entries
                if isinstance(m, dict) and m.get("id")
            ]
            if models:
                return models
    except (urllib.error.URLError, ConnectionRefusedError, OSError, ValueError) as exc:
        _log.warning("Could not list omlx models: %s", exc)
    return _list_model_dirs()


def run_concurrency_test(_model: str, base_url: str | None = None, api_key: str | None = None) -> dict:
    """Estimate max parallel agents for the omlx server."""
    gpu_memory = detect_memory()
    models = list_omlx_models(base_url, api_key)
    if not models:
        return concurrency_result(1, 0, gpu_memory, "omlx is not running or no models available")

    if gpu_memory <= 0:
        return concurrency_result(1, 1, gpu_memory, "Could not detect host memory")

    vram_per_context = max(int(gpu_memory * DEFAULT_MEMORY_FRACTION), 1)
    result = estimate_max_agents(model_size=vram_per_context, gpu_memory=gpu_memory)
    return concurrency_result(result["estimate"], vram_per_context, gpu_memory)
