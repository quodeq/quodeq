"""Cluster 39: a timed-out in-flight wait falls back to a direct fetch and says so."""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from unittest.mock import patch

from quodeq.services import _cache


def _ctx() -> _cache.DimensionCacheContext:
    return _cache.DimensionCacheContext(cache=OrderedDict(), lock=threading.Lock(), max_size=8)


def test_wait_for_inflight_returns_none_and_logs_on_timeout(monkeypatch) -> None:
    monkeypatch.setattr(_cache, "_CACHE_WAIT_TIMEOUT_S", 0.01)
    never_set = threading.Event()
    with patch.object(_cache._logger, "debug") as debug:
        result = _cache._wait_for_inflight(("k",), never_set, _ctx())
    assert result is None
    assert debug.called
    assert "did not finish within" in debug.call_args.args[0]


def test_wait_for_inflight_returns_cached_rows_when_signalled() -> None:
    ctx = _ctx()
    ctx.cache[("k",)] = ["row"]
    done = threading.Event()
    done.set()
    assert _cache._wait_for_inflight(("k",), done, ctx) == ["row"]


def test_get_run_dimensions_falls_back_to_disk_after_inflight_timeout(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(_cache, "_CACHE_WAIT_TIMEOUT_S", 0.01)
    monkeypatch.setattr(_cache, "_cache_lookup", lambda key, ctx: None)
    monkeypatch.setattr(_cache, "_run_is_in_progress", lambda *_a: False)
    sentinel = ["from-disk"]
    monkeypatch.setattr(_cache, "_fetch_dimensions_from_disk", lambda *_a, **_k: sentinel)
    ctx = _ctx()
    key = (tmp_path, "proj", "run-1", "v1")
    ctx.inflight[key] = threading.Event()  # another thread's fetch that never completes
    result = _cache._get_run_dimensions("run-1", tmp_path, "proj", "v1", ctx)
    assert result is sentinel
    assert key in ctx.inflight  # the stuck fetcher still owns its event
