"""Tests for the process-wide cancellation signal.

One evaluation runs per Python process. The cancellation module exposes a
module-level threading.Event so the SIGTERM/SIGINT handler in
run_lifecycle can notify worker threads deep in the analysis pipeline
without threading a cancel token through every call site.

Each test below constructs its own ``CancellationToken`` — no shared state,
no reset fixture needed. One facade test at the bottom pins that the
module-level functions delegate to the default token.
"""
from __future__ import annotations

import threading


def test_starts_not_cancelled() -> None:
    from quodeq.shared.cancellation import CancellationToken

    token = CancellationToken()
    assert token.is_cancelled() is False


def test_request_cancel_marks_cancelled() -> None:
    from quodeq.shared.cancellation import CancellationToken

    token = CancellationToken()
    token.request_cancel()
    assert token.is_cancelled() is True


def test_reset_clears_cancelled() -> None:
    from quodeq.shared.cancellation import CancellationToken

    token = CancellationToken()
    token.request_cancel()
    token.reset()
    assert token.is_cancelled() is False


def test_event_is_shared_threading_event() -> None:
    """Workers need an Event so they can block-wait with a timeout."""
    from quodeq.shared.cancellation import CancellationToken

    token = CancellationToken()
    event = token.get_event()
    assert isinstance(event, threading.Event)
    assert event.is_set() is False
    token.request_cancel()
    assert event.is_set() is True


def test_event_is_stable_across_calls() -> None:
    """Callers that cache the event must see the same instance across cancels/resets."""
    from quodeq.shared.cancellation import CancellationToken

    token = CancellationToken()
    event_before = token.get_event()
    token.request_cancel()
    token.reset()
    event_after = token.get_event()
    assert event_before is event_after


def test_first_reason_wins() -> None:
    """The first non-None reason recorded is the one cancel_reason() reports."""
    from quodeq.shared.cancellation import CancellationToken

    token = CancellationToken()
    token.request_cancel("first")
    token.request_cancel("second")
    assert token.cancel_reason() == "first"


def test_reset_clears_reason() -> None:
    from quodeq.shared.cancellation import CancellationToken

    token = CancellationToken()
    token.request_cancel("why")
    token.reset()
    assert token.cancel_reason() is None


def test_module_facade_delegates_to_default_token(monkeypatch) -> None:
    """The module-level functions are a thin facade over a default token."""
    from quodeq.shared import cancellation
    from quodeq.shared.cancellation import CancellationToken

    monkeypatch.setattr(cancellation, "_DEFAULT", CancellationToken())

    assert cancellation.is_cancelled() is False
    cancellation.request_cancel("reason")
    assert cancellation.is_cancelled() is True
    assert cancellation.cancel_reason() == "reason"
    event = cancellation.get_event()
    assert isinstance(event, threading.Event)
    assert event.is_set() is True
    cancellation.reset()
    assert cancellation.is_cancelled() is False
    assert cancellation.cancel_reason() is None
