"""Read-only liveness resolution for external (CLI-started) runs.

``quodeq evaluate`` writes a ``.pid`` file at run start; the dashboard uses
it to distinguish an in-progress external run from a historical one. Only
the read/probe path lives here — the cancel path (signal delivery) stays in
``services/_external_jobs.py``.
"""
from __future__ import annotations

import re
from pathlib import Path

from quodeq.data.sqlite._index_sync import _is_pid_alive

_PID_FILENAME = ".pid"

# Charset of a legitimate project/run directory name (UUIDs in practice).
# Excludes path separators; "." and ".." are rejected separately below.
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9._-]+")


def is_safe_run_segment(value: str) -> bool:
    """True when *value* is safe to use as a single path segment.

    Guards externally-supplied run/project ids (e.g. the tail of an
    ``ext-<run_id>`` job id from the API) before any filesystem path is
    built from them. Rejects empty strings, ``.``/``..`` and anything
    outside ``[A-Za-z0-9._-]``.
    """
    return bool(_SAFE_ID_RE.fullmatch(value)) and value not in (".", "..")


def resolve_external_pid(project_uuid: str, run_id: str, reports_root: Path) -> int | None:
    """Find the PID of the process running an external job, for cancellation.

    Looks for a `.pid` file written by `quodeq evaluate` at run start. Returns
    None if not found or the process is already gone.
    """
    if not is_safe_run_segment(project_uuid) or not is_safe_run_segment(run_id):
        return None
    pid_file = reports_root / project_uuid / run_id / _PID_FILENAME
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    # _is_pid_alive rather than os.kill(pid, 0) -- signal 0 is unsafe on
    # Windows (CTRL_C_EVENT can broadcast Ctrl+C to the calling process).
    if not _is_pid_alive(pid):
        return None
    return pid
