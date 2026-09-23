"""Tests for _job_file_store.py: FileJobStore persistence, stale cleanup and default persist dir."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


from quodeq.core.run.job_status import JobStatus
from quodeq.services._job_model import Job
from quodeq.services._job_file_store import FileJobStore, _default_persist_dir


# ---------------------------------------------------------------------------
# FileJobStore
# ---------------------------------------------------------------------------


class TestFileJobStore:
    def test_put_and_get(self, tmp_path: Path):
        store = FileJobStore(persist_dir=tmp_path)
        job = Job("j1", "running", ["echo"], "now", None, None)
        store.put(job)
        assert store.get("j1") is job

    def test_persists_to_disk(self, tmp_path: Path):
        store = FileJobStore(persist_dir=tmp_path)
        job = Job("j1", "done", ["echo"], "now", "later", 0)
        store.put(job)
        assert (tmp_path / "j1.json").exists()
        data = json.loads((tmp_path / "j1.json").read_text())
        assert data["job_id"] == "j1"

    def test_status_round_trips_through_disk_as_done(self, tmp_path: Path):
        """A job whose status is JobStatus.DONE serializes to the plain
        string "done" on disk (StrEnum, not the repr) and reads back equal
        to JobStatus.DONE (not merely the string "done")."""
        store = FileJobStore(persist_dir=tmp_path)
        job = Job("j1", JobStatus.DONE, ["echo"], "now", "later", 0)
        store.put(job)
        data = json.loads((tmp_path / "j1.json").read_text())
        assert data["status"] == "done"

        reloaded_store = FileJobStore(persist_dir=tmp_path)
        reloaded = reloaded_store.get("j1")
        assert reloaded is not None
        assert reloaded.status == JobStatus.DONE

    def test_loads_on_init(self, tmp_path: Path):
        # Write a job file manually
        data = {
            "job_id": "j1",
            "status": "completed",
            "command": ["echo"],
            "started_at": "now",
            "ended_at": "later",
            "exit_code": 0,
            "logs": ["line1"],
        }
        (tmp_path / "j1.json").write_text(json.dumps(data))
        store = FileJobStore(persist_dir=tmp_path)
        job = store.get("j1")
        assert job is not None
        assert job.status == "completed"

    def test_running_jobs_marked_lost_on_load(self, tmp_path: Path):
        # The subprocess is spawned start_new_session=True and survives a
        # server restart — the run is usually still alive and writing. It
        # is "lost" (tracking gone), not "failed": marking it failed showed
        # a live scan as dead and (via list dedup) hid the truthful ext-
        # index row that could still track and cancel it.
        data = {
            "job_id": "j1",
            "status": "running",
            "command": ["echo"],
            "started_at": "now",
        }
        (tmp_path / "j1.json").write_text(json.dumps(data))
        store = FileJobStore(persist_dir=tmp_path)
        job = store.get("j1")
        assert job is not None
        assert job.status == "lost"
        assert job.exit_code is None

    def test_corrupt_file_skipped(self, tmp_path: Path):
        (tmp_path / "bad.json").write_text("not json{{{")
        store = FileJobStore(persist_dir=tmp_path)
        assert store.list() == []

    def test_delete_removes_file(self, tmp_path: Path):
        store = FileJobStore(persist_dir=tmp_path)
        job = Job("j1", "done", ["echo"], "now", "later", 0)
        store.put(job)
        assert (tmp_path / "j1.json").exists()
        store.delete("j1")
        assert not (tmp_path / "j1.json").exists()
        assert store.get("j1") is None

    def test_delete_missing_noop(self, tmp_path: Path):
        store = FileJobStore(persist_dir=tmp_path)
        store.delete("nope")  # should not raise

    def test_list_returns_all(self, tmp_path: Path):
        store = FileJobStore(persist_dir=tmp_path)
        store.put(Job("j1", "done", [], "now", "later", 0))
        store.put(Job("j2", "failed", [], "now", "later", 1))
        assert len(store.list()) == 2

    def test_cleanup_stale_jobs(self, tmp_path: Path):
        # Create a stale completed job (ended 48 hours ago)
        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        data = {
            "job_id": "old_job",
            "status": "completed",
            "command": ["echo"],
            "started_at": "2026-01-01T00:00:00Z",
            "ended_at": old_time,
            "exit_code": 0,
        }
        (tmp_path / "old_job.json").write_text(json.dumps(data))

        # Create a recent completed job
        recent_time = datetime.now(timezone.utc).isoformat()
        data2 = {
            "job_id": "new_job",
            "status": "completed",
            "command": ["echo"],
            "started_at": "2026-01-01T00:00:00Z",
            "ended_at": recent_time,
            "exit_code": 0,
        }
        (tmp_path / "new_job.json").write_text(json.dumps(data2))

        store = FileJobStore(persist_dir=tmp_path)
        assert store.get("old_job") is None  # cleaned up
        assert store.get("new_job") is not None  # kept

    def test_stale_cleanup_skips_running(self, tmp_path: Path):
        # Running jobs should never be cleaned up, even if old
        data = {
            "job_id": "j1",
            "status": "running",
            "command": [],
            "started_at": "2020-01-01T00:00:00Z",
        }
        (tmp_path / "j1.json").write_text(json.dumps(data))
        store = FileJobStore(persist_dir=tmp_path)
        # Running -> lost on load, but should still exist
        assert store.get("j1") is not None

    def test_stale_cleanup_skips_no_ended_at(self, tmp_path: Path):
        data = {
            "job_id": "j1",
            "status": "failed",
            "command": [],
            "started_at": "2020-01-01T00:00:00Z",
            "ended_at": None,
        }
        (tmp_path / "j1.json").write_text(json.dumps(data))
        store = FileJobStore(persist_dir=tmp_path)
        assert store.get("j1") is not None

    def test_flipped_running_job_gets_ended_at(self, tmp_path: Path):
        """A 'running' job flipped to lost must get an ended_at.

        Without it, _cleanup_stale skips the job forever (it only prunes
        jobs with ended_at), so crash/test leftovers accumulate until they
        wedge the completed-jobs cap and evict real history instead.
        """
        data = {
            "job_id": "j1",
            "status": "running",
            "command": ["echo"],
            "started_at": "2026-01-01T00:00:00+00:00",
        }
        (tmp_path / "j1.json").write_text(json.dumps(data))
        store = FileJobStore(persist_dir=tmp_path)
        job = store.get("j1")
        assert job is not None
        assert job.status == "lost"
        assert job.ended_at, "flipped jobs must be prunable by _cleanup_stale"
        on_disk = json.loads((tmp_path / "j1.json").read_text())
        assert on_disk["ended_at"], "the flip must be persisted with ended_at"

    def test_write_failure_does_not_crash(self, tmp_path: Path, monkeypatch):
        """If writing to disk fails, put() should not raise."""
        store = FileJobStore(persist_dir=tmp_path)
        job = Job("j1", "done", ["echo"], "now", "later", 0)
        # Make the persist dir read-only to trigger OSError

        def fail_write(*a, **kw):
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_text", fail_write)
        # Should log warning but not raise
        store.put(job)


class TestDefaultPersistDir:
    """The job store's default location must follow the rest of the state.

    It used to honor only QUODEQ_JOB_PERSIST_DIR and otherwise hardcode
    ~/.quodeq/run/jobs, so pytest runs (which isolate QUODEQ_INDEX_DB_PATH
    but not this) polluted the developer's real dashboard with fake jobs.
    Deriving from the index-db parent mirrors get_score_cache_path's idiom:
    one env override isolates every sibling store.
    """

    def test_derives_from_index_db_path(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("QUODEQ_JOB_PERSIST_DIR", raising=False)
        monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
        assert _default_persist_dir() == tmp_path / "run" / "jobs"

    def test_explicit_env_wins(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("QUODEQ_JOB_PERSIST_DIR", str(tmp_path / "explicit"))
        monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
        assert _default_persist_dir() == tmp_path / "explicit"

    def test_falls_back_to_home_without_any_env(self, monkeypatch):
        monkeypatch.delenv("QUODEQ_JOB_PERSIST_DIR", raising=False)
        monkeypatch.delenv("QUODEQ_INDEX_DB_PATH", raising=False)
        assert _default_persist_dir() == Path.home() / ".quodeq" / "run" / "jobs"
