"""Per-tick artifact readers for the SSE run-event watcher.

Reads status.json, evaluation/<dim>.json, and events.jsonl for
``api/_run_event_watcher.py``'s ``compute_tick``. Split out so the API layer
stops touching those files directly and instead goes through the same
readers (``wiring.read_eval_report``, ``wiring.EventLogReader``) every other
service uses.

``read_status`` is the one exception: it reads status.json inline rather
than through ``wiring.read_status`` (``data/fs/run_status_store.read_status``)
or ``wiring.read_run_status_json``. Both of those already log a warning
internally on a read/parse failure, and letting this caller log again on
top would double the WARNING records a corrupt status.json produces, and
add a WARNING (there was none) for non-dict JSON -- a caller-side log
regression a fix-round review caught. The old inline reader is the only
way to keep the exact record count, logger, and message this caller had
before the SSE-reader move, since the exception text those other readers
would need to reproduce it is swallowed inside them.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from quodeq.core.events.models import EventType
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.run.state import RunState
from quodeq.services import wiring
from quodeq.shared.env_resolve import resolve_env

DEFAULT_FINDINGS_BATCH = 500
"""Per-tick cap on findings pulled from the event log for the SSE stream.

Bounds the initial-snapshot burst so a run with tens of thousands of findings
cannot OOM the API process. Subsequent ticks resume from the last event
timestamp via the SSE Last-Event-ID mechanism.
"""

DIM_FILENAME_SUFFIX = ".json"

STATUS_MTIME_MISSING: float = 0.0
"""Sentinel mtime used when status.json does not exist.

WatcherState initialises last_status_mtime=None ("never checked"), which is
distinct from 0.0 ("checked, file absent"). This ensures the pending status
is always emitted on the very first tick even when there is no status.json.
"""


def findings_batch_size(env: Mapping[str, str] | None = None) -> int:
    """QUODEQ_SSE_FINDINGS_BATCH, default DEFAULT_FINDINGS_BATCH; 0/invalid -> default."""
    raw = resolve_env(env).get("QUODEQ_SSE_FINDINGS_BATCH")
    if not raw:
        return DEFAULT_FINDINGS_BATCH
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_FINDINGS_BATCH
    return value if value > 0 else DEFAULT_FINDINGS_BATCH


def read_status(run_dir: Path, *, log: LogSink = NULL_LOG) -> tuple[dict[str, Any], float]:
    """Read status.json. Returns ``({state: pending}, 0.0)`` when the file
    is absent.

    Reads and parses inline (see the module docstring for why this one
    reader doesn't delegate to ``wiring``): no log on a missing file (not
    started yet, not an error), exactly one WARNING -- logged here, with
    the real exception text -- on a read/parse failure, no log at all when
    the JSON parses but isn't a dict (also not an error, just not a status
    payload). Schema version is not validated, matching the pre-move
    reader; a newer schema than this code understands is served as-is
    rather than downgraded to pending.
    """
    path = run_dir / wiring.STATUS_FILENAME
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {"state": RunState.PENDING}, STATUS_MTIME_MISSING
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"state": RunState.PENDING}, mtime
        return data, mtime
    except (OSError, ValueError) as exc:
        log.warning(f"status.json read failed at {path}: {exc}")
        return {"state": RunState.PENDING}, mtime


def scan_completed_dimensions(run_dir: Path) -> set[str]:
    """Return the set of dimension names that have an evaluation/<dim>.json file."""
    eval_dir = run_dir / "evaluation"
    try:
        return {
            entry.name[: -len(DIM_FILENAME_SUFFIX)]
            for entry in eval_dir.iterdir()
            if entry.is_file() and entry.name.endswith(DIM_FILENAME_SUFFIX)
        }
    except OSError:
        return set()


def read_dim_eval(
    run_dir: Path, dimension: str, *, log: LogSink = NULL_LOG,
) -> dict[str, Any] | None:
    """Read evaluation/<dim>.json via ``wiring.read_eval_report``. Returns
    None on any failure (missing file, unreadable, or malformed JSON).

    The returned dict's ``dimension`` key is the canonical dimension name as
    written by the scoring engine. Callers should treat that value as
    authoritative — it always matches the filename stem for well-formed files.
    """
    eval_dir = run_dir / "evaluation"
    path = eval_dir / f"{dimension}{DIM_FILENAME_SUFFIX}"
    try:
        data = wiring.read_eval_report(eval_dir, dimension)
    except (OSError, ValueError) as exc:
        log.warning(f"dimension eval read failed at {path}: {exc}")
        return None
    if data is None:
        log.warning(f"dimension eval read failed at {path}: file not found")
        return None
    return data if isinstance(data, dict) else None


def read_new_findings_from_events(
    run_dir: Path,
    last_event_ts: datetime | None,
    counter_start: int,
    *,
    log: LogSink = NULL_LOG,
) -> list[tuple[datetime, int, Any]]:
    """Return (event_ts, counter, payload) triples for new JUDGMENT_CREATED events.

    Reads from run_dir/events.jsonl via wiring.EventLogReader.stream(since_timestamp).
    Caps at findings_batch_size() results per call so a large initial snapshot
    cannot OOM the API process. Subsequent ticks resume via last_event_ts.

    *payload* is the raw event payload (a Judgment-shaped object); shaping it
    into the SSE finding dict is the caller's job (``payload_as_sse_finding``
    in ``api/_run_event_serializers.py``), so this reader stays free of
    delivery-format concerns.
    """
    events_log = run_dir / "events.jsonl"
    if not events_log.is_file():
        return []
    try:
        results: list[tuple[datetime, int, Any]] = []
        counter = counter_start
        batch_limit = findings_batch_size()
        for event in wiring.EventLogReader(events_log).stream(since_timestamp=last_event_ts):
            if event.event_type != EventType.JUDGMENT_CREATED:
                continue
            counter += 1
            results.append((event.timestamp, counter, event.payload))
            if len(results) >= batch_limit:
                break
        return results
    except Exception as exc:  # noqa: BLE001 — never crash the stream on read errors
        log.warning(f"events.jsonl read failed for {run_dir}: {exc}")
        return []
