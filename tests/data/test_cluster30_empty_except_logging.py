"""Cluster 30: data/ best-effort handlers log at debug instead of swallowing."""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from quodeq.data.cache_store import index as cache_index
from quodeq.data.cache_store import local, migrate
from quodeq.data.cache_store.entry import CacheEntry
from quodeq.data.cache_store.index import ContentIndex
from quodeq.data.cache_store.local import LocalFileBackend
from quodeq.data.fs import evidence_tally, run_files, stream_files
from quodeq.data.fs.dimension_report import _report_io
from quodeq.data.sqlite import _run_index_schema, findings_queries, precedent_vectors


class _RaisingConn:
    """A sqlite-connection stub whose methods raise a canned exception."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def close(self) -> None:
        raise self._exc

    def execute(self, *_args, **_kwargs):
        raise self._exc

    def commit(self) -> None:
        raise self._exc


class _InsertFailConn:
    """Fails the INSERT itself, then fails the rollback that follows it."""

    def execute(self, *_args, **_kwargs):
        raise sqlite3.DatabaseError("insert boom")

    def rollback(self) -> None:
        raise sqlite3.DatabaseError("rollback boom")


def _entry(key: str) -> CacheEntry:
    return CacheEntry(
        key=key, schema_version=4, findings=[], files_read=1, file_path="a.py",
        dimension="security", model_id="m", file_content_hash="aa" * 32,
    )


def test_close_quietly_logs_sqlite_close_failure() -> None:
    with patch.object(_run_index_schema._logger, "debug") as debug:
        _run_index_schema._close_quietly(_RaisingConn(sqlite3.Error("locked")))
    assert debug.called
    assert "close failed" in debug.call_args.args[0]
    assert isinstance(debug.call_args.args[1], sqlite3.Error)


def test_persist_json_logs_cleanup_unlink_failure(tmp_path) -> None:
    """The primary write fails (os.replace) and the finally-block cleanup
    unlink also fails -- both are OSError, so the debug log at the cleanup
    site fires even though the wrapped OSError from the primary failure
    still propagates (this handler never swallows the write failure itself,
    only the best-effort cleanup of the orphaned temp file)."""
    target = tmp_path / "report.json"
    with (
        patch(
            "quodeq.data.fs.dimension_report._report_io.os.replace",
            side_effect=OSError("replace failed"),
        ),
        patch(
            "quodeq.data.fs.dimension_report._report_io.os.unlink",
            side_effect=OSError("unlink failed"),
        ),
        patch.object(_report_io._logger, "debug") as debug,
    ):
        with pytest.raises(OSError):
            _report_io.persist_json({"ok": True}, target)  # (data, path) order
    assert debug.called
    assert "not removed after a failed write" in debug.call_args.args[0]


def test_release_backfill_claim_logs_database_error() -> None:
    conn = _RaisingConn(sqlite3.DatabaseError("readonly"))
    with patch.object(precedent_vectors._logger, "debug") as debug:
        precedent_vectors.release_backfill_claim(conn)  # one parameter: the sqlite connection
    assert debug.called
    assert "release failed" in debug.call_args.args[0]


def test_content_index_close_logs_sqlite_error(tmp_path) -> None:
    idx = ContentIndex(tmp_path / "idx.db")
    idx._conn = _RaisingConn(sqlite3.Error("locked"))
    with patch.object(cache_index._logger, "debug") as debug:
        idx.close()
    assert idx._conn is None
    assert debug.called
    assert "close failed" in debug.call_args.args[0]


def test_local_backend_get_logs_read_failure_on_corrupt_cleanup(tmp_path) -> None:
    """A corrupt entry is detected (bad JSON); the ensuing best-effort removal
    of the corrupt file also fails, and that failure is logged."""
    backend = LocalFileBackend(root=tmp_path / "cache", enable_index=False)
    key = "k1" * 3
    path = backend._entry_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json", encoding="utf-8")
    with (
        patch("pathlib.Path.unlink", side_effect=OSError("locked")),
        patch.object(local._logger, "debug") as debug,
    ):
        result = backend.get(key)
    assert result is None
    assert debug.called
    assert "corrupt local cache entry not removed" in debug.call_args.args[0]


def test_local_backend_put_logs_write_failure_on_tmp_cleanup(tmp_path) -> None:
    """The atomic rename fails; the ensuing best-effort cleanup of the
    orphaned temp file also fails, and that failure is logged."""
    backend = LocalFileBackend(root=tmp_path / "cache", enable_index=False)
    key = "p1" * 3
    entry = _entry(key)
    with (
        patch(
            "quodeq.data.cache_store.local.os.replace",
            side_effect=OSError("disk full"),
        ),
        patch("pathlib.Path.unlink", side_effect=OSError("locked")),
        patch.object(local._logger, "debug") as debug,
    ):
        backend.put(key, entry)
    assert debug.called
    assert "temp cache file not removed after a failed write" in debug.call_args.args[0]


def test_release_lock_logs_oserror(tmp_path) -> None:
    """A directory in place of the lock file makes ``unlink`` raise
    IsADirectoryError (an OSError), which ``missing_ok`` does not suppress."""
    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    with patch.object(migrate._logger, "debug") as debug:
        migrate._release_lock(lock_dir)
    assert lock_dir.exists()
    assert debug.called
    assert "lock release failed" in debug.call_args.args[0]


def test_tally_unique_findings_logs_unreadable_file(tmp_path) -> None:
    jsonl_path = tmp_path / "findings.jsonl"
    jsonl_path.write_text("", encoding="utf-8")
    with (
        patch(
            "quodeq.data.fs.evidence_tally.open_text",
            side_effect=OSError("read failed"),
        ),
        patch.object(evidence_tally._logger, "debug") as debug,
    ):
        tally = evidence_tally.tally_unique_findings(jsonl_path)
    assert tally == evidence_tally.FindingTally()
    assert debug.called
    assert "unreadable during tally" in debug.call_args.args[0]


def test_remove_matching_files_logs_already_removed(tmp_path) -> None:
    victim = tmp_path / "orphan.tmp"
    victim.write_text("x", encoding="utf-8")
    with (
        patch("pathlib.Path.unlink", side_effect=FileNotFoundError("gone")),
        patch.object(run_files._logger, "debug") as debug,
    ):
        run_files.remove_matching_files(tmp_path, ["*.tmp"])
    assert debug.called
    assert "already removed" in debug.call_args.args[0]


def test_count_active_agent_streams_logs_stat_failure() -> None:
    class _GlobRaisingDir:
        def is_dir(self) -> bool:
            return True

        def glob(self, _pattern):
            raise OSError("listing failed")

    with patch.object(stream_files._logger, "debug") as debug:
        count = stream_files.count_active_agent_streams(
            _GlobRaisingDir(), "dim", window_s=60.0,
        )
    assert count == 0
    assert debug.called
    assert "stream directory glob failed" in debug.call_args.args[0]


def test_dismissed_source_stamp_logs_unreadable_wal(tmp_path) -> None:
    """An empty run dir has neither the DB nor its -wal sidecar: the WAL
    stat fails and is logged, then the main-file stat also fails and the
    function returns None (its documented no-DB behaviour)."""
    with patch.object(findings_queries._logger, "debug") as debug:
        result = findings_queries.dismissed_source_stamp(tmp_path)
    assert result is None
    assert debug.called
    assert "dismissed-source stamp unreadable" in debug.call_args.args[0]


def test_insert_vectors_logs_skipped_rollback_failure() -> None:
    conn = _InsertFailConn()
    with patch.object(precedent_vectors._logger, "debug") as debug:
        ok = precedent_vectors.insert_vectors(conn, "model-x", [("fp1", [0.1, 0.2])])
    assert ok is False
    assert debug.called
    assert "rollback after a failed precedent vector insert also failed" in debug.call_args.args[0]
