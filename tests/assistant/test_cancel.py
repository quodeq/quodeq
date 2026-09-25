"""CancelToken / TurnCancelled: the stop-turn signalling primitives."""
import pytest

from quodeq.assistant.cancel import CancelToken, TurnCancelled


def test_token_starts_uncancelled():
    assert CancelToken().cancelled is False


def test_cancel_sets_flag_and_runs_registered_hooks():
    token = CancelToken()
    hits = []
    token.register_kill(lambda: hits.append("kill"))
    token.cancel()
    assert token.cancelled is True
    assert hits == ["kill"]


def test_register_after_cancel_runs_hook_immediately():
    # Covers the stop-races-turn-startup window: the adapter registers its
    # kill hook after the route already cancelled the token.
    token = CancelToken()
    token.cancel()
    hits = []
    token.register_kill(lambda: hits.append("late"))
    assert hits == ["late"]


def test_register_after_cancel_swallows_a_realistic_kill_hook_failure():
    """register_kill's immediate-call except was narrowed from bare
    `Exception` to (OSError, httpx.HTTPError) (R-FT-7): the realistic surface
    of its two production hooks (an httpx client's close(), a subprocess
    kill that already never raises past OSError)."""
    token = CancelToken()
    token.cancel()

    def boom():
        raise OSError("client close failed")

    token.register_kill(boom)  # must not raise past this point


def test_hook_exception_does_not_block_other_hooks():
    """cancel()'s per-hook except was narrowed from bare `Exception` to
    (OSError, httpx.HTTPError) (R-FT-7), the same realistic surface as
    register_kill's own narrowed except: a failing hook of that shape must
    not stop later hooks from running."""
    token = CancelToken()
    hits = []

    def boom():
        raise OSError("kill failed")

    token.register_kill(boom)
    token.register_kill(lambda: hits.append("second"))
    token.cancel()
    assert token.cancelled is True
    assert hits == ["second"]


def test_hook_exception_outside_the_narrowed_tuple_propagates():
    """A RuntimeError from a kill hook is not OSError/httpx.HTTPError, so it
    is a real bug in the hook, not a best-effort kill failure: cancel() now
    lets it escape instead of swallowing it, at the cost of any later hooks
    in the same cancel() call not running."""
    token = CancelToken()
    hits = []

    def boom():
        raise RuntimeError("kill failed")

    token.register_kill(boom)
    token.register_kill(lambda: hits.append("second"))
    with pytest.raises(RuntimeError):
        token.cancel()
    assert token.cancelled is True  # the flag is set before hooks run
    assert hits == []  # the hook after the failing one never ran


def test_cancel_is_idempotent_and_hooks_run_once():
    token = CancelToken()
    hits = []
    token.register_kill(lambda: hits.append(1))
    token.cancel()
    token.cancel()
    assert hits == [1]


def test_wait_reflects_cancellation():
    token = CancelToken()
    assert token.wait(timeout=0.01) is False
    token.cancel()
    assert token.wait(timeout=0.01) is True


def test_turn_cancelled_carries_partial_text():
    assert TurnCancelled("partial answer").partial == "partial answer"
    assert TurnCancelled().partial == ""
