from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PluginDimension:
    """A single quality dimension contributed by a plugin."""

    id: str
    weight: int = 1
    iso_25010: str | None = None


@dataclass(frozen=True, slots=True)
class PluginInfo:
    """Metadata for a detected language plugin (extensions and dimensions)."""

    id: str
    name: str
    extensions: list[str] = field(default_factory=list)
    dimensions: list[PluginDimension] = field(default_factory=list)
