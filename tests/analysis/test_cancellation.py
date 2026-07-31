"""Tests for the process-wide cancellation signal.

One evaluation runs per Python process. The cancellation module exposes a
module-level threading.Event so the SIGTERM/SIGINT handler in
run_lifecycle can notify worker threads deep in the analysis pipeline
without threading a cancel token through every call site.
"""
from __future__ import annotations

import threading

import pytest


@pytest.fixture(autouse=True)
def _reset_cancellation():
    from quodeq.shared import cancellation

    cancellation.reset()
    yield
    cancellation.reset()


def test_starts_not_cancelled() -> None:
    from quodeq.shared import cancellation

    assert cancellation.is_cancelled() is False


def test_request_cancel_marks_cancelled() -> None:
    from quodeq.shared import cancellation

    cancellation.request_cancel()
    assert cancellation.is_cancelled() is True


def test_reset_clears_cancelled() -> None:
    from quodeq.shared import cancellation

    cancellation.request_cancel()
    cancellation.reset()
    assert cancellation.is_cancelled() is False


def test_event_is_shared_threading_event() -> None:
    """Workers need an Event so they can block-wait with a timeout."""
    from quodeq.shared import cancellation

    event = cancellation.get_event()
    assert isinstance(event, threading.Event)
    assert event.is_set() is False
    cancellation.request_cancel()
    assert event.is_set() is True


def test_event_is_stable_across_calls() -> None:
    """Callers that cache the event must see the same instance across cancels/resets."""
    from quodeq.shared import cancellation

    event_before = cancellation.get_event()
    cancellation.request_cancel()
    cancellation.reset()
    event_after = cancellation.get_event()
    assert event_before is event_after
