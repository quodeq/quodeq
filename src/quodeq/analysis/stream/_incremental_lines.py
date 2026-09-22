"""Chunked incremental line reading shared by the progress/JSONL readers."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

_READ_CHUNK = 1 << 16  # 64 KiB


def iter_line_batches(
    path: Path, offset: int, *, chunk: int = _READ_CHUNK
) -> Iterator[tuple[list[str], int]]:
    """Yield line batches read from ``path`` since ``offset``, one per chunk read.

    Each ``(lines, nbytes)`` batch pairs one chunk's complete lines (with any
    partial line carried over from the previous chunk merged in) with that
    chunk's byte count. The trailing non-blank partial line, if any, is
    appended to the LAST batch's lines only, once EOF is reached (gated on
    ``partial.strip()``, the unstripped value kept), matching the old
    reader's behaviour exactly. An empty file, or an offset already at EOF,
    yields nothing.

    Callers must advance their offset by ``nbytes`` BEFORE processing a
    batch's lines. If that processing then raises partway through a batch,
    the batch's bytes are still counted as consumed, so the next call never
    re-reads them: at most the unprocessed remainder of that one chunk is
    lost. Later batches, not yet yielded when the exception hits, are never
    read this call. They get read afresh, from the correct offset, on the
    caller's next call.
    """
    partial = ""
    pending: tuple[list[str], int] | None = None
    with open(path, "rb") as f:
        f.seek(offset)
        while True:
            raw = f.read(chunk)
            if not raw:
                break
            text = partial + raw.decode("utf-8", errors="replace")
            split = text.split("\n")
            partial = split.pop()
            if pending is not None:
                yield pending
            pending = (split, len(raw))
    if pending is not None:
        lines, nbytes = pending
        if partial.strip():
            lines.append(partial)
        yield lines, nbytes
