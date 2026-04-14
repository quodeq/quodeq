"""Provider detection, configuration, and type classification."""
from __future__ import annotations

import os

from quodeq.analysis._provider_cache import get_provider_configs as _get_cached_configs


def get_provider_configs() -> dict[str, dict]:
    """Return all provider configurations from ai_providers.json."""
    return _get_cached_configs()


def get_provider_type(provider_id: str) -> str:
    """Return 'cli' or 'api' for a provider ID."""
    configs = get_provider_configs()
    return configs.get(provider_id, {}).get("type", "cli")


# Configurable via QUODEQ_LOCAL_API_MARKERS (comma-separated).
# Default markers detect common local LLM server patterns.
_LOCAL_API_MARKERS_DEFAULT = {"11434", "localhost", "127.0.0.1", "ollama"}
_env_markers = os.environ.get("QUODEQ_LOCAL_API_MARKERS")
_LOCAL_API_MARKERS: set[str] = (
    {m.strip() for m in _env_markers.split(",") if m.strip()}
    if _env_markers is not None
    else _LOCAL_API_MARKERS_DEFAULT
)


def _is_local_api(provider_id: str) -> bool:
    """Check if an API provider is local (e.g. Ollama)."""
    configs = get_provider_configs()
    cfg = configs.get(provider_id, {})
    api_base = cfg.get("api_base", "")
    return any(marker in api_base.lower() for marker in _LOCAL_API_MARKERS)


def classify_provider(provider_id: str) -> str:
    """Classify a provider as 'cli', 'local-api', or 'cloud-api'."""
    ptype = get_provider_type(provider_id)
    if ptype == "cli":
        return "cli"
    if _is_local_api(provider_id):
        return "local-api"
    return "cloud-api"
