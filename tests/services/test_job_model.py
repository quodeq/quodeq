"""Tests for _job_model.py — Job, InMemoryJobStore, FileJobStore, serialization."""

from __future__ import annotations

import json
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from quodeq.services._job_model import (
    Job,
    InMemoryJobStore,
    FileJobStore,
    _job_to_json,
    _job_from_json,
    _MAX_LOG_LINES,
    _STALE_JOB_AGE_S,
    REPORT_PATH_RE,
)


# ---------------------------------------------------------------------------
# Job data model
# ---------------------------------------------------------------------------


class TestJob:
    def _make_job(self, **overrides) -> Job:
        defaults = dict(
            job_id="j1",
            status="running",
            command=["python", "-m", "quodeq.cli", "evaluate"],
            started_at="2026-01-01T00:00:00+00:00",
            ended_at=None,
            exit_code=None,
        )
        defaults.update(overrides)
        return Job(**defaults)

    def test_complete_success(self):
        job = self._make_job()
        job.complete(0, "2026-01-01T01:00:00+00:00")
        assert job.status == "completed"
        assert job.exit_code == 0
        assert job.ended_at == "2026-01-01T01:00:00+00:00"

    def test_complete_failure(self):
        job = self._make_job()
        job.complete(1, "2026-01-01T01:00:00+00:00")
        assert job.status == "failed"
        assert job.exit_code == 1

    def test_cancel_running(self):
        job = self._make_job()
        job.cancel("2026-01-01T01:00:00+00:00")
        assert job.status == "cancelled"
        assert job.ended_at is not None

    def test_cancel_already_completed_noop(self):
        job = self._make_job(status="completed")
        job.cancel("2026-01-01T02:00:00+00:00")
        assert job.status == "completed"

    def test_cancel_already_failed_noop(self):
        job = self._make_job(status="failed")
        job.cancel("2026-01-01T02:00:00+00:00")
        assert job.status == "failed"

    def test_add_log(self):
        job = self._make_job()
        job.add_log("line 1")
        job.add_log("line 2")
        assert list(job.logs) == ["line 1", "line 2"]

    def test_log_rolling_buffer(self):
        job = self._make_job()
        for i in range(_MAX_LOG_LINES + 50):
            job.add_log(f"line {i}")
        assert len(job.logs) == _MAX_LOG_LINES
        # Oldest lines should have been evicted
        assert "line 0" not in job.logs
        assert f"line {_MAX_LOG_LINES + 49}" in job.logs

    def test_set_phase_with_dimension(self):
        job = self._make_job()
        job.set_phase("analyzing", dimension="security")
        assert job.phase == "analyzing"
        assert job.current_dimension == "security"

    def test_set_phase_without_dimension(self):
        job = self._make_job()
        job.set_phase("setup")
        assert job.phase == "setup"
        assert job.current_dimension is None

    def test_to_dict_returns_snapshot(self):
        job = self._make_job(
            output_project="proj1",
            output_run_id="run1",
            phase="scoring",
            current_dimension="perf",
            dimensions=["security", "perf"],
        )
        job.add_log("hello")
        snap = job.to_dict()
        assert snap.job_id == "j1"
        assert snap.status == "running"
        assert snap.output_project == "proj1"
        assert snap.output_run_id == "run1"
        assert snap.phase == "scoring"
        assert snap.current_dimension == "perf"
        assert snap.dimensions == ["security", "perf"]
        assert snap.logs == ["hello"]

    def test_to_dict_command_is_basename(self):
        job = self._make_job(command=["/usr/bin/python", "-m", "quodeq.cli"])
        snap = job.to_dict()
        assert snap.command == "python"

    def test_to_dict_empty_command(self):
        job = self._make_job(command=[])
        snap = job.to_dict()
        assert snap.command == ""


# ---------------------------------------------------------------------------
# InMemoryJobStore
# ---------------------------------------------------------------------------


