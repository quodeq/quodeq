"""Tests for cache.py — LRU dimension cache with inflight coordination."""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from quodeq.services.cache import (
    DimensionCacheContext,
    _cache_lookup,
    _cache_store,
    _fetch_and_store,
    _fetch_dimensions_from_disk,
    _wait_for_inflight,
    make_lru_dimension_fetcher,
)
from tests._timeouts import budget
from tests.services._cache_fixtures import _make_ctx, _make_dim


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
    @patch("quodeq.services.cache.read_run_data")
    def test_returns_data(self, mock_read):
        mock_read.return_value = [_make_dim()]
        result = _fetch_dimensions_from_disk(Path("/r"), "proj", "run1")
        assert len(result) == 1

    @patch("quodeq.services.cache.read_run_data", side_effect=OSError("disk err"))
    def test_returns_empty_on_error(self, mock_read):
        result = _fetch_dimensions_from_disk(Path("/r"), "proj", "run1")
        assert result == []

    @patch("quodeq.services.cache.read_run_data", side_effect=ValueError("bad data"))
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

    def test_returns_none_if_not_cached(self):
        ctx = _make_ctx()
        event = threading.Event()
        event.set()
        assert _wait_for_inflight(("missing",), event, ctx) is None


# ---------------------------------------------------------------------------
# _fetch_and_store
# ---------------------------------------------------------------------------


class TestFetchAndStore:
    @patch("quodeq.services.cache.read_run_data")
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

    @patch("quodeq.services.cache.read_run_data", return_value=[])
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
    @patch("quodeq.services.cache.read_run_data")
    def test_fetches_and_caches(self, mock_read):
        mock_read.return_value = [_make_dim()]
        cache = OrderedDict()
        lock = threading.Lock()
        ctx = DimensionCacheContext(cache=cache, lock=lock, max_size=10)
        fetcher = make_lru_dimension_fetcher(Path("/r"), "proj", ctx)
        result = fetcher("run1")
        assert len(result) == 1
        # Second call should use cache (no additional read_run_data call)
        result2 = fetcher("run1")
        assert len(result2) == 1
        assert mock_read.call_count == 1

    @patch("quodeq.services.cache.read_run_data")
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
        ctx = DimensionCacheContext(cache=cache, lock=lock, max_size=10)
        fetcher = make_lru_dimension_fetcher(Path("/r"), "proj", ctx)

        results = [None, None]

        def worker(idx):
            results[idx] = fetcher("run1")

        t1 = threading.Thread(target=worker, args=(0,))
        t1.start()
        # Wait for t1 to start the fetch, then launch t2 which should wait
        started.wait(timeout=budget(5))
        t2 = threading.Thread(target=worker, args=(1,))
        t2.start()
        t1.join(timeout=budget(10))
        t2.join(timeout=budget(10))

        # Both should have results
        assert results[0] is not None
        assert results[1] is not None
        # Only one disk read should have occurred
        assert call_count["n"] == 1

    def test_reader_exception_releases_inflight_entry(self, tmp_path):
        ctx = _make_ctx()
        ctx.reader = Mock(side_effect=RuntimeError("boom"))
        fetcher = make_lru_dimension_fetcher(tmp_path, "proj", ctx)

        with pytest.raises(RuntimeError, match="boom"):
            fetcher("run1")

        assert ctx.inflight == {}, "a failed read must not leave later callers waiting on its event"

    def test_waiter_fetches_itself_when_the_inflight_read_fails(self, tmp_path):
        reading, release, parked = threading.Event(), threading.Event(), threading.Event()
        calls = {"n": 0}

        def reader(*args):
            calls["n"] += 1
            if calls["n"] == 1:
                reading.set()
                release.wait(timeout=budget(10))
                raise RuntimeError("boom")
            return [_make_dim()]

        class ParkingEvent(threading.Event):
            def wait(self, timeout=None):
                parked.set()
                return super().wait(timeout)

        ctx = _make_ctx()
        ctx.reader = reader
        fetcher = make_lru_dimension_fetcher(tmp_path, "proj", ctx)
        outcome = {}

        def owner():
            with pytest.raises(RuntimeError, match="boom"):
                fetcher("run1")
            outcome["owner_raised"] = True

        t1 = threading.Thread(target=owner)
        t1.start()
        assert reading.wait(timeout=budget(5))
        with ctx.lock:
            (key,) = ctx.inflight
            ctx.inflight[key] = ParkingEvent()
        t2 = threading.Thread(target=lambda: outcome.update(waiter=fetcher("run1")))
        t2.start()
        assert parked.wait(timeout=budget(5))
        release.set()
        t1.join(timeout=budget(10))
        t2.join(timeout=budget(10))
        assert outcome.get("owner_raised") is True
        assert outcome["waiter"] == [_make_dim()], "the waiter must not take the failed read as no dimensions"


# ---------------------------------------------------------------------------
# _run_is_in_progress (through make_lru_dimension_fetcher's public path)
# ---------------------------------------------------------------------------


class TestRunIsInProgress:
    """Pin the cache guard's "stay cautious" default across every status.json
    shape. The guard must keep behaving exactly as it did before read_run_state
    started normalizing/rejecting state strings: an unrecognized state string
    is treated as in-progress (not cached), same as before that change made
    read_run_state return None for it instead of the raw string.
    """

    @patch("quodeq.services.cache.read_run_data")
    def test_unknown_state_string_is_in_progress_not_cached(self, mock_read, tmp_path):
        mock_read.return_value = [_make_dim()]
        run_dir = tmp_path / "proj" / "run1"
        run_dir.mkdir(parents=True)
        (run_dir / "status.json").write_text('{"state": "bogus"}')
        ctx = _make_ctx()
        fetcher = make_lru_dimension_fetcher(tmp_path, "proj", ctx)

        result = fetcher("run1")

        assert len(result) == 1
        assert ctx.cache == {}, "an unrecognized state must stay in-progress and not be persisted"

    @patch("quodeq.services.cache.read_run_data")
    def test_missing_status_json_is_not_in_progress_and_is_cached(self, mock_read, tmp_path):
        mock_read.return_value = [_make_dim()]
        run_dir = tmp_path / "proj" / "run1"
        run_dir.mkdir(parents=True)
        ctx = _make_ctx()
        fetcher = make_lru_dimension_fetcher(tmp_path, "proj", ctx)

        result = fetcher("run1")

        assert len(result) == 1
        assert len(ctx.cache) == 1, "a missing status.json counts as terminal and its read is cached"
