"""Config dataclass and lazy singleton loader."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from quodeq.shared._io import read_json

_DEFAULTS_PATH = Path(__file__).resolve().parent / "defaults.json"

# Derived constants (not URLs, safe to keep inline).
ACTION_API_MODULE = "quodeq.api.app"


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
        obj._data = read_json(path)
        return obj


class _ConfigHolder:
    """Thread-safe lazy holder for the singleton Config instance."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._instance: Config | None = None

    def get(self) -> Config:
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self._instance = Config.from_file(_DEFAULTS_PATH)
        return self._instance


_config_holder = _ConfigHolder()


def _get_config() -> Config:
    """Return the lazily-loaded singleton Config instance (thread-safe)."""
    return _config_holder.get()
