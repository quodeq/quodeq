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

Data shapes (``_DimProgress``/``_ScanProgress``) live in
``_scan_progress_types.py``; per-dim elapsed-time math lives in
``_scan_progress_elapsed.py``; per-dim progress-row construction lives in
``_scan_progress_dims.py`` -- all split out to keep this module under the
size ratchet's 300-line cap.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from quodeq.config.paths import default_paths
from quodeq.services._scan_progress_dims import _build_dim_progress, _consolidated_dim_progress
from quodeq.services._scan_progress_elapsed import _parse_started_at
from quodeq.services._scan_progress_types import _DimProgress, _ScanProgress  # noqa: F401 - re-export
from quodeq.services._wiring import read_run_status_json, read_scan_total_files
from quodeq.services.suppression import project_suppressions
from quodeq.shared.dim_estimates_io import read_dim_estimates
from quodeq.data.fs.dimensions_state_store import read_dimensions


def _project_total_files(run_dir: Path) -> int:
    """Read project_files (upper bound for pending dims) from scan.json."""
    return read_scan_total_files(run_dir.parent)


def _compute_total_elapsed(status: dict, state: str, started_at: datetime | None) -> float | None:
    if state == "running" and started_at:
        return max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())
    if started_at and status.get("finalized_at"):
        try:
            end = datetime.fromisoformat(status["finalized_at"])
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            return max(0.0, (end - started_at).total_seconds())
        except (ValueError, TypeError):
            return None
    return None


def _recover_dim_ids(status: dict, dim_records: dict, dim_estimates: dict) -> list[str]:
    dim_ids = list(status.get("dimensions") or [])
    if dim_ids:
        return dim_ids
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
    return list(recovered)


def _maybe_consolidated_live_progress(
    job_id: str, run_dir: Path, status: dict, state: str, is_terminal: bool,
    dim_ids: list[str], project_files: int, total_elapsed_s: float | None, run_budget_s: int | None,
) -> _ScanProgress | None:
    """Consolidated (grouped) runs dispatch every dimension in one pass and
    write consolidated_* files — there are no per-dim queues, so the per-dim
    reader would report 0% / "estimating…" for the whole run. While such a
    run is live, report the consolidated pass as one row with the real file
    counts. Once the run is terminal the per-dim evaluation files exist and
    normal per-dim classification applies. Returns None when this doesn't
    apply (caller falls through to per-dim classification)."""
    evidence_dir = run_dir / "evidence"
    consolidated_queue = evidence_dir / "consolidated_queue.json"
    if (
        is_terminal
        or not consolidated_queue.is_file()
        or any((evidence_dir / f"{d}_queue.json").is_file() for d in dim_ids)
    ):
        return None
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


def _gather_progress_context(status: dict, run_dir: Path, time_limit_s: int | None):
    """Resolve the run-level scalars build_scan_progress needs before
    dispatching to the consolidated-live check or the per-dim loop."""
    state = status.get("state") or "unknown"
    is_terminal = state in {"done", "failed", "cancelled"}
    started_at = _parse_started_at(status)
    total_elapsed_s = _compute_total_elapsed(status, state, started_at)
    run_budget_s = time_limit_s if (time_limit_s and time_limit_s > 0) else None
    project_files = _project_total_files(run_dir)
    dim_estimates = read_dim_estimates(run_dir)
    dim_records = read_dimensions(run_dir).get("dimensions") or {}
    dim_ids = _recover_dim_ids(status, dim_records, dim_estimates)
    return (
        state, is_terminal, total_elapsed_s, run_budget_s, project_files,
        dim_estimates, dim_records, dim_ids,
    )


def _build_per_dim_progress(
    job_id: str, run_dir: Path, status: dict, state: str, is_terminal: bool,
    dim_records: dict, dim_estimates: dict, dim_ids: list[str],
    evidence_dir: Path, evaluators_dir: Path | None, compiled_dir: Path | None,
    project_files: int, total_elapsed_s: float | None, run_budget_s: int | None,
) -> _ScanProgress:
    # The scanner re-finds everything the user has dismissed or deleted, so a
    # raw evidence tally can run several times the number the finished report
    # shows. Read the suppression stores once per tick and net them out here,
    # so the live counters and the run report never tell different stories.
    dismissed, deleted = project_suppressions(run_dir.parent)

    dim_results = [
        _build_dim_progress(
            dim_id, run_dir, status, is_terminal, dim_records, dim_estimates,
            dismissed, deleted, evidence_dir, evaluators_dir, compiled_dir,
        )
        for dim_id in dim_ids
    ]

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
    status = read_run_status_json(run_dir)
    if not status:
        return None

    (
        state, is_terminal, total_elapsed_s, run_budget_s, project_files,
        dim_estimates, dim_records, dim_ids,
    ) = _gather_progress_context(status, run_dir, time_limit_s)
    evidence_dir = run_dir / "evidence"
    evaluators_dir = default_paths().evaluators_dir

    consolidated = _maybe_consolidated_live_progress(
        job_id, run_dir, status, state, is_terminal, dim_ids,
        project_files, total_elapsed_s, run_budget_s,
    )
    if consolidated is not None:
        return consolidated

    return _build_per_dim_progress(
        job_id, run_dir, status, state, is_terminal, dim_records, dim_estimates,
        dim_ids, evidence_dir, evaluators_dir, compiled_dir,
        project_files, total_elapsed_s, run_budget_s,
    )
