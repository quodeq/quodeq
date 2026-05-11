"""Public Resolver API."""

from __future__ import annotations

from pathlib import Path

from quodeq.resolver.cache import IndexCache
from quodeq.resolver.indexer import build_index
from quodeq.resolver.manifest import build_manifest
from quodeq.resolver.models import FindingInput, Manifest


class Resolver:
    """High-level facade over the symbol index + manifest builder."""

    def __init__(
        self,
        project_root: Path,
        db_path: Path | None = None,
        parser_version: str = "0.23.2",
    ) -> None:
        self.project_root = project_root.resolve()
        self.db_path = db_path or (self.project_root / ".quodeq-resolver" / "symbols.db")
        self.cache = IndexCache(self.db_path, parser_version=parser_version)

    def build_index(self) -> int:
        """Walk the project, populate the index. Returns the number of files indexed."""
        return build_index(self.cache, self.project_root)

    def build_manifest(self, finding: FindingInput) -> Manifest:
        return build_manifest(self.cache, self.project_root, finding)

    def close(self) -> None:
        self.cache.close()
