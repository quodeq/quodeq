"""Shared test doubles for tests/services/test_evaluation_mixin_register*.py.

Split out of test_evaluation_mixin_register.py.
"""
from __future__ import annotations


class _FakeDispatcher:
    """Records dispatch calls without spawning a subprocess."""

    def __init__(self):
        self.calls = []

    def dispatch(self, cmd, *, cwd=None, env=None, ai_provider=None, ai_model=None, time_limit_s=None):
        self.calls.append(cmd)
        return {"id": "fake-job"}


def _make_mixin():
    from quodeq.services.evaluation_mixin import FsEvaluationMixin

    mixin = FsEvaluationMixin()
    mixin._jobs = object()  # no set_reports_root attr -> guard skips it
    mixin._dispatcher = _FakeDispatcher()
    return mixin
