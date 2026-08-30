"""Provider config cache -- thread-safe lazy loader for ai_providers.json."""
from __future__ import annotations

import json
import threading

from quodeq.shared.provider_env import _providers_path

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
        "mcp_strict_args": ["--strict-mcp-config"],
        "env_set_if_missing": {"CODEX_SANDBOX": "read-only"},
        "env_remove": ["CLAUDECODE"],
    },
    "codex": {
        "type": "cli",
        "cmd": "codex",
        "cmd_subcommand": "exec",
        "base_args": "--json --dangerously-bypass-approvals-and-sandbox",
        "prompt_style": "positional",
        "mcp_style": "config-arg",
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
                        self._configs = json.loads(_providers_path().read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        self._configs = _PROVIDER_CONFIGS_FALLBACK
        return self._configs

    def reset(self) -> None:
        """Drop the cached configs, forcing the next :meth:`get` to reload."""
        with self._lock:
            self._configs = None


_provider_config_cache = _ProviderConfigCache()


def get_provider_configs(*, cache: _ProviderConfigCache | None = None) -> dict[str, dict]:
    """Return provider configurations, loading from disk on first call.

    Reads (and lazily populates) *cache*, defaulting to the module-wide
    instance production code shares.
    """
    return (cache or _provider_config_cache).get()


def reset_provider_config_cache() -> None:
    """Reset the module-wide provider config cache. Test-isolation seam."""
    _provider_config_cache.reset()
