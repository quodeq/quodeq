"""Drain a CLI provider's event stream into the pieces one turn's result needs.

Split out of ``_cli.py`` to keep that module under the size ratchet; the
spawn/cleanup/finalize halves of the turn stay there.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import IO, Callable, NamedTuple

from quodeq.assistant.adapters import _stream
from quodeq.assistant.adapters._linereader import iter_lines
from quodeq.assistant.frame_type import FrameType
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


def _absorb_complete_message(event_texts: list[str], etype: str | None, state: _StreamState) -> None:
    state.texts.extend(event_texts)
    # complete events echo text the drawer already shows (an
    # `assistant`/`result` message repeats streamed deltas). Gate on
    # content, not presence, so a differing echo still emits.
    joined = "".join(event_texts)
    is_echo = (joined == state.partial_buf
               or (etype == EVENT_TYPE_RESULT and joined == state.last_full))
    if not is_echo:
        for t in event_texts:
            state.emit({"type": FrameType.TOKEN, "text": t})
    state.last_full = joined
    state.partial_buf = ""


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
        frame = {"type": FrameType.TOOL_CALL, "name": tu["name"]}
        if tu["args_summary"]:
            frame["argsSummary"] = tu["args_summary"]
        state.emit(frame)
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
