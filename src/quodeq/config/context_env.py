"""Environment-based configuration for ``quodeq.context``.

The online-repo clone cache reads three things from the environment: where
the cache lives, whether it is switched off, and the git child-process
environment used for its clones. The semantic precedent tier reads its flag,
embedding model, server URL and match threshold. ``quodeq.context`` never
reads them itself; they are resolved here, lazily per call, and passed in.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from quodeq.config.process_env import process_environment_copy
from quodeq.shared.constants import ENV_TRUTHY
from quodeq.shared.env import (
    get_embedding_base_url,
    get_embedding_model,
    get_precedent_similarity_threshold,
    semantic_precedents_enabled,
)
from quodeq.shared.env_resolve import resolve_env

CACHE_ROOT_ENV = "QUODEQ_CACHE_ROOT"  # override the cache root for tests / sandboxing
DISABLE_ONLINE_CACHE_ENV = "QUODEQ_DISABLE_ONLINE_CACHE"

_DISABLED_TRUTHY = frozenset({ENV_TRUTHY, "true", "yes"})


def cache_root_override(env: Mapping[str, str] | None = None) -> Path | None:
    """The ``QUODEQ_CACHE_ROOT`` override, or None when unset/blank."""
    raw = resolve_env(env).get(CACHE_ROOT_ENV, "").strip()
    return Path(raw) if raw else None


def online_cache_disabled(env: Mapping[str, str] | None = None) -> bool:
    """True when the user has flipped the online-cache kill switch."""
    raw = resolve_env(env).get(DISABLE_ONLINE_CACHE_ENV, "")
    return raw.strip() in _DISABLED_TRUTHY


def git_child_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Child environment for the cache's git calls.

    LFS smudging is disabled: the cache only needs the tree and the history
    metadata, and pulling LFS blobs on every clone/fetch is the single
    biggest avoidable cost here.
    """
    child = process_environment_copy(env)
    child["GIT_LFS_SKIP_SMUDGE"] = ENV_TRUTHY
    return child


@dataclass(frozen=True)
class PrecedentSettings:
    """What one semantic precedent corpus build reads from the environment."""

    enabled: bool
    model: str
    base_url: str
    similarity_threshold: float


def precedent_settings(env: Mapping[str, str] | None = None) -> PrecedentSettings:
    """QUODEQ_SEMANTIC_PRECEDENTS (default off), QUODEQ_EMBEDDING_MODEL, the
    embeddings base URL and QUODEQ_PRECEDENT_SIMILARITY (default 0.85; out of
    range or invalid -> default), each with its existing parse rule."""
    src = resolve_env(env)
    return PrecedentSettings(
        enabled=semantic_precedents_enabled(src),
        model=get_embedding_model(src),
        base_url=get_embedding_base_url(src),
        similarity_threshold=get_precedent_similarity_threshold(src),
    )
