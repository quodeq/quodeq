"""Connect job reports phase, percent, bytes and projects found."""
from __future__ import annotations

import pytest

from quodeq.core.types.sync_phase import SyncKind, SyncPhase
from quodeq.data.fs.git_progress import ProgressUpdate
from quodeq.services import shared_connect_job
from quodeq.services.shared_connect import ConnectOutcome, ConnectStatus
from quodeq.services.shared_connect_job import (
    ConnectJobStatus,
    ConnectState,
    get_connect_status,
    run_connect_job,
)
from quodeq.services.shared_repo import RepoFormat

_URL = "https://example.invalid/x.git"


@pytest.fixture()
def status():
    return ConnectJobStatus()


def test_connect_job_walks_phases_and_counts_projects(status, tmp_path, monkeypatch):
    root = tmp_path / "evaluations"
    for name in ("a", "b", "c"):
        (root / name).mkdir(parents=True)
    phases = []

    def connect(url, *, log, env=None, progress=None, **_):
        progress(ProgressUpdate(30, 500))
        phases.append(get_connect_status(status)["phase"])
        return ConnectOutcome(status=RepoFormat.OK, url=url)
    monkeypatch.setattr(shared_connect_job, "shared_evaluations_root", lambda url, env=None: root)
    status.claim(_URL)
    run_connect_job(_URL, status=status, connect=connect, env={})
    snap = get_connect_status(status)
    assert phases == [SyncPhase.DOWNLOADING]
    assert snap["state"] == ConnectState.DONE and snap["phase"] is SyncPhase.DONE
    assert snap["projects_found"] == 3 and snap["percent"] == 100 and snap["kind"] is SyncKind.CONNECT


def test_connect_job_failure_sets_error_phase(status):
    run_connect_job(
        _URL, status=status,
        connect=lambda url, **_: ConnectOutcome(status=ConnectStatus.CLONE_FAILED, url=url),
    )
    snap = get_connect_status(status)
    assert snap["state"] == ConnectState.ERROR and snap["phase"] is SyncPhase.ERROR


def test_claim_sets_connecting_phase(status):
    status.claim(_URL)
    assert get_connect_status(status)["phase"] is SyncPhase.CONNECTING
