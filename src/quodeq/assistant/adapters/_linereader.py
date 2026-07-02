"""Incrementally read complete lines from a live text stream (subprocess stdout)."""
from __future__ import annotations

from typing import Iterator, TextIO

_CHUNK = 1 << 16


def iter_lines(stream: TextIO, *, chunk_size: int = _CHUNK) -> Iterator[str]:
    buffer = ""
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            yield line
    if buffer:
        yield buffer
