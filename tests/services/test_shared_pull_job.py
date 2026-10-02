"""Pull job state machine (inline spawn, fake pull)."""
from __future__ import annotations

import pytest

from quodeq.core.types.sync_phase import SyncKind, SyncPhase
from quodeq.services.shared_pull_job import (
    PullOutcome, PullStartResult, PullState, PullStatus, get_pull_status, run_pull_job, start_pull,
)


@pytest.fixture()
def status():
    return PullStatus()


def test_pull_done_reports_ids_and_calls_on_done(status):
    done = []
    status.claim("abc")
    run_pull_job("abc", status=status, pull=lambda p: PullOutcome(True, "new-id", "Billing", False), on_done=lambda: done.append(1))
    snap = get_pull_status(status)
    assert snap["state"] == PullState.DONE and snap["phase"] is SyncPhase.DONE
    assert (snap["project"], snap["project_id"], snap["project_name"], snap["renamed"]) == ("abc", "new-id", "Billing", False)
    assert snap["kind"] is SyncKind.PULL and done == [1]


def test_pull_conflict_is_error_with_code_and_no_on_done(status):
    done = []
    status.claim("abc")
    run_pull_job("abc", status=status, pull=lambda p: PullOutcome(False, code="PROJECT_EXISTS", error="already exists"), on_done=lambda: done.append(1))
    snap = get_pull_status(status)
    assert snap["state"] == PullState.ERROR and snap["code"] == "PROJECT_EXISTS" and done == []


def test_start_pull_inline_and_already_running(status):
    assert start_pull("abc", pull=lambda p: PullOutcome(True, "x", "X"), status=status, spawn=lambda fn: None) is PullStartResult.STARTED
    assert start_pull("def", pull=lambda p: PullOutcome(True, "y", "Y"), status=status, spawn=lambda fn: None) is PullStartResult.ALREADY_RUNNING


def test_pull_phase_is_downloading_while_running(status):
    seen = []

    def pull(p):
        seen.append(get_pull_status(status)["phase"])
        return PullOutcome(True, "x", "X")
    status.claim("abc")
    run_pull_job("abc", status=status, pull=pull)
    assert seen == [SyncPhase.DOWNLOADING]
