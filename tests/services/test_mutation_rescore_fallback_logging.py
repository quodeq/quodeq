"""Cluster 17 site 1 regression: the projection fallback's failure logging.

``rescore_with_fallback`` used to hand the background projection sweep to a
bare ``ThreadBackgroundRunner()``, which defaults to ``log=NULL_LOG``
(services/background.py). ``ThreadBackgroundRunner.submit`` only reports a
failed background task via ``self._log.debug(...)``, a no-op under
``NULL_LOG`` -- so the last-resort fallback could fail completely invisibly.
The fix wires the module's own ``_logger`` in instead. These tests exercise
the real fallback path (run_id=None -> _rescore_run short-circuits -> the
background projection sweep) and assert the failure is now observable.
"""
from __future__ import annotations

import logging
import threading
import time

from quodeq.services import mutation_rescore


def test_rescore_with_fallback_wires_module_logger_into_background_runner(monkeypatch):
    """Deterministic check of the wiring itself: production code (no
    ``runner=`` injected) must construct its ThreadBackgroundRunner with the
    module's own _logger, not the silent default.
    """
    captured = {}
    real_runner_cls = mutation_rescore.ThreadBackgroundRunner

    class _SpyRunner(real_runner_cls):
        def __init__(self, *, log=None):
            captured["log"] = log
            super().__init__(log=log)

        def submit(self, fn, *, name=""):
            # Don't actually spawn a thread for this test -- only the
            # constructor wiring is under test here.
            pass

    monkeypatch.setattr(mutation_rescore, "ThreadBackgroundRunner", _SpyRunner)

    mutation_rescore.rescore_with_fallback("evaluations", "cluster17-wiring-proj", None)

    assert captured["log"] is mutation_rescore._logger


def test_rescore_with_fallback_logs_background_projection_failure(monkeypatch, caplog, tmp_path):
    """End-to-end: a real exception inside the background projection sweep
    must now reach the log, not vanish silently.
    """
    caplog.set_level(logging.DEBUG, logger="quodeq.services.mutation_rescore")

    ran = threading.Event()

    def _boom(*_args, **_kwargs):
        try:
            raise RuntimeError("projection blew up")
        finally:
            ran.set()

    monkeypatch.setattr(mutation_rescore, "_project_all_runs", _boom)
    monkeypatch.setattr(mutation_rescore, "_resolve_project_dir", lambda *_a, **_k: tmp_path)

    # run_id=None -> _rescore_run short-circuits to None -> fallback path,
    # using the REAL (un-injected) ThreadBackgroundRunner default.
    result = mutation_rescore.rescore_with_fallback(
        str(tmp_path), "cluster17-fallback-proj", None,
    )

    assert result is None
    assert ran.wait(timeout=2), "background projection sweep never ran"

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if any("projection blew up" in r.message for r in caplog.records):
            break
        time.sleep(0.02)

    matching = [r for r in caplog.records if "projection blew up" in r.message]
    assert matching, (
        "background projection failure was not logged (fell back to "
        f"NULL_LOG?); records seen: {[r.message for r in caplog.records]}"
    )
    assert matching[0].name == "quodeq.services.mutation_rescore"
    assert "rescore-project-cluster17-fallback-proj" in matching[0].message
