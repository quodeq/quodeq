"""The project-summary cache keeps one version per project, never logs an
unserializable payload, and reads a corrupt row as a miss."""
from __future__ import annotations

import logging
import sqlite3

import pytest

from quodeq.data.sqlite.score_cache_db import open_score_cache
from quodeq.data.sqlite.score_cache_store import (
    read_cached_project_summary,
    write_cached_project_summary,
)

_LOGGER = "quodeq.data.sqlite.score_cache_store"


@pytest.fixture
def conn(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))
    with open_score_cache() as c:
        yield c


def test_the_slot_keeps_one_version_per_project(conn):
    write_cached_project_summary(conn, "P", "v1", {"a": 1})
    write_cached_project_summary(conn, "P", "v2", {"a": 2})
    assert read_cached_project_summary(conn, "P", "v1") is None
    assert read_cached_project_summary(conn, "P", "v2") == {"a": 2}


def test_an_unserializable_payload_is_skipped_silently(conn, caplog):
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    write_cached_project_summary(conn, "P", "v1", {"x": object()})
    assert caplog.records == []
    assert read_cached_project_summary(conn, "P", "v1") is None


def test_a_failed_write_logs_its_own_message(caplog):
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    closed = sqlite3.connect(":memory:")
    closed.close()
    write_cached_project_summary(closed, "P", "v1", {"a": 1})
    assert [r.getMessage() for r in caplog.records] == ["project summary cache write failed for P"]


def test_a_corrupt_payload_reads_as_a_miss(conn):
    write_cached_project_summary(conn, "P", "v1", {"a": 1})
    conn.execute("UPDATE project_summary_cache SET payload='{'")
    assert read_cached_project_summary(conn, "P", "v1") is None


def test_an_old_accumulated_table_is_dropped_on_first_open(monkeypatch, tmp_path):
    """A cache file from before the slot was removed loses its table on init."""
    path = tmp_path / "score_cache.db"
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(path))
    with sqlite3.connect(path) as raw:
        raw.execute("CREATE TABLE accumulated_cache (project TEXT, version TEXT, payload TEXT)")
    with open_score_cache() as c:
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "accumulated_cache" not in names and "project_summary_cache" in names
