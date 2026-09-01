"""status.json readers for index-served run snapshots.

Split (Task 14) out of ``_evaluations_index.py``: external (``ext-``) runs
are not tracked by JobManager, so their dashboard-facing fields (dimensions,
deadline, provider/model, time limit) are read straight from disk. All five
readers, plus ``build_job_snapshot`` which assembles a ``JobSnapshot`` from
an index ``RunRow`` using them, live here; ``_evaluations_index.py``
re-exports every name for backward compatibility.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.types.job import JobSnapshot
from quodeq.data.sqlite import run_index as _run_index


def _tail_run_log(run_dir: Path, max_lines: int = 500) -> list[str]:
    """Return the last *max_lines* lines from run.log."""
    log_path = run_dir / "run.log"
    if not log_path.is_file():
        return []
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as fp:
            lines = fp.readlines()
    except OSError:
        return []
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    return [line.rstrip("\n") for line in tail]


def _read_dimensions_from_status(run_dir: Path) -> list[str] | None:
    """Read the `dimensions` list from status.json, or None if unavailable.

    "All dimensions" runs record an empty list (the raw, unresolved CLI
    filter is None). The UI fetches per-dim evals from this list, so an
    empty one blanks the live findings feed for every full scan served via
    the index. Recover the resolved list from the per-dim sidecars, the
    same fallback scan_progress uses.
    """
    status_path = run_dir / "status.json"
    if not status_path.is_file():
        return None
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    dims = data.get("dimensions")
    if not isinstance(dims, list):
        return None
    if dims:
        return dims
    from quodeq.shared.dim_estimates_io import read_dim_estimates
    from quodeq.data.fs.dimensions_state_store import read_dimensions
    recovered: dict[str, None] = {}
    dim_records = read_dimensions(run_dir).get("dimensions")
    record_keys = dim_records.keys() if isinstance(dim_records, dict) else ()
    for key in (*record_keys, *read_dim_estimates(run_dir).keys()):
        recovered.setdefault(key, None)
    return list(recovered) if recovered else dims


def _read_time_limit_from_status(run_dir: Path) -> int | None:
    """Read the run budget (`time_limit_s`) from status.json, or None."""
    status_path = run_dir / "status.json"
    if not status_path.is_file():
        return None
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    raw = data.get("time_limit_s")
    return raw if isinstance(raw, int) else None


def _read_deadline_from_status(run_dir: Path) -> str | None:
    """Read the `deadline_at` ISO string from status.json, or None.

    External (CLI) runs are not tracked by JobManager so they don't go
    through the marker-parsing path that sets ``Job.deadline_at``. Reading
    directly from status.json keeps the dashboard's countdown ticking.
    """
    status_path = run_dir / "status.json"
    if not status_path.is_file():
        return None
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    val = data.get("deadline_at")
    return val if isinstance(val, str) else None


def _read_provider_model_from_status(run_dir: Path) -> tuple[str | None, str | None]:
    """Read (ai_provider, ai_model) from status.json, or (None, None).

    External (CLI) runs aren't tracked by JobManager, so they don't carry
    provider/model on an in-memory Job. Reading directly from status.json
    keeps the dashboard's in-progress card self-describing for ext- runs.
    """
    status_path = run_dir / "status.json"
    if not status_path.is_file():
        return (None, None)
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (None, None)
    if not isinstance(data, dict):
        return (None, None)
    provider = data.get("ai_provider")
    model = data.get("ai_model")
    return (
        provider if isinstance(provider, str) else None,
        model if isinstance(model, str) else None,
    )


def _read_enriched_status_fields(
    run_dir: Path,
) -> tuple[list[str], list[str] | None, str | None, str | None, str | None, int | None]:
    """Best-effort read of (logs, dimensions, deadline_at, ai_provider, ai_model, time_limit_s)."""
    try:
        logs = _tail_run_log(run_dir)
    except (OSError, ValueError):
        logs = []
    try:
        dimensions = _read_dimensions_from_status(run_dir)
    except (OSError, ValueError):
        dimensions = None
    try:
        deadline_at = _read_deadline_from_status(run_dir)
    except (OSError, ValueError):
        deadline_at = None
    try:
        ai_provider, ai_model = _read_provider_model_from_status(run_dir)
    except (OSError, ValueError):
        ai_provider, ai_model = None, None
    try:
        time_limit_s = _read_time_limit_from_status(run_dir)
    except (OSError, ValueError):
        time_limit_s = None
    return logs, dimensions, deadline_at, ai_provider, ai_model, time_limit_s


def build_job_snapshot(row: "_run_index.RunRow") -> JobSnapshot:
    """Assemble a ``JobSnapshot`` from an index row, enriched from status.json."""
    logs: list[str] = []
    dimensions: list[str] | None = None
    deadline_at: str | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    time_limit_s: int | None = None
    if row.run_dir:
        logs, dimensions, deadline_at, ai_provider, ai_model, time_limit_s = (
            _read_enriched_status_fields(Path(row.run_dir))
        )
    return JobSnapshot(
        job_id=row.job_id,
        status=row.state,
        command="",
        started_at=row.started_at,
        ended_at=row.finalized_at,
        exit_code=None,
        logs=logs,
        output_project=row.project_uuid,
        output_run_id=row.run_id,
        phase=row.phase,
        deadline_at=deadline_at,
        current_dimension=row.current_dimension,
        dimensions=dimensions,
        error=row.exit_reason,
        source="external" if row.job_id.startswith("ext-") else "internal",
        exit_reason=row.exit_reason,
        ai_provider=ai_provider,
        ai_model=ai_model,
        time_limit_s=time_limit_s,
    )
