"""Application bootstrapping and dependency wiring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.ports.evaluators import EvaluatorsRepository


@dataclass(frozen=True)
class DataProvider:
    """Container for application-level repository dependencies."""
    evaluators: EvaluatorsRepository | None = None

    def require_evaluators(self) -> EvaluatorsRepository:
        """Return evaluators or raise if not configured."""
        if self.evaluators is None:
            raise RuntimeError("DataProvider.evaluators is not configured")
        return self.evaluators


def default_provider(root: Path) -> DataProvider:
    """Create a DataProvider backed by the filesystem adapters."""
    from quodeq.adapters.fs.evaluators_repository import FilesystemEvaluatorsRepository

    return DataProvider(
        evaluators=FilesystemEvaluatorsRepository(root=root),
    )
