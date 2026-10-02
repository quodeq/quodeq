"""Refresh job state machine (inline spawn, fake refresh and index sync)."""
from __future__ import annotations

import pytest

from quodeq.core.types.sync_phase import SyncKind, SyncPhase
from quodeq.data.fs.git_progress import ProgressUpdate
from quodeq.services.shared_refresh_job import (
    RefreshStartResult, RefreshState, RefreshStatus, get_refresh_status, is_refresh_running, run_refresh_job, start_refresh,
)

_URL = "https://example.invalid/t/r.git"


@pytest.fixture()
def status():
    return RefreshStatus()


def _refresh_ok(url, env=None, *, progress=None, **_):
    progress(ProgressUpdate(70, 7000))
    return True, ""


def test_refresh_done_walks_phases(status):
    synced = []
    status.claim(_URL)
    assert get_refresh_status(status)["phase"] is SyncPhase.CONNECTING
    run_refresh_job(_URL, status=status, refresh=_refresh_ok, sync_index=synced.append)
    snap = get_refresh_status(status)
    assert snap["state"] == RefreshState.DONE and snap["phase"] is SyncPhase.DONE
    assert snap["percent"] == 100 and snap["bytes"] == 7000 and snap["kind"] is SyncKind.REFRESH
    assert synced == [_URL]


def test_refresh_failure_keeps_reason_and_does_not_sync_index(status):
    synced = []
    status.claim(_URL)
    run_refresh_job(_URL, status=status, refresh=lambda *a, **k: (False, "Could not resolve host"), sync_index=synced.append)
    snap = get_refresh_status(status)
    assert snap["state"] == RefreshState.ERROR and snap["code"] == "REFRESH_FAILED"
    assert snap["error"] == "Could not resolve host" and synced == []


def test_start_refresh_inline_and_already_running(status):
    assert start_refresh(_URL, status=status, spawn=lambda fn: None) is RefreshStartResult.STARTED
    assert is_refresh_running(status)
    assert start_refresh(_URL, status=status, spawn=lambda fn: None) is RefreshStartResult.ALREADY_RUNNING


def test_unexpected_exception_is_captured(status):
    def boom(*a, **k):
        raise RuntimeError("x")
    status.claim(_URL)
    run_refresh_job(_URL, status=status, refresh=boom, sync_index=lambda u: None)
    assert get_refresh_status(status)["state"] == RefreshState.ERROR


def test_start_refresh_spawn_failure_is_failed_not_running(status):
    def no_thread(fn):
        raise RuntimeError("no thread")

    class _Log:
        def error(self, message):
            pass

    assert start_refresh(_URL, status=status, spawn=no_thread, log=_Log()) is RefreshStartResult.FAILED
    assert get_refresh_status(status)["state"] == RefreshState.ERROR
