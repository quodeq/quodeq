"""Centralized configuration loading for the Quodeq package.

Provides the :class:`Config` dataclass and lazy-loaded default constants
read from ``defaults.json``.
"""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

_DEFAULTS_PATH = Path(__file__).resolve().parent / "defaults.json"


@dataclass
class Config:
    """Centralized configuration holder loaded from defaults.json.

    Replaces raw module-level mutable dict with a testable object that
    supports safe overrides via the :meth:`override` context manager.
    """

    _data: dict[str, Any] = field(default_factory=dict, init=False)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def update(self, **overrides: Any) -> None:
        self._data.update(overrides)

    @contextmanager
    def override(self, **overrides: Any) -> Iterator[None]:
        """Temporarily override config values; restores originals on exit."""
        saved = {k: self._data[k] for k in overrides if k in self._data}
        removed = {k for k in overrides if k not in self._data}
        self._data.update(overrides)
        try:
            yield
        finally:
            self._data.update(saved)
            for k in removed:
                self._data.pop(k, None)

    @classmethod
    def from_file(cls, path: Path) -> Config:
        obj = cls()
        obj._data = json.loads(path.read_text())
        return obj


_config_lock = threading.Lock()
_config_instance: Config | None = None


def _get_config() -> Config:
    """Return the lazily-loaded singleton Config instance (thread-safe)."""
    global _config_instance
    if _config_instance is None:
        with _config_lock:
            if _config_instance is None:
                _config_instance = Config.from_file(_DEFAULTS_PATH)
    return _config_instance


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
                _lazy_cache[key] = _get_config()[key]
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
