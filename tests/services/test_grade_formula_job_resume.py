"""GradeFormulaRescorer: durable pending marker, resume, progress reset, start failure."""
from __future__ import annotations

import threading
from pathlib import Path

from quodeq.services import grade_formula
from quodeq.services.grade_formula_job import WORKER_THREAD_NAME, RescoreState
from tests._timeouts import budget
from tests.services._grade_formula_fixtures import formula_path  # noqa: F401 -- pytest fixture
from tests.services._rescorer_fixtures import GatedApply, RecordingSink, make_rescorer  # noqa: F401 -- make_rescorer is a fixture

_ROOT = Path("reports-root")


def _marker() -> Path:
    return grade_formula.rescore_marker_path()


def test_request_writes_the_pending_marker_before_the_pass_runs(make_rescorer, formula_path):
    apply = GatedApply(gated_passes=(0,))
    rescorer = make_rescorer(apply)
    rescorer.request(_ROOT)
    assert apply.started[0].wait(budget(5))

    assert _marker().is_file()
    assert _marker().parent == formula_path.parent


def test_a_completed_pass_removes_the_marker(make_rescorer, formula_path):
    rescorer = make_rescorer(GatedApply())
    rescorer.request(_ROOT)

    assert rescorer.wait_idle(budget(5))
    assert not _marker().exists()


def test_a_superseded_pass_keeps_the_marker_until_the_restart_completes(make_rescorer, formula_path):
    apply = GatedApply(gated_passes=(0, 1))
    rescorer = make_rescorer(apply)
    rescorer.request(_ROOT)
    assert apply.started[0].wait(budget(5))
    rescorer.request(_ROOT)
    apply.release[0].set()
    assert apply.started[1].wait(budget(5))
    during_restart = _marker().is_file()
    apply.release[1].set()

    assert rescorer.wait_idle(budget(5))
    assert during_restart
    assert not _marker().exists()


def test_a_pass_cut_short_by_stop_keeps_the_marker(make_rescorer, formula_path):
    apply = GatedApply(gated_passes=(0,))
    rescorer = make_rescorer(apply)
    rescorer.request(_ROOT)
    assert apply.started[0].wait(budget(5))
    stopper = threading.Thread(target=rescorer.stop, daemon=True)
    stopper.start()
    apply.release_all()
    stopper.join(budget(5))

    assert not stopper.is_alive()
    assert _marker().is_file()


def test_a_pass_that_raises_keeps_the_marker(make_rescorer, formula_path):
    def boom(root, *, progress, should_abort):
        raise RuntimeError("unreadable project dir")

    rescorer = make_rescorer(boom)
    rescorer.request(_ROOT)

    assert rescorer.wait_idle(budget(5))
    assert rescorer.snapshot().state is RescoreState.ERROR
    assert _marker().is_file()


def test_resume_with_a_marker_runs_one_pass_and_clears_it(make_rescorer, formula_path):
    apply = GatedApply()
    grade_formula.mark_rescore_pending()
    rescorer = make_rescorer(apply)

    resumed = rescorer.resume_pending(_ROOT)

    assert resumed is not None
    assert resumed.state is RescoreState.RUNNING
    assert rescorer.wait_idle(budget(5))
    assert apply.roots == [_ROOT]
    assert not _marker().exists()


def test_resume_without_a_marker_starts_no_thread(make_rescorer, formula_path):
    before = set(threading.enumerate())
    apply = GatedApply()
    rescorer = make_rescorer(apply)

    assert rescorer.resume_pending(_ROOT) is None
    assert rescorer.snapshot().generation == 0
    assert [t for t in threading.enumerate() if t.name == WORKER_THREAD_NAME and t not in before] == []


def test_a_fresh_request_does_not_report_the_previous_pass_progress(make_rescorer, formula_path):
    apply = GatedApply(gated_passes=(1,))
    rescorer = make_rescorer(apply)
    rescorer.request(_ROOT)
    assert rescorer.wait_idle(budget(5))
    finished = rescorer.snapshot()

    second = rescorer.request(_ROOT)

    assert (finished.done, finished.total) == (2, 2)
    assert (second.state, second.done, second.total) == (RescoreState.RUNNING, 0, 0)


def test_a_worker_that_cannot_start_sets_error_and_warns(make_rescorer, formula_path, monkeypatch):
    sink = RecordingSink()
    rescorer = make_rescorer(GatedApply(), log=sink)

    def refuse(self):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading.Thread, "start", refuse)
    snap = rescorer.request(_ROOT)
    monkeypatch.undo()

    assert snap.state is RescoreState.ERROR
    assert rescorer.snapshot().state is RescoreState.ERROR
    assert any("can't start new thread" in w for w in sink.warnings)
