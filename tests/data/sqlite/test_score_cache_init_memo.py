"""open_score_cache runs the full init once per file, then only connects."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from quodeq.data.sqlite import score_cache_db
from quodeq.services.score_cache import open_score_cache

_THREADS = 8


@pytest.fixture
def db_path(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "sc.db"
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(path))
    return path


@pytest.fixture
def init_calls(monkeypatch) -> list[Path]:
    calls: list[Path] = []
    real = score_cache_db._init

    def counting(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(score_cache_db, "_init", counting)
    return calls


def _touch() -> int:
    with open_score_cache() as conn:
        return conn.execute("SELECT count(*) FROM run_keys").fetchone()[0]


def _race(n: int) -> list[BaseException]:
    barrier = threading.Barrier(n)
    errors: list[BaseException] = []

    def run() -> None:
        barrier.wait()
        try:
            _touch()
        except BaseException as exc:  # noqa: BLE001 - surfaced to the test
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


def _remove_db(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def test_eight_racing_first_opens_of_a_fresh_db_initialize_once(db_path, init_calls):
    errors = _race(_THREADS)
    assert errors == []
    assert len(init_calls) == 1


def test_later_opens_skip_the_init(db_path, init_calls):
    for _ in range(5):
        _touch()
    assert len(init_calls) == 1


def test_a_second_race_after_init_runs_no_init(db_path, init_calls):
    _touch()
    assert _race(_THREADS) == []
    assert len(init_calls) == 1


def test_a_deleted_file_runs_the_full_init_again(db_path, init_calls):
    _touch()
    _remove_db(db_path)
    assert _touch() == 0
    assert len(init_calls) == 2


def test_a_file_overwritten_in_place_is_rebuilt(db_path, init_calls):
    _touch()
    for suffix in ("-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)
    db_path.write_bytes(b"not a database" * 64)  # same inode, garbage content
    assert _touch() == 0
    # fast path fails -> full init fails on the garbage -> unlink and rebuild
    assert len(init_calls) == 3


def test_an_epoch_bump_runs_the_init_again(db_path, init_calls, monkeypatch):
    _touch()
    monkeypatch.setattr(score_cache_db, "CACHE_WRITER_EPOCH", "test-epoch")
    _touch()
    assert len(init_calls) == 2
    with open_score_cache() as conn:
        row = conn.execute("SELECT value FROM cache_meta WHERE key='writer_epoch'").fetchone()
    assert row[0] == "test-epoch"


def test_a_database_error_inside_the_block_forces_a_full_init_next_time(db_path, init_calls):
    _touch()
    with pytest.raises(sqlite3.OperationalError):
        with open_score_cache() as conn:
            conn.execute("SELECT * FROM no_such_table")
    _touch()
    assert len(init_calls) == 2


def test_a_locked_score_cache_is_not_deleted(db_path, monkeypatch) -> None:
    """Lock contention on the very first schema init must raise, not be
    treated as corruption.

    The db is pre-set to WAL journal mode before the lock is taken, so the
    busy-timeout PRAGMA (set right after journal_mode inside _init) is
    already active by the time the CREATE TABLE write blocks -- otherwise
    the journal_mode statement itself would block first and ride
    sqlite3.connect's default 5s busy handler instead of the monkeypatched
    one, making the test slow. _purge_run_keys_on_epoch_change swallows
    sqlite3.Error internally (a separate, out-of-scope broad catch), so a
    lock hit there would never reach this test; blocking on the schema's
    own CREATE TABLE avoids that path entirely.
    """
    monkeypatch.setattr(score_cache_db, "_BUSY_TIMEOUT_MS", 50)
    pre = sqlite3.connect(db_path)
    pre.execute("PRAGMA journal_mode = WAL")
    pre.close()
    score_cache_db._forget(db_path)
    holder = sqlite3.connect(db_path, isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(sqlite3.OperationalError):
            with open_score_cache():
                pass
        assert db_path.exists()
    finally:
        holder.execute("ROLLBACK")
        holder.close()
