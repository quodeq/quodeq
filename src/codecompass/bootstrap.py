from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codecompass.ports.evaluators import EvaluatorsRepository
from codecompass.ports.practices import PracticesRepository


@dataclass(frozen=True)
class DataProvider:
    practices: PracticesRepository
    dimensions: object | None = None
    evaluators: EvaluatorsRepository | None = None
    reports: object | None = None


def default_provider(root: Path) -> DataProvider:
    """Create a DataProvider backed by the filesystem adapters."""
    from codecompass.adapters.fs.evaluators_repository import FilesystemEvaluatorsRepository
    from codecompass.adapters.fs.practices_repository import FilesystemPracticesRepository

    return DataProvider(
        practices=FilesystemPracticesRepository(root=root),
        evaluators=FilesystemEvaluatorsRepository(root=root),
    )
