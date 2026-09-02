"""Discard-on-cancel: wait for a terminal status, then wipe run scratch state.

Split (Task 14) out of ``evaluation_mixin.py``. Re-exported there for
backward compatibility — ``FsEvaluationMixin.cancel_evaluation`` calls
``_wait_for_terminal_status``/``_discard_run_state`` as bare module-global
names so ``unittest.mock.patch("quodeq.services.evaluation_mixin.<name>")``
keeps working after the move (tests patch both).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Protocol

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.services._wiring import read_dispatched_cache_keys, remove_matching_files

_TERMINAL_RUN_STATES = frozenset({"done", "failed", "cancelled"})
_CANCEL_WAIT_TIMEOUT_S = 2.0
_CANCEL_WAIT_POLL_S = 0.05


def _wait_for_terminal_status(
    run_dir: Path,
    *,
    timeout_s: float = _CANCEL_WAIT_TIMEOUT_S,
    poll_interval_s: float = _CANCEL_WAIT_POLL_S,
) -> bool:
    """Block until ``run_dir/status.json`` reports a terminal state, or timeout.

    Returns True when a terminal state ({done, failed, cancelled}) is
    observed on disk; returns False on timeout. Best-effort: a False
    return does not abort the calling cancel flow — downstream polling
    or SSE will eventually catch up.

    Bridges the async gap between ``JobManager.cancel_job`` returning
    (in-memory state flipped, signal sent to subprocess) and the run
    lifecycle handler in the subprocess flushing ``status.json`` to
    terminal. Without this wait, observers reading from disk
    immediately after the API returns can still see the run as
    ``in_progress`` for ~100ms-1s, producing a window where a
    follow-up "Start" surfaces two ``running`` rows in the UI.
    """
    deadline = time.monotonic() + timeout_s
    status_path = run_dir / "status.json"
    while True:
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("state") in _TERMINAL_RUN_STATES:
                return True
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval_s)


def _open_cache():
    """Lazily construct the default cache backend (import kept local).

    Deferred rather than routed through ``services._wiring``: ``_wiring`` is
    imported by nearly every services module (including ``services.scoring``,
    itself reachable from ``tests/core``), and ``LocalFileBackend``'s module
    reaches the top-level ``quodeq`` package (via ``CacheEntry.quodeq_version``),
    which deferred-imports ``quodeq.cli`` -> httpx/pydantic. Keeping this
    import local keeps that framework chain out of ``_wiring``'s reach.
    """
    from quodeq.data.cache_store.local import LocalFileBackend
    return LocalFileBackend()


def _discard_run_state(
    reports_dir: str, job: dict, *, cache: "_CacheEraser | None" = None,
    log: LogSink = NULL_LOG,
) -> None:
    """Wipe every trace a discarded run left behind.

    Invoked when the user cancels with "Discard findings": the run must end
    up as if it never happened. For EVERY dim that dispatched work (has a
    ``<dim>_dispatch_keys.json`` sidecar) the V2 content-addressed cache
    entries it wrote are deleted, including dims that finished cleanly.
    Without that, the next incremental run counts the discarded run's files
    as "analyzed in previous runs" in the coverage header. The sidecar holds
    only this run's dispatched (cache-miss) keys, so entries written by
    earlier kept runs are not touched.

    All per-dim scratch (queue, fingerprint, evidence JSONL, dispatch-keys
    and replayed-keys sidecars) is removed so the status-GET scoring path
    cannot resurrect a report from leftover evidence. The caller removes the
    run directory itself.
    """
    project = job.get("outputProject")
    run_id = job.get("outputRunId")
    if not project or not run_id:
        return

    run_dir = Path(reports_dir) / project / run_id
    evidence_dir = run_dir / "evidence"
    if not evidence_dir.is_dir():
        return

    keys = read_dispatched_cache_keys(evidence_dir)
    if keys:
        cache = cache or _open_cache()
        for key in keys:
            try:
                cache.delete(key)
            except Exception as exc:  # noqa: BLE001
                log.warning(f"Could not delete cache entry {key}: {exc}")

    scratch_patterns = (
        "*_queue.json", "*_fingerprint.json",
        "*_evidence.jsonl", "*_dispatch_keys.json",
        # Entries listed here belong to EARLIER runs, so they are cleaned up
        # as scratch but deliberately not fed to the cache-deletion loop above.
        "*_replayed_unconsolidated_keys.json",
    )
    remove_matching_files(evidence_dir, scratch_patterns)


class _CacheEraser(Protocol):
    """The one cache-backend method ``_discard_run_state`` needs.

    A local structural type instead of importing
    ``data.cache_store.backend.CacheBackend`` directly: this Protocol is the
    injection seam ``_discard_run_state`` tests against, independent of
    which concrete backend ``_open_cache`` returns. ``LocalFileBackend``
    (returned by ``_open_cache``, and every other real cache backend)
    satisfies this shape without any inheritance. Defined after
    ``_discard_run_state`` (referenced there only as a deferred string
    annotation, per ``from __future__ import annotations``).
    """

    def delete(self, key: str) -> None: ...