class TestInMemoryJobStore:
    def test_put_and_get(self):
        store = InMemoryJobStore()
        job = Job("j1", "running", ["echo"], "now", None, None)
        store.put(job)
        assert store.get("j1") is job

    def test_get_missing(self):
        store = InMemoryJobStore()
        assert store.get("nope") is None

    def test_list(self):
        store = InMemoryJobStore()
        store.put(Job("j1", "running", [], "now", None, None))
        store.put(Job("j2", "done", [], "now", None, None))
        assert len(store.list()) == 2

    def test_delete(self):
        store = InMemoryJobStore()
        store.put(Job("j1", "running", [], "now", None, None))
        store.delete("j1")
        assert store.get("j1") is None

    def test_delete_missing_noop(self):
        store = InMemoryJobStore()
        store.delete("nope")  # should not raise


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_round_trip(self):
        original = Job(
            job_id="j99",
            status="completed",
            command=["python", "run.py"],
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T01:00:00Z",
            exit_code=0,
            output_project="proj",
            output_run_id="run1",
            phase="scoring",
            current_dimension="security",
            dimensions=["security", "performance"],
        )
        original.add_log("log line 1")
        data = _job_to_json(original)
        restored = _job_from_json(data)
        assert restored.job_id == original.job_id
        assert restored.status == original.status
        assert restored.command == original.command
        assert restored.exit_code == original.exit_code
        assert list(restored.logs) == list(original.logs)
        assert restored.output_project == original.output_project
        assert restored.dimensions == original.dimensions

    def test_from_json_missing_optional_fields(self):
        data = {"job_id": "j1", "status": "running"}
        job = _job_from_json(data)
        assert job.command == []
        assert job.started_at == ""
        assert job.ended_at is None
        assert job.exit_code is None
        assert list(job.logs) == []

    def test_to_json_contains_all_keys(self):
        job = Job("j1", "running", ["cmd"], "now", None, None)
        data = _job_to_json(job)
        expected_keys = {
            "job_id", "status", "command", "started_at", "ended_at",
            "exit_code", "logs", "output_project", "output_run_id",
            "phase", "deadline_at", "current_dimension", "dimensions",
            "ai_provider", "ai_model",
        }
        assert set(data.keys()) == expected_keys

    def test_job_round_trips_provider_and_model(self):
        job = Job(
            job_id="job-1",
            status="running",
            command=["x"],
            started_at="2026-01-01T00:00:00Z",
            ended_at=None,
            exit_code=None,
            ai_provider="ollama",
            ai_model="gemma4:26b-mlx",
        )
        blob = _job_to_json(job)
        assert blob["ai_provider"] == "ollama"
        assert blob["ai_model"] == "gemma4:26b-mlx"
        restored = _job_from_json(blob)
        assert restored.ai_provider == "ollama"
        assert restored.ai_model == "gemma4:26b-mlx"

    def test_job_defaults_provider_and_model_to_none(self):
        job = Job(
            job_id="job-1",
            status="running",
            command=["x"],
            started_at="2026-01-01T00:00:00Z",
            ended_at=None,
            exit_code=None,
        )
        blob = _job_to_json(job)
        blob.pop("ai_provider", None)
        blob.pop("ai_model", None)
        restored = _job_from_json(blob)
        assert restored.ai_provider is None
        assert restored.ai_model is None

    def test_to_dict_carries_provider_and_model(self):
        job = Job(
            job_id="job-1", status="running", command=["x"],
            started_at="2026-01-01T00:00:00Z", ended_at=None, exit_code=None,
            ai_provider="ollama", ai_model="gemma4:26b-mlx",
        )
        snap = job.to_dict()
        assert snap.ai_provider == "ollama"
        assert snap.ai_model == "gemma4:26b-mlx"


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

    def test_running_jobs_marked_failed_on_load(self, tmp_path: Path):
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
        assert job.status == "failed"
        assert job.exit_code == -1

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
        # Running -> failed on load, but should still exist
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

    def test_write_failure_does_not_crash(self, tmp_path: Path, monkeypatch):
        """If writing to disk fails, put() should not raise."""
        store = FileJobStore(persist_dir=tmp_path)
        job = Job("j1", "done", ["echo"], "now", "later", 0)
        # Make the persist dir read-only to trigger OSError
        import os
        original_write = Path.write_text

        def fail_write(*a, **kw):
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_text", fail_write)
        # Should log warning but not raise
        store.put(job)


# ---------------------------------------------------------------------------
# REPORT_PATH_RE
# ---------------------------------------------------------------------------


class TestReportPathRegex:
    def test_matches_unix_path(self):
        line = "Report path: /app/reports/my-project/20260220/evaluation"
        m = REPORT_PATH_RE.search(line)
        assert m is not None
        assert m.group(1) == "my-project"
        assert m.group(2) == "20260220"

    def test_matches_windows_path(self):
        line = r"Report path: C:\reports\my-project\20260220\evaluation"
        m = REPORT_PATH_RE.search(line)
        assert m is not None
        assert m.group(1) == "my-project"
        assert m.group(2) == "20260220"

    def test_no_match_on_garbage(self):
        assert REPORT_PATH_RE.search("no report here") is None
