"""Rung 3 of the access ladder: a GitHub CLI login the user already has.

``gh auth token`` prints the token of the active ``gh`` login. gh is
GitHub's own OAuth app, so this needs no quodeq registration and no org
approval. Read-only: quodeq never runs ``gh auth login`` itself.
"""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from quodeq.shared.env_resolve import resolve_env

GH_BIN = "gh"
GH_TOKEN_TIMEOUT_S = 5


@dataclass(frozen=True)
class GhStatus:
    """Status of a GitHub CLI login: whether gh exists, is logged in, and its token."""

    available: bool  # gh is on PATH
    logged_in: bool  # `gh auth token` answered a token
    token: str | None = field(default=None, repr=False)


def gh_status(
    *, env: Mapping[str, str] | None = None,
    which: Callable[..., str | None] = shutil.which,
    run: Callable[..., object] = subprocess.run,
) -> GhStatus:
    """Whether gh exists and is logged in, with its token when it is. Never raises."""
    resolved = resolve_env(env)
    gh = which(GH_BIN, path=resolved.get("PATH"))
    if not gh:
        return GhStatus(False, False)
    try:
        proc = run(
            [gh, "auth", "token"], env=dict(resolved), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=GH_TOKEN_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return GhStatus(True, False)
    token = (getattr(proc, "stdout", "") or "").strip()
    if getattr(proc, "returncode", 1) != 0 or not token:
        return GhStatus(True, False)
    return GhStatus(True, True, token)
