from __future__ import annotations

from quodeq.core.types import DimensionResult
from quodeq.services import _fs_metadata as md
from quodeq.services.score_cache import (
    open_score_cache, read_cached_project_summary, write_cached_project_summary,
)


def test_project_summary_roundtrip_and_versioning(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))
    with open_score_cache() as conn:
        assert read_cached_project_summary(conn, "P", "v1") is None
        write_cached_project_summary(conn, "P", "v1", {"grade": "Good", "score": 7.3, "files": 1538})
    with open_score_cache() as conn:
        assert read_cached_project_summary(conn, "P", "v1") == {"grade": "Good", "score": 7.3, "files": 1538}
        assert read_cached_project_summary(conn, "P", "v2") is None
        write_cached_project_summary(conn, "P", "v2", {"grade": "Adequate", "score": 6.1, "files": 900})
    with open_score_cache() as conn:
        assert read_cached_project_summary(conn, "P", "v1") is None  # evicted (single slot)
        assert read_cached_project_summary(conn, "P", "v2")["grade"] == "Adequate"


def test_read_accumulated_summary_is_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))

    calls = {"n": 0}
    def _read(root, proj, run_id):
        calls["n"] += 1
        return [DimensionResult(dimension="security", overall_score="7.0/10",
                                overall_grade="Good", source_file_count=10)]
    monkeypatch.setattr(md, "read_run_data", _read)

    class _Run:
        def __init__(self, rid):
            self.run_id = rid
            self.status = "complete"
    runs = [_Run("a"), _Run("b")]

    first = md._read_accumulated_summary(tmp_path, "proj", runs)
    n_after_first = calls["n"]
    second = md._read_accumulated_summary(tmp_path, "proj", runs)
    assert first == second
    assert first == ("Good", 7.0, 10)  # grade, numeric_average, files_count
    assert calls["n"] == n_after_first  # second call served from cache, no re-read
