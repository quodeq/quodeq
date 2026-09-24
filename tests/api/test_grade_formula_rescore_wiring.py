"""create_app wires one GradeFormulaRescorer into the grade-formula routes."""
from __future__ import annotations

import dataclasses
import threading

import pytest

from quodeq.api.app import create_app
from quodeq.core.scoring.params import DEFAULT_PARAMS, params_to_dict
from quodeq.services import grade_formula
from quodeq.services.grade_formula_job import WORKER_THREAD_NAME, GradeFormulaRescorer
from tests._timeouts import budget
from tests.api.test_action_api import StubProvider

_ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)


@pytest.fixture
def app():
    """create_app with its rescorer stopped on teardown."""
    application = create_app(StubProvider())
    yield application
    application.extensions["grade_formula_rescore"].stop()


def test_create_app_registers_an_idle_rescorer_without_starting_a_thread(app):
    rescorer = app.extensions["grade_formula_rescore"]
    assert isinstance(rescorer, GradeFormulaRescorer)
    assert rescorer.snapshot().generation == 0
    assert not [t for t in threading.enumerate() if t.name == WORKER_THREAD_NAME]


def test_put_through_create_app_runs_on_the_app_rescorer(app, monkeypatch):
    monkeypatch.setattr(
        grade_formula, "apply_to_all_runs",
        lambda root, *, progress, should_abort: grade_formula.ApplyResult(rescored=0, failed=[]),
    )
    rescorer = app.extensions["grade_formula_rescore"]
    payload = params_to_dict(dataclasses.replace(DEFAULT_PARAMS, base_k=0.3))

    resp = app.test_client().put("/api/grade-formula", json=payload, headers=_ORIGIN)

    assert resp.status_code == 202
    assert rescorer.wait_idle(budget(5))
    assert rescorer.snapshot().applied_generation == 1


def test_create_app_resumes_a_pass_left_pending_by_the_last_process(monkeypatch):
    roots = []

    def apply(root, *, progress, should_abort):
        roots.append(root)
        return grade_formula.ApplyResult(rescored=0, failed=[])

    monkeypatch.setattr(grade_formula, "apply_to_all_runs", apply)
    grade_formula.mark_rescore_pending()
    application = create_app(StubProvider())
    rescorer = application.extensions["grade_formula_rescore"]
    try:
        assert rescorer.wait_idle(budget(5))
        snap = rescorer.snapshot()
    finally:
        rescorer.stop()

    assert (snap.generation, snap.applied_generation) == (1, 1)
    assert len(roots) == 1
    assert not grade_formula.rescore_pending()
