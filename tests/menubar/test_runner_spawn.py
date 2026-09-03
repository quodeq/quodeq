"""Dashboard launch spawns the menu bar when the preference is enabled."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

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


def test_never_raises():
    with patch.object(control, "is_supported", MagicMock(side_effect=RuntimeError("boom"))):
        _maybe_spawn_menubar()  # must not propagate
