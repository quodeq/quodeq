"""Tests for _cache.py — LRU dimension cache with inflight coordination."""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from quodeq.core.types import DimensionResult
from quodeq.services._cache import (
    _CacheContext,
    _cache_lookup,
    _cache_store,
    _fetch_and_store,
    _fetch_dimensions_from_disk,
    _wait_for_inflight,
    make_lru_dimension_fetcher,
)


def _make_dim(name: str = "security") -> DimensionResult:
    return DimensionResult(dimension=name)


def _make_ctx(max_size: int = 10) -> _CacheContext:
    return _CacheContext(
        cache=OrderedDict(),
        lock=threading.Lock(),
        max_size=max_size,
    )


# ---------------------------------------------------------------------------
# _cache_lookup
# ---------------------------------------------------------------------------


class TestCacheLookup:
    def test_returns_none_on_miss(self):
        ctx = _make_ctx()
        assert _cache_lookup(("a", "b", "c"), ctx) is None

    def test_returns_data_on_hit(self):
        ctx = _make_ctx()
        data = [_make_dim()]
        ctx.cache[("a", "b", "c")] = data
        result = _cache_lookup(("a", "b", "c"), ctx)
        assert result is data

    def test_promotes_to_end(self):
        ctx = _make_ctx()
        ctx.cache[("k1",)] = [_make_dim("a")]
        ctx.cache[("k2",)] = [_make_dim("b")]
        _cache_lookup(("k1",), ctx)
        # k1 should now be at the end
        assert list(ctx.cache.keys())[-1] == ("k1",)


# ---------------------------------------------------------------------------
# _cache_store
# ---------------------------------------------------------------------------


class TestCacheStore:
    def test_stores_data(self):
        ctx = _make_ctx()
        data = [_make_dim()]
        _cache_store(("k",), data, ctx)
        assert ctx.cache[("k",)] is data

    def test_evicts_oldest_on_overflow(self):
        ctx = _make_ctx(max_size=2)
        _cache_store(("k1",), [_make_dim("a")], ctx)
        _cache_store(("k2",), [_make_dim("b")], ctx)
        _cache_store(("k3",), [_make_dim("c")], ctx)
        assert ("k1",) not in ctx.cache
        assert ("k2",) in ctx.cache
        assert ("k3",) in ctx.cache


# ---------------------------------------------------------------------------
# _fetch_dimensions_from_disk
# ---------------------------------------------------------------------------


class TestFetchDimensionsFromDisk:
    @patch("quodeq.services._cache.read_run_data")
    def test_returns_data(self, mock_read):
        mock_read.return_value = [_make_dim()]
        result = _fetch_dimensions_from_disk(Path("/r"), "proj", "run1")
        assert len(result) == 1

    @patch("quodeq.services._cache.read_run_data", side_effect=OSError("disk err"))
    def test_returns_empty_on_error(self, mock_read):
        result = _fetch_dimensions_from_disk(Path("/r"), "proj", "run1")
        assert result == []

    @patch("quodeq.services._cache.read_run_data", side_effect=ValueError("bad data"))
    def test_handles_value_error(self, mock_read):
        assert _fetch_dimensions_from_disk(Path("/r"), "proj", "run1") == []


# ---------------------------------------------------------------------------
# _wait_for_inflight
# ---------------------------------------------------------------------------


class TestWaitForInflight:
    def test_returns_cached_data_after_event(self):
        ctx = _make_ctx()
        event = threading.Event()
        key = ("r", "p", "run1")
        data = [_make_dim()]
        ctx.cache[key] = data
        event.set()
        result = _wait_for_inflight(key, event, ctx)
        assert result == data

    def test_returns_empty_if_not_cached(self):
        ctx = _make_ctx()
        event = threading.Event()
        event.set()
        result = _wait_for_inflight(("missing",), event, ctx)
        assert result == []


# ---------------------------------------------------------------------------
# _fetch_and_store
# ---------------------------------------------------------------------------


class TestFetchAndStore:
    @patch("quodeq.services._cache.read_run_data")
    def test_stores_and_notifies(self, mock_read):
        ctx = _make_ctx()
        key = (Path("/r"), "proj", "run1")
        event = threading.Event()
        ctx.inflight[key] = event
        mock_read.return_value = [_make_dim()]

        result = _fetch_and_store(key, Path("/r"), "proj", "run1", ctx)
        assert len(result) == 1
        assert key in ctx.cache
        assert event.is_set()
        assert key not in ctx.inflight

    @patch("quodeq.services._cache.read_run_data", return_value=[])
    def test_empty_data_not_cached(self, mock_read):
        ctx = _make_ctx()
        key = (Path("/r"), "proj", "run1")
        ctx.inflight[key] = threading.Event()
        result = _fetch_and_store(key, Path("/r"), "proj", "run1", ctx)
        assert result == []
        assert key not in ctx.cache


# ---------------------------------------------------------------------------
# make_lru_dimension_fetcher
# ---------------------------------------------------------------------------


class TestMakeLruDimensionFetcher:
    @patch("quodeq.services._cache.read_run_data")
    def test_fetches_and_caches(self, mock_read):
        mock_read.return_value = [_make_dim()]
        cache = OrderedDict()
        lock = threading.Lock()
        fetcher = make_lru_dimension_fetcher(Path("/r"), "proj", cache, lock, 10)
        result = fetcher("run1")
        assert len(result) == 1
        # Second call should use cache (no additional read_run_data call)
        result2 = fetcher("run1")
        assert len(result2) == 1
        assert mock_read.call_count == 1

    @patch("quodeq.services._cache.read_run_data")
    def test_concurrent_access(self, mock_read):
        """Two threads requesting the same key — only one disk read."""
        call_count = {"n": 0}
        started = threading.Event()

        def slow_read(*args, **kwargs):
            call_count["n"] += 1
            started.set()
            import time
            time.sleep(0.1)
            return [_make_dim()]

        mock_read.side_effect = slow_read
        cache = OrderedDict()
        lock = threading.Lock()
        fetcher = make_lru_dimension_fetcher(Path("/r"), "proj", cache, lock, 10)

        results = [None, None]

        def worker(idx):
            results[idx] = fetcher("run1")

        t1 = threading.Thread(target=worker, args=(0,))
        t1.start()
        # Wait for t1 to start the fetch, then launch t2 which should wait
        started.wait(timeout=5)
        t2 = threading.Thread(target=worker, args=(1,))
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # Both should have results
        assert results[0] is not None
        assert results[1] is not None
        # Only one disk read should have occurred
        assert call_count["n"] == 1
