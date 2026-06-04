"""FindingsRouter: deduplicates and writes findings to JSONL.

Transformation (enrichment, downweights) is delegated to FindingEnricher.
"""
from __future__ import annotations

import io
import json
import logging
import sys
from typing import Callable, Protocol, runtime_checkable

if sys.platform != "win32":
    import fcntl

from quodeq.analysis.mcp.enricher import (
    CompiledContext,
    FileReader,
    FindingEnricher,
)
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from quodeq.core.events.writer import EventLogWriter

_logger = logging.getLogger(__name__)


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
        # Per-line flush is intentional: sibling MCP server processes share
        # the same JSONL output file.  Flushing while the exclusive lock is
        # held guarantees that data reaches disk before the lock is released,
        # preventing data loss on crash and partial-write interleaving.
        fh.flush()
    finally:
        if use_lock:
            fcntl.flock(fh, fcntl.LOCK_UN)


class FindingsRouter:
    """Canonical sink for per-dimension JSONL evidence.

    Every provider path that writes ``<dim>_evidence.jsonl`` MUST go through
    a router instance:

    - **CLI/MCP path:** the agent calls ``report_finding`` and ``mark_file_done``
      MCP tools; the dispatcher in ``mcp/handlers.py`` forwards each call to
      this router via ``receive`` / ``mark_file_done``.
    - **API path:** ``analysis/_api_runner.py`` opens the JSONL,
      constructs a router pointed at that file handle, and calls ``receive``
      per finding plus ``mark_file_done`` per source file on a clean return.
    - **Future paths:** any new provider integration uses this same surface.
      Adding a path that bypasses the router is a regression because the V2
      cache layer (``analysis/cache/dimension_helpers.py``) only persists
      files with a ``mark_file_done: ok`` marker -- without one, every run
      re-dispatches every file.

    Beyond the marker contract, the router owns:
    - Atomic per-line writes via ``_locked_write`` (concurrency-safe).
    - Dedup by (principle, file, line, type) -- skips duplicate findings.
    - Delegates all transformation to ``FindingEnricher``.
    - Returns feedback strings to the LLM for the ``Duplicate`` / ``Recorded``
      flow when called from the MCP handler.
    """

    def __init__(
        self,
        output_fh: TextIO,
        context: CompiledContext | None = None,
        seen_store: DeduplicationStore | None = None,
        file_reader: FileReader | None = None,
        event_log: "EventLogWriter | None" = None,
        on_file_done: "Callable[[str, list[dict]], None] | None" = None,
    ):
        self._fh = output_fh
        self._enricher = FindingEnricher(context or CompiledContext(), file_reader)
        self._seen: DeduplicationStore = seen_store if seen_store is not None else set()
        self._event_log: EventLogWriter | None = event_log
        self._on_file_done: "Callable[[str, list[dict]], None] | None" = on_file_done
        self._findings_by_file: dict[str, list[dict]] = {}
        self.counter = 0

    def receive(self, args: dict) -> tuple[str, bool]:
        """Process a finding. Returns (message, is_duplicate)."""
        key = self._enricher.dedup_key(args)
        if key in self._seen:
            return "Duplicate finding, already captured. Move on.", True
        self._seen.add(key)

        finding = self._enricher.enrich(args)

        line = json.dumps(finding) + "\n"
        _locked_write(self._fh, line)
        if self._event_log is not None:
            self._emit_event(finding)
        if self._on_file_done is not None:
            self._findings_by_file.setdefault(finding["file"], []).append(finding)
        self.counter += 1
        return f"Finding #{self.counter} recorded.", False

    def _emit_event(self, finding: dict) -> None:
        """Emit a JudgmentCreatedEvent to the event log. Never raises."""
        try:
            from quodeq.core.events.models import JudgmentCreatedEvent  # noqa: PLC0415
            from quodeq.core.finding_mappings import wire_dict_to_judgment  # noqa: PLC0415
            payload = wire_dict_to_judgment(finding)
            self._event_log.emit(JudgmentCreatedEvent(payload=payload))
        except Exception:  # noqa: BLE001 — event log must never break JSONL durability
            _logger.warning("FindingsRouter: event log emit failed (JSONL succeeded)", exc_info=True)

    def mark_file_done(self, *, file: str, status: str, reason: str | None = None) -> None:
        """Append a per-file completion marker to the JSONL.

        Used by the cache layer to decide which files are safely cached.
        Lines without a matching ok marker are not persisted as cache hits.

        When ``on_file_done`` was provided at construction:
          - on ``status="ok"``: the callback is invoked synchronously with
            (file, accumulated_findings). The JSONL marker is durable BEFORE
            the callback fires, so a cache-side failure cannot lose the
            worker's completion record.
          - on ``status="error"``: the accumulated findings are popped and
            dropped without invoking the callback. The next run re-dispatches.
        """
        if status not in ("ok", "error"):
            raise ValueError(f"mark_file_done: status must be 'ok' or 'error', got {status!r}")
        payload: dict = {"_marker": "file_done", "file": file, "status": status}
        if reason is not None:
            payload["reason"] = reason
        line = json.dumps(payload) + "\n"
        _locked_write(self._fh, line)
        if self._on_file_done is not None:
            accumulated = self._findings_by_file.pop(file, [])
            if status == "ok":
                try:
                    self._on_file_done(file, accumulated)
                except Exception:  # noqa: BLE001 — callback failure must never lose the ok marker
                    _logger.warning(
                        "FindingsRouter: on_file_done callback raised for %s", file,
                        exc_info=True,
                    )
