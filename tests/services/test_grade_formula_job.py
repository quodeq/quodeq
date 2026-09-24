"""GradeFormulaRescorer: grade-formula rescore off the request path."""
from __future__ import annotations

import dataclasses
import threading
from pathlib import Path

import pytest

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services import grade_formula
from quodeq.services.grade_formula_job import (
    WORKER_THREAD_NAME,
    GradeFormulaRescorer,
    RescoreState,
)
from tests._timeouts import budget
from tests.services._grade_formula_fixtures import formula_path  # noqa: F401 -- pytest fixture

_ROOT = Path("reports-root")


class _Sink:
    """LogSink that records warnings and infos."""

    def __init__(self):
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def warning(self, message):
        self.warnings.append(message)

    def info(self, message):
        self.infos.append(message)

    def debug(self, message):
        pass

    def error(self, message):
        pass

    def success(self, message):
        pass


class _GatedApply:
    """Fake apply_to_all_runs. Pass N blocks until released when N is gated."""

    def __init__(self, gated_passes=(), failed=()):
        self.params_seen: list[float] = []
        self.roots: list[Path] = []
        self.started = {n: threading.Event() for n in gated_passes}
        self.release = {n: threading.Event() for n in gated_passes}
        self.failed = list(failed)
        self.threads: list[threading.Thread] = []

    def __call__(self, root, *, progress, should_abort):
        n = len(self.params_seen)
        self.params_seen.append(grade_formula.load_params().base_k)
        self.roots.append(root)
        self.threads.append(threading.current_thread())
        progress(0, 2)
        if n in self.started:
            self.started[n].set()
            self.release[n].wait(budget(5))
        if should_abort():
            return grade_formula.ApplyResult(rescored=0, failed=[], aborted=True)
        progress(2, 2)
        return grade_formula.ApplyResult(rescored=2, failed=list(self.failed))

    def release_all(self):
        for event in self.release.values():
            event.set()


@pytest.fixture
def make_rescorer():
    """Build rescorers; teardown releases every gate and stops every worker."""
    made: list[tuple[GradeFormulaRescorer, object]] = []

    def _make(apply_fn, log=None):
        rescorer = GradeFormulaRescorer(apply_fn, log=log or _Sink())
        made.append((rescorer, apply_fn))
        return rescorer

    yield _make
    for rescorer, apply_fn in made:
        if isinstance(apply_fn, _GatedApply):
            apply_fn.release_all()
        rescorer.stop()


def _save(base_k: float) -> None:
    grade_formula.save_params(dataclasses.replace(DEFAULT_PARAMS, base_k=base_k))


def _new_workers(before: set[threading.Thread]) -> list[threading.Thread]:
    """Worker threads started since *before*, so a worker leaked elsewhere does not count."""
    return [t for t in threading.enumerate() if t.name == WORKER_THREAD_NAME and t not in before]


def test_no_worker_thread_until_the_first_request(make_rescorer):
    before = set(threading.enumerate())
    rescorer = make_rescorer(_GatedApply())

    assert rescorer.snapshot().to_payload() == {
        "state": "idle", "generation": 0, "appliedGeneration": 0,
        "done": 0, "total": 0, "failed": 0,
    }
    assert _new_workers(before) == []


def test_request_mid_pass_restarts_with_the_latest_params(make_rescorer, formula_path):
    apply = _GatedApply(gated_passes=(0,))
    rescorer = make_rescorer(apply)
    before = set(threading.enumerate())
    _save(0.2)
    first = rescorer.request(_ROOT)
    assert apply.started[0].wait(budget(5))
    _save(0.3)
    second = rescorer.request(_ROOT)
    workers_mid_pass = len(_new_workers(before))
    apply.release_all()

    assert rescorer.wait_idle(budget(5))
    snap = rescorer.snapshot()
    assert (first.state, first.generation, second.generation) == (RescoreState.RUNNING, 1, 2)
    assert apply.params_seen == [0.2, 0.3]
    assert (snap.state, snap.applied_generation, snap.done, snap.total) == (RescoreState.IDLE, 2, 2, 2)
    assert workers_mid_pass == 1


def test_many_requests_mid_pass_collapse_into_one_restart(make_rescorer, formula_path):
    apply = _GatedApply(gated_passes=(0,))
    rescorer = make_rescorer(apply)
    rescorer.request(_ROOT)
    assert apply.started[0].wait(budget(5))
    for base_k in (0.3, 0.4, 0.5):
        _save(base_k)
        rescorer.request(_ROOT)
    apply.release_all()

    assert rescorer.wait_idle(budget(5))
    assert len(apply.params_seen) == 2
    assert apply.params_seen[-1] == 0.5
    assert rescorer.snapshot().applied_generation == 4


def test_a_request_after_the_last_run_is_not_counted_as_applied(make_rescorer, formula_path):
    holder: list = []
    seen_in_second_pass = []
    passes: list[int] = []

    def apply(root, *, progress, should_abort):
        passes.append(len(passes))
        if len(passes) == 2:
            seen_in_second_pass.append(holder[0].snapshot())
        if should_abort():
            return grade_formula.ApplyResult(rescored=0, failed=[], aborted=True)
        progress(1, 1)
        if len(passes) == 1:
            holder[0].request(root)  # lands after the last abort check, before the result is recorded
        return grade_formula.ApplyResult(rescored=1, failed=[])

    rescorer = make_rescorer(apply)
    holder.append(rescorer)
    rescorer.request(_ROOT)

    assert rescorer.wait_idle(budget(5))
    assert passes == [0, 1]
    assert seen_in_second_pass[0].applied_generation == 1
    assert rescorer.snapshot().applied_generation == 2


def test_a_pass_that_raises_sets_error_and_the_next_request_recovers(make_rescorer, formula_path):
    calls: list[Path] = []

    def flaky(root, *, progress, should_abort):
        calls.append(root)
        if len(calls) == 1:
            raise RuntimeError("reports dir vanished")
        return grade_formula.ApplyResult(rescored=1, failed=[])

    sink = _Sink()
    rescorer = make_rescorer(flaky, log=sink)
    rescorer.request(_ROOT)
    assert rescorer.wait_idle(budget(5))
    errored = rescorer.snapshot()
    rescorer.request(_ROOT)
    assert rescorer.wait_idle(budget(5))
    recovered = rescorer.snapshot()

    assert (errored.state, errored.applied_generation) == (RescoreState.ERROR, 0)
    assert any("reports dir vanished" in w and "Traceback" in w for w in sink.warnings)
    assert (recovered.state, recovered.applied_generation) == (RescoreState.IDLE, 2)


def test_per_run_failures_land_in_failed(make_rescorer, formula_path):
    rescorer = make_rescorer(_GatedApply(failed=["run-bad"]))
    rescorer.request(_ROOT)

    assert rescorer.wait_idle(budget(5))
    snap = rescorer.snapshot()
    assert snap.failed == ("run-bad",)
    assert snap.to_payload()["failed"] == 1


def test_request_passes_the_reports_root_through(make_rescorer, formula_path):
    apply = _GatedApply()
    rescorer = make_rescorer(apply)
    rescorer.request(Path("somewhere"))

    assert rescorer.wait_idle(budget(5))
    assert apply.roots == [Path("somewhere")]


def test_stop_joins_the_worker(make_rescorer, formula_path):
    apply = _GatedApply()
    rescorer = make_rescorer(apply)
    rescorer.request(_ROOT)
    assert rescorer.wait_idle(budget(5))
    (worker,) = apply.threads

    rescorer.stop()
    assert worker.name == WORKER_THREAD_NAME
    assert not worker.is_alive()
