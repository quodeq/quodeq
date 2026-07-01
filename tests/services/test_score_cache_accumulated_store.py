from quodeq.services.score_cache import (
    open_score_cache, read_cached_accumulated, write_cached_accumulated,
)


def test_accumulated_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    payload = {"dimensions": [{"dimension": "security", "overallScore": "8/10"}],
               "summary": {"critical": 2, "totalViolations": 5}}
    with open_score_cache() as conn:
        write_cached_accumulated(conn, "proj", "v1", payload)
    with open_score_cache() as conn:
        assert read_cached_accumulated(conn, "proj", "v1") == payload


def test_accumulated_miss_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    with open_score_cache() as conn:
        assert read_cached_accumulated(conn, "proj", "v1") is None


def test_accumulated_write_replaces_prior_version(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    with open_score_cache() as conn:
        write_cached_accumulated(conn, "proj", "v1", {"a": 1})
        write_cached_accumulated(conn, "proj", "v2", {"a": 2})   # replaces (only 1 version per project)
        assert read_cached_accumulated(conn, "proj", "v1") is None
        assert read_cached_accumulated(conn, "proj", "v2") == {"a": 2}
