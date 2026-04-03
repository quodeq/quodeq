"""Config dataclass for centralized configuration."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


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
        try:
            from quodeq.shared.utils import read_json
            obj._data = read_json(path)
        except (OSError, ValueError) as exc:
            import logging
            logging.getLogger(__name__).warning("Failed to load config from %s: %s", path, exc)
            obj._data = {}
        return obj
