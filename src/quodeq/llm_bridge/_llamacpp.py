"""llama.cpp-specific integration: server status, model list, VRAM estimation.

Mirrors the Ollama bridge but targets a running ``llama-server`` process
(from the llama.cpp project). llama-server is one-process-per-model:
the loaded model is fixed at launch time via ``-m``, and a separate
draft model can be supplied via ``--model-draft`` for speculative
decoding (MTP). There is no model registry to browse or pull from.

Endpoints used:
  - GET /health           — llama.cpp native health check
  - GET /v1/models        — OpenAI-compatible list (single entry, the loaded model)

Concurrency estimation reuses ``estimate_max_agents`` from the Ollama
module, since the math (VRAM per context vs total GPU memory) is the
same. We do not have an ``/api/ps``-equivalent endpoint, so model size
falls back to whatever ``/v1/models`` reports plus host memory probing.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Mapping

from quodeq.llm_bridge._ollama import (
    DEFAULT_MEMORY_FRACTION,
    _detect_memory,
    estimate_max_agents,
)
from quodeq.config.llm_bridge_env import llamacpp_base_url

_log = logging.getLogger(__name__)

_TIMEOUT_S = 3
# The /health body's own status word; not a quodeq vocabulary.
_HEALTH_OK = "ok"
#: Everything a probe against a llama-server may raise: the socket/HTTP
#: layer (OSError, which urllib's URLError and ConnectionRefusedError both
#: subclass) and a body that is not the JSON we expect (ValueError, which
#: json.JSONDecodeError subclasses).
_TRANSPORT_ERRORS = (OSError, ValueError)


def _default_base_url(env: Mapping[str, str] | None = None) -> str:
    """llama-server base URL: ``LLAMACPP_BASE_URL`` or the default port 8080.

    Resolved by the config layer, so nothing here reads os.environ.
    """
    return llamacpp_base_url(env)


def _normalize_base(base_url: str) -> str:
    """Strip a trailing /v1 (or /v1/) so /health and /v1/models both work.

    Quodeq stores ``api_base`` as the OpenAI-compatible ``/v1`` URL for use
    by the analysis runner. The native llama.cpp ``/health`` endpoint sits
    one level up, so we accept either form here.
    """
    stripped = base_url.rstrip("/")
    if stripped.endswith("/v1"):
        stripped = stripped[: -len("/v1")]
    return stripped


def get_llamacpp_status(base_url: str | None = None) -> dict:
    """Check if a llama-server process is running and reachable."""
    root = _normalize_base(base_url or _default_base_url())
    try:
        req = urllib.request.Request(f"{root}/health")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read() or b"{}")
            return {
                "running": True,
                "status": data.get("status", _HEALTH_OK),
                "address": root.replace("http://", ""),
            }
    except _TRANSPORT_ERRORS as exc:
        _log.warning("llama.cpp status check failed: %s", exc)
        return {"running": False, "error": "Connection failed"}


def list_llamacpp_models(base_url: str | None = None) -> list[dict]:
    """List the model loaded by llama-server.

    Always returns 0 or 1 entries: llama-server is one-model-per-process.
    The model name is whatever llama-server reports for the GGUF passed
    via ``-m``, which is typically the file basename.
    """
    root = _normalize_base(base_url or _default_base_url())
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
    except _TRANSPORT_ERRORS as exc:
        _log.warning("Could not list llama.cpp models: %s", exc)
        return []


def run_concurrency_test(
    _model: str,
    base_url: str | None = None,
) -> dict:
    """Estimate max parallel agents for the loaded llama.cpp model.

    llama-server does not expose per-model VRAM, so we probe host memory
    and assume the loaded model occupies it. The estimate is conservative,
    capped by ``estimate_max_agents``.
    """
    gpu_memory = _detect_memory()
    models = list_llamacpp_models(base_url)
    if not models:
        return {
            "recommended": 1,
            "vram_per_context": 0,
            "gpu_memory": gpu_memory,
            "reason": "llama-server is not running or no model loaded",
        }

    # No size data from /v1/models, so use a fraction of host memory as a
    # rough per-context budget. This mirrors Ollama's behavior when VRAM
    # info is missing: we still return at least 1.
    vram_per_context = models[0].get("size", 0) or max(int(gpu_memory * DEFAULT_MEMORY_FRACTION), 1)

    if gpu_memory <= 0:
        return {
            "recommended": 1,
            "vram_per_context": vram_per_context,
            "gpu_memory": gpu_memory,
            "reason": "Could not detect host memory",
        }

    result = estimate_max_agents(model_size=vram_per_context, gpu_memory=gpu_memory)
    return {
        "recommended": result["estimate"],
        "vram_per_context": vram_per_context,
        "gpu_memory": gpu_memory,
    }
