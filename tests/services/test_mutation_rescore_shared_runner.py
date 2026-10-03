"""rescore_with_fallback shares one bounded runner and skips busy projects."""
from __future__ import annotations

from quodeq.services import mutation_rescore
from quodeq.services.background import ThreadBackgroundRunner


class _SpyRunner:
    """BackgroundRunner that records task names instead of running them."""

    def __init__(self):
        self.names: list[str] = []

    def submit(self, fn, *, name=""):
        self.names.append(name)
        return True


def test_default_path_submits_to_the_one_shared_runner(monkeypatch, tmp_path):
    spy = _SpyRunner()
    monkeypatch.setattr(mutation_rescore, "_SHARED_RUNNER", spy)

    # run_id=None: rescore_run short-circuits to None, so the fallback runs.
    mutation_rescore.rescore_with_fallback(str(tmp_path), "shared-a", None)
    mutation_rescore.rescore_with_fallback(str(tmp_path), "shared-b", None)

    assert spy.names == ["rescore-project-shared-a", "rescore-project-shared-b"]


def test_shared_runner_is_bounded_and_logs_through_the_module_sink():
    runner = mutation_rescore._SHARED_RUNNER
    assert isinstance(runner, ThreadBackgroundRunner)
    assert runner._log is mutation_rescore._log_sink


def test_no_submit_while_the_projects_projection_lock_is_held(tmp_path):
    spy = _SpyRunner()
    lock = mutation_rescore.get_projection_lock("held-proj")
    assert lock.acquire(blocking=False)
    try:
        result = mutation_rescore.rescore_with_fallback(
            str(tmp_path), "held-proj", None, runner=spy,
        )
    finally:
        lock.release()

    assert result is None
    assert spy.names == []
