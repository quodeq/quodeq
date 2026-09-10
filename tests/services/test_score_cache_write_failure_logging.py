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
"""
from __future__ import annotations

import sqlite3

from quodeq.core.types import DimensionResult
from quodeq.services import _score_cache_fetch


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
