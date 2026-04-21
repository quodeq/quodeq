"""Incremental analysis — evidence parsing and fingerprint saving."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis._backfill import extract_files_from_jsonl
from quodeq.analysis.fingerprint import build_fingerprint, save_fingerprint
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents._source_files import _list_source_files
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.shared.logging import log_debug

# Re-export for backward compatibility
_extract_files_from_jsonl = extract_files_from_jsonl


def save_dimension_fingerprint(
    config: RunConfig, dimension: str, files: list[str] | None = None,
    analyzed_files: set[str] | None = None,
) -> None:
    """Save a fingerprint after any successful dimension analysis.

    Skipped in PR diff mode (skip_scoring=True) — PR runs don't persist any
    artifacts that would be consumed by future incremental runs.
    """
    if config.options.skip_scoring:
        return
    try:
        evidence_dir = config.work_dir or config.src
        if files is None:
            files, _ = _list_source_files(config, dimension, ignore_file_filter=True)
        if analyzed_files is None:
            queue_files: set[str] = set()
            queue_path = evidence_dir / f"{dimension}_queue.json"
            if queue_path.exists():
                try:
                    queue_files = set(FileQueue(queue_path).all_taken_files())
                except (OSError, ValueError, KeyError) as exc:
                    log_debug(f"  [{dimension}] Could not read file queue: {exc}")
            jsonl_files = extract_files_from_jsonl(evidence_dir / f"{dimension}_evidence.jsonl")
            analyzed_files = queue_files | jsonl_files
        fp = build_fingerprint(config.src, files, dimension, config.standards_dir, analyzed_files=analyzed_files)
        save_fingerprint(fp, evidence_dir)
    except (OSError, ValueError, TypeError) as exc:
        log_debug(f"  [{dimension}] Fingerprint save failed: {exc}")


def parse_evidence_from_jsonl(
    config: RunConfig, dimension: str, ctx: _AnalysisContext,
    jsonl_file: Path, files_read: int,
) -> Evidence | None:
    """Parse a JSONL file into Evidence."""
    # File existence check is necessary — evidence may not exist yet for new dimensions.
    if not jsonl_file.exists() or jsonl_file.stat().st_size == 0:
        return None
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    return parse_jsonl_to_evidence(
        jsonl_file,
        EvidenceContext(
            language=config.language, repository=str(config.src),
            date_str=ctx.date_str, source_file_count=config.source_file_count,
            files_read=files_read, module=config.target.name if config.target else "",
        ),
        compiled_dir=compiled_dir,
        evaluators_dir=config.evaluators_dir,
    )
