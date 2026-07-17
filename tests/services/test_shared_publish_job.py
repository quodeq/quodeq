"""Publish job state machine (synchronous worker invocation, no sleeps)."""
from unittest.mock import patch

import pytest

from quodeq.services import shared_publish
from quodeq.services.shared_publish import (
    PublishError,
    get_publish_status,
    start_publish,
)


@pytest.fixture(autouse=True)
def _clean_status():
    """Snapshot and restore _STATUS dict before/after each test."""
    with shared_publish._STATUS_LOCK:
        snapshot = dict(shared_publish._STATUS)
    yield
    with shared_publish._STATUS_LOCK:
        shared_publish._STATUS.clear()
        shared_publish._STATUS.update(snapshot)


def _run_inline(monkeypatch):
    """Make the thread run synchronously for deterministic tests."""
    class InlineThread:
        def __init__(self, target=None, args=(), daemon=None):
            self._target, self._args = target, args

        def start(self):
            self._target(*self._args)

    monkeypatch.setattr(shared_publish.threading, "Thread", InlineThread)


def test_publish_job_success(tmp_path, monkeypatch):
    _run_inline(monkeypatch)
    with patch.object(shared_publish, "publish_project", return_value=3) as pub:
        assert start_publish("p1", "u", evaluations_root=tmp_path) is True
    status = get_publish_status()
    assert status["state"] == "done"
    assert status["runs"] == 3
    pub.assert_called_once()


def test_publish_job_error_captured(tmp_path, monkeypatch):
    _run_inline(monkeypatch)
    with patch.object(shared_publish, "publish_project", side_effect=PublishError("boom")):
        start_publish("p1", "u", evaluations_root=tmp_path)
    status = get_publish_status()
    assert status["state"] == "error"
    assert status["error"] == "boom"


def test_publish_rejected_while_running(tmp_path):
    with shared_publish._STATUS_LOCK:
        shared_publish._STATUS.update({"state": "running", "project": "p0"})
    assert start_publish("p1", "u", evaluations_root=tmp_path) is False


def test_publish_thread_start_failure(tmp_path, monkeypatch):
    """Thread creation failure leaves state as error, not stuck at running."""

    class FailingThread:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("thread creation failed")

        def start(self):
            pass

    monkeypatch.setattr(shared_publish.threading, "Thread", FailingThread)

    result = start_publish("p1", "u", evaluations_root=tmp_path)

    assert result is False
    status = get_publish_status()
    assert status["state"] == "error"
    assert "thread creation failed" in status["error"]
