"""Cluster 16: score-cache write failures must log, not just silently degrade.

Each of the three write-side except blocks in ``_score_cache_fetch`` (write
cached_accumulated, write cached_project_summary, write_cached_rows inside
make_cache_backed_fetcher's fetch closure) must log a warning before falling
through to the plain-recompute result. The degrade-to-recompute behavior
itself must be unchanged: the caller still gets the freshly computed value,
never an exception.

Logging is injected via ``quodeq.core.observability.LogSink`` (services/ may
not import a logging framework directly -- see
tests/tools/test_logging_boundary.py), so these tests pass a fake sink
instead of using caplog.

The tests above prove the mechanism works when a caller passes ``log=``.
They do NOT prove any production caller actually does -- final review item B
(fault-tolerance cycle 1) found that every production caller left ``log`` at
its silent ``NULL_LOG`` default, so cluster 16's logging never fired outside
tests. ``TestProductionCallerReachesRealSink`` below drives a real production
caller (``_fs_metadata.py``, which now threads ``log=SHARED_LOG``) with no
``log=`` override at all, to prove the wiring -- not just the mechanism --
reaches a real sink.
"""
from __future__ import annotations

import sqlite3

from quodeq.core.types import DimensionResult
from quodeq.services import _fs_metadata as _md
from quodeq.services import _score_cache_fetch
from quodeq.shared.log_sink import SHARED_LOG


def _boom(*_args, **_kwargs):
    raise sqlite3.Error("disk full")


class _FakeLog:
    """Minimal LogSink recording every call, for asserting a warning fired."""

    def __init__(self):
        self.warnings: list[str] = []

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def debug(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass

    def success(self, message: str) -> None:
        pass


def test_cached_accumulated_logs_on_write_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    monkeypatch.setattr(_score_cache_fetch, "write_cached_accumulated", _boom)

    log = _FakeLog()
    computed = {"score": 7.0}
    result = _score_cache_fetch.cached_accumulated("proj", "v1", lambda: computed, log=log)

    # Degrade-to-recompute is unchanged: the computed value is still returned.
    assert result is computed
    assert any("write_cached_accumulated" in msg for msg in log.warnings)


def test_cached_project_summary_logs_on_write_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    monkeypatch.setattr(_score_cache_fetch, "write_cached_project_summary", _boom)

    log = _FakeLog()
    computed = {"grade": "Good", "score": 8.0}
    result = _score_cache_fetch.cached_project_summary("proj", "v1", lambda: computed, log=log)

    assert result is computed
    assert any("write_cached_project_summary" in msg for msg in log.warnings)


def test_make_cache_backed_fetcher_logs_on_write_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    monkeypatch.setattr(_score_cache_fetch, "write_cached_rows", _boom)

    scalars = [DimensionResult(dimension="security", overall_score="8.0/10", overall_grade="Good")]

    def base_fetcher(_run_id):
        return scalars

    log = _FakeLog()
    fetch = _score_cache_fetch.make_cache_backed_fetcher(
        "proj", lambda _rid: "v1", base_fetcher, log=log,
    )
    out = fetch("r1")

    # Degrade-to-recompute is unchanged: the base fetcher's scalars are served.
    assert [d.overall_score for d in out] == ["8.0/10"]
    assert any("write_cached_rows" in msg for msg in log.warnings)


class TestProductionCallerReachesRealSink:
    """Final review Important 2: cluster 16's logging was inert because every
    production caller left ``log`` at its ``NULL_LOG`` default. These drive a
    real caller (``_fs_metadata.py``) with NO ``log=`` override, proving the
    module-level ``SHARED_LOG`` wiring added in item B actually reaches a
    caller-supplied sink in production, not just when a test hands one in
    directly."""

    def test_compute_on_miss_summary_logs_through_shared_log(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
        monkeypatch.setattr(_score_cache_fetch, "write_cached_project_summary", _boom)

        computed = {"grade": "Good", "score": 7.0, "files": 3}
        monkeypatch.setattr(_md, "_compute_summary", lambda *a, **k: computed)

        log = _FakeLog()
        # Patch the name _fs_metadata.py resolves at call time, not the
        # log_sink module's copy -- proves the import-and-thread wiring in
        # that file, exactly what item B changed.
        monkeypatch.setattr(_md, "SHARED_LOG", log)

        result = _md._compute_on_miss_summary(
            tmp_path, "proj", runs=[], params=None, visible_set=set(), version="v1",
        )

        assert result == ("Good", 7.0, 3, False)
        assert any("write_cached_project_summary" in msg for msg in log.warnings)

    def test_fs_metadata_imports_the_real_shared_log_singleton(self):
        # Sanity check that _fs_metadata.SHARED_LOG is the actual production
        # sink (not a copy/shim) absent any monkeypatching -- the object
        # identity that makes the test above representative of production.
        assert _md.SHARED_LOG is SHARED_LOG
