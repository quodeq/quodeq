"""Environment-based configuration for ``quodeq.context``.

The online-repo clone cache reads three things from the environment: where
the cache lives, whether it is switched off, and the git child-process
environment used for its clones. ``quodeq.context`` never reads them
itself; they are resolved here, lazily per call, and passed in.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from quodeq.config.process_env import process_environment_copy

CACHE_ROOT_ENV = "QUODEQ_CACHE_ROOT"  # override the cache root for tests / sandboxing
DISABLE_ONLINE_CACHE_ENV = "QUODEQ_DISABLE_ONLINE_CACHE"

_DISABLED_TRUTHY = frozenset({"1", "true", "yes"})


def cache_root_override(env: Mapping[str, str] | None = None) -> Path | None:
    """The ``QUODEQ_CACHE_ROOT`` override, or None when unset/blank."""
    raw = (os.environ if env is None else env).get(CACHE_ROOT_ENV, "").strip()
    return Path(raw) if raw else None


def online_cache_disabled(env: Mapping[str, str] | None = None) -> bool:
    """True when the user has flipped the online-cache kill switch."""
    raw = (os.environ if env is None else env).get(DISABLE_ONLINE_CACHE_ENV, "")
    return raw.strip() in _DISABLED_TRUTHY


def git_child_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Child environment for the cache's git calls.

    LFS smudging is disabled: the cache only needs the tree and the history
    metadata, and pulling LFS blobs on every clone/fetch is the single
    biggest avoidable cost here.
    """
    child = process_environment_copy(env)
    child["GIT_LFS_SKIP_SMUDGE"] = "1"
    return child
