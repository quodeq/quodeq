"""Backfill helpers — extracted from _incremental.py for file-length limits."""
from __future__ import annotations

import json as _json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.analysis.incremental import identify_backfill_files
from quodeq.services.base import _DEFAULT_POOL_BUDGET
from quodeq.shared.logging import log_debug, log_info

if TYPE_CHECKING:
    from quodeq.analysis.runner import RunConfig, _AnalysisContext


_MIN_BACKFILL_BUDGET_S = 60


@dataclass
class BackfillContext:
    """Grouped backfill-specific parameters for _run_backfill_phase."""
    files: list[str]
    prev_analyzed: set[str]
    phase1_files: set[str]
    evidence_dir: Path
    phase_start: float


def extract_files_from_jsonl(jsonl_path: Path) -> set[str]:
    """Extract unique file paths from an evidence JSONL file.

    Returns all distinct ``file`` values found in JSONL entries.
    Skips malformed lines and entries without a valid file path.
    """
    if not jsonl_path.exists():
        return set()
    files: set[str] = set()
    try:
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                file_path = obj.get("file")
                if file_path:
                    files.add(file_path)
    except OSError as exc:
        log_debug(f"Cannot read JSONL {jsonl_path}: {exc}")
    return files


def _collect_backfill_taken(evidence_dir: Path, dimension: str, output_jsonl: Path) -> set[str]:
    """Read taken backfill files from queue and deduplicate the output JSONL."""
    backfill_taken: set[str] = set()
    backfill_queue = evidence_dir / f"{dimension}_queue.json"
    if backfill_queue.exists():
        from quodeq.analysis.subagents.file_queue import FileQueue
        try:
            backfill_taken = set(FileQueue(backfill_queue).all_taken_files())
        except Exception as exc:
            log_debug(f"Cannot read backfill queue {backfill_queue}: {exc}")
    from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl
    if output_jsonl.exists():
        deduplicate_jsonl(output_jsonl)
    return backfill_taken


def run_backfill_phase(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
    backfill: BackfillContext,
) -> set[str]:
    """Phase 3: backfill previously-unevaluated files with remaining budget.

    Returns the set of backfill files actually taken.
    """
    from quodeq.analysis.runner import _process_single_dimension

    backfill_candidates = identify_backfill_files(backfill.files, list(backfill.prev_analyzed), backfill.phase1_files)
    output_jsonl = backfill.evidence_dir / f"{dimension}_evidence.jsonl"
    backfill_taken: set[str] = set()

    if not backfill_candidates:
        return backfill_taken

    elapsed = time.monotonic() - backfill.phase_start
    total_budget = config.options.pool_budget or _DEFAULT_POOL_BUDGET
    remaining_budget = max(0, total_budget - int(elapsed))

    if remaining_budget < _MIN_BACKFILL_BUDGET_S:
        log_info(f"  [{dimension}] Backfill: {len(backfill_candidates)} unevaluated files, but no budget remaining")
        return backfill_taken

    log_info(
        f"  [{dimension}] Backfill: {len(backfill_candidates)} unevaluated files, "
        f"{remaining_budget}s budget remaining"
    )
    config.options.incremental_file_filter = set(backfill_candidates)
    saved_budget = config.options.pool_budget
    saved_verify = config.options.verify_findings
    config.options.pool_budget = remaining_budget
    config.options.verify_findings = False
    try:
        _process_single_dimension(config, dimension, idx, ctx, emit_log=False)
    finally:
        config.options.incremental_file_filter = None
        config.options.pool_budget = saved_budget
        config.options.verify_findings = saved_verify

    backfill_taken = _collect_backfill_taken(backfill.evidence_dir, dimension, output_jsonl)
    return backfill_taken
