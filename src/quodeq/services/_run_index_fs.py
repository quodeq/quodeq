"""Run-index housekeeping: liveness and merge, plus the fallback-scan sync.

Split out of ``_evaluations_index.py``. Nothing patches
these directly (verified: no test reaches ``EvaluationsIndex`` internals by
name) so they move as plain free functions — no re-export required, callers
are ``EvaluationsIndex`` methods only. ``_evaluations_index.py`` is a
DECLARED_LOGGING_SITES entry; this sibling does not add a new logging
import.

``remove_run_directory`` and ``scan_reports_root_for_run`` themselves live in
``data/fs/run_dirs.py`` (plain filesystem operations, no run-index business
logic); re-exported here via ``services/wiring.py`` so this module's own
callers (``_evaluations_index.py``, ``_external_jobs.py``) don't need to
change their import path.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.run.job_status import JobStatus
from quodeq.core.types.job import JobSnapshot
from quodeq.services.wiring import remove_run_directory, scan_reports_root_for_run  # noqa: F401
from quodeq.services.wiring import run_index as _run_index
from quodeq.services._run_status_readers import status_json_terminal


def merge_internal_jobs(
    snapshots: list[JobSnapshot], internal_jobs: list[JobSnapshot],
) -> list[JobSnapshot]:
    """Merge SQLite-index snapshots with in-memory internal jobs.

    Internal dashboard-spawned jobs always take priority over index rows
    that project the same on-disk run. The dedup key is (project, run_id)
    rather than job_id because internal jobs carry bare UUIDs while
    indexed rows carry "ext-<run_id>" — keying on job_id never matches
    the two views of the same run and both end up in the merged list.

    'lost' internal jobs are restart placeholders whose subprocess may
    still be alive: they must not shadow the truthful ext- row derived
    from the run's own status.json, and when such a row exists the
    placeholder itself is dropped in its favor.
    """
    covered = {
        (j.output_project, j.output_run_id) for j in internal_jobs
        if j.output_project and j.output_run_id and j.status != JobStatus.LOST
    }
    row_keys = {
        (s.output_project, s.output_run_id) for s in snapshots
        if s.output_project and s.output_run_id
    }
    visible_internal = [
        j for j in internal_jobs
        if not (
            j.status == JobStatus.LOST
            and (j.output_project, j.output_run_id) in row_keys
        )
    ]
    return [
        s for s in snapshots
        if (s.output_project, s.output_run_id) not in covered
    ] + visible_internal


def sync_external_run_by_scan(db, reports_dir: Path, run_id: str) -> None:
    """Fallback for an "ext-" id the index has no usable run_dir for yet.

    Scans every project dir under *reports_dir* for ``<project>/<run_id>``
    and syncs just that run when found; otherwise falls back to a full
    ``sync_index`` so a brand-new run still gets picked up. Once a run has
    been indexed once, ``get_status`` resolves it straight from its stored
    ``run_dir`` instead of reaching this scan again.
    """
    candidate = scan_reports_root_for_run(reports_dir, run_id)
    if candidate is not None:
        _run_index.sync_index_for_run(db, candidate)
        return
    _run_index.sync_index(db, reports_dir)


def external_job_is_complete(run_dir: Path) -> bool:
    """True when an external (``ext-``) job's *run_dir* shows it has ended."""
    if (run_dir / "scan.json").exists():
        return True
    if status_json_terminal(run_dir):
        return True
    from quodeq.services._external_jobs import resolve_external_pid  # noqa: PLC0415
    pid_file = run_dir / ".pid"
    if not pid_file.exists():
        return True  # no PID file -> stale/crashed -> complete
    # run_dir is already resolved; pass its parent straight through
    # instead of splitting it into names and rejoining them.
    return resolve_external_pid(run_dir.parent, run_dir.name) is None
