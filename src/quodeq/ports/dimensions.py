from __future__ import annotations

from typing import Protocol


class DimensionsRepository(Protocol):
    """Repository for accessing evaluation dimension definitions."""

    def list_dimensions(self) -> list[str]:
        """Return all available dimension identifiers."""
        ...

    def get_dimension(self, name: str) -> dict:
        """Return the full definition for a single dimension by name."""
        ...
