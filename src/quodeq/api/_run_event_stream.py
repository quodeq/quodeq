"""SSE watcher and event serializers for /api/evaluations/<jobId>/events.

Producers (lifecycle context, scoring engine, FindingsRouter) write durable
artifacts (status.json, evaluation/<dim>.json, events.jsonl). This module
observes those artifacts on a 250 ms tick and emits SSE events to subscribers.

Reconnect via Last-Event-ID is supported by ISO 8601 timestamps stored in
events.jsonl (the run event log written by EventLogWriter / FindingsRouter).

Serializers live in _run_event_serializers.py, the per-tick artifact reader
in _run_event_watcher.py; both are re-exported here for backward-compatible
imports (tests import them from this module).
"""
from __future__ import annotations

import json
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Iterator

from quodeq.api._run_event_serializers import (  # noqa: F401 — re-export
    serialize_dimension_event,
    serialize_finding_event,
    serialize_status_event,
    payload_as_sse_finding,
)
from quodeq.api._run_event_watcher import (  # noqa: F401 — re-export
    DEFAULT_FINDINGS_BATCH,
    STATUS_MTIME_MISSING,
    EventTuple,
    WatcherState,
    findings_batch_size,
    read_dim_eval,
    read_new_findings_from_events,
    read_status,
    scan_completed_dimensions,
    compute_tick,
)
from quodeq.api._sse_log_helpers import sse_line
from quodeq.core.run.state import TERMINAL_STATES
from quodeq.shared.env import env_float
from quodeq.shared.env_resolve import resolve_env

_EVENT_TYPE_STATUS = "status"  # compute_tick's event tuple tag for a status.json change
_DEFAULT_TICK_MS = 250  # QUODEQ_SSE_TICK_MS fallback: observer poll cadence
_DEFAULT_HEARTBEAT_S = 15.0  # QUODEQ_SSE_HEARTBEAT_S fallback: :keepalive interval
_MIN_HEARTBEAT_S = 0.1  # floor: keeps a bogus tiny/negative override from turning every tick into a keepalive frame


def _tick_ms(env: Mapping[str, str] | None = None) -> int:
    """Read tick interval at call time so tests can set QUODEQ_SSE_TICK_MS=0
    to force a single-tick drain. Reading at module import time made the env
    var a no-op for tests that set it inside the test body."""
    try:
        return int(resolve_env(env).get("QUODEQ_SSE_TICK_MS", str(_DEFAULT_TICK_MS)))
    except ValueError:
        return _DEFAULT_TICK_MS


def _heartbeat_s(env: Mapping[str, str] | None = None) -> float:
    """Read the SSE :keepalive interval at call time, once per stream.

    env_float never raises, so a malformed QUODEQ_SSE_HEARTBEAT_S can't abort
    a stream (it logs and falls back to the default).
    """
    return env_float("QUODEQ_SSE_HEARTBEAT_S", _DEFAULT_HEARTBEAT_S, minimum=_MIN_HEARTBEAT_S, env=env)


def _is_terminal(status_payload: str) -> tuple[bool, str]:
    """Check whether the JSON status payload represents a terminal state."""
    try:
        data = json.loads(status_payload)
    except ValueError:
        return False, ""
    state = data.get("state") if isinstance(data, dict) else None
    if isinstance(state, str) and state in TERMINAL_STATES:
        return True, state
    return False, ""


def _format_tick_frames(
    run_dir: Path, state: WatcherState,
) -> tuple[list[str], str, WatcherState]:
    """Run one tick and format its events as SSE frames.

    Returns (frames, terminal_state, new_state); terminal_state is "" unless
    a status event in this tick reports a terminal state.
    """
    events, new_state = compute_tick(run_dir, state)
    frames: list[str] = []
    terminal_state = ""
    for event_type, payload, event_id in events:
        frames.append(sse_line(payload, event=event_type, event_id=event_id))
        if event_type == _EVENT_TYPE_STATUS:
            done, terminal = _is_terminal(payload)
            if done:
                terminal_state = terminal
    return frames, terminal_state, new_state


def _done_frame(terminal_state: str) -> str:
    """SSE `event: done` frame closing the stream on a terminal status."""
    return sse_line(json.dumps({"state": terminal_state}, separators=(",", ":")), event="done")


def run_events_generator(
    run_dir: Path,
    *,
    last_event_ts: datetime | None = None,
    tick_seconds: float | None = None,
    heartbeat_seconds: float | None = None,
) -> Iterator[str]:
    """Yield SSE frames observing run_dir.

    tick_seconds overrides QUODEQ_SSE_TICK_MS for tests (0.0 drains a single
    tick without sleeping). heartbeat_seconds overrides the 15s :keepalive
    interval for tests.
    """
    sleep_s = tick_seconds if tick_seconds is not None else (_tick_ms() / 1000.0)
    heartbeat_s = heartbeat_seconds if heartbeat_seconds is not None else _heartbeat_s()
    state = WatcherState(last_event_ts=last_event_ts)
    last_emit_at = time.monotonic()
    yield ":keepalive\n\n"

    while True:
        frames, terminal_state, state = _format_tick_frames(run_dir, state)
        for frame in frames:
            yield frame
            last_emit_at = time.monotonic()

        # Terminal status closes the stream. Score updates no longer flow
        # through SSE — mutations ride on their HTTP response instead.
        if terminal_state:
            yield _done_frame(terminal_state)
            return

        if time.monotonic() - last_emit_at >= heartbeat_s:
            yield ":keepalive\n\n"
            last_emit_at = time.monotonic()

        if sleep_s > 0:
            time.sleep(sleep_s)
        else:
            # tick_seconds=0.0 means "drain once and exit" for tests.
            return
