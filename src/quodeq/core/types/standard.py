"""Data types for custom standards / evaluators."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class StandardReference:
    type: str          # "cwe" | "book" | "url" | "custom"
    label: str
    url: str | None = None


@dataclass(frozen=True, slots=True)
class StandardMeta:
    """Lightweight metadata for listing standards."""
    id: str
    name: str
    description: str
    weight: float
    source: str
    type: str           # "builtin" | "custom" | "community"
    managed: bool
    origin: str | None
    origin_hash: str | None
    principle_count: int = 0
    requirement_count: int = 0


@dataclass(frozen=True, slots=True)
class StandardDetail:
    """Full standard with principles and requirements."""
    id: str
    name: str
    description: str
    weight: float
    source: str
    type: str
    managed: bool
    origin: str | None
    origin_hash: str | None
    principles: list[dict] = field(default_factory=list)
