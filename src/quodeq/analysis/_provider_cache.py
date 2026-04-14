"""Provider config cache -- thread-safe lazy loader for ai_providers.json."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_AI_PROVIDERS_PATH = Path(os.environ.get("QUODEQ_AI_PROVIDERS_PATH", str(Path(__file__).resolve().parent.parent / "data" / "config" / "ai_providers.json")))

# Fallback provider configs used when the primary JSON file
# (data/config/ai_providers.json) cannot be loaded.
_PROVIDER_CONFIGS_FALLBACK: dict[str, dict] = {
    "claude": {
        "type": "cli",
        "cmd": "claude",
        "cmd_subcommand": "",
        "base_args": "--print --output-format stream-json --verbose",
        "prompt_style": "flag",
        "prompt_flag": "-p",
        "supports_mcp": True,
        "supports_tools": True,
        "supports_budget": True,
        "supports_turns": True,
        "mcp_permission_args": ["--permission-mode", "bypassPermissions"],
        "env_set_if_missing": {"CODEX_SANDBOX": "read-only"},
        "env_remove": ["CLAUDECODE"],
    },
    "codex": {
        "type": "cli",
        "cmd": "codex",
        "cmd_subcommand": "exec",
        "base_args": "--json --dangerously-bypass-approvals-and-sandbox",
        "prompt_style": "positional",
        "mcp_style": "cli-register",
        "supports_tools": False,
        "supports_budget": False,
        "supports_turns": False,
        "mcp_permission_args": [],
        "env_set_if_missing": {},
        "env_remove": [],
    },
}


class _ProviderConfigCache:
    """Thread-safe lazy cache for provider configurations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._configs: dict[str, dict] | None = None

    def get(self) -> dict[str, dict]:
        if self._configs is None:
            with self._lock:
                if self._configs is None:
                    try:
                        self._configs = json.loads(_AI_PROVIDERS_PATH.read_text())
                    except (OSError, json.JSONDecodeError):
                        self._configs = _PROVIDER_CONFIGS_FALLBACK
        return self._configs


_provider_config_cache = _ProviderConfigCache()


def get_provider_configs() -> dict[str, dict]:
    """Return provider configurations, loading from disk on first call."""
    return _provider_config_cache.get()
