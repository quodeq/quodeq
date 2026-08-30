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


# Fixed-endpoint local model servers. The assistant's in-process web tools
# (search_web/fetch_url) are only ever registered for these providers; cloud
# API providers (openrouter/custom) are excluded by design.
LOCAL_PROVIDERS = frozenset({"ollama", "llamacpp", "omlx"})


# Default markers detect common local LLM server patterns.
_LOCAL_API_MARKERS_DEFAULT = frozenset({"11434", "localhost", "127.0.0.1", "ollama"})


def _local_api_markers(env: dict[str, str] | None = None) -> frozenset[str]:
    """Return the local-API detection markers, honoring QUODEQ_LOCAL_API_MARKERS.

    Unset means the packaged defaults. Explicitly set (comma-separated,
    even to an empty string) means exactly the given markers, so setting
    QUODEQ_LOCAL_API_MARKERS="" disables local-API detection entirely. This
    unset-vs-empty distinction is security-adjacent: classify_provider's
    result gates the assistant's in-process web tools (search_web/fetch_url
    are only ever registered for local-api providers).
    """
    environ = env if env is not None else os.environ
    raw = environ.get("QUODEQ_LOCAL_API_MARKERS")
    if raw is None:
        return _LOCAL_API_MARKERS_DEFAULT
    return frozenset(m.strip() for m in raw.split(",") if m.strip())


def _is_local_api(provider_id: str, *, markers: frozenset[str] | None = None) -> bool:
    """Check if an API provider is local (e.g. Ollama)."""
    configs = get_provider_configs()
    cfg = configs.get(provider_id, {})
    # `or ""`: a present-but-null api_base returns None from .get(default),
    # which would crash the .lower() below.
    api_base = cfg.get("api_base") or ""
    resolved_markers = markers if markers is not None else _local_api_markers()
    return any(marker in api_base.lower() for marker in resolved_markers)


def classify_provider(provider_id: str, *, markers: frozenset[str] | None = None) -> str:
    """Classify a provider as 'cli', 'local-api', or 'cloud-api'."""
    ptype = get_provider_type(provider_id)
    if ptype == "cli":
        return "cli"
    if _is_local_api(provider_id, markers=markers):
        return "local-api"
    return "cloud-api"


def resolve_api_key_env(provider_id: str = "", api_base: str = "") -> str:
    """Return the api_key_env name for *provider_id*, falling back to a
    match on *api_base* for older clients that never sent a provider id.

    Empty string when neither resolves to a configured provider with an
    ``api_key_env`` entry.
    """
    configs = get_provider_configs()
    provider_cfg = configs.get(provider_id, {}) if provider_id else {}
    env_name = provider_cfg.get("api_key_env", "")
    if not env_name and api_base:
        for cfg in configs.values():
            if cfg.get("api_base") == api_base and cfg.get("api_key_env"):
                env_name = cfg["api_key_env"]
                break
    return env_name


def resolve_api_key(
    provider_id: str = "", api_base: str = "", env: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Resolve an API key for *provider_id* (or *api_base*) from the environment.

    Returns ``(key, env_name)``. *key* is ``""`` when the resolved env var is
    unset or there is nothing to resolve; *env_name* is returned regardless,
    so a caller can report which variable is missing.
    """
    environ = env if env is not None else os.environ
    env_name = resolve_api_key_env(provider_id, api_base)
    key = environ.get(env_name, "") if env_name else ""
    return key, env_name
