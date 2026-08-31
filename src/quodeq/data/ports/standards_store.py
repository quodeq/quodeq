"""File mechanics + payload I/O protocol for the standards CRUD service."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class StandardsStore(Protocol):
    """File mechanics + payload I/O seam for the standards CRUD service.

    The default implementation composes the ``standards_store`` re-exports
    in ``services/_wiring.py`` with the service's injected JSON read/write
    callables (built in ``services/standards.py``); tests can substitute an
    in-memory store.
    """

    def path(self, evaluators_dir: Path, standard_id: str) -> Path: ...

    def exists(self, evaluators_dir: Path, standard_id: str) -> bool: ...

    def compiled_exists(self, compiled_dir: Path, standard_id: str) -> bool: ...

    def ensure_dir(self, evaluators_dir: Path) -> None: ...

    def remove(self, evaluators_dir: Path, standard_id: str) -> None: ...

    def read(self, path: Path) -> dict: ...

    def write(self, path: Path, data: dict) -> None: ...
