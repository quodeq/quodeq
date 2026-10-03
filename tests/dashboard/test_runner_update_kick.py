import sys

import pytest

from quodeq.dashboard import runner


def test_kick_update_check_calls_check_async(monkeypatch) -> None:
    called = {"v": False}
    monkeypatch.setattr("quodeq.update.checker.check_async", lambda *a, **k: called.__setitem__("v", True))
    runner._kick_update_check()
    assert called["v"] is True


def test_kick_update_check_is_fail_silent(monkeypatch, caplog) -> None:
    import logging

    # _kick_update_check's except is narrowed to (ImportError,):
    # check_async is already fail-soft internally (its own whole-body
    # `except Exception`), so the only realistic source left is the import.
    import quodeq.update as update_pkg

    monkeypatch.delattr(update_pkg, "checker", raising=False)
    monkeypatch.setitem(sys.modules, "quodeq.update.checker", None)
    with caplog.at_level(logging.DEBUG, logger="quodeq.dashboard.runner"):
        runner._kick_update_check()  # must not raise
    # Verify that the exception was logged
    assert "async update check failed" in caplog.text


def test_kick_update_check_out_of_scope_error_propagates(monkeypatch) -> None:
    """R-FT-7 — an error outside (ImportError,) (e.g. a programming bug)
    must now propagate instead of being swallowed."""
    def boom(*a, **k):
        raise RuntimeError("nope")

    monkeypatch.setattr("quodeq.update.checker.check_async", boom)
    with pytest.raises(RuntimeError, match="nope"):
        runner._kick_update_check()
