"""process_dimension_with_cache — cache persistence and GC wiring.

Split from test_dimension_runner.py: the one-time legacy-entry GC on
default-backend open, and the regression pin for the c88be50e "16% loss"
bug (the final persist tick must not be abandoned mid-flight). Shared
scaffolding lives in tests/analysis/cache/conftest.py.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from quodeq.analysis.cache import LocalFileBackend, build_cache_key_for_file
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from tests.analysis.cache.conftest import (
    FakeDispatcher,
    _make_callbacks,
    _make_ctx,
    _setup,
    _SlowPutCache,
)


class TestGcWiring:
    def test_default_backend_open_collects_legacy_entries(
        self, tmp_path: Path, monkeypatch,
    ):
        # When no cache is injected (the production path), opening the default
        # backend runs the one-time GC, reclaiming schema<3 entries. Sandbox
        # the cache root via env so we never touch the real ~/.quodeq cache.
        from quodeq.analysis.cache.local import default_cache_root

        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "qroot"))
        results_root = default_cache_root()
        legacy_dir = results_root / "aa" / ("0" * 62)
        legacy_dir.mkdir(parents=True, exist_ok=True)
        (legacy_dir / "entry.json").write_text(json.dumps({
            "key": "aa" + "0" * 62, "schema_version": 2, "findings": [],
            "files_read": 1, "file_path": "old.py", "dimension": "security",
            "model_id": "m",
        }))

        config, src = _setup(tmp_path, {"a.py": "x"})
        dispatcher = FakeDispatcher(src)
        # cache=None -> production default-backend path -> GC fires.
        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=None,
            dispatcher=dispatcher,
        )

        assert not (legacy_dir / "entry.json").exists()


class TestSlowFinalPersistIsNotAbandoned:
    """Regression for the c88be50e "16% loss" bug (a flexibility run where
    790 file_done="ok" markers landed in the JSONL but only 662 cache
    entries persisted): prove that ``watcher.join()``'s lack of a timeout
    ceiling actually lets a slow final persist tick complete instead of
    being abandoned mid-flight.

    Dispatch here is fast (FakeDispatcher writes its ok marker immediately),
    so ``stop_event`` is set well within the 60s periodic interval — the
    watcher's periodic loop never ticks, and the only ``persist_fn()`` call
    is the FINAL one after ``stop_event.set()``. Making that one call block
    on an Event, released only after the main thread has confirmed it's in
    flight, pins that ``process_dimension_with_cache`` doesn't return (and
    doesn't drop the entry) until that final tick actually finishes.
    """

    def test_slow_final_persist_is_not_abandoned(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        config, src = _setup(tmp_path, {"a.py": "x"})
        dispatcher = FakeDispatcher(src)

        started = threading.Event()
        release = threading.Event()
        slow_cache = _SlowPutCache(cache, started, release)

        result: dict = {}

        def run() -> None:
            result["evidence"] = process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(),
                cache=slow_cache, dispatcher=dispatcher, persist_interval_s=60.0,
            )

        runner_thread = threading.Thread(target=run)
        runner_thread.start()
        try:
            assert started.wait(timeout=5.0), (
                "the final persist tick never started -- watcher wiring broke"
            )
            # Bounded wait (not a bare sleep -- returns the instant the
            # thread finishes) that gives process_dimension_with_cache every
            # chance to return early if watcher.join() has any short-ish
            # timeout ceiling. It must not: the persist is still blocked on
            # `release`, so a correct join() call blocks right along with it.
            runner_thread.join(timeout=1.0)
            assert runner_thread.is_alive(), (
                "process_dimension_with_cache returned before the slow "
                "final persist completed -- watcher.join() must have no "
                "timeout ceiling (the c88be50e regression)"
            )
        finally:
            release.set()
        runner_thread.join(timeout=5.0)
        assert not runner_thread.is_alive(), "process_dimension_with_cache never returned"
        assert result.get("evidence") is not None

        key = build_cache_key_for_file(config, "a.py", "security")
        entry = cache.get(key)
        assert entry is not None, (
            "the slow final persist tick must not be abandoned -- its "
            "entry must land in the cache once released"
        )
        assert any(f.get("w") == "v-a.py" for f in entry.findings)
