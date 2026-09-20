"""Resolve an injected environment mapping against the process environment.

Units outside the config layer take an optional ``env`` parameter and
resolve it here instead of touching ``os.environ`` themselves. That keeps
the dependency visible in the signature and the unit testable without
mutating the process -- which is exactly what ``tools/check_env_reads.py``
ratchets towards.

A leaf module with no quodeq imports, like ``_env_sanitize.py``, so any
layer can import it (including modules ``_env.py`` itself imports) without
a cycle.

``None`` means "not injected, use the process environment". An injected
``{}`` means "no variables set" and is honoured as such -- never spell this
``env or os.environ``, which turns that empty mapping back into the real one.
"""
from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping


def resolve_env(env: Mapping[str, str] | None = None) -> Mapping[str, str]:
    """Return *env*, or ``os.environ`` when *env* is None."""
    return os.environ if env is None else env


def resolve_mutable_env(
    env: MutableMapping[str, str] | None = None,
) -> MutableMapping[str, str]:
    """Return *env*, or ``os.environ`` when *env* is None, for writing.

    Same rule as :func:`resolve_env`; separate so a caller that writes back
    (the dashboard's launch-token hand-off, ``runner._resolve_environ``)
    declares a writable mapping in its own signature.
    """
    return os.environ if env is None else env
