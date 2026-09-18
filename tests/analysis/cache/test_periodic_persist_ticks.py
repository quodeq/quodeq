"""Periodic persist watcher: incremental ticks and the final full re-read."""
from __future__ import annotations

import threading
from pathlib import Path

from quodeq.analysis.cache import LocalFileBackend, build_cache_key_for_file
from quodeq.analysis.cache.dimension_runner import CacheRunOptions, process_dimension_with_cache
from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl
from quodeq.core.evidence.model import Evidence
from tests.analysis.cache.conftest import _CountingCache, _make_callbacks, _make_ctx

from ._periodic_persist_helpers import _setup


# ============================================================
# Incremental ticks and the final full re-read
# ============================================================

_FINDING_A = '{"file": "a.py", "line": 1, "t": "violation", "w": "found"}\n'
_OK_A = '{"_marker": "file_done", "file": "a.py", "status": "ok"}\n'


class _FirstPutCache(_CountingCache):
    """Counting cache that signals its first put and can swallow it, the way
    LocalFileBackend.put does on OSError (logs, returns None, no entry)."""

    def __init__(self, inner: LocalFileBackend, *, swallow_first: bool = False) -> None:
        super().__init__(inner)
        self.first_put = threading.Event()
        self._swallow_first = swallow_first

    def put(self, key, entry) -> None:
        self.put_count += 1
        if not (self._swallow_first and self.put_count == 1):
            self._inner.put(key, entry)
        self.first_put.set()


def _dispatch_after_first_put(text: str, first_put: threading.Event, after_tick=None):
    """Dispatcher that writes *text*, waits for a watcher tick to put once,
    runs *after_tick*(jsonl) (the pool's own post-dispatch work), returns."""

    def dispatch(cfg, dim_id, idx, ctx, callbacks, **_):
        jsonl = cfg.work_dir / f"{dim_id}_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl.write_text(text)
        assert first_put.wait(timeout=5.0), "no periodic tick put anything"
        if after_tick is not None:
            after_tick(jsonl)
        return Evidence(
            repository="", language="python", date="2026-01-01",
            source_file_count=1, files_read=1, coverage_pct=100.0, principles={},
        )

    return dispatch


class TestTicksAreIncremental:
    def test_unchanged_ok_file_is_not_re_put_by_later_ticks(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """Every tick used to re-read the whole JSONL and re-put every ok
        file. With one DispatchJsonlState per dispatch, later ticks skip a
        file whose lines have not changed. Only the final persist, a
        deliberate full re-read, writes it again: exactly two puts however
        many ticks run between the first put and the stop signal."""
        config = _setup(tmp_path, {"a.py": "x"})
        counting = _FirstPutCache(cache)

        process_dimension_with_cache(
            config, "security", 1, _make_ctx(),
            opts=CacheRunOptions(callbacks=_make_callbacks(), cache=counting, dispatcher=_dispatch_after_first_put(_FINDING_A + _OK_A, counting.first_put), persist_interval_s=0.05),
        )

        assert counting.put_count == 2
        key = build_cache_key_for_file(config, "a.py", "security")
        assert cache.get(key) is not None


class TestFinalPersistIsFullReread:
    def _run(self, tmp_path, cache, text, *, swallow_first=False, after_tick=None):
        config = _setup(tmp_path, {"a.py": "x"})
        wrapped = _FirstPutCache(cache, swallow_first=swallow_first)
        process_dimension_with_cache(
            config, "security", 1, _make_ctx(),
            opts=CacheRunOptions(callbacks=_make_callbacks(), cache=wrapped, dispatcher=_dispatch_after_first_put(text, wrapped.first_put, after_tick), persist_interval_s=0.05),
        )
        return cache.get(build_cache_key_for_file(config, "a.py", "security"))

    def test_put_that_failed_silently_during_a_tick_lands_at_final_persist(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """LocalFileBackend.put swallows OSError, so a tick cannot tell a
        failed write from a good one and clears dirty either way. The final
        persist must not trust that bookkeeping: it re-reads from byte 0 and
        re-puts every ok file."""
        entry = self._run(tmp_path, cache, _FINDING_A + _OK_A, swallow_first=True)
        assert entry is not None
        assert any(f.get("w") == "found" for f in entry.findings)

    def test_dedup_rewrite_after_last_tick_is_reflected(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """The dispatcher runs deduplicate_jsonl in place before the watcher
        is joined; the final persist sees the deduplicated file."""
        entry = self._run(
            tmp_path, cache, _FINDING_A + _FINDING_A + _OK_A, after_tick=deduplicate_jsonl,
        )
        assert entry is not None
        assert len(entry.findings) == 1

    def test_rewrite_invisible_to_the_tail_guard_is_reflected(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """The incremental guard compares only the 512 bytes before the
        offset, so a rewrite that leaves them alone (a same-length change in
        an earlier line) is invisible to a tick. The final persist must not
        depend on the guard."""
        padding = '{"file": "a.py", "line": 2, "t": "violation", "w": "%s"}\n' % ("p" * 600)
        text = _FINDING_A + padding + _OK_A

        def rewrite(jsonl: Path) -> None:
            jsonl.write_text(text.replace('"w": "found"', '"w": "later"'))

        entry = self._run(tmp_path, cache, text, after_tick=rewrite)
        assert entry is not None
        ws = {f.get("w") for f in entry.findings}
        assert "later" in ws
        assert "found" not in ws
