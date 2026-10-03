"""Shared GradeFormulaRescorer test doubles and the make_rescorer fixture."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from quodeq.services import grade_formula
from quodeq.services.grade_formula_job import GradeFormulaRescorer
from tests._timeouts import budget


class RecordingSink:
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


class GatedApply:
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
        rescorer = GradeFormulaRescorer(apply_fn, log=log or RecordingSink())
        made.append((rescorer, apply_fn))
        return rescorer

    yield _make
    for rescorer, apply_fn in made:
        if isinstance(apply_fn, GatedApply):
            apply_fn.release_all()
        rescorer.stop()
