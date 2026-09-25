"""Narrowed catches around run_index's per-run sync steps.

Each catch narrows from a bare ``except Exception`` to the specific
sqlite3/OSError/ValueError/OverflowError set that ``upsert_from_status``,
``check_stale_and_promote`` and ``sync_legacy_run`` can actually raise.
The named exception still takes the handler's path (logged, sync
continues); anything else is a genuine bug and must propagate rather
than being silently absorbed.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

import quodeq.data.sqlite.run_index as run_index_mod
from quodeq.data.fs.run_status_store import RunState, RunStatus, write_status
from quodeq.data.sqlite.run_index import open_index, sync_index, sync_project_dates

_LOGGER_NAME = "quodeq.data.sqlite.run_index"


def _seed_status_run(root: Path, project: str, run_id: str) -> Path:
    d = root / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    write_status(d, RunStatus(
        state=RunState.RUNNING, job_id=f"ext-{run_id}",
        started_at="2026-04-20T00:00:00+00:00", dimensions=[]))
    return d


def _seed_legacy_run(root: Path, project: str, run_id: str) -> Path:
    d = root / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    return d


def _raise(exc: Exception):
    def _thrower(*a, **kw):
        raise exc
    return _thrower


class TestUpsertCatchNarrowing:
    """``_sync_status_backed_run``'s ``_upsert_if_changed`` catch."""

    def test_sqlite_error_is_caught_and_logged(self, tmp_path, monkeypatch, caplog):
        reports = tmp_path / "reports"
        _seed_status_run(reports, "p", "rA")
        db = open_index(tmp_path / "idx.db")
        monkeypatch.setattr(
            run_index_mod, "_upsert_if_changed",
            _raise(sqlite3.OperationalError("db is locked")),
        )
        try:
            with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
                sync_index(db, reports)  # must not raise
            assert any("skipping run" in r.message for r in caplog.records)
        finally:
            db.close()

    def test_an_unnamed_failure_propagates(self, tmp_path, monkeypatch):
        reports = tmp_path / "reports"
        _seed_status_run(reports, "p", "rA")
        db = open_index(tmp_path / "idx.db")
        monkeypatch.setattr(
            run_index_mod, "_upsert_if_changed", _raise(TypeError("unexpected bug")),
        )
        try:
            with pytest.raises(TypeError, match="unexpected bug"):
                sync_index(db, reports)
        finally:
            db.close()


class TestStaleCheckCatchNarrowing:
    """``_sync_status_backed_run``'s ``check_stale_and_promote`` catch."""

    def test_value_error_is_caught_and_logged(self, tmp_path, monkeypatch, caplog):
        reports = tmp_path / "reports"
        _seed_status_run(reports, "p", "rA")
        db = open_index(tmp_path / "idx.db")
        monkeypatch.setattr(
            run_index_mod, "check_stale_and_promote", _raise(ValueError("bad status")),
        )
        try:
            with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
                sync_index(db, reports)  # must not raise
            assert any("stale-check failed" in r.message for r in caplog.records)
        finally:
            db.close()

    def test_an_unnamed_failure_propagates(self, tmp_path, monkeypatch):
        reports = tmp_path / "reports"
        _seed_status_run(reports, "p", "rA")
        db = open_index(tmp_path / "idx.db")
        monkeypatch.setattr(
            run_index_mod, "check_stale_and_promote", _raise(KeyError("unexpected bug")),
        )
        try:
            with pytest.raises(KeyError):
                sync_index(db, reports)
        finally:
            db.close()


class TestLegacySyncCatchNarrowing:
    """``_sync_one_run``'s ``sync_legacy_run`` catch."""

    def test_sqlite_error_is_caught_and_logged(self, tmp_path, monkeypatch, caplog):
        reports = tmp_path / "reports"
        _seed_legacy_run(reports, "p", "rA")
        db = open_index(tmp_path / "idx.db")
        monkeypatch.setattr(
            run_index_mod, "sync_legacy_run", _raise(sqlite3.OperationalError("db is locked")),
        )
        try:
            with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
                sync_index(db, reports)  # must not raise
            assert any("legacy sync failed" in r.message for r in caplog.records)
        finally:
            db.close()

    def test_an_unnamed_failure_propagates(self, tmp_path, monkeypatch):
        reports = tmp_path / "reports"
        _seed_legacy_run(reports, "p", "rA")
        db = open_index(tmp_path / "idx.db")
        monkeypatch.setattr(
            run_index_mod, "sync_legacy_run", _raise(AttributeError("unexpected bug")),
        )
        try:
            with pytest.raises(AttributeError):
                sync_index(db, reports)
        finally:
            db.close()


class TestProjectDatesUpsertCatchNarrowing:
    """``sync_project_dates``'s ``_upsert_if_changed`` catch."""

    def test_overflow_error_is_caught_and_logged(self, tmp_path, monkeypatch, caplog):
        reports = tmp_path / "reports"
        run_dir = _seed_status_run(reports, "p", "rA")
        db = open_index(tmp_path / "idx.db")
        monkeypatch.setattr(
            run_index_mod, "_upsert_if_changed", _raise(OverflowError("too big for sqlite")),
        )
        try:
            with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
                sync_project_dates(db, run_dir.parent, "p")  # must not raise
            assert any("date-sync upsert failed" in r.message for r in caplog.records)
        finally:
            db.close()

    def test_an_unnamed_failure_propagates(self, tmp_path, monkeypatch):
        reports = tmp_path / "reports"
        run_dir = _seed_status_run(reports, "p", "rA")
        db = open_index(tmp_path / "idx.db")
        monkeypatch.setattr(
            run_index_mod, "_upsert_if_changed", _raise(TypeError("unexpected bug")),
        )
        try:
            with pytest.raises(TypeError, match="unexpected bug"):
                sync_project_dates(db, run_dir.parent, "p")
        finally:
            db.close()
