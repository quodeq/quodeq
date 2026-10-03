"""Dashboard launch spawns the menu bar when the preference is enabled."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from quodeq.dashboard.runner import _maybe_spawn_menubar
from quodeq.menubar import control


def test_spawns_when_supported_and_enabled():
    with patch.object(control, "is_supported", return_value=True), \
         patch.object(control, "spawn") as spawn, \
         patch("quodeq.menubar.state.is_enabled", return_value=True):
        _maybe_spawn_menubar()
    spawn.assert_called_once()


def test_skips_when_disabled():
    with patch.object(control, "is_supported", return_value=True), \
         patch.object(control, "spawn") as spawn, \
         patch("quodeq.menubar.state.is_enabled", return_value=False):
        _maybe_spawn_menubar()
    spawn.assert_not_called()


def test_skips_when_unsupported():
    with patch.object(control, "is_supported", return_value=False), \
         patch.object(control, "spawn") as spawn, \
         patch("quodeq.menubar.state.is_enabled", return_value=True):
        _maybe_spawn_menubar()
    spawn.assert_not_called()


def test_import_error_is_swallowed(monkeypatch):
    # _maybe_spawn_menubar's except is narrowed to (ImportError,): both
    # control.is_supported() and state.is_enabled() are already fail-soft
    # internally, so the only realistic source left is the import itself.
    import quodeq.menubar as menubar_pkg

    monkeypatch.delattr(menubar_pkg, "control", raising=False)
    monkeypatch.setitem(sys.modules, "quodeq.menubar.control", None)
    _maybe_spawn_menubar()  # must not propagate


def test_out_of_scope_error_propagates():
    """R-FT-7 — an error outside (ImportError,) (e.g. a programming bug)
    must now propagate instead of being swallowed."""
    with patch.object(control, "is_supported", MagicMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(RuntimeError, match="boom"):
            _maybe_spawn_menubar()
