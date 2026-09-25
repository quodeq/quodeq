"""_prepare_frozen_macos_launch's except narrowing (R-FT-7).

Guards `from quodeq.update import first_launch, selfupdate` plus
`selfupdate.cleanup_stale_staging()` and `first_launch.offer_move_to_applications()`.
Both callees are already fail-soft internally (cleanup_stale_staging has its
own whole-body `except Exception`; offer_move_to_applications is narrowed to
`(OSError, UnicodeDecodeError)` and never raises those), so the only
realistic source left here is the import statement itself.
"""
from __future__ import annotations

import logging
import sys
from unittest.mock import patch

import pytest

from quodeq.dashboard import runner
from quodeq.shared.constants import PLATFORM_DARWIN


def _frozen_darwin():
    return patch.object(sys, "frozen", True, create=True), patch.object(sys, "platform", PLATFORM_DARWIN)


def test_import_error_is_swallowed(monkeypatch, caplog):
    import quodeq.update as update_pkg

    frozen, darwin = _frozen_darwin()
    monkeypatch.delattr(update_pkg, "selfupdate", raising=False)
    monkeypatch.setitem(sys.modules, "quodeq.update.selfupdate", None)
    with frozen, darwin, caplog.at_level(logging.DEBUG, logger="quodeq.dashboard.runner"):
        result = runner._prepare_frozen_macos_launch()
    assert result is False
    assert "frozen macOS app preparation failed" in caplog.text


def test_out_of_scope_error_propagates(monkeypatch):
    """R-FT-7 — an error outside (ImportError,) (e.g. a programming bug in
    cleanup_stale_staging or offer_move_to_applications) must now propagate
    instead of being swallowed."""
    frozen, darwin = _frozen_darwin()

    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr("quodeq.update.selfupdate.cleanup_stale_staging", _boom)
    with frozen, darwin, pytest.raises(RuntimeError, match="boom"):
        runner._prepare_frozen_macos_launch()


def test_not_frozen_or_not_macos_is_a_noop():
    with patch.object(sys, "frozen", False, create=True):
        assert runner._prepare_frozen_macos_launch() is False
