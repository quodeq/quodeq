"""Centralized configuration loading for the Quodeq package.

Provides the :class:`Config` dataclass (via ``_config_class``) and
lazy-loaded default constants read from ``defaults.json``. Delegates to the
canonical process-wide singleton in :mod:`quodeq.shared._config` rather than
keeping a second one here.
"""
from __future__ import annotations

from quodeq.shared._config import _DEFAULTS_PATH, _get_config as _canonical_get_config
from quodeq.shared._config_class import Config  # noqa: F401


def _get_config(override: Config | None = None) -> Config:
    """Return the canonical singleton Config instance.

    Pass *override* to use a specific Config without touching the singleton
    (useful for testing and dependency injection).
    """
    return override if override is not None else _canonical_get_config()


def _lazy_constant(key: str) -> str:
    """Return a config value from the canonical singleton."""
    try:
        return _get_config()[key]
    except KeyError:
        raise KeyError(
            f"Config key {key!r} not found in defaults.json "
            f"({_DEFAULTS_PATH}); the file may be missing or corrupt"
        ) from None


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
