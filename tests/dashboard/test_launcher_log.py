"""A launcher failure in the windowed app (no stderr) lands in a log file."""
from __future__ import annotations

import sys

from quodeq.dashboard import cli as dashboard_cli


def _boom():
    raise RuntimeError("no display")


def test_failure_without_stderr_is_written_to_the_run_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_RUN_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(dashboard_cli, "_run", lambda _argv: _boom())

    assert dashboard_cli.main([]) == 1

    text = (tmp_path / "launcher.log").read_text(encoding="utf-8")
    assert "dashboard failed" in text
    assert "RuntimeError: no display" in text


def test_failure_with_stderr_still_prints_there(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("QUODEQ_RUN_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard_cli, "_run", lambda _argv: _boom())

    assert dashboard_cli.main([]) == 1

    assert "RuntimeError: no display" in capsys.readouterr().err
    assert not (tmp_path / "launcher.log").exists()


def test_an_unwritable_run_dir_does_not_raise(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("QUODEQ_RUN_DIR", str(blocker / "run"))
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(dashboard_cli, "_run", lambda _argv: _boom())

    assert dashboard_cli.main([]) == 1
