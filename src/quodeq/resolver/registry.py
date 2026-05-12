"""Language adapter registry."""

from __future__ import annotations

from pathlib import Path

from quodeq.resolver.languages.base import LanguageAdapter


class LanguageNotSupported(LookupError):
    """No registered adapter matches the file's extension."""


_ADAPTERS_BY_EXT: dict[str, LanguageAdapter] = {}


def register(adapter: LanguageAdapter) -> None:
    """Register an adapter for all its declared extensions."""
    for ext in adapter.extensions:
        _ADAPTERS_BY_EXT[ext.lower()] = adapter


def get_adapter_for(path: Path) -> LanguageAdapter:
    """Return the adapter registered for the given file's extension."""
    ext = path.suffix.lower()
    if ext not in _ADAPTERS_BY_EXT:
        raise LanguageNotSupported(f"No adapter registered for extension: {ext!r}")
    return _ADAPTERS_BY_EXT[ext]


def _clear_registry_for_tests() -> None:
    """Reset the registry. Test-only -- not part of the public API."""
    _ADAPTERS_BY_EXT.clear()
