"""Split the suite across CI jobs by test file.

The Windows leg is the slow one (no fork(), slow subprocess startup, NTFS
small-file I/O), and pytest-xdist already uses every core of one runner. To
go faster it has to run on two runners at once, so ``QUODEQ_TEST_SHARD=i/n``
makes a job collect only the files that hash into shard ``i`` of ``n``.

Files, not tests, are the unit: class and module fixtures stay together and a
failing file reads in one log. A crc32 of the nodeid's file part decides the
shard, so every job agrees without a shared durations file, and adding a test
to a file never moves other files. ``1/1`` (or unset) leaves collection
untouched, which is what local runs and the other legs use.
"""
from __future__ import annotations

import zlib
from collections.abc import Sequence
from typing import Protocol

ENV_VAR = "QUODEQ_TEST_SHARD"

_WHOLE = (1, 1)


class _Collected(Protocol):
    nodeid: str


def parse_shard(raw: str | None) -> tuple[int, int]:
    """Return ``(index, total)`` for ``"i/n"``; unset or empty means the whole suite.

    Malformed input raises rather than degrading to the whole suite: a CI job
    that silently ran everything would double the work while looking green.
    """
    if not raw or raw == "1/1":
        return _WHOLE
    index_text, sep, total_text = raw.partition("/")
    if not sep or not index_text.isdigit() or not total_text.isdigit():
        raise ValueError(f"{ENV_VAR} must look like 'i/n', got {raw!r}")
    index, total = int(index_text), int(total_text)
    if total < 1 or not 1 <= index <= total:
        raise ValueError(f"{ENV_VAR} must satisfy 1 <= i <= n, got {raw!r}")
    return index, total


def select_shard[T: _Collected](
    items: Sequence[T], index: int, total: int
) -> tuple[list[T], list[T]]:
    """Split collected items into ``(kept, dropped)`` for shard ``index`` of ``total``.

    Collection order is preserved on both sides.
    """
    if (index, total) == _WHOLE:
        return list(items), []
    kept: list[T] = []
    dropped: list[T] = []
    for item in items:
        file_part = item.nodeid.split("::")[0]
        shard = zlib.crc32(file_part.encode()) % total + 1
        (kept if shard == index else dropped).append(item)
    return kept, dropped
