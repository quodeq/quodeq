"""The CC_MARKER_KEY phase vocabulary (setup/analyzing/scoring/analyzing_start/
deadline_extended/report_path) is written by analysis/_runner_markers.emit_marker
(and its callers across analysis/) and read back by
services/_job_monitor_mixin._JobMonitorMixin._apply_marker. Both sides import
the same constants from shared.constants -- services may not import analysis
-- so this test drives _apply_marker with the producer's own constants,
never retyped strings, and checks core.stream.events.COPILOT_MCP_POLICY_REASON
the same way.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from quodeq.core.stream.events import COPILOT_MCP_POLICY_REASON
from quodeq.services._job_model import Job
from quodeq.services.jobs import JobManager
from quodeq.shared.constants import (
    CC_MARKER_KEY, CC_PHASE_ANALYZING, CC_PHASE_ANALYZING_START,
    CC_PHASE_DEADLINE_EXTENDED, CC_PHASE_REPORT_PATH, CC_PHASE_SCORING, CC_PHASE_SETUP,
)


def _job():
    return Job(
        job_id="j1", status="running", command=["quodeq"],
        started_at=datetime.now(timezone.utc).isoformat(), ended_at=None, exit_code=None,
    )


def test_job_monitor_mixin_imports_the_shared_phase_constants():
    from quodeq.services import _job_monitor_mixin

    assert _job_monitor_mixin.CC_PHASE_SETUP is CC_PHASE_SETUP
    assert _job_monitor_mixin.CC_PHASE_ANALYZING is CC_PHASE_ANALYZING
    assert _job_monitor_mixin.CC_PHASE_SCORING is CC_PHASE_SCORING
    assert _job_monitor_mixin.CC_PHASE_ANALYZING_START is CC_PHASE_ANALYZING_START
    assert _job_monitor_mixin.CC_PHASE_DEADLINE_EXTENDED is CC_PHASE_DEADLINE_EXTENDED
    assert _job_monitor_mixin.CC_PHASE_REPORT_PATH is CC_PHASE_REPORT_PATH
    assert _job_monitor_mixin.COPILOT_MCP_POLICY_REASON is COPILOT_MCP_POLICY_REASON


def test_setup_marker_from_the_shared_constant_sets_phase():
    job = _job()
    line = json.dumps({CC_MARKER_KEY: CC_PHASE_SETUP, "dimensions": ["security"]})

    JobManager._apply_marker(job, line)

    assert job.phase == CC_PHASE_SETUP
    assert job.dimensions == ["security"]


def test_report_path_marker_from_the_shared_constant_sets_output():
    job = _job()
    line = json.dumps({CC_MARKER_KEY: CC_PHASE_REPORT_PATH, "project": "p1", "runId": "r1"})

    JobManager._apply_marker(job, line)

    assert job.output_project == "p1"
    assert job.output_run_id == "r1"
