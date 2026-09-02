"""Reads/writes ``{run_dir}/status.json`` (state machine in core/run/state).

All state transitions go through ``validate_transition``; hand-rolled JSON is
never written to disk by any other code path.

Failure philosophy: file reads return ``None`` on missing/corrupt; writes
raise only on illegal state transitions or genuine IO errors caller can
propagate.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quodeq.core.run.state import (  # noqa: F401 — re-exported API
    SCHEMA_VERSION,
    STATUS_FILENAME,
    TERMINAL_STATES,
    IllegalTransitionError,
    RunState,
    UnsupportedSchemaError,
    validate_transition,
)

_logger = logging.getLogger(__name__)

# Reentrant: the lifecycle SIGINT/SIGTERM handler runs on the main thread and
# writes status itself. A plain Lock deadlocks when the signal interrupts a
# frame that is already inside write_status holding the lock. Cross-thread
# exclusion is unchanged; the atomic tmp+rename keeps reentrant interleaving
# consistent (the handler raises SystemExit, so the interrupted write's
# remaining statements never run).
_write_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _build_status_payload(
    *,
    state: RunState,
    job_id: str,
    started_at: str,
    dimensions: list[str],
    phase: str | None,
    current_dimension: str | None,
    pid: int | None,
    exit_reason: str | None,
    finalized_at: str | None,
    deadline_at: str | None,
    ai_provider: str | None,
    ai_model: str | None,
    time_limit_s: int | None,
) -> dict[str, Any]:
    if pid is None:
        pid = os.getpid()
    if finalized_at is None and state in TERMINAL_STATES:
        finalized_at = _now_iso()
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "state": state.value,
        "started_at": started_at,
        "updated_at": _now_iso(),
        "finalized_at": finalized_at,
        "phase": phase,
        "current_dimension": current_dimension,
        "dimensions": dimensions,
        "pid": pid,
        "exit_reason": exit_reason,
        "deadline_at": deadline_at,
    }
    if time_limit_s is not None:
        payload["time_limit_s"] = time_limit_s
    if ai_provider is not None:
        payload["ai_provider"] = ai_provider
    if ai_model is not None:
        payload["ai_model"] = ai_model
    return payload


def write_status(
    run_dir: Path,
    *,
    state: RunState,
    job_id: str,
    started_at: str,
    dimensions: list[str],
    phase: str | None = None,
    current_dimension: str | None = None,
    pid: int | None = None,
    exit_reason: str | None = None,
    finalized_at: str | None = None,
    deadline_at: str | None = None,
    ai_provider: str | None = None,
    ai_model: str | None = None,
    time_limit_s: int | None = None,
) -> None:
    """Atomically write status.json with *state* and metadata.

    Uses write-tmp-then-rename so readers never see a partial file.
    Caller is responsible for calling ``validate_transition`` first if a
    transition is being performed.
    """
    payload = _build_status_payload(
        state=state, job_id=job_id, started_at=started_at, dimensions=dimensions,
        phase=phase, current_dimension=current_dimension, pid=pid,
        exit_reason=exit_reason, finalized_at=finalized_at, deadline_at=deadline_at,
        ai_provider=ai_provider, ai_model=ai_model, time_limit_s=time_limit_s,
    )
    body = json.dumps(payload, indent=2)
    tmp_path = run_dir / (STATUS_FILENAME + ".tmp")
    final_path = run_dir / STATUS_FILENAME
    with _write_lock:
        tmp_path.write_text(body, encoding="utf-8")
        tmp_path.replace(final_path)


def read_status(run_dir: Path) -> dict[str, Any] | None:
    """Return parsed status.json or None if missing/corrupt.

    Raises UnsupportedSchemaError if the schema_version is newer than this code supports.
    """
    path = run_dir / STATUS_FILENAME
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        _logger.warning("corrupt status.json at %s", path)
        return None
    if not isinstance(data, dict):
        _logger.warning("status.json contains non-dict JSON at %s", path)
        return None
    schema = data.get("schema_version", 0)
    if isinstance(schema, int) and schema > SCHEMA_VERSION:
        raise UnsupportedSchemaError(f"status.json schema_version={schema} newer than supported ({SCHEMA_VERSION})")
    return data
