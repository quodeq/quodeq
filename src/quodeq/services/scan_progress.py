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
from quodeq.config.paths import default_paths
from quodeq.core.evidence._req_mapping import build_principle_resolver
from quodeq.data.fs.standards_loader import read_req_to_principle_map
from quodeq.services.ports import count_active_agent_streams, read_scan_total_files
from quodeq.services.suppression import build_matcher, project_suppressions
from quodeq.shared.dim_estimates_io import read_dim_estimates
from quodeq.data.fs.dimensions_state_store import read_dimensions

_AGENT_ACTIVE_WINDOW_S = 30


@dataclass
class _DimProgress:
    id: str
    state: str  # "done" | "running" | "pending"
    files: dict
    violations: int = 0
    compliance: int = 0
    duplicates: int = 0
    suppressed: int = 0  # re-found findings already dismissed/deleted in the dashboard
    quarantined: int = 0  # findings whose principle is not in the dimension's standard
    elapsed_s: float | None = None
    active_agents: int = 0
    estimate_reason: str | None = None  # see _dim_estimates module docstring
    exit_reason: str | None = None
    files_cached: int | None = None        # files already analyzed in previous runs
    files_project_total: int | None = None  # all dispatchable source files for this dim
    files_excluded: int | None = None       # files the provider can never dispatch (size cap)


@dataclass
class _ScanProgress:
    job_id: str
    state: str
    phase: str | None
    current_dimension: str | None
    project_files: int
    total_elapsed_s: float | None
    # The time limit is one deadline for the whole run, shared across all
    # selected dimensions — never a per-dimension allowance.
    budget_s: int | None = None
    # Run-level exit_reason from status.json (e.g. "provider_fatal",
    # "failure_streak"). Lets the UI say WHY a failed run stopped instead of
    # only that it did.
    exit_reason: str | None = None
    dimensions: list[_DimProgress] = field(default_factory=list)


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _project_total_files(run_dir: Path) -> int:
    """Read project_files (upper bound for pending dims) from scan.json."""
    return read_scan_total_files(run_dir.parent)


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


