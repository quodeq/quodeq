"""Bounded, seekable view of a project-import upload.

``import_zip_stream`` used to ``read(size_limit + 1)`` the whole upload and
wrap it in ``BytesIO``, so every concurrent import held up to the size limit
(500 MB by default) in memory. ``open_upload`` sizes a seekable stream in
place and copies anything else in fixed chunks into a spool that moves to
disk past a few MB, stopping as soon as the copied total passes the limit.
"""
from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator
from typing import IO, Any

# Read size when copying a non-seekable upload into the spool.
_UPLOAD_CHUNK_BYTES = 1024 * 1024
# The spool stays in memory up to this size, then rolls over to a temp file.
_SPOOL_MEMORY_BYTES = 8 * 1024 * 1024


@contextlib.contextmanager
def open_upload(stream: Any, size_limit: int) -> Iterator[IO[bytes] | None]:
    """Yield a seekable binary view of *stream*, or None when it is over *size_limit* bytes.

    A seekable stream (Werkzeug's ``FileStorage`` proxies ``seek``/``tell`` to
    its spooled file; the shared pull passes an open file) is sized by seeking
    to its end and yielded as is. The caller owns it, so it is not closed
    here. Anything else is copied into a ``SpooledTemporaryFile`` that is
    closed on exit.
    """
    if _is_seekable(stream):
        yield stream if _fits_in_place(stream, size_limit) else None
        return
    with tempfile.SpooledTemporaryFile(max_size=_SPOOL_MEMORY_BYTES) as spool:
        yield spool if _copy_within_limit(stream, spool, size_limit) else None


def _is_seekable(stream: Any) -> bool:
    seekable = getattr(stream, "seekable", None)
    return bool(seekable is not None and seekable())


def _fits_in_place(stream: Any, size_limit: int) -> bool:
    """Size *stream* from its current position without reading it, then seek back."""
    start = stream.tell()
    size = stream.seek(0, os.SEEK_END) - start
    stream.seek(start)
    return size <= size_limit


def _copy_within_limit(stream: Any, spool: IO[bytes], size_limit: int) -> bool:
    """Copy *stream* into *spool* chunk by chunk; False as soon as it passes *size_limit*."""
    copied = 0
    while chunk := stream.read(_UPLOAD_CHUNK_BYTES):
        copied += len(chunk)
        if copied > size_limit:
            return False
        spool.write(chunk)
    spool.seek(0)
    return True
