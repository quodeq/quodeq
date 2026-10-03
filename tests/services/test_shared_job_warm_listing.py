"""Connect and refresh jobs hydrate the shared listing before reporting DONE.

The first listing of a fresh clone computes every project-card summary
inline, which can outlast the UI's request timeout; the jobs warm it under
their READING phase so the list route answers from cache once DONE lands.
"""
from __future__ import annotations

import pytest

from quodeq.core.types.sync_phase import SyncPhase
from quodeq.services import shared_connect_job, shared_refresh_job
from quodeq.services.shared_connect import ConnectOutcome
from quodeq.services.shared_connect_job import (
    ConnectJobStatus, ConnectState, get_connect_status, run_connect_job, start_connect,
)
from quodeq.services.shared_refresh_job import (
    RefreshState, RefreshStatus, RefreshSteps, get_refresh_status, run_refresh_job, start_refresh,
)
from quodeq.services.shared_repo import RepoFormat

_URL = "https://example.invalid/x.git"


class _Log:
    def __init__(self):
        self.warnings = []

    def info(self, message):
        pass

    def warning(self, message):
        self.warnings.append(message)

    def error(self, message):
        pass


@pytest.fixture()
def root(tmp_path, monkeypatch):
    root = tmp_path / "evaluations"
    for name in ("a", "b"):
        (root / name).mkdir(parents=True)
    monkeypatch.setattr(shared_connect_job, "shared_evaluations_root", lambda url, env=None: root)
    monkeypatch.setattr(shared_refresh_job, "shared_evaluations_root", lambda url, env=None: root)
    return root


def _connect_ok(url, **_):
    return ConnectOutcome(status=RepoFormat.OK, url=url)


def _refresh_ok(url, env=None, **_):
    return True, ""


def _recording_warm(read_status, calls):
    def warm(eval_root, url):
        snap = read_status()
        calls.append((eval_root, url, snap["phase"], snap["projects_found"], snap["state"]))
        return 2
    return warm


def _boom(eval_root, url):
    raise OSError("disk went away")


def test_connect_warms_listing_after_count_and_before_done(root):
    status, calls = ConnectJobStatus(), []
    status.claim(_URL)
    run_connect_job(_URL, status=status, connect=_connect_ok,
                    warm=_recording_warm(lambda: get_connect_status(status), calls))
    assert calls == [(root, _URL, SyncPhase.READING, 2, ConnectState.RUNNING)]
    snap = get_connect_status(status)
    assert snap["state"] == ConnectState.DONE and snap["projects_found"] == 2


def test_connect_warm_failure_still_reaches_done(root):
    status, log = ConnectJobStatus(), _Log()
    status.claim(_URL)
    run_connect_job(_URL, status=status, connect=_connect_ok, warm=_boom, log=log)
    snap = get_connect_status(status)
    assert snap["state"] == ConnectState.DONE and snap["phase"] is SyncPhase.DONE
    assert snap["code"] is None and len(log.warnings) == 1


def test_start_connect_threads_the_warmer_through(root, monkeypatch):
    monkeypatch.setattr(shared_connect_job, "connect_shared_repo", _connect_ok)
    status, calls = ConnectJobStatus(), []
    start_connect(_URL, status=status, spawn=lambda fn: fn(),
                  warm=_recording_warm(lambda: get_connect_status(status), calls))
    assert len(calls) == 1 and get_connect_status(status)["state"] == ConnectState.DONE


def test_refresh_warms_listing_under_reading_before_done(root):
    status, calls, synced = RefreshStatus(), [], []
    status.claim(_URL)
    warm = _recording_warm(lambda: get_refresh_status(status), calls)
    run_refresh_job(_URL, status=status, steps=RefreshSteps(refresh=_refresh_ok, sync_index=synced.append, warm=warm))
    assert synced == [_URL]
    assert calls == [(root, _URL, SyncPhase.READING, 2, RefreshState.RUNNING)]
    snap = get_refresh_status(status)
    assert snap["state"] == RefreshState.DONE and snap["projects_found"] == 2


def test_refresh_warm_failure_still_reaches_done(root):
    status, log = RefreshStatus(), _Log()
    status.claim(_URL)
    steps = RefreshSteps(refresh=_refresh_ok, sync_index=lambda u: None, warm=_boom)
    run_refresh_job(_URL, status=status, steps=steps, log=log)
    snap = get_refresh_status(status)
    assert snap["state"] == RefreshState.DONE and snap["code"] is None and len(log.warnings) == 1


def test_start_refresh_threads_the_warmer_through(root, monkeypatch):
    monkeypatch.setattr(shared_refresh_job, "refresh_shared_clone", _refresh_ok)
    monkeypatch.setattr(shared_refresh_job, "sync_shared_index", lambda url: None)
    status, calls = RefreshStatus(), []
    start_refresh(_URL, status=status, spawn=lambda fn: fn(),
                  steps=RefreshSteps(warm=_recording_warm(lambda: get_refresh_status(status), calls)))
    assert len(calls) == 1 and get_refresh_status(status)["state"] == RefreshState.DONE
