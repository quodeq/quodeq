import pytest

from quodeq.services.score_cache import load_run_keys, open_score_cache, store_run_keys


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))


def test_store_then_load_roundtrip():
    with open_score_cache() as conn:
        store_run_keys(conn, "proj", "r1", {("R1", "a.py", 1)}, {("security", "P1", "a.py")})
    with open_score_cache() as conn:
        keys = load_run_keys(conn, "proj")
    assert keys["r1"] == ({("R1", "a.py", 1)}, {("security", "P1", "a.py")})
    with open_score_cache() as conn:
        assert load_run_keys(conn, "other") == {}  # unknown project -> empty
