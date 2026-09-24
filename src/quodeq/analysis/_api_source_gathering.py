"""Credential loading and file-batching helpers for the direct API runner.

Split out of subprocess.py: per-provider credential loaders keyed by AI_CMD,
queue-aware source-file gathering for API dispatch, and greedy size-budgeted
batching of files so one model call's inlined content stays within budget.
``CREDENTIAL_LOADERS`` is a patch target's dependency (read by
``subprocess._resolve_provider_config``, which stays in subprocess.py), so it
is re-exported there; nothing here is itself patched by name.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path

from quodeq.analysis import dispatch_policy
from quodeq.analysis._api_standards_text import gather_source_files
from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis.subagents.file_queue import FileQueue

_log = logging.getLogger(__name__)

# The API runner's stream-done marker: a distinct artifact from the run-list/
# RunState vocabulary (it is never written to status.json), so it gets its
# own name rather than borrowing a RunState-shaped string. Shared by
# subprocess.py's clean-finish write and this module's queue-exhausted write.
API_RUNNER_STREAM_DONE = "complete"


def _read_omlx_key(env: Mapping[str, str] | None = None) -> str | None:
    from quodeq.llm_bridge.omlx import read_omlx_api_key  # noqa: PLC0415
    return read_omlx_api_key(env)


# Registry of provider-specific credential loaders. Each callable takes the
# run's injected environment (None means the process environment) and returns
# the API key string (or None/empty string) for that provider. New providers
# can be added here without touching _resolve_provider_config.
CREDENTIAL_LOADERS: dict[str, Callable[[Mapping[str, str] | None], str | None]] = {
    "omlx": _read_omlx_key,
}


def gather_api_source_files(
    work_dir: Path, cfg: AnalysisConfig, jsonl_file: Path, stream_file: Path,
) -> list[Path] | None:
    """Gather source files from queue or by scanning.

    Returns None (and writes empty output) when the queue is exhausted.
    """
    if cfg.queue_path and cfg.queue_path.exists():
        queue = FileQueue(cfg.queue_path)
        taken = queue.take(count=min(cfg.max_files_per_agent or 10, 3), agent_id=cfg.agent_id)
        # Enumeration applies the same predicate (the run's own policy when a
        # RunConfig is carried), so dropped files here mean the file changed
        # (or vanished) between queue build and dispatch.
        policy = (cfg.run_config.dispatch_policy() if cfg.run_config is not None
                  else dispatch_policy.default_dispatch_policy())
        dispatchable, dropped = policy.split_api_dispatchable(work_dir, taken)
        if dropped:
            # Lazy import keeps the baseline-pinned llm_bridge line above
            # from shifting; the marker helper is router-owned wire format.
            from quodeq.analysis.mcp.router import write_skip_markers  # noqa: PLC0415
            write_skip_markers(
                jsonl_file, dropped,
                reason=(
                    f"skipped: missing or over the API file-size cap "
                    f"({policy.file_size_cap} bytes)"
                ),
            )
        source_files = [work_dir / f for f in dispatchable]
        _log.debug("Took %d files from queue for API analysis", len(source_files))
        if not source_files:
            # Don't touch jsonl_file — it's the SHARED `{dim}_evidence.jsonl`
            # that every agent in the pool appends to via MCP. Truncating it
            # here wipes findings from every other agent in the pool.
            write_stream_done_marker(stream_file)
            return None
        return source_files
    return gather_source_files(work_dir)


def batch_files_by_size(files: list[Path], budget: int) -> list[list[Path]]:
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


def write_stream_done_marker(stream_file: Path) -> None:
    """Overwrite *stream_file* with the API runner's one-line done marker."""
    stream_file.write_text(json.dumps({"type": "api_runner", "status": API_RUNNER_STREAM_DONE}) + "\n", encoding="utf-8")
