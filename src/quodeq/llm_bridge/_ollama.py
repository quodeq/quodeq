"""Ollama-specific integration: server status, model list, VRAM estimation."""
from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import urllib.request
import urllib.error

_log = logging.getLogger(__name__)

_OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
_TIMEOUT_S = 3
_MAX_PARALLEL_AGENTS = 5
_SYSCTL_TIMEOUT_S = 3
_NVIDIA_SMI_TIMEOUT_S = 5
_MIB_TO_BYTES = 1024 * 1024


def get_ollama_status(base_url: str = _OLLAMA_BASE) -> dict:
    """Check if the Ollama server is running."""
    try:
        req = urllib.request.Request(f"{base_url}/api/version")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            return {
                "running": True,
                "version": data.get("version", "unknown"),
                "address": base_url.replace("http://", ""),
            }
    except (urllib.error.URLError, ConnectionRefusedError, OSError) as exc:
        _log.warning("Ollama status check failed: %s", exc)
        return {"running": False, "error": "Connection failed"}


def list_ollama_models(base_url: str = _OLLAMA_BASE) -> list[dict]:
    """List installed Ollama models."""
    try:
        req = urllib.request.Request(f"{base_url}/api/tags")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            models = data.get("models", [])
            return [
                {
                    "name": m["name"],
                    "size": m.get("size", 0),
                    "quantization": m.get("details", {}).get("quantization_level", ""),
                    "family": m.get("details", {}).get("family", ""),
                }
                for m in models
            ]
    except (urllib.error.URLError, ConnectionRefusedError, OSError) as exc:
        _log.warning("Could not list Ollama models: %s", exc)
        return []


def get_running_model_info(base_url: str = _OLLAMA_BASE) -> dict | None:
    """Get info about the currently loaded model (from /api/ps)."""
    try:
        req = urllib.request.Request(f"{base_url}/api/ps")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            models = data.get("models", [])
            if models:
                m = models[0]
                return {
                    "name": m["name"],
                    "size": m.get("size", 0),
                    "size_vram": m.get("size_vram", 0),
                }
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        pass
    return None


def estimate_max_agents(
    model_size: float,
    gpu_memory: float,
    overhead_factor: float = 1.3,
) -> dict:
    """Estimate max parallel agents from model size and GPU memory."""
    if model_size <= 0 or gpu_memory <= 0:
        return {"estimate": 1, "model_size": model_size, "gpu_memory": gpu_memory}

    effective_size = model_size * overhead_factor
    max_contexts = int(gpu_memory / effective_size)
    estimate = max(1, min(max_contexts, _MAX_PARALLEL_AGENTS))

    return {
        "estimate": estimate,
        "model_size": model_size,
        "gpu_memory": gpu_memory,
    }


def _get_gpu_memory() -> float:
    """Detect total GPU/unified memory in bytes. Returns 0 if unknown."""
    system = platform.system()
    try:
        if system == "Darwin":
            # macOS: unified memory — total system RAM is the GPU budget
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=_SYSCTL_TIMEOUT_S)
            return float(out.strip())
        if system == "Linux":
            # Try nvidia-smi for discrete GPU
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                timeout=_NVIDIA_SMI_TIMEOUT_S,
            )
            # First GPU, value in MiB
            mib = float(out.decode().strip().split("\n")[0])
            return mib * _MIB_TO_BYTES
    except (subprocess.SubprocessError, FileNotFoundError, ValueError, OSError):
        pass
    return 0


def run_concurrency_test(
    model: str,
    max_agents: int = 5,
    base_url: str = _OLLAMA_BASE,
) -> dict:
    """Estimate max parallel agents based on VRAM usage.

    Queries the running model's VRAM footprint from Ollama /api/ps
    and compares against available GPU memory to estimate how many
    parallel contexts can fit.
    """
    # Get VRAM used by the loaded model
    running = get_running_model_info(base_url)
    if not running or not running.get("size_vram"):
        # Model not loaded or no VRAM info — try model size from list
        models = list_ollama_models(base_url)
        match = next((m for m in models if m["name"] == model), None)
        model_size = match["size"] if match else 0
        vram_per_context = model_size
    else:
        vram_per_context = running["size_vram"]

    gpu_memory = _get_gpu_memory()

    if vram_per_context <= 0 or gpu_memory <= 0:
        return {
            "recommended": 1,
            "vram_per_context": vram_per_context,
            "gpu_memory": gpu_memory,
            "reason": "Could not detect VRAM" if gpu_memory <= 0 else "Could not determine model size",
        }

    result = estimate_max_agents(model_size=vram_per_context, gpu_memory=gpu_memory)

    return {
        "recommended": result["estimate"],
        "vram_per_context": vram_per_context,
        "gpu_memory": gpu_memory,
    }
