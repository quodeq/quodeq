"""Dedicated Codex CLI home for evaluations.

``codex exec`` loads every MCP server, plugin and skill in its home
(``~/.codex``), and --disable shell_tool does not unload them: a user's
node REPL server alone gives the agent full filesystem access. Evaluations
and assistant turns therefore run with ``CODEX_HOME`` set to a Quodeq-owned dir holding only the
user's login and an empty config.
"""
from __future__ import annotations

import shutil
import threading
from collections.abc import Mapping
from pathlib import Path

from quodeq.shared.env_paths import get_quodeq_dir
from quodeq.shared.env_resolve import resolve_env

_HOME_LOCK = threading.Lock()
_OWNER_RW = 0o600
_OWNER_RWX = 0o700
_AUTH_FILE = "auth.json"
_CONFIG_FILE = "config.toml"
# The ChatGPT login also brings account-level tools (the codex_apps connector:
# site deploys, credentials, plugin and parental-control changes), a browser,
# image generation and sub-agents. The OS sandbox cannot stop network calls to
# OpenAI, so they are switched off here; a scan only needs the shell and MCP.
_DISABLED_FEATURES = (
    "apps", "plugins", "browser_use", "browser_use_external",
    "browser_use_full_cdp_access", "image_generation", "multi_agent", "goals",
    "memories",
)
_CONFIG = (
    "# Managed by Quodeq: no MCP servers, plugins, skills or account apps.\n"
    'web_search = "disabled"\n\n[tools]\nweb_search = false\n\n[features]\n'
    + "".join(f"{name} = false\n" for name in _DISABLED_FEATURES)
)


def user_codex_home(env: Mapping[str, str] | None = None) -> Path:
    """The user's own Codex home, where ``codex login`` stored the credentials."""
    env = resolve_env(env)
    raw = env.get("CODEX_HOME")
    home = env.get("HOME")
    return Path(raw) if raw else (Path(home) if home else Path.home()) / ".codex"


def dedicated_codex_home_path(env: Mapping[str, str] | None = None) -> Path:
    """``<QUODEQ_DIR>/codex`` (``~/.quodeq/codex`` by default), not prepared."""
    return get_quodeq_dir(dict(resolve_env(env))) / "codex"


def dedicated_codex_home(env: Mapping[str, str] | None = None) -> Path:
    """The dedicated home, prepared: login copied in when newer, config reset.

    Codex refreshes tokens in place, so the copy only moves forward: a newer
    auth.json from the user's home replaces ours, an older one never does.
    """
    target = dedicated_codex_home_path(env)
    source_auth = user_codex_home(env) / _AUTH_FILE
    with _HOME_LOCK:
        target.mkdir(parents=True, exist_ok=True, mode=_OWNER_RWX)
        target.chmod(_OWNER_RWX)
        auth = target / _AUTH_FILE
        if source_auth.is_file() and (
                not auth.exists() or source_auth.stat().st_mtime > auth.stat().st_mtime):
            shutil.copy2(source_auth, auth)
            auth.chmod(_OWNER_RW)
        config = target / _CONFIG_FILE
        if not config.exists() or config.read_text(encoding="utf-8") != _CONFIG:
            config.write_text(_CONFIG, encoding="utf-8")
            config.chmod(_OWNER_RW)
        for extra in ("plugins", "skills"):
            shutil.rmtree(target / extra, ignore_errors=True)
    return target
