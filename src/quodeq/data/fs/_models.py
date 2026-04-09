"""Data types for project identity resolution."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ProjectRepository(Protocol):
    """Abstraction over the storage layer used to persist project identities.

    Implement this protocol to swap the default filesystem backend for a
    different storage technology (database, cloud object store, etc.) without
    changing any callers of ``resolve_project_uuid``.
    """

    def load_index(self, reports_dir: Path) -> dict[str, str]:
        """Load the name->uuid mapping. Return empty dict on missing/corrupt data."""
        ...

    def save_index(self, reports_dir: Path, index: dict[str, str]) -> None:
        """Persist the name->uuid mapping."""
        ...


@dataclass(frozen=True)
class ProjectIdentity:
    """Identifies a project by name, resolved repo path, and metadata."""
    project_name: str
    repo_path: str
    discipline: str | None = None
    location: str = "local"
    scope_path: str | None = None
