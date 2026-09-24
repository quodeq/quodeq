"""status.json readers for index-served run snapshots.

Split out of ``_evaluations_index.py``: external (``ext-``) runs
are not tracked by JobManager, so their dashboard-facing fields (dimensions,
deadline, provider/model, time limit) are read straight from disk. All five
readers, plus ``build_job_snapshot`` which assembles a ``JobSnapshot`` from
an index ``RunRow`` using them, live here; ``_evaluations_index.py``
re-exports every name for backward compatibility. ``status_json_terminal``
(the terminal-state check) also lives here — ``_run_index_fs.py``
needs it too, and putting it in ``_evaluations_index.py`` would have made
that a circular import.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.run.job_status import is_external_job_id
from quodeq.core.run.state import TERMINAL_STATES
from quodeq.core.types.job import JobSnapshot
from quodeq.services.wiring import read_run_state, read_run_status_json
from quodeq.services.wiring import run_index as _run_index


def status_json_terminal(run_dir: Path) -> bool:
    """Return True when the run's status.json says it ended."""
    state = read_run_state(run_dir)
    return state is not None and state in TERMINAL_STATES


def tail_run_log(run_dir: Path, max_lines: int = 500) -> list[str]:
    """Return the last *max_lines* lines from run.log.

    Reads backward from the end in growing chunks instead of the whole file,
    so a multi-MB in-progress log costs O(tail size) per call, not O(file
    size). ``run.log`` is append-only in practice (no in-place rewrites), so
    a stale byte count from a concurrent writer only risks re-reading a few
    extra bytes on the next call, never corrupting output.
    """
    log_path = run_dir / "run.log"
    if not log_path.is_file():
        return []
    try:
        file_size = log_path.stat().st_size
        chunk = 8192
        data = b""
        with log_path.open("rb") as fp:
            read_to = file_size
            while read_to > 0:
                read_from = max(0, read_to - chunk)
                fp.seek(read_from)
                data = fp.read(read_to - read_from) + data
                read_to = read_from
                # +1: need max_lines *complete* lines, i.e. max_lines newlines
                # before the final one (or we've hit the start of the file).
                if data.count(b"\n") > max_lines or read_from == 0:
                    break
                chunk *= 2
        text = data.decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]  # trailing newline produces one empty split segment
    # Text-mode writers on Windows produce CRLF; the old text-mode reader's
    # universal newlines absorbed the \r, the byte-level split must drop it.
    lines = [line.removesuffix("\r") for line in lines]
    return lines[-max_lines:] if len(lines) > max_lines else lines


def _load_status_json(run_dir: Path) -> dict:
    """Load and parse status.json; ``{}`` when missing, unreadable, or not a dict."""
    data = read_run_status_json(run_dir)
    return data if isinstance(data, dict) else {}


def _dimensions_from_data(run_dir: Path, data: dict | None) -> list[str] | None:
    """Extract dimensions from parsed status.json data."""
    if data is None:
        return None
    dims = data.get("dimensions")
    if not isinstance(dims, list):
        return None
    if dims:
        return dims
    from quodeq.shared.dim_estimates_io import read_dim_estimates
    from quodeq.services.wiring import read_dimensions
    recovered: dict[str, None] = {}
    dim_records = read_dimensions(run_dir).get("dimensions")
    record_keys = dim_records.keys() if isinstance(dim_records, dict) else ()
    for key in (*record_keys, *read_dim_estimates(run_dir).keys()):
        recovered.setdefault(key, None)
    return list(recovered) if recovered else dims


def _time_limit_from_data(data: dict | None) -> int | None:
    """Extract time_limit_s from parsed status.json data."""
    if data is None:
        return None
    raw = data.get("time_limit_s")
    return raw if isinstance(raw, int) else None


def _deadline_from_data(data: dict | None) -> str | None:
    """Extract deadline_at from parsed status.json data."""
    if data is None:
        return None
    val = data.get("deadline_at")
    return val if isinstance(val, str) else None


