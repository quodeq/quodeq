"""Per-dimension progress row construction for live scan progress.

Split from ``scan_progress.py`` to keep that file under the size ratchet's
300-line cap. Moved verbatim (``_dim_state``, ``_active_agents``,
``consolidated_dim_progress``), plus ``_dim_files_summary`` and
``build_dim_progress`` extracted from ``build_scan_progress``'s per-dim
loop body (no logic change, same values, same order).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quodeq.core.evidence.req_mapping import build_principle_resolver
from quodeq.core.run.dimensions import DimState
from quodeq.services._scan_progress_elapsed import dim_elapsed_s
from quodeq.services._scan_progress_types import DimProgress, ProgressContext
from quodeq.services.wiring import (
    FindingTally,
    IncrementalTally,
    count_active_agent_streams,
    dimension_evidence_file,
    dimension_queue_file,
    dimension_report_exists,
    read_queue_state,
    read_req_to_principle_map,
)
from quodeq.services.suppression import build_matcher
from quodeq.shared.constants import CONSOLIDATED_DIMENSION_KEY
from quodeq.shared.lru import LRUDict

_AGENT_ACTIVE_WINDOW_S = 30

# Bounded process-wide memo of IncrementalTally objects, one per (evidence
# file, suppression state) so a live-progress poll resumes where the last
# poll stopped instead of re-parsing the file from byte 0 (findings
# 5531/5532). The dashboard polls from several threads, hence the lock --
# which covers the memo only, never a tally's own file read.
_LIVE_TALLIES: LRUDict = LRUDict(256)
_LIVE_TALLIES_LOCK = threading.Lock()


@dataclass
class _GuardedTally:
    """One memoized ``IncrementalTally`` plus the lock that serialises it.

    A tally is mutable state (offset, dedup set, counters) shared by every
    poll of the same run and suppression state, so concurrent ``advance()``
    calls on ONE tally have to be serialised. Its own lock, rather than the
    memo's: two polls of different runs then read their files in parallel.
    """

    tally: IncrementalTally
    lock: threading.Lock = field(default_factory=threading.Lock)

    def advance(self) -> FindingTally:
        with self.lock:
            return self.tally.advance()


def _suppression_stamp(dismissed, deleted) -> tuple | None:
    """A hashable stamp of the current suppression state, for the memo key.

    Returns the ``(dismissed, frozenset(deleted))`` tuple itself rather than
    its hash: a dict key relies on hash *and* equality to tell states apart,
    and collapsing to a bare hash first would let two different states that
    happen to collide onto the same 64-bit hash silently share one entry.

    A poll with an unchanged dismissed/deleted state resumes the existing
    tally; a changed one starts a fresh tally under a new key -- no worse
    than today's from-scratch cost. ``dismissed`` may be a plain (unhashable)
    ``set`` (see ``SuppressionMatcher``); such a state has no usable key at
    all and yields None, which keeps it out of the memo entirely. Keying it
    on ``id()`` instead would let a later, different object reuse a freed
    id and resume a tally built with the previous predicate.
    """
    stamp = (dismissed, frozenset(deleted))
    try:
        hash(stamp)
    except TypeError:
        return None
    return stamp


def _standards_stamp(directory: Path | None) -> tuple[str, int]:
    """``(path, dir mtime_ns)`` for one standards directory, 0 when missing.

    Part of the memo key because the principle resolver is built from these
    directories: a standard imported or removed mid-run changes the
    directory's mtime, which starts a fresh tally with the fresh resolver
    instead of resuming one that cannot see the new standard. One stat.
    """
    try:
        return (str(directory), directory.stat().st_mtime_ns if directory is not None else 0)
    except OSError:
        return (str(directory), 0)


def live_tally(path: Path, *, suppressed, make_resolver, memo_key: tuple | None) -> FindingTally:
    """The file's tally, resumed from the last poll when *memo_key* is unchanged.

    *make_resolver* (zero-arg, or None) is called only when a new tally is
    built. ``memo_key=None`` means this state cannot be keyed (see
    ``_suppression_stamp``): the file is tallied from scratch, nothing stored.
    """
    if memo_key is None:
        return IncrementalTally(path, suppressed=suppressed, resolver=make_resolver and make_resolver()).advance()
    key = (str(path), memo_key)
    with _LIVE_TALLIES_LOCK:
        guarded = _LIVE_TALLIES.get(key)
        if guarded is None:
            guarded = _GuardedTally(
                IncrementalTally(path, suppressed=suppressed, resolver=make_resolver and make_resolver()))
            _LIVE_TALLIES.put(key, guarded)
    return guarded.advance()


def forget_live_tallies(run_dir: Path) -> None:
    """Drop every memoized tally for evidence files under *run_dir*.

    Called once a run is terminal: nothing more will be appended to its
    evidence, so its dedup sets are dead weight until 256 other keys evict
    them.
    """
    with _LIVE_TALLIES_LOCK:
        for key in _LIVE_TALLIES.keys():
            # Compared as paths, never as a "/"-prefixed string: a key is
            # str(dimension_evidence_file(...)) and carries the platform's
            # separator, so a hardcoded slash evicts nothing on Windows.
            # with_segments parses the key in run_dir's own flavour.
            if run_dir.with_segments(key[0]).is_relative_to(run_dir):
                _LIVE_TALLIES.discard(key)


def _active_agents(evidence_dir: Path, dim_id: str) -> int:
    """Heuristic: count <dim>_agent-*.stream files modified in the last 30s."""
    return count_active_agent_streams(
        evidence_dir, dim_id, window_s=_AGENT_ACTIVE_WINDOW_S,
    )


def _dim_state(
    dim_id: str,
    status: dict,
    terminal: bool,
    *,
    has_queue: bool,
    has_evaluation: bool,
) -> DimState:
    """Classify a dimension as done | running | pending.

    Order of checks:
    1. If a scored evaluation file exists for this dim → done
    2. If the run reached a terminal state → done (whatever state on disk)
    3. If the queue file exists (dim has been started) → running
    4. If current_dimension matches → running (covers the moment after queue
       creation, before takens are written)
    5. Otherwise → pending
    """
    if has_evaluation:
        return DimState.DONE
    if terminal:
        # If the run terminated and this dim has a queue but no eval, the
        # dimension is *partially done* — surfaces visually via the
        # taken < total signal in the UI. Dims with no queue at all never
        # ran; keep them as pending so they don't claim completion.
        return DimState.DONE if has_queue else DimState.PENDING
    if has_queue:
        return DimState.RUNNING
    if status.get("current_dimension") == dim_id:
        return DimState.RUNNING
    return DimState.PENDING


def _queue_file_counts(queue: dict) -> dict[str, int]:
    """``{"taken": n, "total": n + pending}`` for a file-queue state dict.

    ``taken`` is a list of batch entries ``[{"files": [...], "agent": ...,
    "ts": ...}, ...]``. Match FileQueue.stats(): flatten the file counts
    across batches so the number matches the heartbeat log. Entries that are
    not dicts, and file lists that are not lists, count as nothing.
    """
    taken = 0
    for entry in queue.get("taken") or []:
        fs = entry.get("files") if isinstance(entry, dict) else None
        if isinstance(fs, list):
            taken += len(fs)
    pending = len(queue.get("pending") or [])
    return {"taken": taken, "total": taken + pending}


def consolidated_dim_progress(run_dir: Path) -> DimProgress:
    """Progress row for a live consolidated (grouped) pass.

    Evidence counters are the raw cross-dimension tally: suppression
    netting is per-dimension and cannot be applied to the combined stream,
    so the live numbers may slightly over-read what the finished reports
    will show.
    """
    evidence_dir = run_dir / "evidence"
    queue = read_queue_state(evidence_dir / "consolidated_queue.json") or {}
    tally = live_tally(evidence_dir / "consolidated_evidence.jsonl",
                       suppressed=None, make_resolver=None, memo_key=(CONSOLIDATED_DIMENSION_KEY,))
    return DimProgress(
        id=CONSOLIDATED_DIMENSION_KEY,
        state=DimState.RUNNING,
        files=_queue_file_counts(queue),
        violations=tally.violations,
        compliance=tally.compliance,
        duplicates=tally.duplicates,
        elapsed_s=dim_elapsed_s(CONSOLIDATED_DIMENSION_KEY, run_dir, DimState.RUNNING),
        active_agents=_active_agents(evidence_dir, CONSOLIDATED_DIMENSION_KEY),
    )


def _dim_files_summary(queue: dict | None, d_state: DimState, dim_estimates: dict, dim_id: str) -> dict:
    if queue is not None:
        return _queue_file_counts(queue)
    if d_state == DimState.PENDING:
        # Pending dims report 0 until the precomputed estimate lands.
        # The UI uses "any pending dim with total=0" as the signal to
        # keep the header in "preparing…" — better to show nothing
        # than the project-wide ceiling, which is misleading once
        # incremental filters are applied.
        estimate = dim_estimates.get(dim_id)
        return {"taken": 0, "total": estimate["count"] if estimate else 0}
    return {"taken": 0, "total": 0}


def _dim_exit_reason(record: dict | None) -> str | None:
    """DONE dims carry `exit_reason`; INCOMPLETE dims carry `reason` (e.g.
    "provider_fatal", "cancelled_signal"). Fall back so an interrupted dim
    still tells the UI why it stopped."""
    if isinstance(record, dict):
        return record.get("exit_reason") or record.get("reason")
    return None


def _dim_evidence_tally(dim_id: str, ctx: ProgressContext, dismissed, deleted):
    matcher = build_matcher(dim_id, dismissed, deleted)
    stamp = _suppression_stamp(dismissed, deleted)
    memo_key = None if stamp is None else (
        dim_id, stamp,
        _standards_stamp(ctx.evaluators_dir), _standards_stamp(ctx.compiled_dir),
    )
    return live_tally(
        dimension_evidence_file(ctx.run_dir, dim_id),
        suppressed=matcher.is_suppressed if matcher.active else None,
        make_resolver=lambda: build_principle_resolver(
            dim_id, ctx.evaluators_dir, ctx.compiled_dir, req_map_reader=read_req_to_principle_map),
        memo_key=memo_key,
    )


def _dim_measurements(
    dim_id: str, ctx: ProgressContext, d_state: DimState, record: dict | None,
) -> dict[str, Any]:
    """Elapsed time, live agents and estimate counts for one dim, as ``DimProgress`` kwargs.

    Returned as kwargs rather than as a second dataclass so the field names
    and types are declared once, on ``DimProgress`` itself.
    """
    meta = ctx.dim_estimates.get(dim_id)
    return {
        "elapsed_s": dim_elapsed_s(dim_id, ctx.run_dir, d_state, record),
        "active_agents": _active_agents(ctx.evidence_dir, dim_id) if d_state == DimState.RUNNING else 0,
        "estimate_reason": meta["reason"] if meta else None,
        "files_cached": meta["cached"] if meta else None,
        "files_project_total": meta["total"] if meta else None,
        "files_excluded": meta["excluded"] if meta else None,
    }


def build_dim_progress(
    dim_id: str, ctx: ProgressContext, dismissed, deleted,
) -> DimProgress:
    queue = read_queue_state(dimension_queue_file(ctx.run_dir, dim_id))
    d_state = _dim_state(
        dim_id, ctx.status, terminal=ctx.is_terminal,
        has_queue=queue is not None,
        has_evaluation=dimension_report_exists(ctx.run_dir / "evaluation", dim_id),
    )
    record = ctx.dim_records.get(dim_id) if isinstance(ctx.dim_records, dict) else None
    tally = _dim_evidence_tally(dim_id, ctx, dismissed, deleted)
    measurements = _dim_measurements(dim_id, ctx, d_state, record)
    return DimProgress(
        id=dim_id,
        state=d_state,
        files=_dim_files_summary(queue, d_state, ctx.dim_estimates, dim_id),
        violations=tally.violations,
        compliance=tally.compliance,
        duplicates=tally.duplicates,
        suppressed=tally.suppressed,
        quarantined=tally.quarantined,
        exit_reason=_dim_exit_reason(record),
        **measurements,
    )
