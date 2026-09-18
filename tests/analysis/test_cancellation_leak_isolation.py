"""Regression test for #1201: the process-wide cancellation token must not
leak its cancelled state from one test into the next.

``quodeq.shared.cancellation`` backs a single module-level token shared by
every test in the process. Before #1201, clearing it around a test was
opt-in (a ``reset_cancellation``/``_reset_cancel`` fixture requested per
test module), so a test that called ``request_cancel()`` without opting in
left the token set for whichever test ran next -- the bug that produced an
intermittent "scout burst launches 6 agents where 4 expected" failure in a
file that never touched cancellation itself.

The autouse fixture in tests/conftest.py (``_reset_cancellation``) now
resets the token before and after every test unconditionally. The two
tests below rely on plain file-order execution: the second only passes
because that fixture cleaned up after the first.
"""
from __future__ import annotations

from quodeq.shared import cancellation


def test_a_request_cancel_sets_the_shared_token() -> None:
    """Sets the process-wide token directly (the way a SIGTERM handler or a
    circuit-breaker trip does), not via a fresh, private ``CancellationToken()``."""
    cancellation.request_cancel("leak probe")
    assert cancellation.is_cancelled() is True


def test_b_shared_token_is_clean_for_the_next_test() -> None:
    """Does nothing on its own. Passes only because the session-wide autouse
    fixture reset the token after the previous test (#1201); without that
    fixture this fails whenever it runs after a test that cancels."""
    assert cancellation.is_cancelled() is False
