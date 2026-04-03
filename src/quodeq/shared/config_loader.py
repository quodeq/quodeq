"""Centralized configuration loading for the Quodeq package.

Provides the :class:`Config` dataclass (via ``_config_class``) and
lazy-loaded default constants read from ``defaults.json``.
"""
from __future__ import annotations

import threading
from pathlib import Path

from quodeq.shared._config_class import Config  # noqa: F401

_DEFAULTS_PATH = Path(__file__).resolve().parent / "defaults.json"

_config_lock = threading.Lock()
# Singleton instance — access via _get_config(override) for DI; reset via _reset_config_for_testing().
_config_instance: Config | None = None


def _get_config(override: Config | None = None) -> Config:
    """Return the lazily-loaded singleton Config instance (thread-safe).

    Pass *override* to use a specific Config without touching the singleton
    (useful for testing and dependency injection).
    """
    if override is not None:
        return override
    global _config_instance
    if _config_instance is None:
        with _config_lock:
            if _config_instance is None:
                _config_instance = Config.from_file(_DEFAULTS_PATH)
    return _config_instance


def _reset_config_for_testing() -> None:
    """Clear the singleton so the next ``_get_config()`` call reloads from disk.

    Intended **only** for test teardown — never call in production code.
    """
    global _config_instance
    with _config_lock:
        _config_instance = None
        _lazy_cache.clear()


# ---------------------------------------------------------------------------
# Lazy accessors for constants derived from defaults.json
# ---------------------------------------------------------------------------
_lazy_cache: dict[str, str] = {}
_lazy_lock = threading.Lock()


def _lazy_constant(key: str) -> str:
    """Return a config value, reading defaults.json on first access."""
    if key not in _lazy_cache:
        with _lazy_lock:
            if key not in _lazy_cache:
                try:
                    _lazy_cache[key] = _get_config()[key]
                except KeyError:
                    raise KeyError(
                        f"Config key {key!r} not found in defaults.json "
                        f"({_DEFAULTS_PATH}); the file may be missing or corrupt"
                    ) from None
    return _lazy_cache[key]


def get_anthropic_api_url() -> str:
    """Return the Anthropic API URL from configuration."""
    return _lazy_constant("anthropic_api_url")


def get_anthropic_api_version() -> str:
    """Return the Anthropic API version from configuration."""
    return _lazy_constant("anthropic_api_version")


def get_default_host() -> str:
    """Return the default host from configuration."""
    return _lazy_constant("default_host")


# Keep module-level names for backward compatibility, but now they are
# computed lazily on first attribute access via __getattr__.
_ATTR_MAP = {
    "ANTHROPIC_API_URL": "anthropic_api_url",
    "ANTHROPIC_API_VERSION": "anthropic_api_version",
    "DEFAULT_HOST": "default_host",
}


def __getattr__(name: str) -> str:
    if name in _ATTR_MAP:
        return _lazy_constant(_ATTR_MAP[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