def _parse_iso_utc(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    # Legacy status files can carry naive timestamps; subtracting one from an
    # aware now() raises TypeError. Treat naive as UTC.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_started_at(status: dict) -> datetime | None:
    return _parse_iso_utc(status.get("started_at"))


def _queue_take_timestamps(qstate: dict) -> list[float]:
    """Extract valid take-log timestamps from a queue state dict."""
    taken = qstate.get("taken")
    if not isinstance(taken, list):
        return []
    return [
        e["ts"] for e in taken
        if isinstance(e, dict) and isinstance(e.get("ts"), (int, float))
    ]


def _stamped_elapsed_s(record: dict | None, state: str) -> float | None:
    """Per-dim elapsed from the transition timestamps in dimensions.json.

    write_dim_state stamps ``started_at`` when the dimension starts and
    ``completed_at`` / ``interrupted_at`` when it stops, so the duration is a
    subtraction of two explicit values — no file-system forensics. None when
    the record lacks the needed stamps (legacy runs, hard kills that never
    reached the terminal write): the caller falls back to reconstruction.
    """
    if not isinstance(record, dict):
        return None
    start = _parse_iso_utc(record.get("started_at"))
    if start is None:
        return None
    if state == "running":
        return max(0.0, (datetime.now(timezone.utc) - start).total_seconds())
    end = _parse_iso_utc(record.get("completed_at")) or _parse_iso_utc(record.get("interrupted_at"))
    if end is None:
        return None
    return max(0.0, (end - start).total_seconds())


def _dim_elapsed_s(dim_id: str, run_dir: Path, state: str, record: dict | None = None) -> float | None:
    """Per-dim elapsed time.

    Prefers the transition timestamps stamped in dimensions.json (see
    _stamped_elapsed_s). The queue-state reconstruction below remains as a
    fallback for run dirs written before those stamps were preserved,
    external runs from older CLI versions, the consolidated pseudo-dim
    (which has no dimensions.json entry), and dims that died without a
    terminal transition.

    Reconstruction notes: the queue file is atomically rewritten on every
    take (new inode, fresh mtime), so its mtime tracks the *last* take, not
    the dim start — using it as the start made the running clock reset
    toward zero on every take. Start comes from the queue's ``created_at``
    (stamped at init), falling back to the earliest take timestamp, then the
    file mtime for legacy queues. For done dims the end is the latest
    activity signal we still have: last take, evidence-file mtime, or any
    surviving agent streams (streams are deleted at dim completion, so they
    rarely survive).
    """
    if state == "pending":
        return None
    stamped = _stamped_elapsed_s(record, state)
    if stamped is not None:
        return stamped
    queue = run_dir / "evidence" / f"{dim_id}_queue.json"
    qstate = _read_json(queue)
    if qstate is None:
        return None
    take_ts = _queue_take_timestamps(qstate)
    start = qstate.get("created_at")
    if not isinstance(start, (int, float)):
        if take_ts:
            start = min(take_ts)
        else:
            try:
                start = queue.stat().st_mtime
            except OSError:
                return None
    if state == "running":
        return max(0.0, time.time() - start)
    # done: latest activity signal still on disk
    end = start
    if take_ts:
        end = max(end, max(take_ts))
    for candidate in (
        run_dir / "evidence" / f"{dim_id}_evidence.jsonl",
        *(run_dir / "evidence").glob(f"{dim_id}_agent-*.stream"),
    ):
        try:
            end = max(end, candidate.stat().st_mtime)
        except OSError:
            continue
    return max(0.0, end - start)


def _consolidated_dim_progress(run_dir: Path) -> _DimProgress:
    """Progress row for a live consolidated (grouped) pass.

    Evidence counters are the raw cross-dimension tally: suppression
    netting is per-dimension and cannot be applied to the combined stream,
    so the live numbers may slightly over-read what the finished reports
    will show.
    """
    evidence_dir = run_dir / "evidence"
    queue = _read_json(evidence_dir / "consolidated_queue.json") or {}
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


def build_scan_progress(
    job_id: str,
    run_dir: Path,
    *,
    time_limit_s: int | None = None,
    compiled_dir: Path | None = None,
) -> _ScanProgress | None:
    """Compute progress for a run.

    Reads only on-disk state — works for internal and external runs uniformly.
    Returns None if the run dir is missing or has no status.json.

    *compiled_dir* supplies the built-in standards used to exclude findings the
    report path quarantines, so the live counters match the persisted run report.
    Without it only custom evaluators are consulted, which on a stock install is
    an empty directory — the counters then stay permissive and can over-count by
    the number of unmappable findings.
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
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            total_elapsed_s = max(0.0, (end - started_at).total_seconds())
        except (ValueError, TypeError):
            total_elapsed_s = None
    else:
        total_elapsed_s = None

    run_budget_s = time_limit_s if (time_limit_s and time_limit_s > 0) else None
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
    evaluators_dir = default_paths().evaluators_dir

    # Consolidated (grouped) runs dispatch every dimension in one pass and
    # write consolidated_* files — there are no per-dim queues, so the
    # per-dim reader below would report 0% / "estimating…" for the whole
    # run. While such a run is live, report the consolidated pass as one
    # row with the real file counts. Once the run is terminal the per-dim
    # evaluation files exist and normal per-dim classification applies.
    consolidated_queue = evidence_dir / "consolidated_queue.json"
    if (
        not is_terminal
        and consolidated_queue.is_file()
        and not any((evidence_dir / f"{d}_queue.json").is_file() for d in dim_ids)
    ):
        return _ScanProgress(
            job_id=job_id,
            state=state,
            phase=status.get("phase"),
            current_dimension=status.get("current_dimension"),
            project_files=project_files,
            total_elapsed_s=total_elapsed_s,
            budget_s=run_budget_s,
            exit_reason=status.get("exit_reason"),
            dimensions=[_consolidated_dim_progress(run_dir)],
        )

    # The scanner re-finds everything the user has dismissed or deleted, so a
    # raw evidence tally can run several times the number the finished report
    # shows. Read the suppression stores once per tick and net them out here,
    # so the live counters and the run report never tell different stories.
    dismissed, deleted = project_suppressions(run_dir.parent)

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
        # DONE dims carry `exit_reason`; INCOMPLETE dims carry `reason`
        # (e.g. "provider_fatal", "cancelled_signal"). Fall back so an
        # interrupted dim still tells the UI why it stopped.
        exit_reason = None
        if isinstance(record, dict):
            exit_reason = record.get("exit_reason") or record.get("reason")

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
        files_excluded = estimate_meta["excluded"] if estimate_meta else None

        matcher = build_matcher(dim_id, dismissed, deleted)
        tally = tally_unique_findings(
            evidence_dir / f"{dim_id}_evidence.jsonl",
            suppressed=matcher.is_suppressed if matcher.active else None,
            resolver=build_principle_resolver(dim_id, evaluators_dir, compiled_dir,
                                              req_map_reader=read_req_to_principle_map),
        )
        elapsed = _dim_elapsed_s(dim_id, run_dir, d_state, record)
        active = _active_agents(evidence_dir, dim_id) if d_state == "running" else 0

        dim_results.append(_DimProgress(
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
            exit_reason=exit_reason,
            files_cached=files_cached,
            files_project_total=files_project_total,
            files_excluded=files_excluded,
        ))

    return _ScanProgress(
        job_id=job_id,
        state=state,
        phase=status.get("phase"),
        current_dimension=status.get("current_dimension"),
        project_files=project_files,
        total_elapsed_s=total_elapsed_s,
        budget_s=run_budget_s,
        exit_reason=status.get("exit_reason"),
        dimensions=dim_results,
    )
