from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.ports.evaluators import EvaluatorsRepository


@dataclass(frozen=True)
class DataProvider:
    evaluators: EvaluatorsRepository | None = None
    dimensions: object | None = None
    reports: object | None = None


def default_provider(root: Path) -> DataProvider:
    """Create a DataProvider backed by the filesystem adapters."""
    from quodeq.adapters.fs.evaluators_repository import FilesystemEvaluatorsRepository

    return DataProvider(
        evaluators=FilesystemEvaluatorsRepository(root=root),
    )
