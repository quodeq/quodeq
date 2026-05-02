"""Backfill helpers — extracted from _incremental.py for file-length limits."""
from __future__ import annotations

import json as _json
import os
import time
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.incremental import identify_backfill_files
from quodeq.shared.constants import _DEFAULT_POOL_BUDGET
# NOTE: logging in inner layer — tracked for middleware extraction
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl
from quodeq.shared.logging import log_debug, log_info


_DEFAULT_MIN_BACKFILL_BUDGET_S = 60


def _min_backfill_budget_s() -> int:
    """Return the minimum remaining-budget threshold to start a backfill phase.

    Honours QUODEQ_MIN_BACKFILL_BUDGET_S; falls back to the default on any
    parse error or non-positive value.
    """
    raw = os.environ.get("QUODEQ_MIN_BACKFILL_BUDGET_S")
    if not raw:
        return _DEFAULT_MIN_BACKFILL_BUDGET_S
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MIN_BACKFILL_BUDGET_S
    return value if value > 0 else _DEFAULT_MIN_BACKFILL_BUDGET_S


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
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj = _json.loads(stripped)
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
        try:
            backfill_taken = set(FileQueue(backfill_queue).all_taken_files())
        except (OSError, KeyError, ValueError, _json.JSONDecodeError) as exc:
            log_debug(f"Cannot read backfill queue {backfill_queue}: {exc}")
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
    backfill_candidates = identify_backfill_files(backfill.files, list(backfill.prev_analyzed), backfill.phase1_files)
    output_jsonl = backfill.evidence_dir / f"{dimension}_evidence.jsonl"
    backfill_taken: set[str] = set()

    if not backfill_candidates:
        return backfill_taken

    pool_budget = config.options.pool_budget
    unlimited = pool_budget is not None and pool_budget <= 0

    if not unlimited:
        elapsed = time.monotonic() - backfill.phase_start
        total_budget = pool_budget or _DEFAULT_POOL_BUDGET
        remaining_budget = max(0, total_budget - int(elapsed))

        if remaining_budget < _min_backfill_budget_s():
            log_info(f"  [{dimension}] Backfill: {len(backfill_candidates)} unevaluated files, but no budget remaining")
            return backfill_taken
        log_info(
            f"  [{dimension}] Backfill: {len(backfill_candidates)} unevaluated files, "
            f"{remaining_budget}s budget remaining"
        )
    else:
        remaining_budget = 0  # 0 = unlimited in pool
        log_info(f"  [{dimension}] Backfill: {len(backfill_candidates)} unevaluated files, unlimited budget")

    original_options = config.options
    config.options = copy(original_options)
    config.options.incremental_file_filter = set(backfill_candidates)
    config.options.pool_budget = remaining_budget
    config.options.verify_findings = False
    # Deferred import: circular dependency _dimension_ops → _incremental_evidence → _backfill
    from quodeq.analysis._dimension_ops import _process_single_dimension
    try:
        _process_single_dimension(config, dimension, idx, ctx, emit_log=False)
    finally:
        config.options = original_options

    backfill_taken = _collect_backfill_taken(backfill.evidence_dir, dimension, output_jsonl)
    return backfill_taken
