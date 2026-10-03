"""shared.stamp_memo: a stamp-keyed memo any file-backed read can use."""
from __future__ import annotations

from pathlib import Path

from quodeq.shared.stamp_memo import StampCache, file_stamp, memoized_by_stamp


def test_file_stamp_is_mtime_and_size(tmp_path: Path) -> None:
    p = tmp_path / "a.json"
    p.write_text("{}")
    st = p.stat()
    assert file_stamp(p) == (st.st_mtime_ns, st.st_size)


def test_file_stamp_none_for_missing(tmp_path: Path) -> None:
    assert file_stamp(tmp_path / "missing") is None


def test_memo_reuses_while_stamp_unchanged() -> None:
    cache = StampCache()
    calls = []
    compute = lambda: calls.append(1) or {"n": len(calls)}  # noqa: E731
    first = memoized_by_stamp("k", (1, 2), compute, cache=cache)
    second = memoized_by_stamp("k", (1, 2), compute, cache=cache)
    assert first is second
    assert calls == [1]


def test_memo_recomputes_when_stamp_changes() -> None:
    cache = StampCache()
    calls = []
    compute = lambda: calls.append(1) or {"n": len(calls)}  # noqa: E731
    memoized_by_stamp("k", (1, 2), compute, cache=cache)
    third = memoized_by_stamp("k", (1, 3), compute, cache=cache)
    assert third == {"n": 2}


def test_memo_does_not_store_none() -> None:
    cache = StampCache()
    calls = []
    compute = lambda: calls.append(1)  # noqa: E731  returns None
    assert memoized_by_stamp("k", (1,), compute, cache=cache) is None
    assert memoized_by_stamp("k", (1,), compute, cache=cache) is None
    assert calls == [1, 1]


def test_cache_clears_wholesale_when_full() -> None:
    cache = StampCache(max_entries=2)
    cache.put("a", (1,), 1)
    cache.put("b", (1,), 2)
    cache.put("c", (1,), 3)
    assert cache.get("a", (1,)) is None
    assert cache.get("c", (1,)) == 3
