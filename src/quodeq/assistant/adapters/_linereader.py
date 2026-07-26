"""Incrementally read complete lines from a live text stream (subprocess stdout)."""
from __future__ import annotations

from typing import Iterator, TextIO


def iter_lines(stream: TextIO, *, max_line: int = 1 << 20) -> Iterator[str]:
    """Yield each line as soon as it arrives, without waiting for EOF.

    readline() returns the moment a newline is decoded, unlike read(n) on a
    TextIOWrapper, which is greedy (blocks until n chars or EOF) and would
    hold a live pipe's output hostage until the subprocess exits.

    The size argument bounds a newline-less run: past max_line, readline
    returns the oversized fragment as its own piece (downstream JSON-parse
    simply fails it and moves on), so one malformed/huge line can't hang or
    OOM the reader.
    """
    while True:
        line = stream.readline(max_line)
        if not line:
            break
        yield line[:-1] if line.endswith("\n") else line
