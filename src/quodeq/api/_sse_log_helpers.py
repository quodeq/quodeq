"""Shared SSE helpers for log-stream routes."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

_POLL_MS = int(os.environ.get("QUODEQ_LOG_STREAM_POLL_MS", "100"))
_MAX_WAIT_S = int(os.environ.get("QUODEQ_LOG_STREAM_MAX_WAIT_S", "10"))
# Cadence for SSE comments emitted while waiting on a not-yet-existing log
# file. Keeps the EventSource from being torn down by intermediaries even
# when the runner spends a long time in the "preparing" phase.
_KEEPALIVE_MS = 2000

# Per-tick byte cap on the SSE tail read. Caps a runaway log file from blowing
# out RAM in a single read; remaining bytes are served on the next tick.
_DEFAULT_TAIL_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB


def _tail_max_bytes() -> int:
    raw = os.environ.get("QUODEQ_LOG_TAIL_MAX_BYTES")
    if not raw:
        return _DEFAULT_TAIL_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_TAIL_MAX_BYTES
    return value if value > 0 else _DEFAULT_TAIL_MAX_BYTES


def sse_line(data: str, event: str | None = None, event_id: int | None = None) -> str:
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}\n")
    if event is not None:
        parts.append(f"event: {event}\n")
    parts.append(f"data: {data}\n\n")
    return "".join(parts)


def _emit_done_frame(terminal_state, offset: int) -> str:
    """Build the ``event: done`` frame that ends a tail stream.

    terminal_state: optional callable returning a string describing why the
             run ended (e.g. ``"cancelled"``, ``"failed"``, ``"completed"``).
             If provided and non-empty, that value rides in the done frame
             as ``data:`` so the client can show the right title without
             relying on a separate dashboard poll.
    """
    state = ""
    if terminal_state is not None:
        try:
            state = terminal_state() or ""
        except Exception:  # noqa: BLE001 — never block the done frame on a bad reader
            state = ""
    parts: list[str] = []
    if offset:
        parts.append(f"id: {offset}\n")
    parts.append("event: done\n")
    parts.append(f"data: {state}\n\n")
    return "".join(parts)


def _wait_for_log_file(is_done, waited_ms: int, keepalive_ms: int):
    """One poll tick while the log file doesn't exist yet.

    Two regimes when the file is missing:
      - is_done provided (job-log stream): wait as long as the job is still
        active. The runner's "preparing" phase (resolving inputs, cloning a
        remote repo) routinely takes longer than the legacy 10s timeout, and
        a 404 during that window shows up in the dashboard as a dead
        "stream disconnected" pane until the user reopens it.
      - is_done absent (legacy callers, e.g. ollama log stream): preserve
        the original "give up after _MAX_WAIT_S" behaviour so a missing file
        doesn't hang the connection forever.

    Yields keepalive/error SSE frames as needed. Returns
    ``(waited_ms, keepalive_ms, status)`` where status is ``"continue"``,
    ``"timeout"`` (error frame already yielded, caller should return), or
    ``"done"`` (is_done() returned True; caller emits the done frame).
    """
    if is_done is None:
        if waited_ms >= _MAX_WAIT_S * 1000:
            yield sse_line("log file unavailable", event="error")
            return waited_ms, keepalive_ms, "timeout"
        waited_ms += _POLL_MS
    else:
        if is_done():
            return waited_ms, keepalive_ms, "done"
        keepalive_ms += _POLL_MS
        if keepalive_ms >= _KEEPALIVE_MS:
            yield ":keepalive\n\n"
            keepalive_ms = 0
    time.sleep(_POLL_MS / 1000)
    return waited_ms, keepalive_ms, "continue"


def _tail_new_lines(path: Path, offset: int, line_filter):
    """Read new bytes from *path* since *offset*, yield an SSE frame per
    complete new line, and return the updated offset."""
    with open(path, "rb") as fh:
        fh.seek(offset)
        raw = fh.read(_tail_max_bytes())
    text = raw.decode("utf-8", errors="replace")
    if text:
        complete = text if text.endswith("\n") else text[: text.rfind("\n") + 1]
        if complete:
            for line in complete.splitlines():
                offset += len(line.encode("utf-8")) + 1  # +1 for '\n'
                if line_filter is None or line_filter(line):
                    yield sse_line(line, event_id=offset)
    return offset


def sse_tail_generator(
    log_path: Path | Callable[[], Path | None],
    initial_offset: int,
    is_done=None,
    line_filter=None,
    terminal_state=None,
):
    """Yield SSE frames by tailing *log_path*.

    log_path: either a ``Path`` or a zero-arg callable returning ``Path | None``.
             The callable form lets callers resolve the path lazily — useful
             when a job is still in the "preparing" phase and the run
             directory hasn't been created yet. The generator polls until the
             callable returns an existing file, emitting SSE comments to keep
             the EventSource alive in the meantime.
    is_done: optional callable returning True when streaming should terminate
             with an ``event: done`` frame. None means tail forever (subject
             to the legacy 10s ``_MAX_WAIT_S`` timeout when the file never
             materializes).
    line_filter: optional callable(str) -> bool. Lines for which it returns
             False are not emitted (kept in the file but hidden from clients).
    terminal_state: optional callable returning a string describing why the
             run ended; see :func:`_emit_done_frame`.
    """
    def _resolve() -> Path | None:
        return log_path() if callable(log_path) else log_path

    offset = initial_offset
    waited_ms = 0
    keepalive_ms = 0
    yield ":keepalive\n\n"
    while True:
        path = _resolve()
        if path is None or not path.exists():
            waited_ms, keepalive_ms, status = yield from _wait_for_log_file(
                is_done, waited_ms, keepalive_ms,
            )
            if status == "timeout":
                return
            if status == "done":
                yield _emit_done_frame(terminal_state, offset)
                return
            continue
        offset = yield from _tail_new_lines(path, offset, line_filter)
        if is_done is not None and is_done():
            yield _emit_done_frame(terminal_state, offset)
            return
        time.sleep(_POLL_MS / 1000)
