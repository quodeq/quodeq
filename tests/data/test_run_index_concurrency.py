"""Regression tests for the run index's open/create race.

Split from test_run_index.py, which covers single-threaded open/migrate.

Background: ``open_index`` used to treat *any* ``sqlite3.DatabaseError`` from
the connect step as "this file is corrupt" and delete it. But the very first
connection to a new index has to switch the journal from rollback to WAL, and
SQLite refuses that switch with ``OperationalError("database is locked")``
whenever another connection holds the file -- a transient, healthy condition
it does not route through ``busy_timeout``. So a loser of that race deleted a
perfectly good database out from under the winner's live WAL connection.
SQLite then treated the replacement file as a brand-new database and zeroed
the ``-shm`` wal-index the winner still had memory-mapped, and the winner's
next write died with ``Fatal Python error: Bus error`` inside
``walIndexAppend``. The paginated project listing hits this: it opens the one
shared index from up to 8 ThreadPoolExecutor workers at once.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from quodeq.data.sqlite import _run_index_schema
from quodeq.data.sqlite.run_index import SCHEMA_VERSION, open_index

_INSERT_SENTINEL = (
    "INSERT INTO runs (job_id, project_uuid, run_id, run_dir, state, "
    "started_at, updated_at, status_mtime) "
    "VALUES ('sentinel', 'p', 'sentinel', '/p/sentinel', 'done', '0', '0', 0)"
)


def _rollback_mode_index(db_path: Path) -> None:
    """Write a healthy v1 index at *db_path*, left in rollback-journal mode.

    Rollback mode is what a not-yet-opened index looks like, and it is the
    only state in which the WAL switch can return SQLITE_BUSY.
    """
    raw = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        raw.executescript(
            "CREATE TABLE runs (job_id TEXT PRIMARY KEY, project_uuid TEXT NOT NULL,"
            " run_id TEXT NOT NULL, run_dir TEXT NOT NULL, state TEXT NOT NULL,"
            " phase TEXT, current_dimension TEXT, started_at TEXT NOT NULL,"
            " updated_at TEXT NOT NULL, finalized_at TEXT, heartbeat_at TEXT,"
            " pid INTEGER, exit_reason TEXT, status_mtime INTEGER NOT NULL);"
            " CREATE TABLE schema_version (version INTEGER NOT NULL);"
        )
        raw.execute("INSERT INTO schema_version VALUES (1)")
        raw.execute(_INSERT_SENTINEL)
        assert raw.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    finally:
        raw.close()


def test_busy_wal_switch_does_not_delete_a_healthy_index(tmp_path: Path) -> None:
    """A locked WAL switch must be waited out, never mistaken for corruption.

    Deterministic: a peer holding a RESERVED write lock (``BEGIN IMMEDIATE``,
    which is what ``_apply_schema_v1`` holds while it runs) makes
    ``PRAGMA journal_mode=WAL`` fail with "database is locked" *immediately* --
    SQLite does not consult the busy handler for that one, so no amount of
    ``busy_timeout`` hides it. The peer commits shortly after, so a correct
    ``open_index`` retries and comes back with the user's rows intact. The
    pre-fix version deleted the file on that first error, taking the sentinel
    row (and, when a live connection had the WAL index mapped, the process)
    with it.
    """
    db_path = tmp_path / "index.db"
    _rollback_mode_index(db_path)

    # check_same_thread=False so the timer thread can release the lock while
    # the main thread is blocked inside open_index. Access stays sequential.
    writer = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
    writer.execute("BEGIN IMMEDIATE")  # RESERVED lock, as a schema write holds
    released = threading.Event()

    def _release() -> None:
        writer.execute("COMMIT")
        released.set()

    timer = threading.Timer(0.15, _release)
    timer.start()
    try:
        db = open_index(db_path)
        try:
            kept = db.execute("SELECT state FROM runs WHERE job_id = 'sentinel'").fetchone()
            assert kept is not None and kept[0] == "done", (
                "open_index destroyed a healthy index after a transient "
                "'database is locked' on the rollback->WAL switch"
            )
            assert released.is_set(), (
                "open_index returned before the write lock was released -- it "
                "cannot have waited the WAL switch out"
            )
            assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        finally:
            db.close()
    finally:
        timer.cancel()
        writer.close()


def test_concurrent_first_open_yields_one_consistent_schema(tmp_path: Path) -> None:
    """Threads racing to create the same fresh index must all get a good DB.

    Mirrors ``_build_project_entries_threaded``: several workers call
    ``open_index`` on the one shared index path at the same instant. Every
    thread must come back with the current schema and the index must end up
    with exactly one ``schema_version`` row -- no duplicate inserts from two
    ``_apply_schema_v1`` runs interleaving.
    """
    db_path = tmp_path / "index.db"
    workers = 8
    barrier = threading.Barrier(workers)
    versions: list[int] = []
    errors: list[BaseException] = []
    guard = threading.Lock()

    def _open() -> None:
        barrier.wait()
        try:
            db = open_index(db_path)
            try:
                version = db.execute("SELECT version FROM schema_version").fetchone()[0]
            finally:
                db.close()
        except BaseException as exc:  # noqa: BLE001 -- reported, not swallowed
            with guard:
                errors.append(exc)
            return
        with guard:
            versions.append(version)

    threads = [threading.Thread(target=_open) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent open_index raised: {errors!r}"
    assert versions == [SCHEMA_VERSION] * workers

    db = open_index(db_path)
    try:
        assert db.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 1
    finally:
        db.close()


def test_recreate_clears_stale_wal_sidecars(tmp_path: Path) -> None:
    """Rebuilding a discarded index must take its -wal/-shm sidecars with it.

    They describe the file being thrown away. Left in place, the replacement
    database adopts them: the pre-fix version handed back a connection still
    pointing at a 5-byte ``-shm``, which is exactly the malformed wal-index
    the SIGBUS came out of. Calls ``_recreate_index_db`` directly because the
    first write through ``open_index`` grows the ``-shm`` to its real size and
    would hide a stale one.
    """
    db_path = tmp_path / "index.db"
    open_index(db_path).close()
    db_path.write_bytes(b"not a sqlite file")
    for suffix in ("-wal", "-shm"):
        Path(f"{db_path}{suffix}").write_bytes(b"stale")

    db = _run_index_schema._recreate_index_db(db_path)
    try:
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{db_path}{suffix}")
            assert not sidecar.exists() or sidecar.read_bytes() != b"stale", (
                f"{sidecar.name} still describes the discarded database"
            )
    finally:
        db.close()
