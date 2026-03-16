from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PluginDimension:
    id: str
    weight: int = 1
    iso_25010: str | None = None


@dataclass(frozen=True, slots=True)
class PluginInfo:
    id: str
    name: str
    extensions: list[str] = field(default_factory=list)
    dimensions: list[PluginDimension] = field(default_factory=list)
