"""Leaf helper for sanitizing an operator-supplied filesystem path from an env var.

Split out of ``_env.py`` so ``_env_paths.py``/``_env_db.py`` (which need this
helper) don't import it back from ``_env.py`` (which imports them) -- that
shape only worked because ``_env.py`` happened to initiate the import cycle
first every time; a direct ``import quodeq.shared._env_paths`` in isolation
would hit a partially-initialized ``_env`` module. This module has no
dependents of its own, so both sides import it with no cycle.
"""
from __future__ import annotations

import os


def _sanitized_env_path(raw: str) -> str:
    """Normalize an operator-supplied filesystem path from an env var.

    Env vars are the operator's own trust domain, but expanduser + abspath
    (which collapses '.' and '..' segments) keeps a stray relative or '~'
    value from resolving somewhere surprising at use time, and gives every
    consumer one canonical absolute form.
    """
    return os.path.abspath(os.path.expanduser(raw))
