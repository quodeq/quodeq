"""Cluster 33: analysis/config best-effort handlers log through the injected sink."""
from __future__ import annotations

import os
import signal
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis import _api_standards_text, _loop_state
from quodeq.analysis._run_lifecycle_support import _SIGNALS_TO_HANDLE, _SignalGuard
from quodeq.analysis.subagents import _queue_state
from quodeq.analysis.subagents.priority import PriorityContext, prioritize_files
from quodeq.config import ai_provider
from quodeq.config.paths import ConfigPaths


def test_silence_broken_stdout_survives_unopenable_devnull(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(_loop_state.os, "devnull", str(tmp_path / "missing" / "null"))
    out, err = sys.stdout, sys.stderr
    _loop_state._silence_broken_stdout()  # must not raise
    assert sys.stdout is out
    assert sys.stderr is err


def test_signal_guard_logs_install_failure_off_main_thread(recording_log) -> None:
    guard = _SignalGuard(lambda *_: None, log=recording_log)
    worker = threading.Thread(target=guard.install)
    worker.start()
    worker.join()
    assert recording_log.debug_messages
    assert "not installed" in recording_log.debug_messages[0]
    guard.restore()  # main thread: restores whatever getsignal captured, must not raise


def test_signal_guard_logs_restore_failure_off_main_thread(recording_log) -> None:
    originals = {sig: signal.getsignal(sig) for sig in _SIGNALS_TO_HANDLE}
    guard = _SignalGuard(lambda *_: None, log=recording_log)
    try:
        guard.install()  # main thread: succeeds
        worker = threading.Thread(target=guard.restore)
        worker.start()
        worker.join()
        assert any("not restored" in m for m in recording_log.debug_messages)
    finally:
        for sig, handler in originals.items():
            signal.signal(sig, handler)


def test_prioritize_files_logs_unreadable_file_size(tmp_path, recording_log) -> None:
    files = prioritize_files(["missing.py"], tmp_path, "security", context=PriorityContext(log=recording_log))
    assert files == ["missing.py"]
    assert recording_log.debug_messages
    assert "missing.py" in recording_log.debug_messages[0]


def test_cleanup_stale_lock_logs_when_unlink_finds_it_already_gone() -> None:
    """The stat-then-unlink pair races with another process's own cleanup.

    A duck-typed stand-in gives a deterministic "stat succeeds, unlink then
    discovers the lock file is already gone" sequence without depending on
    real filesystem timing.
    """
    class _RacyLockPath:
        def stat(self):
            from types import SimpleNamespace
            return SimpleNamespace(st_mtime=0.0)

        def unlink(self):
            raise FileNotFoundError("already removed")

    with patch.object(_queue_state._log, "debug") as debug:
        result = _queue_state.cleanup_stale_lock(_RacyLockPath(), threshold=0)

    assert result is True
    assert any("already removed" in call.args[0] for call in debug.call_args_list)


def test_write_state_logs_cleanup_failure_after_replace_error(tmp_path, monkeypatch) -> None:
    """os.replace fails and the tmp file is gone by the time cleanup runs."""
    state_path = tmp_path / "queue.json"
    messages: list[tuple] = []

    def _fail_and_remove(src, dst):
        os.remove(src)  # simulates the tmp file vanishing before cleanup runs
        raise OSError("replace failed")

    monkeypatch.setattr(_queue_state.os, "replace", _fail_and_remove)
    monkeypatch.setattr(_queue_state._log, "debug", lambda *a: messages.append(a))

    with pytest.raises(OSError, match="replace failed"):
        _queue_state.write_state({"version": 1, "pending": [], "taken": []}, state_path)

    assert messages
    assert "temp queue state file not removed after a failed write" in messages[0][0]


def test_load_standards_text_logs_corrupt_json_and_falls_back(tmp_path) -> None:
    """The compiled JSON is corrupt; the handler logs it and falls through
    to the (absent) .md file, the same failure path
    ``test_subprocess_coverage.py::test_falls_back_to_md`` exercises for the
    success case."""
    (tmp_path / "security.json").write_text("{not json")
    with patch.object(_api_standards_text._log, "debug") as debug:
        result = _api_standards_text._load_standards_text(tmp_path, "security")
    assert debug.called
    assert "compiled standards file skipped" in debug.call_args.args[0]
    assert result == ""


def test_gather_source_files_logs_unreadable_file(tmp_path, monkeypatch) -> None:
    """One candidate's stat() raises (e.g. the file vanished between the
    directory listing and the stat-caching loop reading it)."""
    good = tmp_path / "a.py"
    good.write_text("print(1)\n")
    flaky = tmp_path / "b.py"
    flaky.write_text("print(2)\n")

    real_stat = Path.stat

    def _flaky_stat(self, *args, **kwargs):
        if self == flaky:
            raise OSError("vanished")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _flaky_stat)
    messages: list[tuple] = []
    monkeypatch.setattr(_api_standards_text._log, "debug", lambda *a: messages.append(a))

    result = _api_standards_text._gather_source_files(tmp_path)

    assert good in result
    assert flaky not in result
    assert messages
    assert "source file skipped" in messages[0][0]


def test_write_env_logs_cleanup_failure_and_reraises(tmp_path, monkeypatch) -> None:
    paths = ConfigPaths.from_root(tmp_path)

    def _raise(*_args, **_kwargs):
        raise OSError("boom")

    monkeypatch.setattr(ai_provider.os, "replace", _raise)
    monkeypatch.setattr(ai_provider.os, "unlink", _raise)
    messages: list[str] = []
    monkeypatch.setattr(ai_provider, "log_debug", messages.append)

    with pytest.raises(OSError, match="boom"):
        ai_provider._write_env(paths, "claude", "ANTHROPIC_API_KEY", "secret")

    assert messages
    assert "temp env file cleanup failed" in messages[0]
