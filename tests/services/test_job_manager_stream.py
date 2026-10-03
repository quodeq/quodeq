"""Tests for jobs.py: JobManager log-stream handling (markers, log append, stream consumption)."""

from __future__ import annotations

import io
import json


from quodeq.services._job_model import InMemoryJobStore, Job
from quodeq.services.jobs import JobManager


# ---------------------------------------------------------------------------
# _apply_marker
# ---------------------------------------------------------------------------


class TestApplyMarker:
    def _make_job(self):
        return Job("j1", "running", [], "now", None, None)

    def _manager(self):
        return JobManager(job_store=InMemoryJobStore())

    def test_setup_marker(self):
        job = self._make_job()
        line = json.dumps({"_cc": "setup", "dimensions": ["sec", "perf"]})
        self._manager()._apply_marker(job, line)
        assert job.phase == "setup"
        assert job.dimensions == ["sec", "perf"]

    def test_analyzing_marker(self):
        job = self._make_job()
        line = json.dumps({"_cc": "analyzing", "dimension": "security"})
        self._manager()._apply_marker(job, line)
        assert job.phase == "analyzing"
        assert job.current_dimension == "security"

    def test_scoring_marker(self):
        job = self._make_job()
        line = json.dumps({"_cc": "scoring", "dimension": "perf"})
        self._manager()._apply_marker(job, line)
        assert job.phase == "scoring"
        assert job.current_dimension == "perf"

    def test_report_path_marker(self):
        job = self._make_job()
        line = json.dumps({"_cc": "report_path", "project": "myproj", "runId": "r1"})
        self._manager()._apply_marker(job, line)
        assert job.output_project == "myproj"
        assert job.output_run_id == "r1"

    def test_report_path_marker_missing_fields(self):
        job = self._make_job()
        line = json.dumps({"_cc": "report_path"})
        self._manager()._apply_marker(job, line)
        assert job.output_project is None

    def test_invalid_json_ignored(self):
        job = self._make_job()
        self._manager()._apply_marker(job, "not json")
        assert job.phase is None

    def test_invalid_json_logs_a_warning(self, recording_log):
        job = self._make_job()
        manager = JobManager(job_store=InMemoryJobStore(), log=recording_log)
        manager._apply_marker(job, "not json")
        assert recording_log.warning_messages
        assert "malformed structured marker" in recording_log.warning_messages[0]


# ---------------------------------------------------------------------------
# _append_log
# ---------------------------------------------------------------------------


class TestAppendLog:
    def test_empty_line_ignored(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        job = Job("j1", "running", [], "now", None, None)
        mgr._append_log(job, "")
        assert len(job.logs) == 0

    def test_marker_line_not_in_logs(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        job = Job("j1", "running", [], "now", None, None)
        marker = json.dumps({"_cc": "setup", "dimensions": ["sec"]})
        mgr._append_log(job, marker)
        assert len(job.logs) == 0
        assert job.phase == "setup"

    def test_ansi_stripped(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        job = Job("j1", "running", [], "now", None, None)
        mgr._append_log(job, "\x1b[32mhello\x1b[0m")
        assert job.logs[0] == "hello"

    def test_fallback_report_path_extraction(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        job = Job("j1", "running", [], "now", None, None)
        mgr._append_log(job, "Report path: /r/my-project/run123/evaluation")
        assert job.output_project == "my-project"
        assert job.output_run_id == "run123"

    def test_fallback_report_path_skipped_if_already_set(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        job = Job("j1", "running", [], "now", None, None, output_project="already")
        mgr._append_log(job, "Report path: /r/other/run2/evaluation")
        assert job.output_project == "already"  # not overwritten


# ---------------------------------------------------------------------------
# _consume_stream
# ---------------------------------------------------------------------------


class TestConsumeStream:
    def test_none_stream(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        mgr._consume_stream("j1", None)  # should not raise

    def test_consumes_lines(self):
        store = InMemoryJobStore()
        job = Job("j1", "running", [], "now", None, None)
        store.put(job)
        mgr = JobManager(job_store=store)
        stream = io.StringIO("line1\nline2\n")
        mgr._consume_stream("j1", stream)
        assert "line1" in job.logs
        assert "line2" in job.logs

    def test_stops_if_job_removed(self):
        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        # Job not in store — _flush_batch should return False
        stream = io.StringIO("line1\n")
        mgr._consume_stream("j1", stream)  # should not raise
