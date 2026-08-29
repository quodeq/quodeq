"""Publish job state machine (synchronous worker invocation, no sleeps)."""
from unittest.mock import patch

import pytest

from quodeq.services import shared_publish
from quodeq.services.shared_publish import (
    PublishError,
    PublishStatus,
    get_publish_status,
    start_publish,
)


@pytest.fixture()
def status():
    """Isolated status instance: nothing leaks across tests or into the
    module-default (production) instance."""
    return PublishStatus()


def _run_inline(monkeypatch):
    """Make the thread run synchronously for deterministic tests."""
    class InlineThread:
        def __init__(self, target=None, args=(), daemon=None):
            self._target, self._args = target, args

        def start(self):
            self._target(*self._args)

    monkeypatch.setattr(shared_publish.threading, "Thread", InlineThread)


def test_publish_job_success(tmp_path, monkeypatch, status):
    _run_inline(monkeypatch)
    with patch.object(shared_publish, "publish_project", return_value=3) as pub:
        assert start_publish("p1", "u", evaluations_root=tmp_path, status=status) == "started"
    result = get_publish_status(status)
    assert result["state"] == "done"
    assert result["runs"] == 3
    pub.assert_called_once()


def test_publish_job_error_captured(tmp_path, monkeypatch, status):
    _run_inline(monkeypatch)
    with patch.object(shared_publish, "publish_project", side_effect=PublishError("boom")):
        start_publish("p1", "u", evaluations_root=tmp_path, status=status)
    result = get_publish_status(status)
    assert result["state"] == "error"
    assert result["error"] == "boom"


def test_publish_rejected_while_running(tmp_path, status):
    status.set(state="running", project="p0")
    assert start_publish("p1", "u", evaluations_root=tmp_path, status=status) == "already_running"


def test_publish_thread_start_failure(tmp_path, monkeypatch, status):
    """Thread creation failure leaves state as error, not stuck at running."""

    class FailingThread:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("thread creation failed")

        def start(self):
            pass

    monkeypatch.setattr(shared_publish.threading, "Thread", FailingThread)

    result = start_publish("p1", "u", evaluations_root=tmp_path, status=status)

    assert result == "failed"
    state = get_publish_status(status)
    assert state["state"] == "error"
    assert "thread creation failed" in state["error"]


def test_status_instances_are_independent():
    """Two PublishStatus instances never share the publish slot."""
    a, b = PublishStatus(), PublishStatus()
    assert a.claim("p1")
    assert b.copy()["state"] == "idle"
    assert not a.claim("p2")  # a's slot is taken
    assert b.claim("p2")      # b's is not


def test_default_status_used_when_omitted(tmp_path, monkeypatch):
    """get_publish_status()/start_publish() without an instance read and
    claim the module default (the production single publish slot)."""
    monkeypatch.setattr(shared_publish, "_default_status", PublishStatus())
    assert get_publish_status()["state"] == "idle"
    shared_publish._default_status.set(state="running", project="p0")
    assert start_publish("p1", "u", evaluations_root=tmp_path) == "already_running"
