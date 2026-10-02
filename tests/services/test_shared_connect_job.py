"""Connect job state machine (inline spawn, no threads, no sleeps)."""
from __future__ import annotations

import pytest

from quodeq.services import shared_connect_job
from quodeq.services.shared_connect import ConnectOutcome, ConnectStatus
from quodeq.services.shared_connect_job import (
    ConnectJobStatus,
    ConnectStartResult,
    get_connect_status,
    is_connect_running,
    run_connect_job,
    start_connect,
)
from quodeq.services.shared_repo import RepoFormat

_URL = "https://example.invalid/x.git"


@pytest.fixture()
def status():
    return ConnectJobStatus()


def _inline(fn):
    fn()


def _outcome(kind, detail=""):
    return lambda url, **_kwargs: ConnectOutcome(status=kind, url=url, detail=detail)


def test_connect_job_done(status):
    run_connect_job(_URL, status=status, connect=_outcome(RepoFormat.OK))
    result = get_connect_status(status)
    assert result["state"] == "done"
    assert result["code"] is None
    assert result["error"] is None
    assert result["finished_at"] is not None


@pytest.mark.parametrize(
    ("kind", "code", "error"),
    [
        (
            ConnectStatus.CLONE_FAILED,
            "CLONE_FAILED",
            f"could not clone the repository, check that git can access {_URL}",
        ),
        (
            RepoFormat.FOREIGN,
            "FOREIGN_REPO",
            "the repository exists but does not look like a quodeq results repository",
        ),
        (
            RepoFormat.UNSUPPORTED_VERSION,
            "UNSUPPORTED_VERSION",
            "this shared repository requires a newer version of quodeq",
        ),
        (ConnectStatus.INVALID_URL, "INVALID_URL", "bad url"),
    ],
)
def test_connect_job_error_codes(status, kind, code, error):
    run_connect_job(_URL, status=status, connect=_outcome(kind, detail="bad url"))
    result = get_connect_status(status)
    assert (result["state"], result["code"], result["error"]) == ("error", code, error)
    assert result["finished_at"] is not None


class _RecordingLog:
    def __init__(self):
        self.messages = []

    def warning(self, message):
        self.messages.append(message)

    error = warning


def test_connect_job_unexpected_error_is_connect_failed(status):
    def _boom(url, **_kwargs):
        raise RuntimeError("bug")

    log = _RecordingLog()
    run_connect_job(_URL, status=status, connect=_boom, log=log)
    result = get_connect_status(status)
    assert result["state"] == "error"
    assert result["code"] == "CONNECT_FAILED"
    assert result["error"] == "An unexpected error occurred while connecting."
    assert any("connect failed" in m for m in log.messages)


def test_start_connect_runs_job(status, monkeypatch):
    monkeypatch.setattr(shared_connect_job, "connect_shared_repo", _outcome(RepoFormat.OK))
    assert start_connect(_URL, status=status, spawn=_inline) == ConnectStartResult.STARTED
    result = get_connect_status(status)
    assert result["state"] == "done"
    assert result["url"] == _URL


def test_start_connect_rejected_while_running(status):
    assert status.claim("https://example.invalid/first.git")
    assert is_connect_running(status)
    assert start_connect(_URL, status=status, spawn=_inline) == ConnectStartResult.ALREADY_RUNNING
    assert get_connect_status(status)["url"] == "https://example.invalid/first.git"


def test_start_connect_spawn_failure(status):
    def _failing_spawn(_fn):
        raise RuntimeError("thread creation failed")

    log = _RecordingLog()
    assert start_connect(_URL, status=status, spawn=_failing_spawn, log=log) == ConnectStartResult.FAILED
    assert log.messages == ["failed to start connect thread, thread creation failed"]
    result = get_connect_status(status)
    assert result["state"] == "error"
    assert result["code"] == "CONNECT_FAILED"
    assert not is_connect_running(status)


def test_claim_resets_previous_error(status):
    status.set(state="error", code="CLONE_FAILED", error="old", finished_at=1.0)
    assert status.claim(_URL)
    result = status.copy()
    assert (result["state"], result["code"], result["error"], result["finished_at"]) == (
        "running", None, None, None,
    )


def test_default_status_used_when_omitted(monkeypatch):
    monkeypatch.setattr(shared_connect_job, "_default_status", ConnectJobStatus())
    assert get_connect_status()["state"] == "idle"
    shared_connect_job._default_status.set(state="running")
    assert is_connect_running()
    assert start_connect(_URL, spawn=_inline) == ConnectStartResult.ALREADY_RUNNING


def test_run_connect_job_forwards_env_to_connect(status):
    seen = {}

    def connect(url, **kw):
        seen.update(kw)
        return ConnectOutcome(status=RepoFormat.OK, url=url)
    run_connect_job(_URL, status=status, connect=connect, env={"GIT_CONFIG_COUNT": "1"})
    assert seen["env"] == {"GIT_CONFIG_COUNT": "1"}
