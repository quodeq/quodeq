import os

import pytest

from quodeq.core.types import DimensionResult
from quodeq.data.sqlite.score_cache_store import read_all_cached_rows
from quodeq.services.score_cache import (
    load_run_keys_or_empty,
    open_score_cache,
    read_cached_rows,
    store_run_keys_best_effort,
    write_cached_rows,
)


def test_write_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    dims = [DimensionResult(dimension="security", overall_score="8.5/10", overall_grade="Good"),
            DimensionResult(dimension="reliability", overall_score="6.0/10", overall_grade="Fair")]
    with open_score_cache() as conn:
        write_cached_rows(conn, "proj", "r1", "v1", dims)
    with open_score_cache() as conn:
        got = read_cached_rows(conn, "proj", "r1", "v1")
    assert [(d.dimension, d.overall_score, d.overall_grade) for d in got] == \
           [("reliability", "6.0/10", "Fair"), ("security", "8.5/10", "Good")]  # ordered by dimension


def test_read_miss_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    with open_score_cache() as conn:
        assert read_cached_rows(conn, "proj", "nope", "v1") is None


def test_write_replaces_prior_version_for_run(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    d = [DimensionResult(dimension="security", overall_score="9/10", overall_grade="A")]
    with open_score_cache() as conn:
        write_cached_rows(conn, "proj", "r1", "v1", d)
        write_cached_rows(conn, "proj", "r1", "v2", d)  # new version replaces
        assert read_cached_rows(conn, "proj", "r1", "v1") is None
        assert read_cached_rows(conn, "proj", "r1", "v2") is not None


def test_corrupt_db_is_rebuilt(tmp_path, monkeypatch):
    p = tmp_path / "sc.db"
    p.write_text("not a database")  # garbage
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(p))
    with open_score_cache() as conn:  # must not raise; rebuilds
        assert read_cached_rows(conn, "proj", "r1", "v1") is None


def test_read_all_cached_rows_groups_by_run_and_version(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    d1 = [DimensionResult(dimension="security", overall_score="8/10", overall_grade="Good")]
    d2 = [DimensionResult(dimension="reliability", overall_score="6/10", overall_grade="Fair")]
    with open_score_cache() as conn:
        write_cached_rows(conn, "proj", "r1", "v1", d1)
        write_cached_rows(conn, "proj", "r2", "v1", d2)
        rows = read_all_cached_rows(conn, "proj")
    assert set(rows) == {("r1", "v1"), ("r2", "v1")}
    assert [d.dimension for d in rows[("r1", "v1")]] == ["security"]
    assert [d.dimension for d in rows[("r2", "v1")]] == ["reliability"]


def test_read_all_cached_rows_empty_when_nothing_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    with open_score_cache() as conn:
        assert read_all_cached_rows(conn, "proj") == {}


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod-based permission denial is ineffective as root or on Windows",
)
def test_unopenable_cache_dir_degrades_read_and_write(tmp_path, monkeypatch):
    """An unopenable cache dir (open/rebuild failure, not just a query error)
    must degrade read -> {} and write -> no-op, never raise.

    Regression: load_run_keys_or_empty / store_run_keys_best_effort used to
    take an already-open connection and wrap only the query in try/except
    sqlite3.Error; the caller (per_run_versions) opened the connection itself
    with no guard, so a twice-corrupt/unopenable db's sqlite3.OperationalError
    propagated out of open_score_cache into hot read paths that expect this
    disposable cache to always degrade to recompute.
    """
    ro_dir = tmp_path / "ro"
    ro_dir.mkdir()
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(ro_dir / "sc.db"))
    os.chmod(ro_dir, 0o500)  # read+execute only: the db file can never be created
    try:
        assert load_run_keys_or_empty("proj") == {}  # must not raise
        store_run_keys_best_effort(  # must not raise
            "proj", "r1", {("R1", "a.py", 1)}, {("security", "P1", "a.py")}
        )
    finally:
        os.chmod(ro_dir, 0o700)
