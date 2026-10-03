"""ExitReason wire values and the budget-exhausted subset."""
from quodeq.core.run.exit_reason import DEADLINE_EXIT_REASONS, ExitReason


def test_values():
    assert {m.value for m in ExitReason} == {
        "done", "time_limit", "deadline", "failure_streak", "cancelled", "error",
        "stale_detected", "stale_legacy_pid_dead", "stale_legacy_no_pid",
    }


def test_deadline_reasons():
    assert DEADLINE_EXIT_REASONS == frozenset({ExitReason.DEADLINE, ExitReason.TIME_LIMIT})
