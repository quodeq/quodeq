"""The scalar cache carries each dimension's counts, not only its score.

History's majors and open-types columns read the trend's per-dimension
counts; the trend is served from this cache for finished runs, so a row
without them shows every run as 0.
"""
from __future__ import annotations

import sqlite3

from quodeq.core.types import DimensionResult
from quodeq.core.types.finding import Finding, SeverityTally, Totals
from quodeq.services.dashboard_trend import dimension_counts
from quodeq.services.score_cache import open_score_cache, read_cached_rows, write_cached_rows


def _dim(name: str, **kw) -> DimensionResult:
    return DimensionResult(dimension=name, overall_score="8.5/10", overall_grade="Good", **kw)


def test_counts_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    totals = Totals(violation_count=577, compliance_count=12, severity=SeverityTally(critical=1, major=2, minor=574))
    dims = [_dim("security", totals=totals, open_types=35), _dim("reliability")]
    with open_score_cache() as conn:
        write_cached_rows(conn, "proj", "r1", "v1", dims)
    with open_score_cache() as conn:
        got = {d.dimension: d for d in read_cached_rows(conn, "proj", "r1", "v1")}
    sec = got["security"]
    assert sec.totals == totals
    assert sec.open_types == 35
    # A dimension written without counts reads back without them, never as zeros.
    assert got["reliability"].totals is None and got["reliability"].open_types is None


def test_an_older_cache_file_gains_the_count_columns(tmp_path, monkeypatch):
    path = tmp_path / "sc.db"
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(path))
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE run_scalars ("
        " project TEXT NOT NULL, run_id TEXT NOT NULL, version TEXT NOT NULL,"
        " dimension TEXT NOT NULL, overall_score TEXT, overall_grade TEXT,"
        " updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
        " PRIMARY KEY (project, run_id, dimension, version));"
        "INSERT INTO run_scalars (project, run_id, version, dimension, overall_score, overall_grade)"
        " VALUES ('proj', 'r0', 'v0', 'security', '7/10', 'Good');"
    )
    old.commit()
    old.close()
    totals = Totals(violation_count=3, severity=SeverityTally(major=1, minor=2))
    with open_score_cache() as conn:
        # The pre-existing row is readable and count-less, not an error.
        (legacy,) = read_cached_rows(conn, "proj", "r0", "v0")
        assert legacy.totals is None and legacy.open_types is None
        write_cached_rows(conn, "proj", "r1", "v1", [_dim("security", totals=totals, open_types=2)])
        (fresh,) = read_cached_rows(conn, "proj", "r1", "v1")
    assert fresh.totals == totals and fresh.open_types == 2


def test_the_trend_fetcher_keeps_counts_on_a_miss_and_on_a_bulk_hit(tmp_path, monkeypatch):
    """History reads the trend through the per-run fetcher: the miss path must
    not strip a dimension's counts before caching, and a later bulk load must
    hand them back."""
    from quodeq.services.score_cache import make_cache_backed_fetcher  # noqa: PLC0415
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    totals = Totals(violation_count=40, compliance_count=5, severity=SeverityTally(major=4, minor=36))

    # A rescored dim has the findings and totals but no open_types scalar: the
    # types must be counted before the findings are dropped.
    findings = [Finding(req="R-A"), Finding(req="R-B"), Finding(req="R-B")]

    def base(_rid):
        return [_dim("security", totals=totals, violations=findings)]

    miss = make_cache_backed_fetcher("proj", lambda _rid: "v1", base)("r1")
    assert (miss[0].totals, miss[0].open_types) == (totals, 2)
    assert miss[0].violations == []  # scalars only: the findings never enter the cache

    def boom(_rid):
        raise AssertionError("base fetcher called on a cache hit")
    hit = make_cache_backed_fetcher("proj", lambda _rid: "v1", boom)("r1")
    assert (hit[0].totals, hit[0].open_types) == (totals, 2)
    assert dimension_counts(hit[0])["openTypes"] == 2
