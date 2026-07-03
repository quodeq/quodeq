"""Incrementally read complete lines from a live text stream (subprocess stdout)."""
from __future__ import annotations

from typing import Iterator, TextIO

_CHUNK = 1 << 16


def iter_lines(stream: TextIO, *, chunk_size: int = _CHUNK, max_line: int = 1 << 20) -> Iterator[str]:
    buffer = ""
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            yield line
        # A newline-less stream can't be allowed to grow the buffer forever.
        # Yield the oversized chunk as a "line" (downstream JSON-parse simply
        # fails it and moves on) instead of raising, so one malformed/huge
        # line can't hang or OOM the reader.
        if len(buffer) > max_line:
            yield buffer
            buffer = ""
    if buffer:
        yield buffer
