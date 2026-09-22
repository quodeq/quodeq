"""Config dataclass and lazy singleton loader."""
from __future__ import annotations

import threading
from collections.abc import Mapping
from pathlib import Path

from quodeq.shared._config_class import Config
from quodeq.shared.env_resolve import resolve_env

__all__ = ["ACTION_API_MODULE", "Config", "defaults_path"]


def defaults_path(env: Mapping[str, str] | None = None) -> Path:
    """Path of ``defaults.json``; ``QUODEQ_DEFAULTS_PATH`` overrides the bundled file.

    Read when the config is first loaded, not when this module is imported,
    so the variable is honoured however late it is set (and an injected
    *env* is honoured at all).
    """
    raw = resolve_env(env).get("QUODEQ_DEFAULTS_PATH")
    return Path(raw) if raw else Path(__file__).resolve().parent / "defaults.json"


# Derived constants (not URLs, safe to keep inline).
ACTION_API_MODULE = "quodeq.api.app"


class _ConfigHolder:
    """Thread-safe lazy holder for the singleton Config instance."""

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self._lock = threading.Lock()
        self._instance: Config | None = None
        self._env = env

    def get(self) -> Config:
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self._instance = Config.from_file(defaults_path(self._env))
        return self._instance


_config_holder = _ConfigHolder()


def _get_config() -> Config:
    """Return the lazily-loaded singleton Config instance (thread-safe)."""
    return _config_holder.get()
