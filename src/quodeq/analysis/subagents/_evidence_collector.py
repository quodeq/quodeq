"""Evidence collection, deduplication, and parsing after subagent pool runs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quodeq.analysis._types import RunConfig
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.analysis.subagents.pool import SubagentPool
from quodeq.analysis.fingerprint import build_fingerprint, save_fingerprint as _default_save
from quodeq.analysis.subagents._pool_launcher import _collect_all_evidence
from quodeq.engine._runner_markers import cleanup_stream


@dataclass
class _CollectionContext:
    """Grouped parameters for collecting evidence after a subagent pool run."""
    results: list[Any]
    ctx: Any
    files: list[str] | None = None
    save_fingerprint_fn: Any = None


def _collect_evidence(
    config: RunConfig, dim_id: str, evidence_dir: Path,
    collection: _CollectionContext,
) -> Evidence:
    """Deduplicate JSONL, count files read, save fingerprint, and parse into Evidence.

    *collection.save_fingerprint_fn* is an injectable ``(fingerprint, dir) -> None``
    for persistence; defaults to ``analysis.fingerprint.save_fingerprint``.
    """
    _save = collection.save_fingerprint_fn or _default_save

    merged_jsonl = evidence_dir / f"{dim_id}_evidence.jsonl"
    SubagentPool.deduplicate_jsonl(merged_jsonl)

    total_files_read = _collect_all_evidence(collection.results, cleanup_stream)

    # Save fingerprint so next run can carry forward unchanged-file findings
    if collection.files:
        fp = build_fingerprint(config.src, collection.files, dim_id, config.standards_dir)
        _save(fp, evidence_dir)

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
        ),
        compiled_dir=compiled_dir,
        evaluators_dir=config.evaluators_dir,
    )
    return ev
