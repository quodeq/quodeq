"""Environment-based configuration accessors -- semantic precedent embeddings."""
from __future__ import annotations

import os

from quodeq.shared._env_db import _SQLITE_DISABLE_TRUTHY

_DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
_DEFAULT_EMBEDDING_BASE_URL = "http://localhost:11434"
_DEFAULT_PRECEDENT_SIMILARITY = 0.85


def get_embedding_model(env: dict[str, str] | None = None) -> str:
    """Embedding model for semantic precedent matching (QUODEQ_EMBEDDING_MODEL).

    Independent of the chat provider: CLI providers have no HTTP endpoint and
    llama.cpp serves one model per process, so embeddings get their own model.
    """
    return (env if env is not None else os.environ).get(
        "QUODEQ_EMBEDDING_MODEL", _DEFAULT_EMBEDDING_MODEL
    )


def get_embedding_base_url(env: dict[str, str] | None = None) -> str:
    """Base URL of the embeddings server.

    Resolution: QUODEQ_EMBEDDING_BASE_URL, then OLLAMA_BASE_URL, then localhost.
    """
    environ = env if env is not None else os.environ
    return (
        environ.get("QUODEQ_EMBEDDING_BASE_URL")
        or environ.get("OLLAMA_BASE_URL")
        or _DEFAULT_EMBEDDING_BASE_URL
    )


def semantic_precedents_enabled(env: dict[str, str] | None = None) -> bool:
    """True when QUODEQ_SEMANTIC_PRECEDENTS is truthy. Default OFF in v1."""
    environ = env if env is not None else os.environ
    raw = environ.get("QUODEQ_SEMANTIC_PRECEDENTS", "")
    return raw.strip().lower() in _SQLITE_DISABLE_TRUTHY


def get_precedent_similarity_threshold(env: dict[str, str] | None = None) -> float:
    """Cosine threshold for a semantic precedent match (QUODEQ_PRECEDENT_SIMILARITY).

    Default 0.85 is a placeholder until Phase B golden-set calibration.
    Out-of-range or unparsable values fall back to the default.
    """
    raw = (env if env is not None else os.environ).get("QUODEQ_PRECEDENT_SIMILARITY", "")
    try:
        val = float(raw)
    except ValueError:
        return _DEFAULT_PRECEDENT_SIMILARITY
    if not 0.0 < val <= 1.0:
        return _DEFAULT_PRECEDENT_SIMILARITY
    return val
