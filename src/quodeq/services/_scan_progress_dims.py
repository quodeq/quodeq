"""Per-dimension progress row construction for live scan progress.

Split from ``scan_progress.py`` to keep that file under the size ratchet's
300-line cap. Moved verbatim (``_dim_state``, ``_active_agents``,
``_consolidated_dim_progress``), plus ``_dim_files_summary`` and
``_build_dim_progress`` extracted from ``build_scan_progress``'s per-dim
loop body (no logic change, same values, same order).
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.evidence._req_mapping import build_principle_resolver
from quodeq.data.fs.standards_loader import read_req_to_principle_map
from quodeq.services._scan_progress_elapsed import _dim_elapsed_s
from quodeq.services._scan_progress_types import _DimProgress
from quodeq.services._wiring import (
    count_active_agent_streams,
    dimension_evidence_file,
    dimension_queue_file,
    dimension_report_exists,
    read_queue_state,
    tally_unique_findings,
)
from quodeq.services.suppression import build_matcher

_AGENT_ACTIVE_WINDOW_S = 30


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
) -> str:
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
        return "done"
    if terminal:
        # If the run terminated and this dim has a queue but no eval, the
        # dimension is *partially done* — surfaces visually via the
        # taken < total signal in the UI. Dims with no queue at all never
        # ran; keep them as pending so they don't claim completion.
        return "done" if has_queue else "pending"
    if has_queue:
        return "running"
    if status.get("current_dimension") == dim_id:
        return "running"
    return "pending"


def _consolidated_dim_progress(run_dir: Path) -> _DimProgress:
    """Progress row for a live consolidated (grouped) pass.

    Evidence counters are the raw cross-dimension tally: suppression
    netting is per-dimension and cannot be applied to the combined stream,
    so the live numbers may slightly over-read what the finished reports
    will show.
    """
    evidence_dir = run_dir / "evidence"
    queue = read_queue_state(evidence_dir / "consolidated_queue.json") or {}
    taken = 0
    for entry in queue.get("taken") or []:
        fs = entry.get("files") if isinstance(entry, dict) else None
        if isinstance(fs, list):
            taken += len(fs)
    pending = len(queue.get("pending") or [])
    tally = tally_unique_findings(evidence_dir / "consolidated_evidence.jsonl")
    return _DimProgress(
        id="consolidated",
        state="running",
        files={"taken": taken, "total": taken + pending},
        violations=tally.violations,
        compliance=tally.compliance,
        duplicates=tally.duplicates,
        elapsed_s=_dim_elapsed_s("consolidated", run_dir, "running"),
        active_agents=_active_agents(evidence_dir, "consolidated"),
    )


def _dim_files_summary(queue: dict | None, d_state: str, dim_estimates: dict, dim_id: str) -> dict:
    if queue is not None:
        # `taken` is a list of batch entries [{"files": [...], "agent": ..., "ts": ...}, ...].
        # Match FileQueue.stats(): flatten file counts across batches so the
        # number matches the heartbeat log.
        taken_entries = queue.get("taken") or []
        taken = 0
        for entry in taken_entries:
            fs = entry.get("files") if isinstance(entry, dict) else None
            if isinstance(fs, list):
                taken += len(fs)
        pending = len(queue.get("pending") or [])
        return {"taken": taken, "total": taken + pending}
    if d_state == "pending":
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


def _dim_evidence_tally(
    dim_id: str, run_dir: Path, dismissed, deleted,
    evaluators_dir: Path | None, compiled_dir: Path | None,
):
    matcher = build_matcher(dim_id, dismissed, deleted)
    return tally_unique_findings(
        dimension_evidence_file(run_dir, dim_id),
        suppressed=matcher.is_suppressed if matcher.active else None,
        resolver=build_principle_resolver(dim_id, evaluators_dir, compiled_dir,
                                          req_map_reader=read_req_to_principle_map),
    )


def _build_dim_progress(
    dim_id: str, run_dir: Path, status: dict, is_terminal: bool,
    dim_records: dict, dim_estimates: dict, dismissed, deleted,
    evidence_dir: Path, evaluators_dir: Path | None, compiled_dir: Path | None,
) -> _DimProgress:
    queue = read_queue_state(dimension_queue_file(run_dir, dim_id))
    d_state = _dim_state(
        dim_id, status, terminal=is_terminal,
        has_queue=queue is not None,
        has_evaluation=dimension_report_exists(run_dir / "evaluation", dim_id),
    )
    record = dim_records.get(dim_id) if isinstance(dim_records, dict) else None
    files = _dim_files_summary(queue, d_state, dim_estimates, dim_id)

    estimate_meta = dim_estimates.get(dim_id)
    estimate_reason = estimate_meta["reason"] if estimate_meta else None
    files_cached = estimate_meta["cached"] if estimate_meta else None
    files_project_total = estimate_meta["total"] if estimate_meta else None
    files_excluded = estimate_meta["excluded"] if estimate_meta else None

    tally = _dim_evidence_tally(dim_id, run_dir, dismissed, deleted, evaluators_dir, compiled_dir)
    elapsed = _dim_elapsed_s(dim_id, run_dir, d_state, record)
    active = _active_agents(evidence_dir, dim_id) if d_state == "running" else 0

    return _DimProgress(
        id=dim_id,
        state=d_state,
        files=files,
        violations=tally.violations,
        compliance=tally.compliance,
        duplicates=tally.duplicates,
        suppressed=tally.suppressed,
        quarantined=tally.quarantined,
        elapsed_s=elapsed,
        active_agents=active,
        estimate_reason=estimate_reason,
        exit_reason=_dim_exit_reason(record),
        files_cached=files_cached,
        files_project_total=files_project_total,
        files_excluded=files_excluded,
    )
