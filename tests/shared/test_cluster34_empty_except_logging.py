"""Cluster 34: shared/ best-effort handlers log at debug instead of swallowing."""
from __future__ import annotations

import os
import signal
import subprocess
from unittest.mock import patch

import pytest

from quodeq.shared import _io, _process_kill, frozen, ssrf


def test_configure_stdio_utf8_logs_each_unreconfigurable_stream(monkeypatch) -> None:
    class _Stream:
        def reconfigure(self, **_kwargs):
            raise ValueError("not reconfigurable")

    monkeypatch.setattr(_io.sys, "stdout", _Stream())
    monkeypatch.setattr(_io.sys, "stderr", _Stream())
    with patch.object(_io._logger, "debug") as debug:
        _io.configure_stdio_utf8()
    assert debug.call_count == 2
    assert "reconfigured to UTF-8" in debug.call_args.args[0]


@pytest.mark.skipif(os.name == "nt", reason="POSIX only")
def test_kill_tree_logs_when_process_is_already_gone(monkeypatch) -> None:
    def _gone(*_args):
        raise ProcessLookupError(3, "No such process")

    monkeypatch.setattr(_process_kill.os, "getpgid", _gone)
    monkeypatch.setattr(_process_kill.os, "kill", _gone)
    with patch.object(_process_kill._logger, "debug") as debug:
        _process_kill.kill_tree(999999, signal.SIGTERM)
    assert debug.called
    assert "already gone" in debug.call_args.args[0]


@pytest.mark.skipif(os.name == "nt", reason="POSIX only")
def test_kill_proc_tree_logs_killpg_failure_then_proc_kill_failure(monkeypatch) -> None:
    class _Proc:
        pid = 999999

        def kill(self):
            raise ProcessLookupError(3, "No such process")

    def _denied(*_args):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(_process_kill.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(_process_kill.os, "killpg", _denied)
    with patch.object(_process_kill._logger, "debug") as debug:
        _process_kill.kill_proc_tree(_Proc())
    messages = [c.args[0] for c in debug.call_args_list]
    assert any("killpg failed" in m for m in messages)
    assert any("already gone" in m for m in messages)


def test_source_user_path_logs_timeout_and_falls_back(monkeypatch) -> None:
    def _slow(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="zsh", timeout=1)

    # source_user_path() early-returns when not is_frozen() (line 66); force
    # the frozen-bundle path so the shell probe below actually runs.
    monkeypatch.setattr(frozen, "is_frozen", lambda: True)
    monkeypatch.setattr(frozen.subprocess, "run", _slow)
    monkeypatch.setenv("PATH", "/usr/bin")
    with patch.object(frozen._logger, "debug") as debug:
        frozen.source_user_path()
    assert debug.called
    assert "PATH discovery failed" in debug.call_args.args[0]
    assert os.environ["PATH"].startswith("/usr/bin")
    assert ".local/bin" in os.environ["PATH"]


def test_is_private_address_logs_non_literal_before_dns(monkeypatch) -> None:
    monkeypatch.setattr(
        ssrf.socket, "getaddrinfo",
        lambda *_a, **_k: [(None, None, None, None, ("10.0.0.1", 0))],
    )
    with patch.object(ssrf._logger, "debug") as debug:
        assert ssrf.is_private_address("intranet.example") is True
    assert any("falling through to DNS" in c.args[0] for c in debug.call_args_list)
