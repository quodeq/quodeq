"""FindingsRouter: deduplicates, enriches, and writes findings to JSONL.

Contains the core routing class and its supporting data types / protocols.
"""
from __future__ import annotations

import io
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, TextIO, runtime_checkable

if sys.platform != "win32":
    import fcntl

from quodeq.analysis.mcp.enrichment import enrich_code
from quodeq.analysis.mcp.ref_scoring import select_best_refs

_FINDING_SCHEMA_VERSION = 1


@dataclass
class CompiledContext:
    """Grouped compiled-standards data for finding enrichment."""
    compiled_refs: dict[str, list[dict]] = field(default_factory=dict)
    compiled_reqs: dict[str, dict] = field(default_factory=dict)
    req_to_dim: dict[str, str] = field(default_factory=dict)
    dimension: str | None = None
    work_dir: Path | None = None


@runtime_checkable
class FileReader(Protocol):
    """Abstraction for reading source file content."""
    def __call__(self, path: Path) -> str: ...


@runtime_checkable
class DeduplicationStore(Protocol):
    """Abstraction for finding deduplication state.

    The default implementation uses a process-local ``set``.  For horizontal
    scaling (multiple MCP server instances), implement this protocol with a
    shared backend (e.g. Redis set) and pass it to ``FindingsRouter``.
    """

    def __contains__(self, key: tuple) -> bool: ...
    def add(self, key: tuple) -> None: ...


def _locked_write(fh: TextIO, line: str) -> None:
    """Write a line to *fh*, holding an exclusive POSIX lock when possible.

    The lock protects against concurrent writes from sibling MCP server
    processes that share the same JSONL output file.  Falls back to a plain
    write when the file handle doesn't support ``fileno()`` (e.g. StringIO
    in tests) or on Windows.
    """
    use_lock = sys.platform != "win32"
    if use_lock:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX)
        except (OSError, io.UnsupportedOperation):
            use_lock = False
    try:
        fh.write(line)
        fh.flush()
    finally:
        if use_lock:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _default_read_file(path: Path) -> str:
    return path.read_text()


class FindingsRouter:
    """Deduplicates and enriches findings before writing to JSONL.

    - Dedup by (principle, file, line, type) -- skips duplicate findings
    - Auto-fills principle name (p) and dimension (d) from req ID
    - Enriches req_refs from compiled standards -- LLM doesn't need to pick refs
    - Returns feedback to the LLM so it can move on from duplicates
    """

    def __init__(
        self,
        output_fh: TextIO,
        context: CompiledContext | None = None,
        seen_store: DeduplicationStore | None = None,
        file_reader: FileReader | None = None,
    ):
        ctx = context or CompiledContext()
        self._fh = output_fh
        self._refs = ctx.compiled_refs
        self._reqs = ctx.compiled_reqs
        self._dimension = ctx.dimension
        self._req_to_dim = ctx.req_to_dim
        self._seen: DeduplicationStore = seen_store if seen_store is not None else set()
        self._work_dir = ctx.work_dir
        self._read_file = file_reader or _default_read_file
        self.counter = 0

    def _enrich(self, args: dict, finding: dict) -> None:
        """Auto-fill principle, dimension, and refs from compiled standards."""
        req = args.get("req")
        if not req:
            return
        if not args.get("p") and req in self._reqs:
            finding["p"] = self._reqs[req]["principle"]
        if not args.get("d"):
            if req and req in self._req_to_dim:
                finding["d"] = self._req_to_dim[req]
            elif self._dimension:
                finding["d"] = self._dimension
        if req in self._refs:
            finding["req_refs"] = select_best_refs(
                self._refs[req], args.get("w", ""), args.get("reason", ""),
            )

    def receive(self, args: dict) -> tuple[str, bool]:
        """Process a finding. Returns (message, is_duplicate)."""
        p = args.get("p")
        req = args.get("req")
        if not p and req and req in self._reqs:
            p = self._reqs[req]["principle"]
        key = (p, args.get("file"), args.get("line"), args.get("t"))
        if key in self._seen:
            return "Duplicate finding, already captured. Move on.", True
        self._seen.add(key)

        finding: dict = {"schema_version": _FINDING_SCHEMA_VERSION}
        finding.update({k: v for k, v in args.items() if v is not None})
        self._enrich(args, finding)
        enrich_code(finding, self._work_dir, self._read_file)

        line = json.dumps(finding) + "\n"
        _locked_write(self._fh, line)
        self.counter += 1
        return f"Finding #{self.counter} recorded.", False
