"""run_index's per-run fault isolation (SAVEPOINT + run_isolated boundary).

sync_index()/sync_project_dates() walk many runs inside one shared ``with
db:`` transaction. Each run is one work-queue iteration: a run whose sync
step raises must not stop syncing the rest, must not roll back rows already
committed for OTHER runs synced earlier in the same call, and must not
leave a partial row for itself when it fails after an earlier write in the
same step.
"""
from __future__ import annotations

import logging
from pathlib import Path

import quodeq.data.sqlite.run_index as run_index_mod
from quodeq.data.fs.run_status_store import RunState, RunStatus, write_status
from quodeq.data.sqlite.index_sync import check_stale_and_promote, upsert_from_status
from quodeq.data.sqlite.run_index import open_index, sync_index, sync_project_dates

_LOGGER_NAME = "quodeq.data.sqlite.run_index"

# _run_sync_step is a private sibling of run_index (leading underscore): it
# is patched by dotted string path below, never imported directly, so this
# file stays on the public surface the same way its own production imports do.
_CHECK_STALE_TARGET = "quodeq.data.sqlite._run_sync_step.check_stale_and_promote"


def _seed_run(root: Path, project: str, run_id: str) -> Path:
    d = root / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    write_status(d, RunStatus(
        state=RunState.RUNNING, job_id=f"ext-{run_id}",
        started_at="2026-04-20T00:00:00+00:00", dimensions=[]))
    return d


class TestSyncIndexPerRunIsolation:
    def test_one_bad_run_does_not_stop_the_others(self, tmp_path, monkeypatch, caplog):
        reports = tmp_path / "reports"
        _seed_run(reports, "p", "good1")
        _seed_run(reports, "p", "bad")
        _seed_run(reports, "p", "good2")
        db = open_index(tmp_path / "idx.db")

        def flaky_check(db, run_dir, *, project_uuid, run_id):
            if run_id == "bad":
                raise AttributeError("boom")
            return check_stale_and_promote(db, run_dir, project_uuid=project_uuid, run_id=run_id)

        monkeypatch.setattr(_CHECK_STALE_TARGET, flaky_check)

        try:
            with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
                sync_index(db, reports)  # must not raise

            rows = {r[0] for r in db.execute("SELECT job_id FROM runs").fetchall()}
            assert rows == {"ext-good1", "ext-good2"}, (
                "the bad run must not be indexed, and the others must still be"
            )
            assert any("index sync bad" in r.message for r in caplog.records)
        finally:
            db.close()

    def test_a_bad_run_leaves_no_partial_row_from_its_own_earlier_write(
        self, tmp_path, monkeypatch,
    ):
        """upsert_if_changed succeeds (writes the row) and THEN
        check_stale_and_promote raises: the run's own successful upsert must
        be rolled back by the per-run SAVEPOINT, not left as a half-synced
        row."""
        reports = tmp_path / "reports"
        _seed_run(reports, "p", "bad")
        db = open_index(tmp_path / "idx.db")

        monkeypatch.setattr(
            _CHECK_STALE_TARGET,
            lambda *a, **kw: (_ for _ in ()).throw(AttributeError("boom")),
        )

        try:
            sync_index(db, reports)  # must not raise

            rows = db.execute("SELECT job_id FROM runs").fetchall()
            assert rows == [], "the failed run's own successful upsert must be rolled back"
        finally:
            db.close()

    def test_second_sync_call_still_works_after_a_rolled_back_run(self, tmp_path, monkeypatch):
        """The SAVEPOINT rollback must not corrupt the connection/transaction
        for later work in a later sync_index call."""
        reports = tmp_path / "reports"
        _seed_run(reports, "p", "flaky")
        db = open_index(tmp_path / "idx.db")

        should_fail = {"value": True}

        def flaky_check(db, run_dir, *, project_uuid, run_id):
            if should_fail["value"]:
                raise AttributeError("boom")
            return check_stale_and_promote(db, run_dir, project_uuid=project_uuid, run_id=run_id)

        monkeypatch.setattr(_CHECK_STALE_TARGET, flaky_check)

        try:
            sync_index(db, reports)
            assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0

            should_fail["value"] = False
            sync_index(db, reports)  # a normal later call must still work

            rows = {r[0] for r in db.execute("SELECT job_id FROM runs").fetchall()}
            assert rows == {"ext-flaky"}
        finally:
            db.close()


class TestSyncProjectDatesPerRunIsolation:
    def test_one_bad_run_does_not_stop_the_others(self, tmp_path, monkeypatch, caplog):
        reports = tmp_path / "reports"
        _seed_run(reports, "p", "good1")
        _seed_run(reports, "p", "bad")
        _seed_run(reports, "p", "good2")
        db = open_index(tmp_path / "idx.db")

        real_upsert = run_index_mod.upsert_if_changed

        def flaky_upsert(db, run_dir, *, project_uuid, run_id, cached_mtime):
            if run_id == "bad":
                raise AttributeError("boom")
            return real_upsert(
                db, run_dir, project_uuid=project_uuid, run_id=run_id, cached_mtime=cached_mtime,
            )

        # sync_project_dates calls the name bound in run_index's own
        # namespace (`from ... import upsert_if_changed`), not the one on
        # _run_sync_step -- patch where it is used.
        monkeypatch.setattr(run_index_mod, "upsert_if_changed", flaky_upsert)

        try:
            with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
                sync_project_dates(db, reports / "p", "p")  # must not raise

            rows = {r[0] for r in db.execute("SELECT run_id FROM runs").fetchall()}
            assert rows == {"good1", "good2"}, (
                "the bad run must not be indexed, and the others must still be"
            )
            assert any("index sync bad" in r.message for r in caplog.records)
        finally:
            db.close()

    def test_a_bad_run_leaves_no_partial_row_from_its_own_earlier_write(
        self, tmp_path, monkeypatch,
    ):
        """The fake step performs a real write (mirroring what
        ``upsert_if_changed`` itself would do) and then raises: the SAVEPOINT
        must roll that write back too, not just skip a would-be write."""
        reports = tmp_path / "reports"
        _seed_run(reports, "p", "bad")
        db = open_index(tmp_path / "idx.db")

        def fake_upsert(db, run_dir, *, project_uuid, run_id, cached_mtime):
            upsert_from_status(db, run_dir, project_uuid=project_uuid, run_id=run_id)
            raise AttributeError("boom")

        monkeypatch.setattr(run_index_mod, "upsert_if_changed", fake_upsert)

        try:
            sync_project_dates(db, reports / "p", "p")  # must not raise

            rows = db.execute("SELECT run_id FROM runs").fetchall()
            assert rows == [], "the failed run's own successful write must be rolled back"
        finally:
            db.close()
