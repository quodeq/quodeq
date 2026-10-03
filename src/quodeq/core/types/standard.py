"""Data types for custom standards / evaluators."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class StandardReference:
    """An external citation backing a requirement. ``url`` is absent for book refs."""

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
    type: str           # "iso" | "quodeq" | "wcag" | "custom" | "community"
    managed: bool
    origin: str | None
    origin_hash: str | None
    principle_count: int = 0
    requirement_count: int = 0
    subtype: str | None = None  # the family's edition: "25010" (ISO), "2.2" (WCAG)
    version: str | None = None  # that edition's revision: "2023"; quodeq's own release for quodeq standards


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
    subtype: str | None = None  # the family's edition: "25010" (ISO), "2.2" (WCAG)
    version: str | None = None  # that edition's revision: "2023"; quodeq's own release for quodeq standards
