"""A job that never emits the report_path marker keeps a bounded pre-marker buffer."""
from __future__ import annotations

from quodeq.services.jobs import JobManager
from tests.services._jobs_run_log_fixtures import _make_job

_LINES = 2000


def test_pre_marker_buffer_keeps_only_the_newest_lines(tmp_path):
    jm = JobManager(reports_root=tmp_path)
    jm._store.put(_make_job("job-1"))

    for i in range(_LINES):
        jm._tee_run_log("job-1", f"line {i}")

    buf = jm._pre_marker_buffer["job-1"]
    assert buf.maxlen is not None and buf.maxlen < _LINES
    assert len(buf) == buf.maxlen
    assert buf[-1] == f"line {_LINES - 1}"
