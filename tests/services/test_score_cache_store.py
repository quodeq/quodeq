from quodeq.core.types import DimensionResult
from quodeq.services.score_cache import open_score_cache, read_cached_rows, write_cached_rows


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
