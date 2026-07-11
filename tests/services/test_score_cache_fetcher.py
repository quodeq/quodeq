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

    f1 = make_cache_backed_fetcher("proj", lambda _rid: "v1", base)
    out1 = f1("r1")                    # miss -> base called, cached
    assert [d.overall_score for d in out1] == ["8.0/10"]
    assert calls == ["r1"]

    # New fetcher instance (fresh bulk-load) sees the cached row -> base NOT called.
    def boom(rid):
        raise AssertionError("base fetcher called on a cache hit")
    f2 = make_cache_backed_fetcher("proj", lambda _rid: "v1", boom)
    out2 = f2("r1")
    assert [(d.dimension, d.overall_score, d.overall_grade) for d in out2] == [("security", "8.0/10", "Good")]


def test_version_change_is_a_miss(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    make_cache_backed_fetcher("proj", lambda _rid: "v1", _rescored)("r1")  # cache under v1
    calls = []
    def base(rid):
        calls.append(rid)
        return _rescored(rid)
    make_cache_backed_fetcher("proj", lambda _rid: "v2", base)("r1")       # different version -> miss
    assert calls == ["r1"]


def test_kill_switch_returns_base_fetcher(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
    base = _rescored
    assert make_cache_backed_fetcher("proj", lambda _rid: "v1", base) is base


def _dims(*names):
    return [DimensionResult(dimension=n, overall_score="8.0/10", overall_grade="Good") for n in names]


def test_in_progress_run_is_not_persisted(tmp_path, monkeypatch):
    """A run cached mid-flight must not permanently mask its completed result.

    Regression: opening History while a scan runs (only the first dim scored)
    used to persist that partial set. Because the cache version only hashes
    dismissals/deletions/params, the run completing never invalidated it, so
    the history trend showed 1 dim forever while run-detail showed all of them.
    Non-cacheable (in-progress) runs must compute-through without persisting.
    """
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))

    # Build 1: run "r1" is in progress -- only "security" has scored so far.
    partial_calls = []
    def base_partial(rid):
        partial_calls.append(rid)
        return _dims("security")

    f1 = make_cache_backed_fetcher("proj", lambda _rid: "v1", base_partial, is_cacheable=lambda rid: False)
    out1 = f1("r1")
    assert [d.dimension for d in out1] == ["security"]   # still served this build
    assert partial_calls == ["r1"]

    # Build 2 (fresh bulk-load): the run has since completed all 6 dims. Because
    # the partial set was never persisted, this is a MISS and re-fetches fresh.
    full_calls = []
    def base_full(rid):
        full_calls.append(rid)
        return _dims("security", "reliability", "maintainability",
                     "performance", "usability", "flexibility")

    f2 = make_cache_backed_fetcher("proj", lambda _rid: "v1", base_full, is_cacheable=lambda rid: True)
    out2 = f2("r1")
    assert [d.dimension for d in out2] == sorted(
        ["flexibility", "maintainability", "performance", "reliability", "security", "usability"]
    ) or len(out2) == 6
    assert full_calls == ["r1"]   # re-fetched, not served the stale 1-dim set

    # Build 3: now the completed run IS persisted -> hit, base not called.
    def boom(rid):
        raise AssertionError("base fetcher called on a cache hit for a completed run")
    f3 = make_cache_backed_fetcher("proj", lambda _rid: "v1", boom, is_cacheable=lambda rid: True)
    assert len(f3("r1")) == 6
