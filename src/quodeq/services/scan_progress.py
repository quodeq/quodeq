"""Read live scan progress from a run directory.

Pure-on-disk: works for both internal (started via dashboard) and external
(started via `quodeq evaluate` in another terminal) runs. No reliance on
the in-memory JobManager state.

Sources:
- ``status.json``                 — phase, current_dimension, started_at, dimensions
- ``scan.json``                   — total_files (project-wide upper bound for pending dims)
- ``<dim>_queue.json``            — taken / pending counts (precise once dim has started)
- ``<dim>_evidence.jsonl``        — violation / compliance counters
- ``<dim>_agent-*.stream`` mtime  — per-dim active-agents heuristic
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_AGENT_ACTIVE_WINDOW_S = 30


@dataclass
class _DimProgress:
    id: str
    state: str  # "done" | "running" | "pending"
    files: dict
    violations: int = 0
    compliance: int = 0
    elapsed_s: float | None = None
    budget_s: int | None = None
    active_agents: int = 0


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


def _count_jsonl_findings(jsonl_path: Path) -> tuple[int, int]:
    """Return (violation_count, compliance_count) from a dimension's JSONL.

    Tolerant: malformed lines are skipped silently.
    """
    if not jsonl_path.is_file():
        return 0, 0
    violations = 0
    compliance = 0
    try:
        with jsonl_path.open(encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                t = obj.get("t")
                if t == "violation":
                    violations += 1
                elif t == "compliance":
                    compliance += 1
    except OSError:
        pass
    return violations, compliance


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


def _dim_state(dim_id: str, status: dict, terminal: bool) -> str:
    """Classify a dimension as done | running | pending.

    A dim is *done* if its evidence file exists AND it isn't the current_dimension
    of a still-running scan. Falls back to current_dimension match for *running*.
    """
    current = status.get("current_dimension")
    if terminal:
        return "done"
    if current == dim_id:
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
    pool_budget_s: int | None = None,
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
    dim_ids = list(status.get("dimensions") or [])
    evidence_dir = run_dir / "evidence"

    dim_results: list[_DimProgress] = []
    for dim_id in dim_ids:
        # Treat all dims as "done" once the run reaches a terminal state — a dim
        # that started and wasn't the current_dimension at termination is finished.
        d_state = _dim_state(dim_id, status, terminal=is_terminal)

        queue_path = evidence_dir / f"{dim_id}_queue.json"
        queue = _read_json(queue_path) if queue_path.is_file() else None
        if queue is not None:
            taken = len(queue.get("taken") or [])
            pending = len(queue.get("pending") or [])
            files = {"taken": taken, "total": taken + pending}
        elif d_state == "pending":
            files = {"taken": 0, "total": project_files}
        else:
            files = {"taken": 0, "total": 0}

        v, c = _count_jsonl_findings(evidence_dir / f"{dim_id}_evidence.jsonl")
        elapsed = _dim_elapsed_s(dim_id, run_dir, d_state)
        budget = pool_budget_s if (d_state == "running" and pool_budget_s and pool_budget_s > 0) else None
        active = _active_agents(evidence_dir, dim_id) if d_state == "running" else 0

        dim_results.append(_DimProgress(
            id=dim_id,
            state=d_state,
            files=files,
            violations=v,
            compliance=c,
            elapsed_s=elapsed,
            budget_s=budget,
            active_agents=active,
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
    """Serialize for the API response (snake_case → camelCase done at the route)."""
    return asdict(progress)
