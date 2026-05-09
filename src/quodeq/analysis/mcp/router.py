"""FindingsRouter: deduplicates, enriches, and writes findings to JSONL.

Contains the core routing class and its supporting data types / protocols.
"""
from __future__ import annotations

import io
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, TextIO, runtime_checkable

if sys.platform != "win32":
    import fcntl

from quodeq.analysis.mcp.enrichment import enrich_code
from quodeq.analysis.mcp.ref_scoring import select_best_refs
from quodeq.context.path_role import NON_PROD_ROLES, path_role
from quodeq.context.precedent import fingerprint as _precedent_fingerprint
from quodeq.context.project_shape import Deployment, ProjectShape
from quodeq.data.ports.findings import FindingsRepository
from quodeq.shared._env import sqlite_disabled

_logger = logging.getLogger(__name__)
_FINDING_SCHEMA_VERSION = 1
_NON_PROD_DOWNWEIGHT = 50  # confidence applied to violations on non-prod paths
                           # when the LLM didn't already lower it.
_SHAPE_DOWNWEIGHT = 40  # confidence applied when the finding clearly assumes
                        # a hosted multi-tenant service but the project shape
                        # says single-user desktop / CLI / library.
_PRECEDENT_DOWNWEIGHT = 25  # confidence applied when the finding fingerprint
                            # matches a prior dismissal in this project — the
                            # user has already judged the same code before.

_HOSTED_SERVICE_KEYWORDS: tuple[str, ...] = (
    "concurrent caller", "concurrent callers", "concurrent request",
    "concurrent requests", "thread block", "blocks the thread",
    "blocks thread", "blocks the event loop", "blocks the request thread",
    "distributed state", "distributed system", "distributed lock",
    "multi-tenant", "multitenant", "tenant isolation",
    "rate limit", "rate-limit", "rate limiting",
    "ddos", "denial of service", "denial-of-service",
    "horizontal scaling", "horizontal scale",
)


def _apply_path_role_downweight(finding: dict[str, object]) -> None:
    """Lower a finding's confidence to 50 when it lives on a non-prod path.

    Skipped when the LLM emitted an explicit confidence below the default of
    100 (we trust the model's own self-doubt over a coarse path heuristic)
    and for compliance findings (downweighting "this code is fine" makes
    no sense).
    """
    if finding.get("t") != "violation":
        return
    role = path_role(finding.get("file"))
    if role not in NON_PROD_ROLES:
        return
    existing = finding.get("confidence")
    if existing is None or existing == 100:
        finding["confidence"] = _NON_PROD_DOWNWEIGHT


def _shape_irrelevant_to_hosted_service(shape: ProjectShape | None) -> bool:
    """True when the project clearly isn't a hosted multi-tenant service."""
    if shape is None:
        return False
    if shape.deployment in (Deployment.DESKTOP, Deployment.LIBRARY):
        return True
    if shape.deployment is Deployment.CLI and shape.is_single_user:
        return True
    return False


def _apply_shape_downweight(
    finding: dict[str, object], shape: ProjectShape | None,
) -> None:
    """Downweight findings that clearly assume a hosted service when the
    project is desktop / CLI / library.

    Matches keywords inside the finding's reason / title. The keyword list
    is generic across languages; it isn't tied to any one framework or
    project. Like the path-role downweight, this only fires when the LLM
    didn't already lower confidence.
    """
    if finding.get("t") != "violation":
        return
    if not _shape_irrelevant_to_hosted_service(shape):
        return
    haystack_parts: list[str] = []
    for key in ("reason", "w", "title"):
        val = finding.get(key)
        if isinstance(val, str):
            haystack_parts.append(val.lower())
    haystack = " ".join(haystack_parts)
    if not any(kw in haystack for kw in _HOSTED_SERVICE_KEYWORDS):
        return
    existing = finding.get("confidence")
    if existing is None or existing == 100:
        finding["confidence"] = _SHAPE_DOWNWEIGHT


def _apply_precedent_downweight(
    finding: dict[str, object], fingerprints: set[str] | None,
) -> None:
    """Drop confidence to ~25 when this finding's fingerprint matches a
    finding the user previously dismissed in this project.

    Skipped when:
    * the user has dismissed nothing yet (fingerprints empty / None).
    * the finding is a compliance entry (precedents only suppress noise,
      not "code is fine" signals).
    * the LLM already lowered confidence below 100 (we trust its self-doubt).
    """
    if not fingerprints:
        return
    if finding.get("t") != "violation":
        return
    req = finding.get("req")
    snippet = finding.get("snippet")
    fp = _precedent_fingerprint(
        req if isinstance(req, str) else None,
        snippet if isinstance(snippet, str) else None,
    )
    if fp is None or fp not in fingerprints:
        return
    existing = finding.get("confidence")
    if existing is None or existing == 100:
        finding["confidence"] = _PRECEDENT_DOWNWEIGHT


@dataclass
class CompiledContext:
    """Grouped compiled-standards data for finding enrichment."""
    compiled_refs: dict[str, list[dict]] = field(default_factory=dict)
    compiled_reqs: dict[str, dict] = field(default_factory=dict)
    req_to_dim: dict[str, str] = field(default_factory=dict)
    dimension: str | None = None
    work_dir: Path | None = None
    project_shape: ProjectShape | None = None
    precedent_fingerprints: set[str] = field(default_factory=set)


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
        # Per-line flush is intentional: sibling MCP server processes share
        # the same JSONL output file.  Flushing while the exclusive lock is
        # held guarantees that data reaches disk before the lock is released,
        # preventing data loss on crash and partial-write interleaving.
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
        findings_repo: FindingsRepository | None = None,
    ):
        ctx = context or CompiledContext()
        self._fh = output_fh
        self._refs = ctx.compiled_refs
        self._reqs = ctx.compiled_reqs
        self._dimension = ctx.dimension
        self._req_to_dim = ctx.req_to_dim
        self._seen: DeduplicationStore = seen_store if seen_store is not None else set()
        self._work_dir = ctx.work_dir
        self._project_shape = ctx.project_shape
        self._precedent_fingerprints = ctx.precedent_fingerprints
        self._read_file = file_reader or _default_read_file
        self._findings_repo = findings_repo
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
        _apply_path_role_downweight(finding)
        _apply_shape_downweight(finding, self._project_shape)
        _apply_precedent_downweight(finding, self._precedent_fingerprints)

        line = json.dumps(finding) + "\n"
        _locked_write(self._fh, line)
        if self._findings_repo is not None and not sqlite_disabled():
            try:
                self._findings_repo.insert_finding(finding)
            except Exception:  # noqa: BLE001 — SQLite must never break JSONL durability
                # Dual-write is a safety net during rollout. JSONL is the truth.
                # Log so operators see broken SQLite sinks instead of silent data loss.
                _logger.warning(
                    "FindingsRouter: SQLite dual-write failed (JSONL succeeded)",
                    exc_info=True,
                )
        self.counter += 1
        return f"Finding #{self.counter} recorded.", False

    def mark_file_done(self, *, file: str, status: str, reason: str | None = None) -> None:
        """Append a per-file completion marker to the JSONL.

        Used by the cache layer to decide which files are safely cached.
        Lines without a matching ok marker are not persisted as cache hits.
        """
        if status not in ("ok", "error"):
            raise ValueError(f"mark_file_done: status must be 'ok' or 'error', got {status!r}")
        payload: dict = {"_marker": "file_done", "file": file, "status": status}
        if reason:
            payload["reason"] = reason
        line = json.dumps(payload) + "\n"
        _locked_write(self._fh, line)
