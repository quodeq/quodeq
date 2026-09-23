"""Tests for _job_model.py — Job, InMemoryJobStore, REPORT_PATH_RE."""

from __future__ import annotations


from quodeq.services._job_model import (
    Job,
    InMemoryJobStore,
    MAX_LOG_LINES,
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

    def test_log_rolling_buffer(self):
        job = self._make_job()
        for i in range(MAX_LOG_LINES + 50):
            job.logs.append(f"line {i}")
        assert len(job.logs) == MAX_LOG_LINES
        # Oldest lines should have been evicted
        assert "line 0" not in job.logs
        assert f"line {MAX_LOG_LINES + 49}" in job.logs

    def test_to_dict_returns_snapshot(self):
        job = self._make_job(
            output_project="proj1",
            output_run_id="run1",
            phase="scoring",
            current_dimension="perf",
            dimensions=["security", "perf"],
        )
        job.logs.append("hello")
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
