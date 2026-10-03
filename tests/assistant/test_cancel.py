"""CancelToken / TurnCancelled: the stop-turn signalling primitives."""
import logging

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
    """register_kill's immediate-call path runs the hook inside the same
    fault-isolation boundary cancel()'s loop uses (R-FT-7): a realistic
    production failure (an httpx client's close(), a subprocess kill) must
    not raise past register_kill."""
    token = CancelToken()
    token.cancel()

    def boom():
        raise OSError("client close failed")

    token.register_kill(boom)  # must not raise past this point


def test_hook_exception_does_not_block_other_hooks():
    """Each kill hook runs inside its own fault-isolation boundary
    (R-FT-7): a failing hook must not stop later hooks from running."""
    token = CancelToken()
    hits = []

    def boom():
        raise OSError("kill failed")

    token.register_kill(boom)
    token.register_kill(lambda: hits.append("second"))
    token.cancel()
    assert token.cancelled is True
    assert hits == ["second"]


def test_hook_exception_is_logged_and_the_next_hook_still_runs(caplog):
    """A kill hook is a third-party/adapter callback, so cancel()'s
    fault-isolation boundary covers ANY exception from it (not just
    OSError/httpx.HTTPError): it must be logged with its traceback, and the
    next hook in the same cancel() call must still run."""
    token = CancelToken()
    hits = []

    def boom():
        raise AttributeError("'NoneType' object has no attribute 'close'")

    token.register_kill(boom)
    token.register_kill(lambda: hits.append("second"))

    with caplog.at_level(logging.WARNING, logger="quodeq.assistant.cancel"):
        token.cancel()

    assert token.cancelled is True
    assert hits == ["second"]
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert warnings[0].exc_info is not None


def test_late_cancel_hook_exception_is_logged_not_raised(caplog):
    """The late-cancel path in register_kill (token already cancelled) gets
    the same fault-isolation boundary as cancel()'s loop: an AttributeError
    from the hook is logged with its traceback, not raised to the caller."""
    token = CancelToken()
    token.cancel()

    def boom():
        raise AttributeError("'NoneType' object has no attribute 'close'")

    with caplog.at_level(logging.WARNING, logger="quodeq.assistant.cancel"):
        token.register_kill(boom)  # must not raise past this point

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert warnings[0].exc_info is not None


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
