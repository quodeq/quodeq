"""Credential loading and file-batching helpers for the direct API runner.

Split out of subprocess.py: per-provider credential loaders keyed by AI_CMD,
queue-aware source-file gathering for API dispatch, and greedy size-budgeted
batching of files so one model call's inlined content stays within budget.
``_CREDENTIAL_LOADERS`` is a patch target's dependency (read by
``subprocess._resolve_provider_config``, which stays in subprocess.py), so it
is re-exported there; nothing here is itself patched by name.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from quodeq.analysis import dispatch_policy
from quodeq.analysis._api_standards_text import _gather_source_files
from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis.subagents.file_queue import FileQueue

_log = logging.getLogger(__name__)


def _read_omlx_key() -> str | None:
    from quodeq.llm_bridge._omlx import _read_omlx_api_key  # noqa: PLC0415
    return _read_omlx_api_key()


# Registry of provider-specific credential loaders. Each callable returns the
# API key string (or None/empty string) for that provider. New providers can
# be added here without touching _resolve_provider_config.
_CREDENTIAL_LOADERS: dict[str, Callable[[], str | None]] = {
    "omlx": _read_omlx_key,
}


def _gather_api_source_files(
    work_dir: Path, cfg: AnalysisConfig, jsonl_file: Path, stream_file: Path,
) -> list[Path] | None:
    """Gather source files from queue or by scanning.

    Returns None (and writes empty output) when the queue is exhausted.
    """
    if cfg.queue_path and cfg.queue_path.exists():
        queue = FileQueue(cfg.queue_path)
        taken = queue.take(count=min(cfg.max_files_per_agent or 10, 3), agent_id=cfg.agent_id)
        # Enumeration applies the same predicate, so dropped files here mean
        # the file changed (or vanished) between queue build and dispatch.
        dispatchable, dropped = dispatch_policy.split_api_dispatchable(work_dir, taken)
        if dropped:
            # Lazy import keeps the baseline-pinned llm_bridge line above
            # from shifting; the marker helper is router-owned wire format.
            from quodeq.analysis.mcp.router import write_skip_markers  # noqa: PLC0415
            write_skip_markers(
                jsonl_file, dropped,
                reason=(
                    f"skipped: missing or over the API file-size cap "
                    f"({dispatch_policy.api_file_size_cap()} bytes)"
                ),
            )
        source_files = [work_dir / f for f in dispatchable]
        _log.debug("Took %d files from queue for API analysis", len(source_files))
        if not source_files:
            # Don't touch jsonl_file — it's the SHARED `{dim}_evidence.jsonl`
            # that every agent in the pool appends to via MCP. Truncating it
            # here wipes findings from every other agent in the pool.
            stream_file.write_text('{"type":"api_runner","status":"complete"}\n', encoding="utf-8")
            return None
        return source_files
    return _gather_source_files(work_dir)


def _batch_files_by_size(files: list[Path], budget: int) -> list[list[Path]]:
    """Greedy, order-preserving split so one model call's inlined file
    content stays within *budget* bytes.

    A single file over the budget still dispatches solo: the call may come
    back truncated, but then only that file gets the error marker and
    re-dispatches, instead of dragging its batchmates down with it.
    """
    batches: list[list[Path]] = []
    current: list[Path] = []
    current_size = 0
    for f in files:
        try:
            size = f.stat().st_size
        except OSError:
            size = 0
        if current and current_size + size > budget:
            batches.append(current)
            current, current_size = [], 0
        current.append(f)
        current_size += size
    if current:
        batches.append(current)
    return batches
