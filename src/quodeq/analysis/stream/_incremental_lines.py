"""Chunked incremental line reading shared by the progress/JSONL readers."""
from __future__ import annotations

from pathlib import Path

_READ_CHUNK = 1 << 16  # 64 KiB


def read_new_lines(path: Path, offset: int, *, chunk: int = _READ_CHUNK) -> tuple[list[str], int]:
    """Read complete lines newly available at ``path`` since ``offset``.

    Returns the complete lines plus the trailing non-blank partial (if any)
    as the last element, and the number of bytes consumed. Callers should
    advance their own offset by the consumed count themselves, typically in
    a ``finally`` block so a later per-line processing error still leaves
    the offset past the bytes already read.
    """
    lines: list[str] = []
    partial = ""
    consumed = 0
    with open(path, "rb") as f:
        f.seek(offset)
        while True:
            raw = f.read(chunk)
            if not raw:
                break
            consumed += len(raw)
            text = partial + raw.decode("utf-8", errors="replace")
            split = text.split("\n")
            partial = split.pop()
            lines.extend(split)
    if partial.strip():
        lines.append(partial)
    return lines, consumed
