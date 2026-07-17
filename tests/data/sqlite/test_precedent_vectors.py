"""Vector store: roundtrip, model wipe, dims filter, claims, corruption."""
import sqlite3
from pathlib import Path

from quodeq.data.sqlite.precedent_vectors import (
    DB_NAME,
    insert_vectors,
    load_vectors,
    open_vector_store,
    release_backfill_claim,
    stored_fingerprints,
    try_claim_backfill,
)


def test_roundtrip(tmp_path: Path) -> None:
    with open_vector_store(tmp_path, "m1") as conn:
        assert conn is not None
        assert insert_vectors(conn, "m1", [("fp1", [1.0, 2.0]), ("fp2", [3.0, 4.0])])
        assert stored_fingerprints(conn) == {"fp1", "fp2"}
        assert dict(load_vectors(conn)) == {"fp1": [1.0, 2.0], "fp2": [3.0, 4.0]}


def test_insert_or_ignore_is_idempotent(tmp_path: Path) -> None:
    with open_vector_store(tmp_path, "m1") as conn:
        assert insert_vectors(conn, "m1", [("fp1", [1.0, 0.0])])
        assert insert_vectors(conn, "m1", [("fp1", [9.0, 9.0])])  # ignored, no error
        assert dict(load_vectors(conn))["fp1"] == [1.0, 0.0]


def test_model_change_wipes(tmp_path: Path) -> None:
    with open_vector_store(tmp_path, "m1") as conn:
        insert_vectors(conn, "m1", [("fp1", [1.0, 0.0])])
    with open_vector_store(tmp_path, "m2") as conn:
        assert conn is not None
        assert stored_fingerprints(conn) == set()


def test_insert_aborts_if_model_changed_underneath(tmp_path: Path) -> None:
    with open_vector_store(tmp_path, "m1") as conn:
        assert insert_vectors(conn, "other-model", [("fp1", [1.0, 0.0])]) is False
        assert stored_fingerprints(conn) == set()


def test_load_discards_dims_mismatch(tmp_path: Path) -> None:
    with open_vector_store(tmp_path, "m1") as conn:
        insert_vectors(conn, "m1", [("fp1", [1.0, 2.0])])  # stamps dims=2
        # Force a bad row past the API to simulate a mixed-space write.
        conn.execute(
            "INSERT INTO vectors VALUES ('bad', ?, 'now')", (b"\x00" * 12,)
        )  # 3 floats
        conn.commit()
        assert dict(load_vectors(conn)) == {"fp1": [1.0, 2.0]}


def test_backfill_claim_single_winner(tmp_path: Path) -> None:
    with open_vector_store(tmp_path, "m1") as conn:
        assert try_claim_backfill(conn) is True
        assert try_claim_backfill(conn) is False  # already claimed, not stale
        release_backfill_claim(conn)
        assert try_claim_backfill(conn) is True


def test_corruption_rebuilds(tmp_path: Path) -> None:
    db = tmp_path / DB_NAME
    db.write_bytes(b"this is not a sqlite database at all, padding padding")
    with open_vector_store(tmp_path, "m1") as conn:
        assert conn is not None  # rebuilt from scratch
        assert stored_fingerprints(conn) == set()


def test_lock_contention_yields_none_and_keeps_file(tmp_path: Path) -> None:
    with open_vector_store(tmp_path, "m1") as conn:
        insert_vectors(conn, "m1", [("fp1", [1.0, 0.0])])
    blocker = sqlite3.connect(tmp_path / DB_NAME)
    blocker.execute("PRAGMA busy_timeout = 0")
    blocker.execute("BEGIN EXCLUSIVE")
    try:
        with open_vector_store(tmp_path, "m1", busy_timeout_ms=50) as conn:
            assert conn is None  # degraded, NOT rebuilt
    finally:
        blocker.rollback()
        blocker.close()
    with open_vector_store(tmp_path, "m1") as conn:
        assert stored_fingerprints(conn) == {"fp1"}  # data survived
