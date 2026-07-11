"""CancelToken / TurnCancelled: the stop-turn signalling primitives."""
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


def test_hook_exception_does_not_block_other_hooks():
    token = CancelToken()
    hits = []

    def boom():
        raise RuntimeError("kill failed")

    token.register_kill(boom)
    token.register_kill(lambda: hits.append("second"))
    token.cancel()
    assert token.cancelled is True
    assert hits == ["second"]


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