def _provider_model_from_data(data: dict | None) -> tuple[str | None, str | None]:
    """Extract (ai_provider, ai_model) from parsed status.json data."""
    if data is None:
        return (None, None)
    provider = data.get("ai_provider")
    model = data.get("ai_model")
    return (
        provider if isinstance(provider, str) else None,
        model if isinstance(model, str) else None,
    )


def read_dimensions_from_status(run_dir: Path) -> list[str] | None:
    """Read the `dimensions` list from status.json, or None if unavailable.

    "All dimensions" runs record an empty list (the raw, unresolved CLI
    filter is None). The UI fetches per-dim evals from this list, so an
    empty one blanks the live findings feed for every full scan served via
    the index. Recover the resolved list from the per-dim sidecars, the
    same fallback scan_progress uses.
    """
    return _dimensions_from_data(run_dir, _load_status_json(run_dir))


def read_time_limit_from_status(run_dir: Path) -> int | None:
    """Read the run budget (`time_limit_s`) from status.json, or None."""
    return _time_limit_from_data(_load_status_json(run_dir))


def read_deadline_from_status(run_dir: Path) -> str | None:
    """Read the `deadline_at` ISO string from status.json, or None.

    External (CLI) runs are not tracked by JobManager so they don't go
    through the marker-parsing path that sets ``Job.deadline_at``. Reading
    directly from status.json keeps the dashboard's countdown ticking.
    """
    return _deadline_from_data(_load_status_json(run_dir))


def read_provider_model_from_status(run_dir: Path) -> tuple[str | None, str | None]:
    """Read (ai_provider, ai_model) from status.json, or (None, None).

    External (CLI) runs aren't tracked by JobManager, so they don't carry
    provider/model on an in-memory Job. Reading directly from status.json
    keeps the dashboard's in-progress card self-describing for ext- runs.
    """
    return _provider_model_from_data(_load_status_json(run_dir))


def _read_enriched_status_fields(
    run_dir: Path, *, with_logs: bool = True,
) -> tuple[list[str], list[str] | None, str | None, str | None, str | None, int | None]:
    """Best-effort read of (logs, dimensions, deadline_at, ai_provider, ai_model, time_limit_s).

    Reads and parses status.json once, deriving all four status-backed
    fields from the same dict instead of four independent reads. With
    ``with_logs=False`` the 500-line run-log tail is skipped and logs is [].
    """
    logs: list[str] = []
    if with_logs:
        try:
            logs = tail_run_log(run_dir)
        except (OSError, ValueError):
            logs = []
    try:
        data = _load_status_json(run_dir)
    except (OSError, ValueError):
        data = None
    dimensions = _dimensions_from_data(run_dir, data)
    deadline_at = _deadline_from_data(data)
    ai_provider, ai_model = _provider_model_from_data(data)
    time_limit_s = _time_limit_from_data(data)
    return logs, dimensions, deadline_at, ai_provider, ai_model, time_limit_s


def build_job_snapshot(row: "_run_index.RunRow", *, with_logs: bool = True) -> JobSnapshot:
    """Assemble a ``JobSnapshot`` from an index row, enriched from status.json.

    ``with_logs=False`` leaves ``logs`` empty instead of tailing run.log.
    List reads pass it for non-running rows only: the dashboard adopts a
    running CLI job straight from the list and shows its logs.
    """
    logs: list[str] = []
    dimensions: list[str] | None = None
    deadline_at: str | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    time_limit_s: int | None = None
    if row.run_dir:
        logs, dimensions, deadline_at, ai_provider, ai_model, time_limit_s = (
            _read_enriched_status_fields(Path(row.run_dir), with_logs=with_logs)
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
        source="external" if is_external_job_id(row.job_id) else "internal",
        exit_reason=row.exit_reason,
        ai_provider=ai_provider,
        ai_model=ai_model,
        time_limit_s=time_limit_s,
    )
