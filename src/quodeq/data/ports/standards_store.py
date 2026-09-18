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

    def path(self, evaluators_dir: Path, standard_id: str) -> Path:
        """Return where *standard_id* lives under *evaluators_dir*.

        Pure path arithmetic — the file need not exist.
        """
        ...

    def exists(self, evaluators_dir: Path, standard_id: str) -> bool:
        """True when *standard_id* has a custom file in *evaluators_dir*."""
        ...

    def compiled_exists(self, compiled_dir: Path, standard_id: str) -> bool:
        """True when *standard_id* ships as a compiled built-in.

        The CRUD service uses this to reject ids that would shadow a built-in.
        """
        ...

    def ensure_dir(self, evaluators_dir: Path) -> None:
        """Create *evaluators_dir* and its parents. A no-op when it exists."""
        ...

    def remove(self, evaluators_dir: Path, standard_id: str) -> None:
        """Delete the standard's file. Raises FileNotFoundError when absent."""
        ...

    def read(self, path: Path) -> dict:
        """Return the parsed standard payload at *path*, or None when absent."""
        ...

    def write(self, path: Path, data: dict) -> None:
        """Write *data* as the standard payload, creating parents as needed."""
        ...
