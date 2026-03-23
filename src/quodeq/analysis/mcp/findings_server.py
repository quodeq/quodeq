"""MCP tool server: receives findings via tool calls, deduplicates, enriches, writes JSONL.

Protocol: JSON-RPC 2.0 over stdio, newline-delimited JSON (no Content-Length).
No external dependencies.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, TextIO, runtime_checkable

from quodeq.engine.file_queue import FileQueue
from quodeq.analysis.mcp.args import ServerArgs, parse_args
from quodeq.analysis.mcp.dispatch import (
    read_message,
    dispatch as _dispatch,
)
from quodeq.engine._ref_utils import ref_label as _ref_label, load_compiled_refs as _load_compiled_refs
from quodeq.core.standards.refs import load_compiled_requirements as _load_compiled_requirements

_FINDING_SCHEMA_VERSION = 1


@dataclass
class CompiledContext:
    """Grouped compiled-standards data for finding enrichment."""
    compiled_refs: dict[str, list[dict]] = field(default_factory=dict)
    compiled_reqs: dict[str, dict] = field(default_factory=dict)
    req_to_dim: dict[str, str] = field(default_factory=dict)
    dimension: str | None = None


@runtime_checkable
class DeduplicationStore(Protocol):
    """Abstraction for finding deduplication state.

    The default implementation uses a process-local ``set``.  For horizontal
    scaling (multiple MCP server instances), implement this protocol with a
    shared backend (e.g. Redis set) and pass it to ``FindingsRouter``.
    """

    def __contains__(self, key: tuple) -> bool: ...
    def add(self, key: tuple) -> None: ...


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
        compiled_refs: dict[str, list[dict]] | None = None,
        seen_store: DeduplicationStore | None = None,
        compiled_reqs: dict[str, dict] | None = None,
        dimension: str | None = None,
        req_to_dim: dict[str, str] | None = None,
        *,
        context: CompiledContext | None = None,
    ):
        if context is not None:
            compiled_refs = compiled_refs or context.compiled_refs
            compiled_reqs = compiled_reqs or context.compiled_reqs
            req_to_dim = req_to_dim or context.req_to_dim
            dimension = dimension or context.dimension
        self._fh = output_fh
        self._refs = compiled_refs or {}
        self._reqs = compiled_reqs or {}
        self._dimension = dimension
        self._req_to_dim = req_to_dim or {}
        self._seen: DeduplicationStore = seen_store if seen_store is not None else set()
        self.counter = 0

    def _enrich(self, args: dict, finding: dict) -> None:
        """Auto-fill principle, dimension, and refs from compiled standards."""
        req = args.get("req")
        if not req:
            return
        # Auto-fill principle name from req ID
        if not args.get("p") and req in self._reqs:
            finding["p"] = self._reqs[req]["principle"]
        # Auto-fill dimension: prefer req-to-dim mapping (consolidated), fallback to single dimension
        if not args.get("d"):
            if req and req in self._req_to_dim:
                finding["d"] = self._req_to_dim[req]
            elif self._dimension:
                finding["d"] = self._dimension
        # Enrich with compiled standard refs
        if req in self._refs:
            finding["req_refs"] = _select_best_refs(
                self._refs[req], args.get("w", ""), args.get("reason", ""),
            )

    def receive(self, args: dict) -> tuple[str, bool]:
        """Process a finding. Returns (message, is_duplicate)."""
        # Resolve principle name for dedup key (prefer explicit, fall back to lookup)
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

        self._fh.write(json.dumps(finding) + "\n")
        self._fh.flush()
        self.counter += 1
        return f"Finding #{self.counter} recorded.", False


_STOP_WORDS = frozenset({"a", "an", "the", "of", "to", "in", "for", "is", "and", "or", "not", "with", "without"})


def _text_overlap(ref_name: str, description: str, reason: str) -> int:
    """Score how well a ref name matches the finding text by counting shared words."""
    stop = _STOP_WORDS
    ref_words = set(ref_name.lower().split()) - stop
    finding_words = (set(description.lower().split()) | set(reason.lower().split())) - stop
    return len(ref_words & finding_words)


def _select_best_refs(
    all_refs: list[dict], description: str, reason: str,
) -> list[dict]:
    """Pick one ref per source type (CWE, CISQ, etc.), choosing the best text match.

    When no words overlap at all, picks the broadest (first/lowest-ID) ref as a
    safe default rather than an arbitrary specific one.
    """
    by_source: dict[str, list[dict]] = {}
    for ref in all_refs:
        source = ref.get("source", "") or ref.get("label", "").split("-")[0]
        by_source.setdefault(source, []).append(ref)

    result: list[dict] = []
    for source, refs in by_source.items():
        if len(refs) == 1:
            result.append(refs[0])
        else:
            scored = [(r, _text_overlap(r.get("name", ""), description, reason)) for r in refs]
            max_score = max(s for _, s in scored)
            if max_score == 0:
                # No text match -- pick the broadest (first listed, typically the parent)
                result.append(refs[0])
            else:
                result.append(max(scored, key=lambda x: x[1])[0])
    return result


def main() -> None:
    """Run the MCP findings server, reading JSON-RPC from stdin and writing JSONL to a file."""
    sa = parse_args()
    if not sa.findings_file:
        sys.stderr.write(
            "Error: findings output path is required.\n"
            "Usage: mcp_findings.py <findings_file> [--compiled-dir DIR --dimension DIM]"
            " [--queue PATH --agent-id ID]\n"
            "Provide the path where findings JSONL should be written.\n"
        )
        sys.exit(1)

    compiled_refs = _load_compiled_refs(sa.compiled_dir, sa.dimension)
    compiled_reqs = _load_compiled_requirements(sa.compiled_dir, sa.dimension)

    # Build req_id → dimension mapping for consolidated multi-dimension mode
    req_to_dim: dict[str, str] = {}
    if len(sa.dimensions) > 1:
        for dim in sa.dimensions:
            dim_reqs = _load_compiled_requirements(sa.compiled_dir, dim)
            for req_id in dim_reqs:
                req_to_dim[req_id] = dim

    ctx = CompiledContext(
        compiled_refs=compiled_refs or {},
        compiled_reqs=compiled_reqs or {},
        req_to_dim=req_to_dim,
        dimension=sa.dimension,
    )

    queue: FileQueue | None = None
    if sa.queue_path:
        queue = FileQueue(Path(sa.queue_path))

    try:
        with open(sa.findings_file, "a") as findings_fh:
            router = FindingsRouter(findings_fh, context=ctx)
            while True:
                msg = read_message()
                if msg is None:
                    break
                try:
                    _dispatch(msg, router, queue, sa.agent_id)
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError) as exc:
                    sys.stderr.write(f"Dispatch error: {exc}\n")
    except OSError as exc:
        sys.stderr.write(f"Cannot open findings file {sa.findings_file}: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
