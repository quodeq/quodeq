"""Dedicated Antigravity CLI (agy) home for scans and assistant turns.

agy keeps everything under ``$HOME/.gemini``: one global MCP config, the
user's own rules (GEMINI.md, AGENTS.md), plugins, hooks and skills, and the
saved tool outputs of every conversation (``brain/``), which agy writes to a
file whenever a result passes 10 KB and the model then reads back. Quodeq
runs agy with ``HOME`` set to a Quodeq-owned dir instead, so a scan loads
none of the user's customizations, never writes its MCP server into the
user's config, and the saved outputs it may read are only Quodeq's own.

The Google login stays the user's: agy reads it from the macOS keychain,
which it finds under ``$HOME/Library/Keychains``, so that dir is a link to
the user's. The MCP servers agy starts get the user's ``HOME`` back.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from pathlib import Path

from quodeq.core.types.provider import Provider
from quodeq.shared.env_paths import get_quodeq_dir
from quodeq.shared.env_resolve import resolve_env

_log = logging.getLogger(__name__)
_HOME_LOCK = threading.Lock()
_OWNER_RWX = 0o700
_KEYCHAINS = Path("Library") / "Keychains"
_BRAIN = Path(".gemini") / "antigravity-cli" / "brain"
_MCP_ENV_FLAG = "-e"  # `agy mcp add -e KEY=value`, before the server name


def user_home(env: Mapping[str, str] | None = None) -> Path:
    """The user's own home, as the env (else the OS) names it."""
    home = resolve_env(env).get("HOME")
    return Path(home) if home else Path.home()


def dedicated_agy_home_path(env: Mapping[str, str] | None = None) -> Path:
    """``<QUODEQ_DIR>/agy`` (``~/.quodeq/agy`` by default), not prepared."""
    return get_quodeq_dir(dict(resolve_env(env))) / "agy"


def dedicated_agy_home(env: Mapping[str, str] | None = None) -> Path:
    """The dedicated home, created with its keychain link when missing."""
    home = dedicated_agy_home_path(env)
    keychains = user_home(env) / _KEYCHAINS
    with _HOME_LOCK:
        home.mkdir(mode=_OWNER_RWX, parents=True, exist_ok=True)
        link = home / _KEYCHAINS
        if keychains.is_dir() and not link.is_symlink() and not link.exists():
            link.parent.mkdir(mode=_OWNER_RWX, exist_ok=True)
            try:
                link.symlink_to(keychains)
            except OSError as exc:  # no link privilege: agy then asks to sign in again
                _log.warning("Could not link %s into the agy home %s: %s", keychains, home, exc)
    return home


def agy_brain_dir(env: Mapping[str, str] | None = None) -> Path:
    """Where agy, run from the dedicated home, saves oversized tool outputs."""
    return dedicated_agy_home_path(env) / _BRAIN


def mcp_register_overrides(
    cmd: str, env: Mapping[str, str] | None = None,
) -> tuple[dict[str, str] | None, list[str]]:
    """``(env, flags)`` for ``<cmd> mcp add/remove``: for agy, the process env
    with the dedicated ``HOME`` (the registration lands in Quodeq's config,
    not the user's) and the flags giving the server the user's ``HOME``;
    ``(None, [])`` for every other CLI."""
    if cmd != Provider.AGY:
        return None, []
    source = dict(resolve_env(env))
    real_home = user_home(source)
    return ({**source, "HOME": str(dedicated_agy_home(source))},
            [_MCP_ENV_FLAG, f"HOME={real_home}"])
