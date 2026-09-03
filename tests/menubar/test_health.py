"""Health/icon helpers for the built-in menu bar app."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from quodeq.menubar import _health


def test_find_icon_resolves_bundled_template_icon():
    path = _health.find_icon("menubar_iconTemplate.png")
    assert path is not None
    assert Path(path).exists()
    assert Path(path).name == "menubar_iconTemplate.png"


def test_find_icon_missing_returns_none():
    assert _health.find_icon("no_such_icon.png") is None


def test_health_check_false_when_unreachable():
    with patch.object(_health.urllib.request, "urlopen", side_effect=OSError("refused")):
        assert _health.health_check(1) is False


def test_health_check_true_on_ok_payload():
    resp = MagicMock()
    resp.read.return_value = b'{"ok": true}'
    resp.__enter__ = lambda s: resp
    resp.__exit__ = MagicMock(return_value=False)
    with patch.object(_health.urllib.request, "urlopen", return_value=resp):
        assert _health.health_check(7863) is True


def test_find_commands_defaults_exclude_quodeq():
    cmds = _health.find_commands(env={"PATH": "/nonexistent"})
    assert set(cmds) == {"python3", "node", "claude"}
