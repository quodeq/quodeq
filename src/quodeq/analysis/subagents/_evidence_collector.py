"""Evidence collection, deduplication, and parsing after subagent pool runs.

Post-V2 (B6.2): the V1 per-dimension fingerprint write is gone. The
V2 cache owns incremental state via per-file entries written during
dispatch (see ``cache/dimension_helpers.py:persist_dispatch_results``).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quodeq.analysis._types import RunConfig
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.analysis.subagents.pool import SubagentPool
from quodeq.analysis.subagents._pool_launcher import _collect_all_evidence
from quodeq.engine._runner_markers import cleanup_stream


@dataclass
class _CollectionContext:
    """Grouped parameters for collecting evidence after a subagent pool run."""
    results: list[Any]
    ctx: Any
    files: list[str] | None = None
    exit_reason: str | None = None


def _collect_evidence(
    config: RunConfig, dim_id: str, evidence_dir: Path,
    collection: _CollectionContext,
) -> Evidence:
    """Deduplicate JSONL, count files read, and parse into Evidence."""
    merged_jsonl = evidence_dir / f"{dim_id}_evidence.jsonl"
    SubagentPool.deduplicate_jsonl(merged_jsonl)

    total_files_read = _collect_all_evidence(collection.results, cleanup_stream)

    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    ev = parse_jsonl_to_evidence(
        merged_jsonl,
        EvidenceContext(
            language=config.language,
            repository=str(config.src),
            date_str=collection.ctx.date_str,
            source_file_count=config.source_file_count,
            files_read=total_files_read,
            module=config.target.name if config.target else "",
            exit_reason=collection.exit_reason,
        ),
        compiled_dir=compiled_dir,
        evaluators_dir=config.evaluators_dir,
    )
    return ev
