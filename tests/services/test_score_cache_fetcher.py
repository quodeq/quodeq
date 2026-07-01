from quodeq.core.types import DimensionResult
from quodeq.services.score_cache import make_cache_backed_fetcher


def _rescored(rid):
    # A "rescored" full dim (findings omitted for the test).
    return [DimensionResult(dimension="security", overall_score="8.0/10", overall_grade="Good")]


def test_miss_computes_and_caches_then_hit_skips_base(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    calls = []
    def base(rid):
        calls.append(rid)
        return _rescored(rid)

    f1 = make_cache_backed_fetcher("proj", "v1", base)
    out1 = f1("r1")                    # miss -> base called, cached
    assert [d.overall_score for d in out1] == ["8.0/10"]
    assert calls == ["r1"]

    # New fetcher instance (fresh bulk-load) sees the cached row -> base NOT called.
    def boom(rid):
        raise AssertionError("base fetcher called on a cache hit")
    f2 = make_cache_backed_fetcher("proj", "v1", boom)
    out2 = f2("r1")
    assert [(d.dimension, d.overall_score, d.overall_grade) for d in out2] == [("security", "8.0/10", "Good")]


def test_version_change_is_a_miss(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    make_cache_backed_fetcher("proj", "v1", _rescored)("r1")  # cache under v1
    calls = []
    def base(rid):
        calls.append(rid)
        return _rescored(rid)
    make_cache_backed_fetcher("proj", "v2", base)("r1")       # different version -> miss
    assert calls == ["r1"]


def test_kill_switch_returns_base_fetcher(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
    base = _rescored
    assert make_cache_backed_fetcher("proj", "v1", base) is base
