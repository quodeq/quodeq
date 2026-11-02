"""Drain a CLI provider's event stream into the pieces one turn's result needs.

Split out of ``_cli.py`` to keep that module under the size ratchet; the
spawn/cleanup/finalize halves of the turn stay there.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import IO, Callable, NamedTuple

from quodeq.assistant.adapters import _stream
from quodeq.assistant.adapters._linereader import iter_lines
from quodeq.assistant.frame_type import FrameType
from quodeq.assistant.tool_activity import end_frame, new_call_id, start_frame
from quodeq.core.stream.events import EVENT_TYPE_RESULT

_BENIGN_RAW_LINES = (
    "Reading additional input from stdin",
    "WARNING: proceeding, even though we could not create PATH aliases",
)


def _raw_error_line(line: str) -> str | None:
    text = line.strip()
    if not text:
        return None
    if any(text.startswith(prefix) for prefix in _BENIGN_RAW_LINES):
        return None
    return text


@dataclass
class _StreamState:
    """What one pass over the CLI's event stream accumulates."""

    emit: Callable[[dict], None]
    session_id: str | None
    texts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw_errors: list[str] = field(default_factory=list)
    last_full: str | None = None  # text of the last complete message, emitted or not
    partial_buf: str = ""  # delta text streamed since the last complete message
    saw_result: bool = False
    # Tool calls announced but not yet finished: call id -> (raw name, start stamp).
    running: dict[str, tuple[str, float]] = field(default_factory=dict)


def _absorb_complete_message(event_texts: list[str], etype: str | None, state: _StreamState) -> None:
    state.texts.extend(event_texts)
    # complete events echo text the drawer already shows (an
    # `assistant`/`result` message repeats streamed deltas). Gate on
    # content, not presence, so a differing echo still emits. agy's `result`
    # repeats only its last message, the tail of deltas that also carried
    # the text written before its tool calls.
    joined = "".join(event_texts)
    is_echo = (joined == state.partial_buf
               or (etype == EVENT_TYPE_RESULT
                   and (joined == state.last_full or (joined and state.partial_buf.endswith(joined)))))
    if not is_echo:
        for t in event_texts:
            state.emit({"type": FrameType.TOKEN, "text": t})
    state.last_full = joined
    state.partial_buf = ""


def _finish_tool_call(result: dict, state: _StreamState) -> None:
    """Emit the end frame of the running call *result* closes: by id, or for
    a dialect without ids, the oldest running call of the same name."""
    call_id = result["id"] if result["id"] in state.running else next(
        (cid for cid, (name, _) in state.running.items() if name == result["name"]), None)
    if call_id is None:
        return
    name, started = state.running.pop(call_id)
    state.emit(end_frame(call_id, name, result["ok"], started))


def _handle_stream_event(event: dict, state: _StreamState) -> None:
    etype = event.get("type")
    if etype == EVENT_TYPE_RESULT and "exitCode" not in event:
        state.saw_result = True
    err = _stream.error_message(event)
    if err:
        state.errors.append(err)
    delta = _stream.partial_text(event)
    if delta:
        state.partial_buf += delta
        state.emit({"type": FrameType.TOKEN, "text": delta})
    event_texts = _stream.assistant_text(event)
    if event_texts:
        _absorb_complete_message(event_texts, etype, state)
    for tu in _stream.tool_use_details(event):
        call_id = tu["id"] or new_call_id()
        state.running[call_id] = (tu["name"], time.monotonic())
        state.emit(start_frame(call_id, tu["name"], tu["args"]))
    for tr in _stream.tool_result_details(event):
        _finish_tool_call(tr, state)
    sid = _stream.session_id(event)
    if sid:
        state.session_id = sid


class StreamOutcome(NamedTuple):
    """What one pass over the CLI's event stream leaves for the turn to finish."""

    texts: list[str]
    errors: list[str]
    raw_errors: list[str]
    session_id: str | None
    partial_buf: str
    saw_result: bool


def consume_stream_events(
    stdout: IO[str] | None, emit: Callable[[dict], None], parsed_sid: str | None,
) -> StreamOutcome:
    """Drain the CLI's event stream, emitting token/tool_call frames as they
    arrive. Returns the raw pieces ``_finalize_turn_result`` assembles.
    """
    state = _StreamState(emit=emit, session_id=parsed_sid)
    for line in iter_lines(stdout):
        event = _stream.parse_line(line)
        if event is None:
            raw = _raw_error_line(line)
            if raw:
                state.raw_errors.append(raw)
            continue
        _handle_stream_event(event, state)
    return StreamOutcome(
        texts=state.texts, errors=state.errors, raw_errors=state.raw_errors,
        session_id=state.session_id, partial_buf=state.partial_buf,
        saw_result=state.saw_result,
    )
