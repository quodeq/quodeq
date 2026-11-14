"""What a relaunch tells the user when a window is already open, or the port moved."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quodeq.dashboard import runner
from quodeq.dashboard.runner import run_dashboard
from tests.dashboard.test_dashboard_runner import TestHandoffToRunningInstance as _Handoff

# The code under test sets PYTHONUTF8 / QUODEQ_WEBVIEW_TOKEN for the process.
pytestmark = pytest.mark.usefixtures("restore_environ")


def _run_with_taken_port(tmp_path, monkeypatch, *, running: bool) -> tuple[list[str], list[str]]:
    """Launch while the UI port is taken; return the (warnings, infos) logged."""
    instance = MagicMock()
    instance.probe_existing.return_value = running
    _calls, make_hooks = _Handoff._patch_launch_path(monkeypatch, instance)
    monkeypatch.setattr(runner, "choose_ui_port", lambda port: port + 1)
    warnings: list[str] = []
    infos: list[str] = []
    monkeypatch.setattr(runner, "log_warning", warnings.append)
    monkeypatch.setattr(runner, "log_info", infos.append)

    config = _Handoff()._config(tmp_path)
    hooks = make_hooks(build_ui=lambda *a, **k: config.static_dist)
    assert run_dashboard(config, hooks=hooks) == 0
    return warnings, infos


def test_handoff_does_not_warn_about_the_port_its_own_instance_holds(tmp_path, monkeypatch):
    warnings, _infos = _run_with_taken_port(tmp_path, monkeypatch, running=True)
    assert not [w for w in warnings if "is in use" in w]


def test_cold_start_still_warns_when_the_port_moved(tmp_path, monkeypatch):
    warnings, _infos = _run_with_taken_port(tmp_path, monkeypatch, running=False)
    assert [w for w in warnings if "is in use" in w]


def test_handoff_message_does_not_claim_the_window_moved(tmp_path, monkeypatch):
    """The request is one-way, so the launch cannot know the window came forward."""
    _warnings, infos = _run_with_taken_port(tmp_path, monkeypatch, running=True)
    message = " ".join(infos)
    assert "brought its window" not in message
    assert "quodeq stop" in message
