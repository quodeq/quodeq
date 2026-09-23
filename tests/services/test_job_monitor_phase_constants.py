"""The CC_MARKER_KEY phase vocabulary (setup/analyzing/scoring/analyzing_start/
deadline_extended/report_path) is written by analysis/runner_markers.emit_marker
(and its callers across analysis/) and read back by
services/_job_monitor_mixin.JobMonitorMixin._apply_marker. Both sides import
the same constants from shared.constants -- services may not import analysis
-- so this test drives _apply_marker with the producer's own constants,
never retyped strings, and checks core.stream.events.COPILOT_MCP_POLICY_REASON
the same way.

Both ends are pinned: the consumer assertions below cover _apply_marker, and
_PRODUCERS pins every emit_marker call site that writes a CC_PHASE_* value, so
re-typing the string on either side fails rather than silently desyncing the
dashboard's phase display.
"""
from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone

import pytest

from quodeq.core.stream.events import COPILOT_MCP_POLICY_REASON
from quodeq.services._job_model import Job
from quodeq.services.jobs import JobManager
from quodeq.shared import constants as _constants_module
from quodeq.shared.constants import (
    CC_MARKER_KEY, CC_PHASE_ANALYZING, CC_PHASE_ANALYZING_START,
    CC_PHASE_DEADLINE_EXTENDED, CC_PHASE_REPORT_PATH, CC_PHASE_SCORING, CC_PHASE_SETUP,
)

# The whole phase vocabulary, read off the module so a newly added CC_PHASE_*
# shows up here without editing the test.
shared_constants = {
    name: value for name, value in vars(_constants_module).items()
    if name.startswith("CC_PHASE_")
}


# Every module that calls emit_marker with a CC_PHASE_* value, and the phases
# it writes. Keep in step with `grep -rn "emit_marker(" src/quodeq` -- the
# coverage test below fails if a phase constant loses its producer here.
_PRODUCERS = {
    "quodeq.analysis._pipeline": (
        "CC_PHASE_SETUP", "CC_PHASE_ANALYZING", "CC_PHASE_SCORING",
    ),
    "quodeq.analysis._pipeline_setup": ("CC_PHASE_ANALYZING_START",),
    "quodeq.analysis._loop_steps": ("CC_PHASE_ANALYZING",),
    "quodeq.analysis.dimension_runner": ("CC_PHASE_ANALYZING", "CC_PHASE_SCORING"),
    "quodeq.analysis.subagents._pool_launcher": ("CC_PHASE_DEADLINE_EXTENDED",),
    "quodeq._cli_lifecycle": ("CC_PHASE_REPORT_PATH",),
}


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


@pytest.mark.parametrize(("module_name", "phase_names"), sorted(_PRODUCERS.items()))
def test_marker_producers_use_the_shared_phase_constants(module_name, phase_names):
    module = importlib.import_module(module_name)

    for name in phase_names:
        assert getattr(module, name) is shared_constants[name], f"{module_name}.{name}"


def test_every_phase_constant_has_a_pinned_producer():
    produced = {name for names in _PRODUCERS.values() for name in names}

    assert produced == set(shared_constants)


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
