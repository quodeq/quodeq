"""Tests for _cache.py self-healing guards: stale-entry eviction, in-progress runs, custom readers."""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

import pytest

from quodeq.core.types import DimensionResult
from quodeq.services.cache import DimensionCacheContext, make_lru_dimension_fetcher
from tests.services._cache_fixtures import _make_dim


# ---------------------------------------------------------------------------
# Self-healing guards: every caller inherits them from the base factory
# ---------------------------------------------------------------------------


def _write_eval_files(tmp_path: Path, run_id: str, dims: tuple[str, ...]) -> None:
    eval_dir = tmp_path / "proj" / run_id / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    for d in dims:
        (eval_dir / f"{d}.json").write_text("{}", encoding="utf-8")


def _write_status(tmp_path: Path, run_id: str, state: str) -> None:
    run_dir = tmp_path / "proj" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status.json").write_text(f'{{"state": "{state}"}}', encoding="utf-8")


class TestSelfHealingGuards:
    """A request landing mid-run must never freeze a partial dim list.

    Regression: three scoring read paths built this fetcher without the
    dashboard's staleness guards, so a /scores request that fired while only
    security.json was on disk froze a 1-dim entry in the shared process LRU;
    after the run completed, the accumulated rescore read that entry, rescored
    only security, and persisted the half-rescored payload forever.
    """

    def test_stale_entry_evicted_when_disk_count_differs(self, tmp_path):
        _write_eval_files(tmp_path, "r1", ("flexibility", "reliability", "security"))
        full = [_make_dim("flexibility"), _make_dim("reliability"), _make_dim("security")]
        reader_calls = []

        def reader(reports_root, project, run_id):
            reader_calls.append(run_id)
            return full

        cache = OrderedDict()
        # Poisoned entry: cached while only 1 of 3 dims was on disk.
        cache[(tmp_path, "proj", "r1", "")] = [_make_dim("security")]
        ctx = DimensionCacheContext(cache=cache, lock=threading.Lock(), max_size=10, reader=reader)
        fetcher = make_lru_dimension_fetcher(tmp_path, "proj", ctx)

        result = fetcher("r1")
        assert len(result) == 3
        assert reader_calls == ["r1"]
        # The healed entry is cached; no further reads.
        assert len(fetcher("r1")) == 3
        assert reader_calls == ["r1"]

    def test_entry_without_disk_anchor_is_trusted(self, tmp_path):
        """No evaluation/ dir on disk (test stubs, mocked paths) -> no eviction."""
        cache = OrderedDict()
        seeded = [_make_dim("security")]
        cache[(tmp_path, "proj", "r1", "")] = seeded
        ctx = DimensionCacheContext(
            cache=cache, lock=threading.Lock(), max_size=10,
            reader=lambda *a: pytest.fail("reader must not run on a trusted hit"),
        )
        fetcher = make_lru_dimension_fetcher(tmp_path, "proj", ctx)
        assert fetcher("r1") is seeded

    def test_in_progress_run_reads_fresh_and_is_not_cached(self, tmp_path):
        _write_status(tmp_path, "r1", "running")
        _write_eval_files(tmp_path, "r1", ("security",))
        reader_calls = []

        def reader(reports_root, project, run_id):
            reader_calls.append(run_id)
            return [_make_dim("security")]

        cache = OrderedDict()
        ctx = DimensionCacheContext(cache=cache, lock=threading.Lock(), max_size=10, reader=reader)
        fetcher = make_lru_dimension_fetcher(tmp_path, "proj", ctx)
        fetcher("r1")
        fetcher("r1")
        assert reader_calls == ["r1", "r1"]  # disk read both times
        assert cache == {}  # nothing frozen mid-run

    def test_terminal_run_is_cached(self, tmp_path):
        _write_status(tmp_path, "r1", "done")
        _write_eval_files(tmp_path, "r1", ("security",))
        reader_calls = []

        def reader(reports_root, project, run_id):
            reader_calls.append(run_id)
            return [_make_dim("security")]

        ctx = DimensionCacheContext(cache=OrderedDict(), lock=threading.Lock(), max_size=10, reader=reader)
        fetcher = make_lru_dimension_fetcher(tmp_path, "proj", ctx)
        fetcher("r1")
        fetcher("r1")
        assert reader_calls == ["r1"]  # second call served from cache


def test_make_lru_dimension_fetcher_uses_custom_reader():
    """A custom reader is invoked instead of read_run_data, and results cache."""
    calls: list[str] = []

    def fake_reader(reports_root, project, run_id):
        calls.append(run_id)
        return [DimensionResult(dimension="security", overall_score="9.0/10", overall_grade="Good")]

    ctx = DimensionCacheContext(cache=OrderedDict(), lock=threading.Lock(), max_size=8, reader=fake_reader)
    fetcher = make_lru_dimension_fetcher(Path("/reports"), "proj", ctx)
    result = fetcher("r1")
    result_again = fetcher("r1")  # served from cache, reader not called twice

    assert [d.overall_score for d in result] == ["9.0/10"]
    assert result_again == result
    assert calls == ["r1"]  # cached: reader ran exactly once
