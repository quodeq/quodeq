"""Environment-based configuration for the LLM provider bridge.

``quodeq.llm_bridge`` never reads the environment: the local-server base
URLs, the omlx key and the local-API detection markers are resolved here,
lazily per call, and passed in.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

from quodeq.shared.constants import (
    DEFAULT_LLAMACPP_BASE_URL,
    OLLAMA_DEFAULT_BASE_URL,
    OLLAMA_DEFAULT_PORT,
    OMLX_DEFAULT_BASE_URL,
)

#: Markers that identify a local model server by its ``api_base``.
LOCAL_API_MARKERS_DEFAULT = frozenset(
    {OLLAMA_DEFAULT_PORT, "localhost", "127.0.0.1", "ollama"})


def ollama_base_url(env: Mapping[str, str] | None = None) -> str:
    """Ollama server base URL: ``OLLAMA_BASE_URL`` or the packaged default."""
    return (os.environ if env is None else env).get(
        "OLLAMA_BASE_URL", OLLAMA_DEFAULT_BASE_URL)


def llamacpp_base_url(env: Mapping[str, str] | None = None) -> str:
    """llama-server base URL: ``LLAMACPP_BASE_URL`` or the default port 8080."""
    return (os.environ if env is None else env).get(
        "LLAMACPP_BASE_URL", DEFAULT_LLAMACPP_BASE_URL)


def omlx_base_url(env: Mapping[str, str] | None = None) -> str:
    """omlx server base URL: ``OMLX_BASE_URL`` or the default port 8000."""
    return (os.environ if env is None else env).get(
        "OMLX_BASE_URL", OMLX_DEFAULT_BASE_URL)


def omlx_api_key(env: Mapping[str, str] | None = None) -> str:
    """omlx API key from ``OMLX_API_KEY``; empty when unset."""
    return (os.environ if env is None else env).get("OMLX_API_KEY", "")


def api_key(env_name: str, env: Mapping[str, str] | None = None) -> str:
    """Value of the provider's API-key variable, or "" when unset/unnamed."""
    if not env_name:
        return ""
    return (os.environ if env is None else env).get(env_name, "")


def local_api_markers(env: Mapping[str, str] | None = None) -> frozenset[str]:
    """Local-API detection markers, honoring ``QUODEQ_LOCAL_API_MARKERS``.

    Unset means the packaged defaults. Explicitly set (comma-separated, even
    to an empty string) means exactly the given markers, so setting
    ``QUODEQ_LOCAL_API_MARKERS=""`` disables local-API detection entirely.
    That unset-vs-empty distinction is security-adjacent: the classification
    gates the assistant's in-process web tools.
    """
    raw = (os.environ if env is None else env).get("QUODEQ_LOCAL_API_MARKERS")
    if raw is None:
        return LOCAL_API_MARKERS_DEFAULT
    return frozenset(m.strip() for m in raw.split(",") if m.strip())
