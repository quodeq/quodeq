import pytest

from quodeq.services.score_cache import load_run_key_sets, open_score_cache, store_run_keys


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))


def test_store_then_load_roundtrip():
    with open_score_cache() as conn:
        store_run_keys(conn, "proj", "r1", {("R1", "a.py", 1)}, {("security", "P1", "a.py")})
    with open_score_cache() as conn:
        keys = load_run_key_sets(conn, "proj", "r1")
    assert keys == ({("R1", "a.py", 1)}, {("security", "P1", "a.py")})
    with open_score_cache() as conn:
        assert load_run_key_sets(conn, "other", "r1") is None  # unknown project -> absent


def test_store_run_keys_accepts_mixed_line_and_fingerprint_keys():
    # Since #1165 a run's dismiss set holds (req, file, int line) alongside
    # (req, file, str fingerprint) for the same finding. Both shapes must
    # persist together: a bare sort compares the int with the str and raises.
    fingerprint = "ab12" * 16
    dismiss = {("R1", "a.py", 1), ("R1", "a.py", fingerprint)}
    with open_score_cache() as conn:
        store_run_keys(conn, "proj", "r1", dismiss, {("security", "P1", "a.py")})
    with open_score_cache() as conn:
        keys = load_run_key_sets(conn, "proj", "r1")
    assert keys[0] == dismiss


def test_store_run_keys_serialization_error_is_logged_not_raised(caplog):
    # Module contract: every write logs and returns on a serialization error.
    # The project-listing path calls this for each terminal run and treats the
    # cache as disposable, so a bad key set must never propagate out.
    caplog.set_level("WARNING", logger="quodeq.data.sqlite.score_cache_store")
    with open_score_cache() as conn:
        store_run_keys(conn, "proj", "r1", {("R1", "a.py", object())}, set())
        assert load_run_key_sets(conn, "proj", "r1") is None
    assert any("run_keys write failed" in rec.getMessage() for rec in caplog.records)


def test_load_run_key_sets_reads_one_run():
    # The per-run lookup the trend and version paths use: one row decoded,
    # not the project's whole table (a large project's blobs run to MBs).
    with open_score_cache() as conn:
        store_run_keys(conn, "proj", "r1", {("R1", "a.py", 1)}, {("security", "P1", "a.py")})
        store_run_keys(conn, "proj", "r2", {("R2", "b.py", 2)}, set())
    with open_score_cache() as conn:
        assert load_run_key_sets(conn, "proj", "r2") == ({("R2", "b.py", 2)}, set())
        assert load_run_key_sets(conn, "proj", "missing") is None
        assert load_run_key_sets(conn, "other", "r1") is None
