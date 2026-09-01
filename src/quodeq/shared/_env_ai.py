"""Environment-based configuration accessors -- AI provider/CLI selection."""
from __future__ import annotations

import os

from quodeq.shared._config import _get_config


def get_ai_provider(env: dict[str, str] | None = None) -> str:
    """Return the AI provider from environment or default."""
    return (env or os.environ).get("AI_PROVIDER", _get_config()["ai_provider_default"])


def get_ai_cmd(env: dict[str, str] | None = None) -> str:
    """Return the AI CLI command from environment or default.

    Falls back to AI_PROVIDER when AI_CMD is not set, so that
    ``AI_PROVIDER=ollama`` implies ``AI_CMD=ollama`` unless overridden.
    """
    _env = env or os.environ
    if "AI_CMD" in _env:
        return _env["AI_CMD"]
    if "AI_PROVIDER" in _env:
        return _env["AI_PROVIDER"]
    return _get_config()["ai_cmd_default"]


def get_ai_model(env: dict[str, str] | None = None) -> str | None:
    """Return the AI model from environment, or None."""
    return (env or os.environ).get("AI_MODEL") or None


def get_ai_cmd_path(env: dict[str, str] | None = None) -> str | None:
    """Return the binary override for the AI CLI (AI_CMD_PATH), or None.

    When set, spawn sites use this as argv[0] instead of the provider id,
    while the provider id (get_ai_cmd) keeps selecting the ai_providers.json
    entry. Lets an alternate install or wrapper (e.g. a `claude-api` script
    that switches CLAUDE_CONFIG_DIR) run with unchanged provider behavior.
    """
    return (env or os.environ).get("AI_CMD_PATH") or None
