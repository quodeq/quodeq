"""Read live scan progress from a run directory.

Pure-on-disk: works for both internal (started via dashboard) and external
(started via `quodeq evaluate` in another terminal) runs. No reliance on
the in-memory JobManager state.

Sources:
- ``status.json``                 — phase, current_dimension, started_at, dimensions
- ``dim_estimates.json``          — per-dim file count predicted before any dim runs, plus total/cached coverage
- ``scan.json``                   — total_files (project-wide fallback for pending dims)
- ``<dim>_queue.json``            — taken / pending counts (precise once dim has started)
- ``<dim>_evidence.jsonl``        — unique violation / compliance / duplicate counts (in-memory dedup)
- ``<dim>_agent-*.stream`` mtime  — per-dim active-agents heuristic
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from quodeq.analysis.subagents.jsonl_utils import tally_unique_findings
from quodeq.shared.dim_estimates_io import read_dim_estimates
from quodeq.shared.dimensions_state import read_dimensions

_AGENT_ACTIVE_WINDOW_S = 30


@dataclass
class _DimProgress:
    id: str
    state: str  # "done" | "running" | "pending"
    files: dict
    violations: int = 0
    compliance: int = 0
    duplicates: int = 0
    elapsed_s: float | None = None
    budget_s: int | None = None
    active_agents: int = 0
    estimate_reason: str | None = None  # see _dim_estimates module docstring
    exit_reason: str | None = None
    files_cached: int | None = None        # files already analyzed in previous runs
    files_project_total: int | None = None  # all source files for this dim


@dataclass
class _ScanProgress:
    job_id: str
    state: str
    phase: str | None
    current_dimension: str | None
    project_files: int
    total_elapsed_s: float | None
    dimensions: list[_DimProgress] = field(default_factory=list)


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _project_total_files(run_dir: Path) -> int:
    """Read project_files (upper bound for pending dims) from scan.json."""
    project_dir = run_dir.parent
    scan = _read_json(project_dir / "scan.json")
    if not scan:
        return 0
    raw = scan.get("total_files")
    return int(raw) if isinstance(raw, int) else 0


def _active_agents(evidence_dir: Path, dim_id: str) -> int:
    """Heuristic: count <dim>_agent-*.stream files modified in the last 30s."""
    if not evidence_dir.is_dir():
        return 0
    cutoff = time.time() - _AGENT_ACTIVE_WINDOW_S
    count = 0
    try:
        for p in evidence_dir.glob(f"{dim_id}_agent-*.stream"):
            try:
                if p.stat().st_mtime >= cutoff:
                    count += 1
            except OSError:
                continue
    except OSError:
        pass
    return count


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


def _parse_started_at(status: dict) -> datetime | None:
    raw = status.get("started_at")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _dim_elapsed_s(dim_id: str, run_dir: Path, state: str) -> float | None:
    """Per-dim elapsed time, derived from queue file mtime / status timing.

    Best-effort: queue creation time approximates the dimension start. For done
    dims we use the youngest agent-stream mtime as the end. For running dims we
    use now. For pending dims we return None.
    """
    if state == "pending":
        return None
    queue = run_dir / "evidence" / f"{dim_id}_queue.json"
    if not queue.is_file():
        return None
    try:
        start = queue.stat().st_mtime
    except OSError:
        return None
    if state == "running":
        return max(0.0, time.time() - start)
    # done: use latest agent-stream mtime
    end = start
    try:
        for s in (run_dir / "evidence").glob(f"{dim_id}_agent-*.stream"):
            try:
                end = max(end, s.stat().st_mtime)
            except OSError:
                continue
    except OSError:
        pass
    return max(0.0, end - start)


def build_scan_progress(
    job_id: str,
    run_dir: Path,
    *,
    time_limit_s: int | None = None,
) -> _ScanProgress | None:
    """Compute progress for a run.

    Reads only on-disk state — works for internal and external runs uniformly.
    Returns None if the run dir is missing or has no status.json.
    """
    if not run_dir.is_dir():
        return None
    status = _read_json(run_dir / "status.json") or {}
    if not status:
        return None

    state = status.get("state") or "unknown"
    terminal_states = {"done", "failed", "cancelled"}
    is_terminal = state in terminal_states

    started_at = _parse_started_at(status)
    if state == "running" and started_at:
        total_elapsed_s: float | None = max(
            0.0, (datetime.now(timezone.utc) - started_at).total_seconds(),
        )
    elif started_at and status.get("finalized_at"):
        try:
            end = datetime.fromisoformat(status["finalized_at"])
            total_elapsed_s = max(0.0, (end - started_at).total_seconds())
        except (ValueError, TypeError):
            total_elapsed_s = None
    else:
        total_elapsed_s = None

    project_files = _project_total_files(run_dir)
    dim_estimates = read_dim_estimates(run_dir)
    dim_records = read_dimensions(run_dir).get("dimensions") or {}
    dim_ids = list(status.get("dimensions") or [])
    if not dim_ids:
        # "All dimensions" runs (no --dimensions filter) record an empty list in
        # status.json: the raw, unresolved filter is None and gets coerced to []
        # before the lifecycle writes it. Reading the dim list from status alone
        # would then zero out the whole progress header — and the ETA the UI
        # derives from it — for the entire run. The per-dim sidecars still hold
        # the resolved dims, so recover the list from them (order-preserving,
        # deduped) when status carries none.
        recovered: dict[str, None] = {}
        record_keys = dim_records.keys() if isinstance(dim_records, dict) else ()
        for key in (*record_keys, *dim_estimates.keys()):
            recovered.setdefault(key, None)
        dim_ids = list(recovered)
    evidence_dir = run_dir / "evidence"

    dim_results: list[_DimProgress] = []
    for dim_id in dim_ids:
        queue_path = evidence_dir / f"{dim_id}_queue.json"
        eval_path = run_dir / "evaluation" / f"{dim_id}.json"
        queue = _read_json(queue_path) if queue_path.is_file() else None
        d_state = _dim_state(
            dim_id, status, terminal=is_terminal,
            has_queue=queue is not None,
            has_evaluation=eval_path.is_file(),
        )
        record = dim_records.get(dim_id) if isinstance(dim_records, dict) else None
        exit_reason = record.get("exit_reason") if isinstance(record, dict) else None

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
            files = {"taken": taken, "total": taken + pending}
        elif d_state == "pending":
            # Pending dims report 0 until the precomputed estimate lands.
            # The UI uses "any pending dim with total=0" as the signal to
            # keep the header in "preparing…" — better to show nothing
            # than the project-wide ceiling, which is misleading once
            # incremental filters are applied.
            estimate = dim_estimates.get(dim_id)
            files = {"taken": 0, "total": estimate["count"] if estimate else 0}
        else:
            files = {"taken": 0, "total": 0}

        estimate_meta = dim_estimates.get(dim_id)
        estimate_reason = estimate_meta["reason"] if estimate_meta else None
        files_cached = estimate_meta["cached"] if estimate_meta else None
        files_project_total = estimate_meta["total"] if estimate_meta else None

        tally = tally_unique_findings(evidence_dir / f"{dim_id}_evidence.jsonl")
        elapsed = _dim_elapsed_s(dim_id, run_dir, d_state)
        budget = time_limit_s if (d_state == "running" and time_limit_s and time_limit_s > 0) else None
        active = _active_agents(evidence_dir, dim_id) if d_state == "running" else 0

        dim_results.append(_DimProgress(
            id=dim_id,
            state=d_state,
            files=files,
            violations=tally.violations,
            compliance=tally.compliance,
            duplicates=tally.duplicates,
            elapsed_s=elapsed,
            budget_s=budget,
            active_agents=active,
            estimate_reason=estimate_reason,
            exit_reason=exit_reason,
            files_cached=files_cached,
            files_project_total=files_project_total,
        ))

    return _ScanProgress(
        job_id=job_id,
        state=state,
        phase=status.get("phase"),
        current_dimension=status.get("current_dimension"),
        project_files=project_files,
        total_elapsed_s=total_elapsed_s,
        dimensions=dim_results,
    )


def progress_to_dict(progress: _ScanProgress) -> dict:
    """Serialize the dataclass tree to a camelCase dict for jsonify.

    Uses to_camel_dict so dataclass field names like ``exit_reason`` and
    ``estimate_reason`` become ``exitReason`` and ``estimateReason`` in the
    JSON the client sees. The route still wraps the result in to_camel_dict;
    that second pass is a no-op for already-camelCased dicts.
    """
    from quodeq.core.types import to_camel_dict
    result = to_camel_dict(progress)
    if not isinstance(result, dict):
        return {}
    return result
