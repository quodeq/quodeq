"""The accumulated and project-summary caches each keep one version per
project and never share rows; only the accumulated slot logs a warning on
an unserializable payload."""
from __future__ import annotations

import logging
import sqlite3

import pytest

from quodeq.data.sqlite.score_cache_db import open_score_cache
from quodeq.data.sqlite.score_cache_store import (
    read_cached_accumulated,
    read_cached_project_summary,
    write_cached_accumulated,
    write_cached_project_summary,
)

_LOGGER = "quodeq.data.sqlite.score_cache_store"
_SLOTS = [
    (read_cached_accumulated, write_cached_accumulated),
    (read_cached_project_summary, write_cached_project_summary),
]


@pytest.fixture
def conn(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))
    with open_score_cache() as c:
        yield c


@pytest.mark.parametrize(("read", "write"), _SLOTS)
def test_each_slot_keeps_one_version_per_project(conn, read, write):
    write(conn, "P", "v1", {"a": 1})
    write(conn, "P", "v2", {"a": 2})
    assert read(conn, "P", "v1") is None
    assert read(conn, "P", "v2") == {"a": 2}


def test_the_slots_do_not_share_rows(conn):
    write_cached_accumulated(conn, "P", "v1", {"kind": "acc"})
    write_cached_project_summary(conn, "P", "v1", {"kind": "sum"})
    assert read_cached_accumulated(conn, "P", "v1") == {"kind": "acc"}
    assert read_cached_project_summary(conn, "P", "v1") == {"kind": "sum"}


def test_only_the_accumulated_slot_warns_on_an_unserializable_payload(conn, caplog):
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    write_cached_accumulated(conn, "P", "v1", {"x": object()})
    assert [r.getMessage() for r in caplog.records] == [
        "accumulated payload for P not serializable; skipping cache",
    ]
    caplog.clear()
    write_cached_project_summary(conn, "P", "v1", {"x": object()})
    assert caplog.records == []
    assert read_cached_project_summary(conn, "P", "v1") is None


@pytest.mark.parametrize(("write", "message"), [
    (write_cached_accumulated, "accumulated cache write failed for P"),
    (write_cached_project_summary, "project summary cache write failed for P"),
])
def test_a_failed_write_logs_its_own_message(caplog, write, message):
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    closed = sqlite3.connect(":memory:")
    closed.close()
    write(closed, "P", "v1", {"a": 1})
    assert [r.getMessage() for r in caplog.records] == [message]


@pytest.mark.parametrize(("read", "write"), _SLOTS)
def test_a_corrupt_payload_reads_as_a_miss(conn, read, write):
    write(conn, "P", "v1", {"a": 1})
    conn.execute("UPDATE accumulated_cache SET payload='{'")
    conn.execute("UPDATE project_summary_cache SET payload='{'")
    assert read(conn, "P", "v1") is None
