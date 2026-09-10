"""Cluster 17 site 1 regression: the projection fallback's failure logging.

``rescore_with_fallback`` used to hand the background projection sweep to a
bare ``ThreadBackgroundRunner()``, which defaults to ``log=NULL_LOG``
(services/background.py). ``ThreadBackgroundRunner.submit`` only reports a
failed background task via ``self._log.debug(...)`` -- a no-op under
``NULL_LOG``, but ALSO effectively a no-op under this process's real default
runtime config: ``shared/logging.py`` sets the "quodeq" logger's effective
level to INFO by default (overridable only via ``LOG_LEVEL``), so
``.debug()`` calls don't even construct a record unless an operator has
opted into debug logging. Wiring in the module's own ``_logger`` (instead of
``NULL_LOG``) alone would only make the failure *categorically* loggable,
not *actually visible by default* -- see the module diff / cluster-17
report for why passing ``log=_logger`` into ``ThreadBackgroundRunner`` is
still kept (defense in depth for the narrow sliver of failure that could
occur outside ``_bg_project``'s own try/except, e.g. ``lock.acquire()``
itself), but is NOT what makes this failure observable in production.

The actual production-visible fix is that ``_bg_project`` now catches a
failure escaping ``_project_all_runs`` itself and logs it via
``_logger.warning(...)`` -- WARNING is above the default INFO threshold, so
this reaches stderr/the log buffer without any operator opt-in. This matches
the level ``_project_all_runs`` itself already uses for per-run projection
failures (``services/_mutation_projection.py:108``).

These tests exercise the real fallback path (run_id=None -> _rescore_run
short-circuits -> the background projection sweep, via the REAL, un-injected
``ThreadBackgroundRunner``) and assert the failure is observable WITHOUT
lowering the logger below its production default level.
"""
from __future__ import annotations

import logging
import threading
import time

from quodeq.services import mutation_rescore


def test_rescore_with_fallback_wires_module_logger_into_background_runner(monkeypatch):
    """Deterministic check of the wiring itself: production code (no
    ``runner=`` injected) must construct its ThreadBackgroundRunner with the
    module's own _logger, not the silent default. This is defense in depth
    (see module docstring) -- it does not by itself make the common failure
    path production-visible; the ``_bg_project`` warning-level catch below
    does that.
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


def test_rescore_with_fallback_logs_background_projection_failure_at_warning(
    monkeypatch, caplog, tmp_path,
):
    """End-to-end, at the production-default level: a real exception inside
    the background projection sweep must reach the log at WARNING (visible
    under the real server's default INFO threshold), not just at DEBUG.
    """
    # WARNING, not DEBUG: this is the level required to observe the fix in
    # production (shared/logging.py's default "quodeq" logger level is
    # INFO). If the fix regressed to only logging at debug again, this test
    # would go back to failing.
    caplog.set_level(logging.WARNING, logger="quodeq.services.mutation_rescore")

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
        "background projection failure was not logged at WARNING (fell "
        f"back to debug-only visibility?); records seen: "
        f"{[(r.levelname, r.message) for r in caplog.records]}"
    )
    assert matching[0].name == "quodeq.services.mutation_rescore"
    assert matching[0].levelno == logging.WARNING
    assert "cluster17-fallback-proj" in matching[0].message
